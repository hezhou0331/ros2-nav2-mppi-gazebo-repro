"""Thread-safe, ROS-independent safety state for the A2 adapter."""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Integral
import threading
import time
from typing import Mapping, Optional, Sequence, Tuple


SDK_WRITER_WAIT_QUANTUM_S = 0.10
HARD_MAX_LINEAR_X = 0.10
HARD_MAX_ANGULAR_Z = 0.20
HARD_MAX_COMMAND_TIMEOUT_S = 0.08
HARD_MAX_CONTROL_PERIOD_S = 0.02
HARD_MAX_RPC_TIMEOUT_S = 0.02
HARD_MAX_SPORT_STATE_TIMEOUT_S = 0.20
HARD_MAX_EXTERNAL_STATE_TIMEOUT_S = 0.25
HARD_MAX_UNSUPPORTED_AXIS_EPSILON = 1.0e-6
HARD_MAX_STOP_REFRESH_PERIOD_S = 0.10
HARD_MAX_STATUS_PUBLISH_PERIOD_S = 0.05
HARD_MIN_SHUTDOWN_JOIN_TIMEOUT_S = 0.50
HARD_ALLOWED_SPORT_MODES = frozenset((3, 4))
NANOSECONDS_PER_SECOND = 1_000_000_000


def monotonic_receive_time(
    message_info: Mapping[str, object],
    *,
    monotonic_now: Optional[float] = None,
    wall_time_ns: Optional[int] = None,
) -> float:
    """Map a local DDS receive timestamp onto the monotonic clock."""

    received_ns = message_info.get("received_timestamp")
    if isinstance(received_ns, bool) or not isinstance(received_ns, Integral):
        raise ValueError("DDS received_timestamp must be an integer")
    received_ns = int(received_ns)
    if received_ns <= 0:
        raise ValueError("DDS received_timestamp must be positive")

    callback_wall_ns = time.time_ns() if wall_time_ns is None else wall_time_ns
    if isinstance(callback_wall_ns, bool) or not isinstance(callback_wall_ns, Integral):
        raise ValueError("callback wall timestamp must be an integer")
    callback_wall_ns = int(callback_wall_ns)
    queue_age_ns = callback_wall_ns - received_ns
    if queue_age_ns < 0:
        raise ValueError("DDS received_timestamp is in the future")

    callback_monotonic = (
        time.monotonic() if monotonic_now is None else float(monotonic_now)
    )
    received_monotonic = (
        callback_monotonic - queue_age_ns / NANOSECONDS_PER_SECOND
    )
    if not math.isfinite(received_monotonic):
        raise ValueError("derived monotonic receive timestamp must be finite")
    return received_monotonic


