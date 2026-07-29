"""Narrow, lazily imported wrapper around Unitree's official A2 SDK2 API."""

from __future__ import annotations

import importlib
from importlib import metadata
import hashlib
import json
from pathlib import Path
import socket
from typing import Callable, Optional


SDK2_PYTHON_REPOSITORY = "https://github.com/unitreerobotics/unitree_sdk2_python"
SDK2_PYTHON_COMMIT = "65691c8a8bc53b98d3976dba4dbf9d5d20b2e7f5"
SDK2_PYTHON_VERSION = "1.0.1"
CYCLONEDDS_VERSION = "0.10.2"
A2_SPORT_API_VERSION = "1.0.0.1"
SPORT_STATE_TOPIC = "rt/lf/sportmodestate"
ARPHRD_ETHER = 1
IFF_UP = 0x1
IFF_LOOPBACK = 0x8
SDK2_CRITICAL_FILE_SHA256 = {
    "unitree_sdk2py/a2/sport/sport_client.py": (
        "a62996f88721259e5306a9636d5db78cfbb9a01818b818c45efaa0b8fb8b27b0"
    ),
    "unitree_sdk2py/a2/sport/sport_api.py": (
        "68bc46ef16ea70f5f1aa604e224e7e85b5ba833afa61e83ac49cee4e49ed777a"
    ),
    "unitree_sdk2py/rpc/client.py": (
        "20840192dee42525b64ecc3a3e8d5ec5d1d7e122b7bfc4236c482cb2b0f6e186"
    ),
    "unitree_sdk2py/rpc/client_base.py": (
        "2a815a5c798be95df1c8a4af525873c2ee47d5e0bbfbcc8a4ccf2d991a341321"
    ),
    "unitree_sdk2py/rpc/client_stub.py": (
        "37c860bb4783c2f13b24bc369ebf99b2131a21dfb49f0f7a8b74e79960d879b0"
    ),
    "unitree_sdk2py/rpc/internal.py": (
        "38896942088a7b0d03e3d9e5fa06ef3aee81e8ec6d52e0a9a640e35aaf955343"
    ),
    "unitree_sdk2py/core/channel.py": (
        "8a58eea2bc6bb8792e5b5fa76949407bd8c2ef8af07172d1a3a465bcc544e247"
    ),
    "unitree_sdk2py/idl/unitree_go/msg/dds_/_SportModeState_.py": (
        "8f05eea51a6822727a14572e656bb59a84a899ac264c96c8c7104d2acccf5909"
    ),
}


