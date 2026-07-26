#!/usr/bin/python3
"""Validate the generated map and end-to-end demo reports."""

import argparse
import json
from pathlib import Path


MIN_MAP_WIDTH = 100
MIN_MAP_HEIGHT = 100
MIN_KNOWN_PIXELS = 500
MIN_OCCUPIED_PIXELS = 20
EXPECTED_WAYPOINTS = 6
EXPECTED_GOALS = 2
MAX_GOAL_ERROR_M = 0.35


def fail(message):
    raise SystemExit(message)


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"Cannot read JSON report {path}: {exc}")


def parse_map_yaml(path):
    values = {}
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip().strip('"\'')
    except OSError as exc:
        fail(f"Cannot read map YAML {path}: {exc}")

    image_name = values.get("image")
    if not image_name:
        fail(f"Map YAML does not declare an image: {path}")
    image_path = Path(image_name)
    if not image_path.is_absolute():
        image_path = path.parent / image_path
    return values, image_path.resolve()


def next_pgm_token(data, offset):
    size = len(data)
    while offset < size:
        if data[offset] == ord("#"):
            newline = data.find(b"\n", offset)
            if newline < 0:
                fail("PGM comment is not terminated")
            offset = newline + 1
        elif chr(data[offset]).isspace():
            offset += 1
        else:
            break
    start = offset
    while offset < size and not chr(data[offset]).isspace():
        offset += 1
    if start == offset:
        fail("PGM header is incomplete")
    return data[start:offset].decode("ascii"), offset


def parse_pgm(path):
    try:
        data = path.read_bytes()
    except OSError as exc:
        fail(f"Cannot read map image {path}: {exc}")

    offset = 0
    tokens = []
    for _ in range(4):
        token, offset = next_pgm_token(data, offset)
        tokens.append(token)
    if tokens[0] != "P5":
        fail(f"Expected binary PGM (P5), got {tokens[0]!r}")
    width, height, max_value = map(int, tokens[1:])
    if max_value != 255:
        fail(f"Expected 8-bit PGM, got max value {max_value}")

    if offset >= len(data) or not chr(data[offset]).isspace():
        fail("PGM header is missing its pixel-data separator")
    if data[offset:offset + 2] == b"\r\n":
        offset += 2
    else:
        offset += 1
    pixels = data[offset:]
    expected_size = width * height
    if len(pixels) != expected_size:
        fail(
            f"PGM pixel count mismatch: expected {expected_size}, got {len(pixels)}"
        )

    occupied = pixels.count(0)
    unknown = pixels.count(205)
    free = pixels.count(254)
    known = expected_size - unknown
    return {
        "width": width,
        "height": height,
        "pixels": expected_size,
        "known_pixels": known,
        "occupied_pixels": occupied,
        "free_pixels": free,
        "unknown_pixels": unknown,
    }


def validate_map(map_yaml):
    if not map_yaml.is_file():
        fail(f"Map YAML does not exist: {map_yaml}")
    values, image_path = parse_map_yaml(map_yaml)
    if not image_path.is_file():
        fail(f"Map image does not exist: {image_path}")
    metrics = parse_pgm(image_path)
    if metrics["width"] < MIN_MAP_WIDTH or metrics["height"] < MIN_MAP_HEIGHT:
        fail(
            "Map is too small: "
            f"{metrics['width']}x{metrics['height']} (minimum "
            f"{MIN_MAP_WIDTH}x{MIN_MAP_HEIGHT})"
        )
    if metrics["known_pixels"] < MIN_KNOWN_PIXELS:
        fail(
            f"Map has only {metrics['known_pixels']} known pixels "
            f"(minimum {MIN_KNOWN_PIXELS})"
        )
    if metrics["occupied_pixels"] < MIN_OCCUPIED_PIXELS:
        fail(
            f"Map has only {metrics['occupied_pixels']} occupied pixels "
            f"(minimum {MIN_OCCUPIED_PIXELS})"
        )
    try:
        metrics["resolution"] = float(values["resolution"])
    except (KeyError, ValueError):
        fail(f"Map YAML has an invalid resolution: {map_yaml}")
    metrics["yaml"] = str(map_yaml.resolve())
    metrics["image"] = str(image_path)
    return metrics


def report_succeeded(report):
    return report.get("success") is True or report.get("status") == "succeeded"


def validate_mapping_report(path):
    report = load_json(path)
    if not report_succeeded(report):
        fail(f"Mapping patrol did not succeed: {path}")
    completed = report.get("waypoints_completed", report.get("completed_waypoints"))
    if completed != EXPECTED_WAYPOINTS:
        fail(
            f"Mapping patrol completed {completed!r} waypoints; "
            f"expected {EXPECTED_WAYPOINTS}"
        )
    return report


def validate_navigation_report(path):
    report = load_json(path)
    if not report_succeeded(report):
        fail(f"Navigation mission did not succeed: {path}")
    goals = report.get("goals", [])
    if len(goals) != EXPECTED_GOALS:
        fail(f"Navigation report contains {len(goals)} goals; expected {EXPECTED_GOALS}")
    for index, goal in enumerate(goals, start=1):
        status = str(goal.get("status", "")).upper()
        if status not in {"SUCCEEDED", "STATUS_SUCCEEDED"}:
            fail(f"Navigation goal {index} status is {status!r}, not SUCCEEDED")
        error = goal.get("final_error_m", goal.get("distance_error_m"))
        if not isinstance(error, (int, float)) or error > MAX_GOAL_ERROR_M:
            fail(
                f"Navigation goal {index} final error is {error!r}; "
                f"maximum is {MAX_GOAL_ERROR_M:.2f} m"
            )
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--mapping-report", required=True, type=Path)
    parser.add_argument("--navigation-report", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    result = {
        "schema_version": 1,
        "success": True,
        "map": validate_map(args.map),
        "mapping": validate_mapping_report(args.mapping_report),
    }
    if args.navigation_report is not None:
        result["navigation"] = validate_navigation_report(args.navigation_report)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Validated demo artifacts; report written to {args.output}")


if __name__ == "__main__":
    main()