@dataclass(frozen=True)
class SafetyLimits:
    """Limits for the fail-closed command decision and nominal RPC path."""

    max_linear_x: float = 0.10
    max_angular_z: float = 0.20
    command_timeout_s: float = 0.08
    control_period_s: float = 0.02
    rpc_timeout_s: float = 0.02
    sport_state_timeout_s: float = 0.20
    external_state_timeout_s: float = 0.25
    nominal_stop_request_budget_s: float = 0.20
    unsupported_axis_epsilon: float = 1.0e-6
    allowed_sport_modes: Tuple[int, ...] = (3, 4)

    @property
    def nominal_stop_request_latency_s(self) -> float:
        # This applies only while the DDS service writer remains matched. Each
        # possible in-flight Move and subsequent StopMove can wait for a reply.
        return (
            self.command_timeout_s
            + self.control_period_s
            + 2.0 * self.rpc_timeout_s
        )

    @property
    def unmatched_rpc_return_path_s(self) -> float:
        # Pinned SDK2 Writer.Write sleeps in 100 ms quanta when unmatched,
        # regardless of a smaller configured RPC timeout. This is only an
        # estimate of caller return time; an undeliverable stop has no physical
        # stop bound without a robot-side watchdog.
        return (
            self.command_timeout_s
            + self.control_period_s
            + 2.0 * SDK_WRITER_WAIT_QUANTUM_S
        )

    def validate(self) -> None:
        positive = {
            "max_linear_x": self.max_linear_x,
            "max_angular_z": self.max_angular_z,
            "command_timeout_s": self.command_timeout_s,
            "control_period_s": self.control_period_s,
            "rpc_timeout_s": self.rpc_timeout_s,
            "sport_state_timeout_s": self.sport_state_timeout_s,
            "external_state_timeout_s": self.external_state_timeout_s,
            "nominal_stop_request_budget_s": self.nominal_stop_request_budget_s,
            "unsupported_axis_epsilon": self.unsupported_axis_epsilon,
        }
        for name, value in positive.items():
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and greater than zero")
        hard_maxima = {
            "max_linear_x": (self.max_linear_x, HARD_MAX_LINEAR_X),
            "max_angular_z": (self.max_angular_z, HARD_MAX_ANGULAR_Z),
            "command_timeout_s": (
                self.command_timeout_s,
                HARD_MAX_COMMAND_TIMEOUT_S,
            ),
            "control_period_s": (
                self.control_period_s,
                HARD_MAX_CONTROL_PERIOD_S,
            ),
            "rpc_timeout_s": (self.rpc_timeout_s, HARD_MAX_RPC_TIMEOUT_S),
            "sport_state_timeout_s": (
                self.sport_state_timeout_s,
                HARD_MAX_SPORT_STATE_TIMEOUT_S,
            ),
            "external_state_timeout_s": (
                self.external_state_timeout_s,
                HARD_MAX_EXTERNAL_STATE_TIMEOUT_S,
            ),
            "unsupported_axis_epsilon": (
                self.unsupported_axis_epsilon,
                HARD_MAX_UNSUPPORTED_AXIS_EPSILON,
            ),
        }
        for name, (value, hard_maximum) in hard_maxima.items():
            if value > hard_maximum:
                raise ValueError(
                    f"{name} must not exceed the hardware cap {hard_maximum}"
                )
        if self.nominal_stop_request_budget_s > 0.20:
            raise ValueError(
                "nominal_stop_request_budget_s must not exceed 0.20 seconds"
            )
        if (
            self.nominal_stop_request_latency_s
            > self.nominal_stop_request_budget_s + 1.0e-12
        ):
            raise ValueError(
                "command_timeout_s + control_period_s + 2 * rpc_timeout_s "
                "exceeds nominal_stop_request_budget_s"
            )
        if not self.allowed_sport_modes:
            raise ValueError("allowed_sport_modes must not be empty")
        if not set(self.allowed_sport_modes).issubset(HARD_ALLOWED_SPORT_MODES):
            raise ValueError("allowed_sport_modes must be a subset of modes 3 and 4")


@dataclass(frozen=True)
class SafeCommand:
    linear_x: float
    angular_z: float
    received_at: float


@dataclass(frozen=True)
class SafetySnapshot:
    ready: bool
    ready_reasons: Tuple[str, ...]
    move_permitted: bool
    stop_reason: str
    command: Optional[SafeCommand]
    command_age_s: Optional[float]
    sport_state_age_s: Optional[float]
    automatic_mode_age_s: Optional[float]
    manual_override_age_s: Optional[float]
    estop_age_s: Optional[float]
    sport_mode: Optional[int]
    sport_error_code: Optional[int]
    backend_available: bool
    backend_rpc_ok: bool
    last_rpc_code: Optional[int]
    backend_detail: str
    command_rejection: str
    fault_latched: bool
    fault_reason: str


@dataclass
class _TimedBool:
    value: Optional[bool] = None
    received_at: Optional[float] = None


