#!/usr/bin/env python3
"""Fail-closed static preflight for a patched official Unitree A2 simulator."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable
import xml.etree.ElementTree as ET


SCHEMA_VERSION = 2
SCOPE = "static_source_preflight_only"
PINNED_HEADS = {
    "unitree_rl_mjlab": "1425b15f73bd4095f0df53709d7c389c3eb9e790",
    "unitree_mujoco": "ae6a8403e272733e9996ef59990880330496177f",
    "unitree_sdk2": "21d0a3b2c46ee48c8fdf2783becb6be3beb0a59b",
}

POLICY_PATH = Path(
    "deploy/robots/a2/config/policy/velocity/v0/exported/policy.onnx"
)
A2_TYPES_PATH = Path("deploy/robots/a2/include/Types.h")
VELOCITY_OBSERVATIONS_PATH = Path(
    "deploy/include/isaaclab/envs/mdp/observations/observations.h"
)
COMMAND_SOURCE_PATH = Path(
    "deploy/robots/a2/include/PlatformVelocityCommandSource.h"
)
UNITREE_MUJOCO_A2_MODEL_PATH = Path("unitree_robots/a2/a2.xml")
RL_A2_TRAIN_MODEL_PATH = Path("src/assets/robots/unitree_a2/xmls/a2.xml")
RL_A2_SCENE_MODEL_PATH = Path("src/assets/robots/unitree_a2/xmls/scene_a2.xml")
SIMULATOR_MAIN_PATH = Path("simulate/src/main.cc")
SIMULATOR_BRIDGE_PATH = Path("simulate/src/unitree_sdk2_bridge.h")
SDK2_G1_PUBLISHER_PATH = Path("include/unitree/dds_wrapper/robots/g1/g1_pub.h")
SDK2_G1_SUBSCRIBER_PATH = Path("include/unitree/dds_wrapper/robots/g1/g1_sub.h")

# Backward-compatible name for callers that imported the initial checker.
A2_MODEL_PATH = UNITREE_MUJOCO_A2_MODEL_PATH

SOURCE_SIZE_LIMIT = 4 * 1024 * 1024
MAX_XML_DOCUMENTS = 32
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class GitState:
    root: Path | None
    head: str | None
    error: str | None = None


@dataclass(frozen=True)
class CheckResult:
    id: str
    passed: bool
    expected: Any
    actual: Any
    detail: str


def inspect_git_checkout(checkout: Path) -> GitState:
    """Read checkout identity without fetching missing objects or taking locks."""
    checkout = checkout.resolve()
    env = os.environ.copy()
    env.update(
        {
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    try:
        completed = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "--show-toplevel", "HEAD"],
            check=False,
            capture_output=True,
            env=env,
            text=True,
            timeout=5.0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return GitState(None, None, f"git inspection failed: {exc}")

    if completed.returncode != 0:
        return GitState(None, None, completed.stderr.strip() or "git rev-parse failed")
    lines = completed.stdout.splitlines()
    if len(lines) != 2:
        return GitState(None, None, "git rev-parse returned an unexpected result")
    return GitState(Path(lines[0]).resolve(), lines[1].strip().lower())


def _read_source(root: Path, relative_path: Path) -> tuple[str | None, str | None]:
    path = root / relative_path
    try:
        if path.stat().st_size > SOURCE_SIZE_LIMIT:
            return None, f"source exceeds {SOURCE_SIZE_LIMIT} bytes: {path}"
        return path.read_text(encoding="utf-8"), None
    except (OSError, UnicodeError) as exc:
        return None, f"cannot read {path}: {exc}"


def _sha256_file(path: Path) -> tuple[str | None, str | None]:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        return None, f"cannot hash {path}: {exc}"
    return digest.hexdigest(), None


def _strip_cpp_comments(source: str) -> str:
    """Remove comments while preserving quoted text and line positions."""
    token = re.compile(
        r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/',
        flags=re.DOTALL,
    )

    def replace(match: re.Match[str]) -> str:
        value = match.group(0)
        if value.startswith(('"', "'")):
            return value
        return "".join("\n" if char == "\n" else " " for char in value)

    return token.sub(replace, source)


def _mask_cpp_literals(source: str) -> str:
    token = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', re.DOTALL)
    return token.sub(lambda match: " " * len(match.group(0)), source)


def _balanced_end(source: str, start: int, opening: str, closing: str) -> int | None:
    depth = 0
    for index in range(start, len(source)):
        if source[index] == opening:
            depth += 1
        elif source[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    return None


def _extract_braced_block(source: str, marker: str) -> tuple[str | None, str | None]:
    code = _mask_cpp_literals(_strip_cpp_comments(source))
    marker_at = code.find(marker)
    if marker_at < 0:
        return None, f"marker not found: {marker}"
    open_at = code.find("{", marker_at + len(marker))
    if open_at < 0:
        return None, f"opening brace not found after: {marker}"
    close_at = _balanced_end(code, open_at, "{", "}")
    if close_at is None:
        return None, f"unterminated block after: {marker}"
    return code[open_at + 1 : close_at], None


def _a2_condition_contains(source: str, required_pattern: str) -> bool:
    code = _strip_cpp_comments(source)
    masked = _mask_cpp_literals(code)
    for match in re.finditer(r"\bif\s*\(", masked):
        open_parenthesis = masked.find("(", match.start())
        close_parenthesis = _balanced_end(masked, open_parenthesis, "(", ")")
        if close_parenthesis is None:
            continue
        condition = code[open_parenthesis + 1 : close_parenthesis]
        if not re.search(
            r'(?:\brobot\b\s*==\s*"a2"|"a2"\s*==\s*\brobot\b)',
            condition,
            flags=re.IGNORECASE,
        ):
            continue
        body_at = close_parenthesis + 1
        while body_at < len(masked) and masked[body_at].isspace():
            body_at += 1
        if body_at >= len(masked):
            continue
        if masked[body_at] == "{":
            body_end = _balanced_end(masked, body_at, "{", "}")
            if body_end is None:
                continue
            body = masked[body_at + 1 : body_end]
        else:
            body_end = masked.find(";", body_at)
            if body_end < 0:
                continue
            body = masked[body_at : body_end + 1]
        if re.search(required_pattern, body, flags=re.DOTALL):
            return True
    return False


def _record(
    checks: list[CheckResult],
    check_id: str,
    passed: bool,
    expected: Any,
    actual: Any,
    detail: str,
) -> None:
    checks.append(CheckResult(check_id, bool(passed), expected, actual, detail))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _load_xml_closure(
    entry_path: Path, checkout_root: Path
) -> tuple[list[tuple[Path, ET.Element]], str | None]:
    checkout_root = checkout_root.resolve()
    documents: list[tuple[Path, ET.Element]] = []
    visited: set[Path] = set()
    active: set[Path] = set()

    def visit(path: Path) -> str | None:
        resolved = path.resolve()
        if not _within(resolved, checkout_root):
            return f"XML include escapes checkout root: {path}"
        if resolved in active:
            return f"cyclic XML include: {resolved}"
        if resolved in visited:
            return None
        if len(visited) >= MAX_XML_DOCUMENTS:
            return f"XML include closure exceeds {MAX_XML_DOCUMENTS} documents"
        try:
            if resolved.stat().st_size > SOURCE_SIZE_LIMIT:
                return f"XML exceeds {SOURCE_SIZE_LIMIT} bytes: {resolved}"
            root_element = ET.parse(resolved).getroot()
        except (OSError, ET.ParseError) as exc:
            return f"cannot parse {resolved}: {exc}"
        visited.add(resolved)
        active.add(resolved)
        documents.append((resolved, root_element))
        for element in root_element.iter():
            if _local_name(element.tag) != "include":
                continue
            included = element.get("file")
            if not included:
                return f"XML include has no file attribute: {resolved}"
            error = visit(resolved.parent / included)
            if error is not None:
                return error
        active.remove(resolved)
        return None

    error = visit(entry_path)
    return documents, error


def _parse_positive_numbers(value: str | None, count: int) -> list[float] | None:
    if value is None:
        return None
    parts = value.split()
    if len(parts) != count:
        return None
    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        return None
    if not all(math.isfinite(number) and number > 0.0 for number in numbers):
        return None
    return numbers


def _valid_payload_inertia(body: ET.Element) -> tuple[bool, dict[str, Any]]:
    inertials = [child for child in body if _local_name(child.tag) == "inertial"]
    if len(inertials) != 1:
        return False, {"inertial_count": len(inertials)}
    inertial = inertials[0]
    mass_values = _parse_positive_numbers(inertial.get("mass"), 1)
    diagonal = _parse_positive_numbers(inertial.get("diaginertia"), 3)
    triangle_valid = bool(
        diagonal is not None
        and diagonal[0] + diagonal[1] > diagonal[2]
        and diagonal[0] + diagonal[2] > diagonal[1]
        and diagonal[1] + diagonal[2] > diagonal[0]
    )
    return bool(mass_values is not None and triangle_valid), {
        "mass": None if mass_values is None else mass_values[0],
        "diaginertia": diagonal,
        "principal_moment_triangle_valid": triangle_valid,
    }


def _inspect_payload_model(entry_path: Path, checkout_root: Path) -> dict[str, Any]:
    documents, error = _load_xml_closure(entry_path, checkout_root)
    mounts: list[tuple[Path, ET.Element]] = []
    p7_bases: list[tuple[Path, ET.Element]] = []
    valid_chains: list[tuple[Path, ET.Element, ET.Element]] = []
    for path, root in documents:
        bodies = [element for element in root.iter() if _local_name(element.tag) == "body"]
        mounts.extend((path, body) for body in bodies if body.get("name") == "a2_p7_mount_link")
        p7_bases.extend((path, body) for body in bodies if body.get("name") == "p7_base_link")
        for mount in (body for body in bodies if body.get("name") == "a2_p7_mount_link"):
            for descendant in mount.iter():
                if (
                    descendant is not mount
                    and _local_name(descendant.tag) == "body"
                    and descendant.get("name") == "p7_base_link"
                ):
                    valid_chains.append((path, mount, descendant))

    inertia_results = []
    for path, mount, p7_base in valid_chains:
        mount_valid, mount_detail = _valid_payload_inertia(mount)
        p7_valid, p7_detail = _valid_payload_inertia(p7_base)
        inertia_results.append(
            {
                "source": str(path),
                "mount": mount_detail,
                "p7_base": p7_detail,
                "valid": mount_valid and p7_valid,
            }
        )

    return {
        "entry": str(entry_path),
        "documents": [str(path) for path, _ in documents],
        "error": error,
        "mount_count": len(mounts),
        "p7_base_count": len(p7_bases),
        "p7_is_mount_descendant": bool(valid_chains),
        "topology_valid": error is None and bool(valid_chains),
        "inertia": inertia_results,
        "inertia_valid": bool(inertia_results)
        and all(result["valid"] for result in inertia_results),
    }


def _count_motors(entry_path: Path, checkout_root: Path) -> tuple[int | None, str | None]:
    documents, error = _load_xml_closure(entry_path, checkout_root)
    if error is not None:
        return None, error
    count = 0
    for _, root in documents:
        for actuator in root.iter():
            if _local_name(actuator.tag) != "actuator":
                continue
            count += sum(1 for child in actuator if _local_name(child.tag) == "motor")
    return count, None


def _extract_numeric_constant(source: str, name: str) -> float | None:
    match = re.search(
        rf"\b{re.escape(name)}\b\s*=\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*[fF]?",
        source,
    )
    if match is None:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _has_clamp(source: str, value: str, limit: str) -> bool:
    return re.search(
        rf"std::clamp\s*\(\s*{re.escape(value)}\s*,\s*-\s*{re.escape(limit)}\s*,\s*{re.escape(limit)}\s*\)",
        source,
        flags=re.DOTALL,
    ) is not None


def _record_payload_checks(
    checks: list[CheckResult], check_prefix: str, state: dict[str, Any]
) -> None:
    topology_actual = {
        "mount_count": state["mount_count"],
        "p7_base_count": state["p7_base_count"],
        "p7_is_mount_descendant": state["p7_is_mount_descendant"],
        "documents": state["documents"],
    }
    _record(
        checks,
        f"{check_prefix}.topology",
        state["topology_valid"],
        "a2_p7_mount_link contains p7_base_link",
        topology_actual,
        state["error"] or "exact A2+P7 MuJoCo body topology is required",
    )
    _record(
        checks,
        f"{check_prefix}.payload_inertia",
        state["inertia_valid"],
        "finite positive mass and physical diaginertia on both payload bodies",
        state["inertia"],
        state["error"] or "mount and P7 base need explicit valid inertial elements",
    )


def validate_checkouts(
    unitree_rl_mjlab: Path,
    unitree_mujoco: Path,
    unitree_sdk2: Path,
    *,
    policy_sha256: str | None = None,
    allow_unpinned_policy: bool = False,
    git_inspector: Callable[[Path], GitState] | None = None,
) -> dict[str, Any]:
    roots = {
        "unitree_rl_mjlab": Path(unitree_rl_mjlab).resolve(),
        "unitree_mujoco": Path(unitree_mujoco).resolve(),
        "unitree_sdk2": Path(unitree_sdk2).resolve(),
    }
    checks: list[CheckResult] = []
    warnings: list[str] = []
    inspect_git = inspect_git_checkout if git_inspector is None else git_inspector

    for name, root in roots.items():
        state = inspect_git(root)
        expected_head = PINNED_HEADS[name]
        passed = state.root == root and state.head == expected_head and state.error is None
        _record(
            checks,
            f"checkout.{name}.head",
            passed,
            {"root": str(root), "head": expected_head},
            {"root": None if state.root is None else str(state.root), "head": state.head},
            state.error or "checkout root and HEAD must match exactly",
        )

    rl_root = roots["unitree_rl_mjlab"]
    policy_path = rl_root / POLICY_PATH
    policy_exists = policy_path.is_file()
    _record(
        checks,
        "policy.exists",
        policy_exists,
        str(POLICY_PATH),
        str(policy_path) if policy_exists else None,
        "the A2 deployment policy is mandatory",
    )
    policy_digest, policy_hash_error = (
        _sha256_file(policy_path) if policy_exists else (None, "policy is missing")
    )
    normalized_policy_sha = policy_sha256.strip().lower() if policy_sha256 else None
    if normalized_policy_sha is not None:
        format_valid = SHA256_PATTERN.fullmatch(normalized_policy_sha) is not None
        hash_matches = format_valid and policy_digest == normalized_policy_sha
        _record(
            checks,
            "policy.sha256",
            hash_matches,
            normalized_policy_sha,
            policy_digest,
            policy_hash_error or ("policy SHA-256 matches" if hash_matches else "policy SHA-256 mismatch"),
        )
    elif allow_unpinned_policy:
        _record(
            checks,
            "policy.sha256",
            False,
            "a separately reviewed expected SHA-256",
            policy_digest,
            policy_hash_error or "digest observed in audit-only mode; it is not trusted",
        )
        warnings.append("policy SHA-256 is observed but not pinned; audit-only mode cannot pass preflight")
    else:
        _record(
            checks,
            "policy.sha256",
            False,
            "--policy-sha256",
            policy_digest,
            "an expected policy SHA-256 is required",
        )

    types_source, types_error = _read_source(rl_root, A2_TYPES_PATH)
    types_passed = bool(
        types_source is not None
        and re.search(r"using\s+LowCmd_t\s*=\s*unitree::robot::g1::publisher::LowCmd\s*;", types_source)
        and re.search(r"using\s+LowState_t\s*=\s*unitree::robot::g1::subscription::LowState\s*;", types_source)
    )
    _record(
        checks,
        "dds.a2_controller_uses_g1",
        types_passed,
        "G1 LowCmd publisher and G1 LowState subscriber aliases",
        "matched" if types_passed else "not matched",
        types_error or "A2 controller aliases must use the G1 wrapper",
    )

    sdk_root = roots["unitree_sdk2"]
    g1_pub, g1_pub_error = _read_source(sdk_root, SDK2_G1_PUBLISHER_PATH)
    g1_sub, g1_sub_error = _read_source(sdk_root, SDK2_G1_SUBSCRIBER_PATH)
    publisher_patterns = (
        r"RealTimePublisher\s*<\s*unitree_hg::msg::dds_::LowCmd_\s*>",
        r"RealTimePublisher\s*<\s*unitree_hg::msg::dds_::LowState_\s*>",
        r'"rt/lowcmd"',
        r'"rt/lowstate"',
    )
    subscriber_patterns = (
        r"SubscriptionBase\s*<\s*unitree_hg::msg::dds_::LowCmd_\s*>",
        r"SubscriptionBase\s*<\s*unitree_hg::msg::dds_::LowState_\s*>",
        r'"rt/lowcmd"',
        r'"rt/lowstate"',
    )
    sdk_hg_passed = bool(g1_pub is not None and g1_sub is not None) and all(
        re.search(pattern, source) is not None
        for source, patterns in ((g1_pub or "", publisher_patterns), (g1_sub or "", subscriber_patterns))
        for pattern in patterns
    )
    _record(
        checks,
        "dds.sdk2_g1_wrapper_is_hg",
        sdk_hg_passed,
        "G1 wrapper uses unitree_hg LowCmd/LowState on rt/lowcmd and rt/lowstate",
        "matched" if sdk_hg_passed else "not matched",
        g1_pub_error or g1_sub_error or "SDK2 G1 wrapper must resolve to HG IDL",
    )

    mujoco_root = roots["unitree_mujoco"]
    model_specs = (
        (
            "plant.unitree_mujoco.a2_p7",
            mujoco_root / UNITREE_MUJOCO_A2_MODEL_PATH,
            mujoco_root,
        ),
        (
            "plant.unitree_rl_mjlab.training_a2_p7",
            rl_root / RL_A2_TRAIN_MODEL_PATH,
            rl_root,
        ),
        (
            "plant.unitree_rl_mjlab.deployment_a2_p7",
            rl_root / RL_A2_SCENE_MODEL_PATH,
            rl_root,
        ),
    )
    for prefix, entry_path, checkout_root in model_specs:
        _record_payload_checks(checks, prefix, _inspect_payload_model(entry_path, checkout_root))

    motor_specs = (
        ("mujoco.a2_motor_count", mujoco_root / UNITREE_MUJOCO_A2_MODEL_PATH, mujoco_root),
        ("rl_mjlab.scene_a2_motor_count", rl_root / RL_A2_SCENE_MODEL_PATH, rl_root),
    )
    for check_id, model_path, checkout_root in motor_specs:
        motor_count, model_error = _count_motors(model_path, checkout_root)
        _record(
            checks,
            check_id,
            motor_count == 12,
            12,
            motor_count,
            model_error or "A2 deployment model must expose exactly 12 motor actuators",
        )

    simulator_main, simulator_main_error = _read_source(rl_root, SIMULATOR_MAIN_PATH)
    dispatch_block: str | None = None
    dispatch_error: str | None = simulator_main_error
    if simulator_main is not None:
        dispatch_block, dispatch_error = _extract_braced_block(simulator_main, "UnitreeSdk2BridgeThread")
    motor_dispatch_pattern = re.compile(r"NUM_MOTOR_IDL|\b(?:m|model|mj_model_)\s*->\s*nu\b")
    no_motor_dispatch = bool(dispatch_block is not None) and not motor_dispatch_pattern.search(dispatch_block or "")
    _record(
        checks,
        "bridge.no_motor_count_dispatch",
        no_motor_dispatch,
        "bridge family selected by explicit robot identity",
        "motor-count dispatch absent" if no_motor_dispatch else "motor-count dispatch found",
        dispatch_error or "motor count must not select a DDS message family",
    )
    a2_uses_g1 = bool(simulator_main is not None) and _a2_condition_contains(
        simulator_main, r"(?:make_unique\s*<\s*G1Bridge\s*>|\bG1Bridge\b)"
    )
    _record(
        checks,
        "bridge.a2_uses_g1_hg",
        a2_uses_g1,
        "explicit A2 -> G1Bridge mapping",
        "matched" if a2_uses_g1 else "not matched",
        simulator_main_error or "A2 must explicitly select the G1/HG bridge",
    )

    simulator_bridge, simulator_bridge_error = _read_source(rl_root, SIMULATOR_BRIDGE_PATH)
    a2_mode_machine = bool(simulator_bridge is not None) and _a2_condition_contains(
        simulator_bridge, r"mode_machine\s*\(\s*\)\s*=\s*1\s*;"
    )
    _record(
        checks,
        "bridge.a2_mode_machine",
        a2_mode_machine,
        1,
        1 if a2_mode_machine else None,
        simulator_bridge_error or "A2 HG LowState must advertise mode_machine=1",
    )

    observations_source, observations_error = _read_source(rl_root, VELOCITY_OBSERVATIONS_PATH)
    velocity_block: str | None = None
    velocity_block_error: str | None = observations_error
    if observations_source is not None:
        velocity_block, velocity_block_error = _extract_braced_block(
            observations_source, "REGISTER_OBSERVATION(velocity_commands)"
        )
    command_source, command_source_error = _read_source(rl_root, COMMAND_SOURCE_PATH)
    command_clean = _strip_cpp_comments(command_source or "")
    command_code = _mask_cpp_literals(command_clean)
    command_digest, _ = _sha256_file(rl_root / COMMAND_SOURCE_PATH)

    source_exists = command_source is not None
    _record(
        checks,
        "command.source_exists",
        source_exists,
        str(COMMAND_SOURCE_PATH),
        {"exists": source_exists, "sha256": command_digest},
        command_source_error or "a fixed A2 platform command source is required",
    )
    topic_exact = bool(
        command_source is not None
        and re.search(
            r"create_subscription\s*<\s*geometry_msgs::msg::Twist\s*>\s*\([^;]*\"/platform/cmd_vel\"",
            command_clean,
            flags=re.DOTALL,
        )
    )
    _record(
        checks,
        "command.topic_exact",
        topic_exact,
        "/platform/cmd_vel Twist subscription",
        "matched" if topic_exact else "not matched",
        command_source_error or "the policy command source must subscribe to the gated platform topic",
    )

    monotonic_clock = bool(
        re.search(r"using\s+Clock\s*=\s*std::chrono::steady_clock\s*;", command_code)
        and len(re.findall(r"\bClock::now\s*\(\s*\)", command_code)) >= 2
        and re.search(r"last_received_\s*=\s*Clock::now\s*\(\s*\)", command_code)
    )
    _record(
        checks,
        "command.monotonic_clock",
        monotonic_clock,
        "receive timestamp and watchdog use std::chrono::steady_clock",
        "matched" if monotonic_clock else "not matched",
        command_source_error or "wall/ROS time must not drive the command watchdog",
    )

    timeout_match = re.search(
        r"\bkCommandTimeout\b\s*=\s*std::chrono::milliseconds\s*\(\s*(\d+)\s*\)",
        command_code,
    )
    timeout_ms = int(timeout_match.group(1)) if timeout_match else None
    watchdog_bound = timeout_ms is not None and 0 < timeout_ms <= 80
    _record(
        checks,
        "command.watchdog_80ms",
        watchdog_bound,
        {"maximum_ms": 80},
        {"configured_ms": timeout_ms},
        command_source_error or "command watchdog must be positive and no greater than 80 ms",
    )

    command_block, command_block_error = (
        _extract_braced_block(command_source, "command() const")
        if command_source is not None
        else (None, command_source_error)
    )
    zero_triplet = r"return\s*\{\s*0(?:\.0+)?[fF]?\s*,\s*0(?:\.0+)?[fF]?\s*,\s*0(?:\.0+)?[fF]?\s*\}\s*;"
    watchdog_zero = bool(
        command_block is not None
        and re.search(r"!\s*has_command_", command_block)
        and re.search(r"Clock::now\s*\(\s*\)\s*-\s*last_received_\s*>=\s*kCommandTimeout", command_block)
        and re.search(zero_triplet, command_block)
    )
    _record(
        checks,
        "command.watchdog_zero_output",
        watchdog_zero,
        "zero vx/vy/wz before first command and at watchdog expiry",
        "matched" if watchdog_zero else "not matched",
        command_block_error or "stale or absent commands must produce an exact zero vector",
    )

    finite_fields = (
        "message.linear.x",
        "message.linear.y",
        "message.linear.z",
        "message.angular.x",
        "message.angular.y",
        "message.angular.z",
    )
    finite_matches = {
        field: bool(re.search(rf"std::isfinite\s*\(\s*{re.escape(field)}\s*\)", command_code))
        for field in finite_fields
    }
    accept_block, accept_block_error = (
        _extract_braced_block(command_source, "accept(")
        if command_source is not None
        else (None, command_source_error)
    )
    invalid_zero_before_timestamp = bool(
        accept_block is not None
        and re.search(zero_triplet.replace("return", r"command_\s*="), accept_block)
        and re.search(r"return\s+false\s*;", accept_block)
        and accept_block.find("return false") < accept_block.find("last_received_")
    )
    finite_passed = all(finite_matches.values()) and invalid_zero_before_timestamp
    _record(
        checks,
        "command.finite_values",
        finite_passed,
        "all six Twist components finite; invalid input zeros output without refreshing timestamp",
        {"fields": finite_matches, "invalid_zero_before_timestamp": invalid_zero_before_timestamp},
        accept_block_error or "NaN/Inf must fail closed before the receive timestamp is refreshed",
    )

    linear_limit = _extract_numeric_constant(command_code, "kMaxLinearX")
    linear_clamped = _has_clamp(command_code, "message.linear.x", "kMaxLinearX")
    linear_passed = linear_limit is not None and 0 < linear_limit <= 0.10 and linear_clamped
    _record(
        checks,
        "command.linear_limit",
        linear_passed,
        {"maximum_m_s": 0.10, "clamped": True},
        {"configured_m_s": linear_limit, "clamped": linear_clamped},
        command_source_error or "linear.x must be clamped to at most 0.10 m/s",
    )

    angular_limit = _extract_numeric_constant(command_code, "kMaxAngularZ")
    angular_clamped = _has_clamp(command_code, "message.angular.z", "kMaxAngularZ")
    angular_passed = angular_limit is not None and 0 < angular_limit <= 0.20 and angular_clamped
    _record(
        checks,
        "command.angular_limit",
        angular_passed,
        {"maximum_rad_s": 0.20, "clamped": True},
        {"configured_rad_s": angular_limit, "clamped": angular_clamped},
        command_source_error or "angular.z must be clamped to at most 0.20 rad/s",
    )

    safe_output_consumed = bool(
        velocity_block is not None
        and re.search(r"velocity_command_source\s*->\s*command\s*\(\s*\)", velocity_block)
    )
    _record(
        checks,
        "command.safe_output_consumed",
        safe_output_consumed,
        "velocity observation consumes PlatformVelocityCommandSource::command()",
        "matched" if safe_output_consumed else "not matched",
        velocity_block_error or "policy observation must consume the watchdog-limited command",
    )
    joystick_pattern = re.compile(r"\bjoystick\b|\bgamepad\b|->\s*(?:lx|ly|rx|ry)\s*\(", re.IGNORECASE)
    no_joystick = bool(
        velocity_block is not None
        and command_source is not None
        and not joystick_pattern.search(velocity_block)
        and not joystick_pattern.search(command_code)
    )
    _record(
        checks,
        "command.no_joystick_path",
        no_joystick,
        "no joystick or gamepad fallback in command source or velocity observation",
        "matched" if no_joystick else "not matched",
        velocity_block_error or command_source_error or "automatic navigation must not fall back to joystick axes",
    )

    failed_checks = [check.id for check in checks if not check.passed]
    all_checks_passed = not failed_checks
    audit_only = bool(
        allow_unpinned_policy
        and policy_digest is not None
        and all(check.passed or check.id == "policy.sha256" for check in checks)
    )
    static_preflight_passed = all_checks_passed and normalized_policy_sha is not None
    status = (
        "static_preflight_passed"
        if static_preflight_passed
        else "audit_only"
        if audit_only
        else "failed"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "status": status,
        "static_preflight_passed": static_preflight_passed,
        "runtime_ready": False,
        "is_runtime_validation": False,
        "is_gait_validation": False,
        "safe_for_real_robot": False,
        "inputs": {name: str(root) for name, root in roots.items()},
        "expected_heads": PINNED_HEADS.copy(),
        "policy": {
            "path": str(POLICY_PATH),
            "sha256": policy_digest,
            "sha256_pinned": normalized_policy_sha is not None,
        },
        "observed_artifacts": {
            "command_source": {
                "path": str(COMMAND_SOURCE_PATH),
                "sha256": command_digest,
            }
        },
        "checks": [asdict(check) for check in checks],
        "failed_checks": failed_checks,
        "warnings": warnings,
        "summary": {
            "total": len(checks),
            "passed": len(checks) - len(failed_checks),
            "failed": len(failed_checks),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unitree-rl-mjlab", required=True, type=Path)
    parser.add_argument("--unitree-mujoco", required=True, type=Path)
    parser.add_argument("--unitree-sdk2", required=True, type=Path)
    policy_group = parser.add_mutually_exclusive_group()
    policy_group.add_argument(
        "--policy-sha256",
        help="Expected reviewed A2 policy digest required for static preflight",
    )
    policy_group.add_argument(
        "--allow-unpinned-policy",
        action="store_true",
        help="Observe an existing policy digest in audit-only mode (always exits nonzero)",
    )
    return parser


def _exception_report(exc: Exception) -> dict[str, Any]:
    check = CheckResult(
        "internal.exception",
        False,
        "validation completes without an exception",
        type(exc).__name__,
        str(exc),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "status": "failed",
        "static_preflight_passed": False,
        "runtime_ready": False,
        "is_runtime_validation": False,
        "is_gait_validation": False,
        "safe_for_real_robot": False,
        "checks": [asdict(check)],
        "failed_checks": [check.id],
        "warnings": [],
        "summary": {"total": 1, "passed": 0, "failed": 1},
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = validate_checkouts(
            args.unitree_rl_mjlab,
            args.unitree_mujoco,
            args.unitree_sdk2,
            policy_sha256=args.policy_sha256,
            allow_unpinned_policy=args.allow_unpinned_policy,
        )
    except Exception as exc:  # Keep unexpected preflight failures fail-closed.
        report = _exception_report(exc)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("static_preflight_passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
