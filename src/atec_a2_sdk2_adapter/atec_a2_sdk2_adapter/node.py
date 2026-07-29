"""ROS 2 node for the fail-closed Unitree A2 SDK2 adapter."""

from __future__ import annotations

import math
import time
from typing import Optional

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from geometry_msgs.msg import Twist
import rclpy
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool

from .safety import (
    HARD_MAX_STATUS_PUBLISH_PERIOD_S,
    HARD_MAX_STOP_REFRESH_PERIOD_S,
    HARD_MIN_SHUTDOWN_JOIN_TIMEOUT_S,
    SafetyEnvelope,
    SafetyLimits,
    SafetySnapshot,
    monotonic_receive_time,
)
from .sdk2_backend import UnitreeA2SportBackend
from .worker import SportCommandWorker


class A2SDK2AdapterNode(Node):
    def __init__(self) -> None:
        super().__init__("a2_sdk2_adapter")
        self._declare_parameters()
        limits = self._read_limits()
        self._limits = limits
        self._safety = SafetyEnvelope(limits)
        self._shutdown_started = False

        state_qos = QoSProfile(depth=1)
        state_qos.reliability = ReliabilityPolicy.RELIABLE
        state_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self._ready_publisher = self.create_publisher(
            Bool, "/platform/ready", state_qos
        )
        self._status_publisher = self.create_publisher(
            DiagnosticArray, "/platform/adapter_status", state_qos
        )

        input_qos = QoSProfile(depth=1)
        input_qos.reliability = ReliabilityPolicy.RELIABLE
        input_qos.durability = DurabilityPolicy.VOLATILE
        self.create_subscription(
            Twist, "/platform/cmd_vel", self._command_callback, input_qos
        )
        self.create_subscription(
            Bool,
            "/platform/automatic_mode",
            self._automatic_mode_callback,
            input_qos,
        )
        self.create_subscription(
            Bool,
            "/platform/manual_override",
            self._manual_override_callback,
            input_qos,
        )
        self.create_subscription(
            Bool,
            "/platform/estop",
            self._estop_callback,
            input_qos,
        )

        network_interface = str(self.get_parameter("network_interface").value)
        dds_domain_id = int(self.get_parameter("dds_domain_id").value)
        backend = UnitreeA2SportBackend(
            network_interface=network_interface,
            dds_domain_id=dds_domain_id,
            rpc_timeout_s=limits.rpc_timeout_s,
            state_callback=self._sport_state_callback,
        )
        self._worker = SportCommandWorker(
            safety=self._safety,
            backend=backend,
            stop_refresh_period_s=float(
                self.get_parameter("stop_refresh_period_s").value
            ),
            log=self.get_logger().error,
        )
        shutdown_join_timeout = float(
            self.get_parameter("shutdown_join_timeout_s").value
        )
        if (
            not math.isfinite(shutdown_join_timeout)
            or shutdown_join_timeout < HARD_MIN_SHUTDOWN_JOIN_TIMEOUT_S
        ):
            raise ValueError(
                "shutdown_join_timeout_s must be finite and at least "
                f"{HARD_MIN_SHUTDOWN_JOIN_TIMEOUT_S}"
            )
        self._shutdown_join_timeout_s = shutdown_join_timeout
        status_period = float(self.get_parameter("status_publish_period_s").value)
        if (
            not math.isfinite(status_period)
            or status_period <= 0.0
            or status_period > HARD_MAX_STATUS_PUBLISH_PERIOD_S
        ):
            raise ValueError(
                "status_publish_period_s must be finite, positive, and no greater "
                f"than {HARD_MAX_STATUS_PUBLISH_PERIOD_S}"
            )
        stop_refresh = float(self.get_parameter("stop_refresh_period_s").value)
        if (
            not math.isfinite(stop_refresh)
            or stop_refresh <= 0.0
            or stop_refresh > HARD_MAX_STOP_REFRESH_PERIOD_S
        ):
            raise ValueError(
                "stop_refresh_period_s must be finite, positive, and no greater "
                f"than {HARD_MAX_STOP_REFRESH_PERIOD_S}"
            )
        self.create_timer(status_period, self._publish_status)
        self._publish_status()
        self._worker.start()

        self.get_logger().warning(
            "A2 SDK2 adapter starts fail-closed; authoritative automatic-mode, "
            "manual-override, estop, and fresh SportModeState inputs are required"
        )

    def destroy_node(self) -> bool:
        if not self._shutdown_started:
            self._shutdown_started = True
            joined = self._worker.close(self._shutdown_join_timeout_s)
            if not joined:
                self.get_logger().error(
                    "SDK2 worker did not finish its shutdown StopMove within "
                    "shutdown_join_timeout_s"
                )
        return super().destroy_node()

    def _declare_parameters(self) -> None:
        descriptor = ParameterDescriptor(read_only=True)
        defaults = (
            ("network_interface", ""),
            ("dds_domain_id", 0),
            ("max_linear_x", 0.10),
            ("max_angular_z", 0.20),
            ("command_timeout_s", 0.08),
            ("control_period_s", 0.02),
            ("rpc_timeout_s", 0.02),
            ("sport_state_timeout_s", 0.20),
            ("external_state_timeout_s", 0.25),
            ("nominal_stop_request_budget_s", 0.20),
            ("unsupported_axis_epsilon", 1.0e-6),
            ("allowed_sport_modes", [3, 4]),
            ("stop_refresh_period_s", 0.10),
            ("status_publish_period_s", 0.05),
            ("shutdown_join_timeout_s", 0.50),
        )
        for name, default in defaults:
            self.declare_parameter(name, default, descriptor)

    def _read_limits(self) -> SafetyLimits:
        return SafetyLimits(
            max_linear_x=float(self.get_parameter("max_linear_x").value),
            max_angular_z=float(self.get_parameter("max_angular_z").value),
            command_timeout_s=float(
                self.get_parameter("command_timeout_s").value
            ),
            control_period_s=float(self.get_parameter("control_period_s").value),
            rpc_timeout_s=float(self.get_parameter("rpc_timeout_s").value),
            sport_state_timeout_s=float(
                self.get_parameter("sport_state_timeout_s").value
            ),
            external_state_timeout_s=float(
                self.get_parameter("external_state_timeout_s").value
            ),
            nominal_stop_request_budget_s=float(
                self.get_parameter("nominal_stop_request_budget_s").value
            ),
            unsupported_axis_epsilon=float(
                self.get_parameter("unsupported_axis_epsilon").value
            ),
            allowed_sport_modes=tuple(
                int(value)
                for value in self.get_parameter("allowed_sport_modes").value
            ),
        )

    def _input_received_at(
        self,
        message_info: dict,
        input_name: str,
        maximum_age_s: float,
    ) -> Optional[float]:
        callback_at = time.monotonic()
        try:
            received_at = monotonic_receive_time(
                message_info,
                monotonic_now=callback_at,
            )
        except (TypeError, ValueError) as exc:
            reason = f"{input_name}_timestamp_invalid"
            self._safety.record_input_fault(reason)
            self.get_logger().error(f"Rejected {input_name}: {exc}")
            return None
        age_s = callback_at - received_at
        if age_s > maximum_age_s:
            reason = f"{input_name}_sample_stale"
            self._safety.record_input_fault(reason)
            self.get_logger().error(
                f"Rejected {input_name}: DDS queue age {age_s:.3f} s exceeds "
                f"{maximum_age_s:.3f} s"
            )
            return None
        return received_at

    def _command_callback(self, message: Twist, message_info: dict) -> None:
        received_at = self._input_received_at(
            message_info,
            "platform_cmd_vel",
            self._limits.command_timeout_s,
        )
        if received_at is None:
            return
        accepted, reason = self._safety.accept_command(
            (
                message.linear.x,
                message.linear.y,
                message.linear.z,
                message.angular.x,
                message.angular.y,
                message.angular.z,
            ),
            received_at,
        )
        if not accepted:
            self.get_logger().error(f"Rejected /platform/cmd_vel: {reason}")

    def _automatic_mode_callback(self, message: Bool, message_info: dict) -> None:
        received_at = self._input_received_at(
            message_info,
            "automatic_mode",
            self._limits.external_state_timeout_s,
        )
        if received_at is not None:
            self._safety.set_automatic_mode(message.data, received_at)

    def _manual_override_callback(self, message: Bool, message_info: dict) -> None:
        received_at = self._input_received_at(
            message_info,
            "manual_override",
            self._limits.external_state_timeout_s,
        )
        if received_at is not None:
            self._safety.set_manual_override(message.data, received_at)

    def _estop_callback(self, message: Bool, message_info: dict) -> None:
        received_at = self._input_received_at(
            message_info,
            "estop",
            self._limits.external_state_timeout_s,
        )
        if received_at is not None:
            self._safety.set_estop(message.data, received_at)

    def _sport_state_callback(
        self, error_code: Optional[int], mode: Optional[int]
    ) -> None:
        self._safety.update_sport_state(
            error_code=error_code,
            mode=mode,
            received_at=time.monotonic(),
        )

    def _publish_status(self) -> None:
        snapshot = self._safety.snapshot(time.monotonic())
        self._ready_publisher.publish(Bool(data=snapshot.ready))
        self._status_publisher.publish(self._diagnostic_message(snapshot))

    def _diagnostic_message(self, snapshot: SafetySnapshot) -> DiagnosticArray:
        message = DiagnosticArray()
        message.header.stamp = self.get_clock().now().to_msg()
        status = DiagnosticStatus()
        status.name = "atec_a2_sdk2_adapter"
        status.hardware_id = "unitree_a2"
        if snapshot.ready:
            status.level = DiagnosticStatus.OK
            status.message = "ready"
        elif snapshot.backend_available:
            status.level = DiagnosticStatus.WARN
            status.message = ",".join(snapshot.ready_reasons) or snapshot.stop_reason
        else:
            status.level = DiagnosticStatus.ERROR
            status.message = ",".join(snapshot.ready_reasons) or "backend_unavailable"

        values = {
            "ready": snapshot.ready,
            "move_permitted": snapshot.move_permitted,
            "stop_reason": snapshot.stop_reason,
            "ready_reasons": ",".join(snapshot.ready_reasons),
            "backend_available": snapshot.backend_available,
            "backend_rpc_ok": snapshot.backend_rpc_ok,
            "backend_detail": snapshot.backend_detail,
            "last_rpc_code": snapshot.last_rpc_code,
            "sport_mode": snapshot.sport_mode,
            "sport_error_code": snapshot.sport_error_code,
            "command_age_s": self._format_optional(snapshot.command_age_s),
            "sport_state_age_s": self._format_optional(
                snapshot.sport_state_age_s
            ),
            "automatic_mode_age_s": self._format_optional(
                snapshot.automatic_mode_age_s
            ),
            "manual_override_age_s": self._format_optional(
                snapshot.manual_override_age_s
            ),
            "estop_age_s": self._format_optional(snapshot.estop_age_s),
            "command_rejection": snapshot.command_rejection,
            "fault_latched": snapshot.fault_latched,
            "fault_reason": snapshot.fault_reason,
            "nominal_stop_request_latency_s": (
                f"{self._safety.limits.nominal_stop_request_latency_s:.3f}"
            ),
            "unmatched_rpc_return_path_s": (
                f"{self._safety.limits.unmatched_rpc_return_path_s:.3f}"
            ),
        }
        status.values = [
            KeyValue(key=key, value=str(value)) for key, value in values.items()
        ]
        message.status = [status]
        return message

    @staticmethod
    def _format_optional(value: Optional[float]) -> str:
        return "unknown" if value is None else f"{value:.3f}"


def main(args=None) -> None:
    rclpy.init(args=args)
    node = None
    try:
        node = A2SDK2AdapterNode()
        rclpy.spin(node)
    except (ExternalShutdownException, KeyboardInterrupt):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