class SafetyEnvelope:
    """Owns adapter state and produces fail-closed movement decisions."""

    def __init__(self, limits: SafetyLimits):
        limits.validate()
        self.limits = limits
        self._lock = threading.Lock()
        self._automatic_mode = _TimedBool()
        self._manual_override = _TimedBool()
        self._estop = _TimedBool()
        self._sport_received_at: Optional[float] = None
        self._sport_mode: Optional[int] = None
        self._sport_error_code: Optional[int] = None
        self._backend_available = False
        self._backend_rpc_ok = False
        self._last_rpc_code: Optional[int] = None
        self._backend_detail = "not_started"
        self._command: Optional[SafeCommand] = None
        self._command_rejection = ""
        self._fault_latched = False
        self._fault_reason = ""
        self._automatic_rearm_armed = False
        self._has_been_ready = False

    def set_automatic_mode(self, value: bool, received_at: float) -> None:
        self._validate_time(received_at)
        enabled = bool(value)
        with self._lock:
            self._automatic_mode.value = enabled
            self._automatic_mode.received_at = received_at
            if not enabled:
                self._automatic_rearm_armed = True
            elif self._automatic_rearm_armed:
                self._automatic_rearm_armed = False
                if self._can_rearm_locked(received_at):
                    self._fault_latched = False
                    self._fault_reason = ""
                    self._command_rejection = ""
                    # A post-rearm command must be received before movement.
                    self._command = None

    def set_manual_override(self, value: bool, received_at: float) -> None:
        self._set_external_state(
            self._manual_override,
            value,
            received_at,
            fault_reason="manual_override_active",
        )

    def set_estop(self, value: bool, received_at: float) -> None:
        self._set_external_state(
            self._estop,
            value,
            received_at,
            fault_reason="estop_active",
        )

    def _set_external_state(
        self,
        state: _TimedBool,
        value: bool,
        received_at: float,
        fault_reason: str,
    ) -> None:
        self._validate_time(received_at)
        with self._lock:
            state.value = bool(value)
            state.received_at = received_at
            if value:
                self._latch_fault_locked(fault_reason)

    def update_sport_state(
        self,
        error_code: Optional[int],
        mode: Optional[int],
        received_at: float,
    ) -> None:
        self._validate_time(received_at)
        with self._lock:
            self._sport_error_code = None if error_code is None else int(error_code)
            self._sport_mode = None if mode is None else int(mode)
            self._sport_received_at = received_at
            if error_code is None or mode is None:
                self._latch_fault_locked("sport_state_invalid")
            elif error_code != 0:
                self._latch_fault_locked("sport_error")
            elif mode not in self.limits.allowed_sport_modes:
                self._latch_fault_locked("sport_mode_not_allowed")

    def set_backend_available(self, available: bool, detail: str = "") -> None:
        with self._lock:
            self._backend_available = bool(available)
            if not available:
                self._backend_rpc_ok = False
            self._backend_detail = detail

    def record_rpc_result(self, code: int, detail: str) -> None:
        with self._lock:
            self._last_rpc_code = int(code)
            self._backend_rpc_ok = code == 0
            self._backend_detail = detail
            if code != 0:
                self._latch_fault_locked(f"rpc_failure:{code}")

    def record_rpc_exception(self, detail: str) -> None:
        with self._lock:
            self._backend_rpc_ok = False
            self._backend_detail = detail
            self._latch_fault_locked("rpc_exception")

    def record_input_fault(self, reason: str) -> None:
        if not reason:
            raise ValueError("input fault reason must not be empty")
        with self._lock:
            self._command = None
            self._latch_fault_locked(reason)

    def accept_command(
        self,
        components: Sequence[float],
        received_at: float,
    ) -> Tuple[bool, str]:
        """Validate a Twist represented as lx, ly, lz, ax, ay, az."""

        self._validate_time(received_at)
        if len(components) != 6:
            raise ValueError("components must contain exactly six values")
        values = tuple(float(value) for value in components)
        rejection = ""
        if not all(math.isfinite(value) for value in values):
            rejection = "non_finite_command"
        else:
            _, linear_y, linear_z, angular_x, angular_y, _ = values
            unsupported = (linear_y, linear_z, angular_x, angular_y)
            if any(
                abs(value) > self.limits.unsupported_axis_epsilon
                for value in unsupported
            ):
                rejection = "unsupported_nonzero_axis"

        with self._lock:
            if rejection:
                self._command = None
                self._command_rejection = rejection
                self._latch_fault_locked(rejection)
                return False, rejection
            linear_x = self._clamp(values[0], self.limits.max_linear_x)
            angular_z = self._clamp(values[5], self.limits.max_angular_z)
            self._command = SafeCommand(linear_x, angular_z, received_at)
            self._command_rejection = ""
            return True, ""

    def snapshot(self, now: float) -> SafetySnapshot:
        self._validate_time(now)
        with self._lock:
            self._latch_stale_authority_locked(now)
            automatic = _TimedBool(
                self._automatic_mode.value, self._automatic_mode.received_at
            )
            manual = _TimedBool(
                self._manual_override.value, self._manual_override.received_at
            )
            estop = _TimedBool(self._estop.value, self._estop.received_at)
            sport_received_at = self._sport_received_at
            sport_mode = self._sport_mode
            sport_error_code = self._sport_error_code
            backend_available = self._backend_available
            backend_rpc_ok = self._backend_rpc_ok
            last_rpc_code = self._last_rpc_code
            backend_detail = self._backend_detail
            command = self._command
            command_rejection = self._command_rejection
            fault_latched = self._fault_latched
            fault_reason = self._fault_reason

        automatic_age = self._age(now, automatic.received_at)
        manual_age = self._age(now, manual.received_at)
        estop_age = self._age(now, estop.received_at)
        sport_age = self._age(now, sport_received_at)
        command_age = self._age(now, command.received_at if command else None)

        reasons = []
        if not backend_available:
            reasons.append("backend_unavailable")
        elif not backend_rpc_ok:
            reasons.append("backend_rpc_unhealthy")
        self._append_external_reason(
            reasons, "automatic_mode", automatic, automatic_age, required=True
        )
        self._append_external_reason(
            reasons, "manual_override", manual, manual_age, required=False
        )
        self._append_external_reason(
            reasons, "estop", estop, estop_age, required=False
        )
        if sport_received_at is None:
            reasons.append("sport_state_unknown")
        elif sport_age is None or sport_age > self.limits.sport_state_timeout_s:
            reasons.append("sport_state_stale")
        elif sport_error_code is None or sport_mode is None:
            reasons.append("sport_state_invalid")
        else:
            if sport_error_code != 0:
                reasons.append("sport_error")
            if sport_mode not in self.limits.allowed_sport_modes:
                reasons.append("sport_mode_not_allowed")
        if command_rejection:
            reasons.append(command_rejection)
        if fault_latched:
            reasons.append(f"fault_latched:{fault_reason}")

        ready = not reasons
        if ready:
            with self._lock:
                self._has_been_ready = True
        if not ready:
            stop_reason = reasons[0]
        elif command is None:
            stop_reason = "command_missing"
        elif command_age is None or command_age > self.limits.command_timeout_s:
            stop_reason = "command_stale"
        else:
            stop_reason = ""
        move_permitted = ready and not stop_reason

        return SafetySnapshot(
            ready=ready,
            ready_reasons=tuple(reasons),
            move_permitted=move_permitted,
            stop_reason=stop_reason,
            command=command,
            command_age_s=command_age,
            sport_state_age_s=sport_age,
            automatic_mode_age_s=automatic_age,
            manual_override_age_s=manual_age,
            estop_age_s=estop_age,
            sport_mode=sport_mode,
            sport_error_code=sport_error_code,
            backend_available=backend_available,
            backend_rpc_ok=backend_rpc_ok,
            last_rpc_code=last_rpc_code,
            backend_detail=backend_detail,
            command_rejection=command_rejection,
            fault_latched=fault_latched,
            fault_reason=fault_reason,
        )

    def _latch_fault_locked(self, reason: str) -> None:
        if not self._fault_latched:
            self._automatic_rearm_armed = False
        self._fault_latched = True
        if not self._fault_reason:
            self._fault_reason = reason

    def _latch_stale_authority_locked(self, now: float) -> None:
        if not self._has_been_ready or self._fault_latched:
            return
        external_states = (
            ("automatic_mode_stale", self._automatic_mode),
            ("manual_override_stale", self._manual_override),
            ("estop_stale", self._estop),
        )
        for reason, state in external_states:
            if (
                state.received_at is None
                or now - state.received_at > self.limits.external_state_timeout_s
            ):
                self._command = None
                self._latch_fault_locked(reason)
                return
        if (
            self._sport_received_at is None
            or now - self._sport_received_at > self.limits.sport_state_timeout_s
        ):
            self._command = None
            self._latch_fault_locked("sport_state_stale")

    def _can_rearm_locked(self, now: float) -> bool:
        external_states_safe = all(
            state.value is False
            and state.received_at is not None
            and now - state.received_at <= self.limits.external_state_timeout_s
            for state in (self._manual_override, self._estop)
        )
        sport_state_safe = (
            self._sport_received_at is not None
            and now - self._sport_received_at <= self.limits.sport_state_timeout_s
            and self._sport_error_code == 0
            and self._sport_mode in self.limits.allowed_sport_modes
        )
        return (
            external_states_safe
            and sport_state_safe
            and self._backend_available
            and self._backend_rpc_ok
        )

    def _append_external_reason(
        self,
        reasons: list[str],
        name: str,
        state: _TimedBool,
        age: Optional[float],
        required: bool,
    ) -> None:
        if state.received_at is None or state.value is None:
            reasons.append(f"{name}_unknown")
        elif age is None or age > self.limits.external_state_timeout_s:
            reasons.append(f"{name}_stale")
        elif state.value is not required:
            reasons.append(f"{name}_{'disabled' if required else 'active'}")

    @staticmethod
    def _clamp(value: float, magnitude: float) -> float:
        return max(-magnitude, min(magnitude, value))

    @staticmethod
    def _age(now: float, received_at: Optional[float]) -> Optional[float]:
        if received_at is None:
            return None
        return max(0.0, now - received_at)

    @staticmethod
    def _validate_time(value: float) -> None:
        if not math.isfinite(value):
            raise ValueError("monotonic timestamp must be finite")