class SDK2BackendError(RuntimeError):
    """Raised when the pinned SDK cannot be loaded or initialized."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_wired_network_interface(
    network_interface: str,
    interface_lookup: Callable[[str], int] = socket.if_nametoindex,
    sysfs_root: Path = Path("/sys/class/net"),
) -> None:
    """Require an enabled, non-wireless Ethernet interface for A2 DDS."""

    name = network_interface.strip()
    if not name:
        raise SDK2BackendError("network_interface must name the A2 Ethernet NIC")
    try:
        interface_index = interface_lookup(name)
    except OSError as exc:
        raise SDK2BackendError(
            f"network_interface does not exist: {name}"
        ) from exc
    if interface_index <= 0:
        raise SDK2BackendError(f"network_interface is not usable: {name}")

    interface_path = sysfs_root / name
    try:
        hardware_type = int(
            (interface_path / "type").read_text(encoding="ascii").strip()
        )
        flags = int(
            (interface_path / "flags").read_text(encoding="ascii").strip(),
            0,
        )
    except (OSError, ValueError) as exc:
        raise SDK2BackendError(
            f"cannot verify network_interface properties: {name}"
        ) from exc
    if hardware_type != ARPHRD_ETHER or flags & IFF_LOOPBACK:
        raise SDK2BackendError(
            f"network_interface is not a wired Ethernet NIC: {name}"
        )
    if (interface_path / "wireless").exists():
        raise SDK2BackendError(
            f"network_interface must not be wireless: {name}"
        )
    if not flags & IFF_UP:
        raise SDK2BackendError(f"network_interface is not enabled: {name}")


def verify_pinned_sdk2_installation(
    distribution_loader: Callable[[str], object] = metadata.distribution,
    package_version_loader: Callable[[str], str] = metadata.version,
    file_hasher: Callable[[Path], str] = _sha256_file,
) -> None:
    """Require pip metadata proving the audited SDK Git revision is installed."""

    try:
        distribution = distribution_loader("unitree_sdk2py")
        direct_url_text = distribution.read_text("direct_url.json")
    except Exception as exc:
        raise SDK2BackendError(
            "cannot verify the installed unitree_sdk2py revision"
        ) from exc
    if not direct_url_text:
        raise SDK2BackendError(
            "unitree_sdk2py has no direct_url.json revision metadata"
        )
    try:
        direct_url = json.loads(direct_url_text)
        repository = str(direct_url["url"]).removesuffix(".git").rstrip("/")
        vcs_info = direct_url["vcs_info"]
        vcs = vcs_info["vcs"]
        commit_id = vcs_info["commit_id"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SDK2BackendError(
            "unitree_sdk2py direct_url.json does not identify a Git revision"
        ) from exc
    if repository != SDK2_PYTHON_REPOSITORY or vcs != "git":
        raise SDK2BackendError(
            "installed unitree_sdk2py repository does not match the audited source"
        )
    if commit_id != SDK2_PYTHON_COMMIT:
        raise SDK2BackendError(
            "installed unitree_sdk2py commit does not match the audited revision"
        )
    if str(distribution.version) != SDK2_PYTHON_VERSION:
        raise SDK2BackendError(
            "installed unitree_sdk2py package version does not match the pin"
        )
    try:
        cyclonedds_version = package_version_loader("cyclonedds")
    except Exception as exc:
        raise SDK2BackendError("cannot verify the cyclonedds version") from exc
    if cyclonedds_version != CYCLONEDDS_VERSION:
        raise SDK2BackendError(
            "installed cyclonedds version does not match the SDK2 pin"
        )
    for relative_name, expected_sha256 in SDK2_CRITICAL_FILE_SHA256.items():
        try:
            installed_path = Path(distribution.locate_file(relative_name))
            actual_sha256 = file_hasher(installed_path)
        except Exception as exc:
            raise SDK2BackendError(
                f"cannot verify installed SDK2 file: {relative_name}"
            ) from exc
        if actual_sha256 != expected_sha256:
            raise SDK2BackendError(
                f"installed SDK2 file hash does not match: {relative_name}"
            )


class UnitreeA2SportBackend:
    """Expose only Move and StopMove from the A2 SportClient.

    Unitree modules are deliberately imported in ``start`` instead of module
    scope. This keeps package discovery, ROS builds, and unit tests independent
    of the hardware-only SDK installation.
    """

    def __init__(
        self,
        network_interface: str,
        dds_domain_id: int,
        rpc_timeout_s: float,
        state_callback: Callable[[Optional[int], Optional[int]], None],
        module_loader: Callable[[str], object] = importlib.import_module,
        revision_verifier: Callable[[], None] = verify_pinned_sdk2_installation,
        interface_validator: Callable[
            [str], None
        ] = validate_wired_network_interface,
    ) -> None:
        self._network_interface = network_interface.strip()
        self._dds_domain_id = int(dds_domain_id)
        self._rpc_timeout_s = float(rpc_timeout_s)
        self._state_callback = state_callback
        self._module_loader = module_loader
        self._revision_verifier = revision_verifier
        self._interface_validator = interface_validator
        self._client = None
        self._subscriber = None

    @property
    def started(self) -> bool:
        return self._client is not None

    def start(self) -> None:
        if self.started:
            raise SDK2BackendError("SDK2 backend is already started")
        if not self._network_interface:
            raise SDK2BackendError("network_interface must name the A2 Ethernet NIC")
        if self._dds_domain_id < 0 or self._dds_domain_id > 232:
            raise SDK2BackendError("dds_domain_id must be between 0 and 232")
        self._interface_validator(self._network_interface)

        subscriber = None
        try:
            self._revision_verifier()
            channel_module = self._module_loader("unitree_sdk2py.core.channel")
            sport_module = self._module_loader(
                "unitree_sdk2py.a2.sport.sport_client"
            )
            state_module = self._module_loader(
                "unitree_sdk2py.idl.unitree_go.msg.dds_"
            )
            channel_module.ChannelFactoryInitialize(
                self._dds_domain_id, self._network_interface
            )
            # Initialize the state reader first so a reader failure cannot
            # strand a fully initialized command client.
            subscriber = channel_module.ChannelSubscriber(
                SPORT_STATE_TOPIC, state_module.SportModeState_
            )
            # Avoid the SDK's optional Python FIFO: Sport freshness is stamped
            # when this direct DDS callback runs, not when an old queued sample
            # is eventually drained.
            subscriber.Init(self._handle_sport_state, 0)
            client = sport_module.SportClient()
            client.SetTimeout(self._rpc_timeout_s)
            client.Init()
            version_code, server_api_version = client.GetServerApiVersion()
            if int(version_code) != 0:
                raise SDK2BackendError(
                    f"A2 Sport server API version query failed: {version_code}"
                )
            if str(server_api_version) != A2_SPORT_API_VERSION:
                raise SDK2BackendError(
                    "A2 Sport server API version does not match "
                    f"{A2_SPORT_API_VERSION}: {server_api_version}"
                )
        except Exception as exc:
            if subscriber is not None:
                try:
                    subscriber.Close()
                except Exception:
                    pass
            raise SDK2BackendError(f"failed to initialize Unitree SDK2: {exc}") from exc

        self._client = client
        self._subscriber = subscriber

    def move(self, linear_x: float, angular_z: float) -> int:
        self._require_started()
        # Lateral velocity is intentionally unavailable at this navigation
        # boundary. The SafetyEnvelope rejects every non-zero unsupported DOF.
        return int(self._client.Move(float(linear_x), 0.0, float(angular_z)))

    def stop(self) -> int:
        self._require_started()
        return int(self._client.StopMove())

    def close(self) -> None:
        subscriber = self._subscriber
        self._subscriber = None
        self._client = None
        if subscriber is not None:
            try:
                subscriber.Close()
            except Exception:
                # Shutdown StopMove is attempted by the worker before close.
                pass

    def _handle_sport_state(self, message: object) -> None:
        try:
            error_code = int(message.error_code)
            mode = int(message.mode)
        except (AttributeError, TypeError, ValueError, OverflowError):
            error_code = None
            mode = None
        self._state_callback(error_code, mode)

    def _require_started(self) -> None:
        if not self.started:
            raise SDK2BackendError("SDK2 backend is not started")
