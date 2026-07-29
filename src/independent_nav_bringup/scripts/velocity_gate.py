#!/usr/bin/python3
"""Safety boundary between Nav2 and a platform adapter."""

import math
from numbers import Integral
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool


NANOSECONDS_PER_SECOND = 1_000_000_000


def monotonic_receive_time(message_info, monotonic_now, wall_time_ns=None):
    """Map local DDS arrival time to the watchdog's monotonic clock."""
    received_ns = message_info.get("received_timestamp")
    if isinstance(received_ns, bool) or not isinstance(received_ns, Integral):
        raise ValueError("DDS received_timestamp must be an integer")
    received_ns = int(received_ns)
    callback_wall_ns = time.time_ns() if wall_time_ns is None else wall_time_ns
    if received_ns <= 0 or received_ns > callback_wall_ns:
        raise ValueError("DDS received_timestamp is invalid")
    received_at = monotonic_now - (
        callback_wall_ns - received_ns
    ) / NANOSECONDS_PER_SECOND
    if not math.isfinite(received_at):
        raise ValueError("derived monotonic timestamp must be finite")
    return received_at


def is_planar_twist(msg):
    values = (
        msg.linear.x,
        msg.linear.y,
        msg.linear.z,
        msg.angular.x,
        msg.angular.y,
        msg.angular.z,
    )
    unsupported_values = (
        msg.linear.y,
        msg.linear.z,
        msg.angular.x,
        msg.angular.y,
    )
    return all(math.isfinite(value) for value in values) and all(
        value == 0.0 for value in unsupported_values
    )


class RearmInterlock:
    """Require an observed disable before startup and after a latched fault."""

    def __init__(self):
        self.await_disable = True
        self.fault_latched = False
        self.armed = False

    def update_enable(self, enabled):
        if not enabled:
            self.await_disable = False
            self.fault_latched = False
            self.armed = False

    def latch_fault(self, latch_faults):
        self.armed = False
        if latch_faults:
            self.fault_latched = True
            self.await_disable = True

    def evaluate(self, conditions_healthy, latch_faults):
        allowed = (
            conditions_healthy and not self.await_disable and not self.fault_latched
        )
        if allowed:
            self.armed = True
            return True
        if self.armed and latch_faults:
            self.fault_latched = True
            self.await_disable = True
        self.armed = False
        return False


class VelocityGate(Node):
    def __init__(self):
        super().__init__("velocity_gate")
        self.declare_parameter("input_cmd_topic", "/cmd_vel")
        self.declare_parameter("output_cmd_topic", "/platform/cmd_vel")
        self.declare_parameter("cmd_timeout", 0.20)
        self.declare_parameter("state_timeout", 0.50)
        self.declare_parameter("max_linear_x", 0.20)
        self.declare_parameter("max_angular_z", 0.30)
        self.declare_parameter("latch_faults", True)
        self.command = Twist()
        self.command_time = None
        self.states = {"enable": False, "ready": False, "healthy": False}
        self.state_times = {name: None for name in self.states}
        self.interlock = RearmInterlock()
        self.publisher = self.create_publisher(
            Twist, self.get_parameter("output_cmd_topic").value, 10
        )
        input_qos = QoSProfile(depth=1)
        input_qos.reliability = ReliabilityPolicy.RELIABLE
        self.create_subscription(
            Twist,
            self.get_parameter("input_cmd_topic").value,
            self.command_callback,
            input_qos,
        )
        self.create_subscription(Bool, "/nav/enable", self.enable_callback, input_qos)
        self.create_subscription(
            Bool, "/platform/ready", self.state_callback("ready"), input_qos
        )
        self.create_subscription(
            Bool, "/nav/healthy", self.state_callback("healthy"), input_qos
        )
        self.create_timer(0.05, self.publish_safe_command)

    def now(self):
        return time.monotonic()

    def received_at(self, message_info, maximum_age, input_name):
        callback_at = self.now()
        try:
            received_at = monotonic_receive_time(message_info, callback_at)
        except (TypeError, ValueError) as exc:
            self.interlock.latch_fault(
                self.get_parameter("latch_faults").value
            )
            self.get_logger().error(f"Rejected {input_name}: {exc}")
            return None
        age = callback_at - received_at
        if age > maximum_age:
            self.interlock.latch_fault(
                self.get_parameter("latch_faults").value
            )
            self.get_logger().error(
                f"Rejected {input_name}: DDS queue age {age:.3f} s exceeds "
                f"{maximum_age:.3f} s"
            )
            return None
        return received_at

    def command_callback(self, msg, message_info):
        received_at = self.received_at(
            message_info,
            self.get_parameter("cmd_timeout").value,
            self.get_parameter("input_cmd_topic").value,
        )
        if received_at is None:
            self.command = Twist()
            self.command_time = None
            return
        if is_planar_twist(msg):
            self.command = msg
            self.command_time = received_at
        else:
            self.command = Twist()
            self.command_time = None
            self.interlock.latch_fault(
                self.get_parameter("latch_faults").value
            )

    def enable_callback(self, msg, message_info):
        received_at = self.received_at(
            message_info,
            self.get_parameter("state_timeout").value,
            "/nav/enable",
        )
        if received_at is None:
            self.states["enable"] = False
            self.state_times["enable"] = None
            return
        self.states["enable"] = msg.data
        self.state_times["enable"] = received_at
        self.interlock.update_enable(msg.data)

    def state_callback(self, name):
        def callback(msg, message_info):
            received_at = self.received_at(
                message_info,
                self.get_parameter("state_timeout").value,
                f"/{name}",
            )
            if received_at is None:
                self.states[name] = False
                self.state_times[name] = None
                return
            self.states[name] = msg.data
            self.state_times[name] = received_at
        return callback

    def conditions_healthy(self):
        now = self.now()
        state_timeout = self.get_parameter("state_timeout").value
        states_fresh = all(
            self.states[name] and timestamp is not None and now - timestamp <= state_timeout
            for name, timestamp in self.state_times.items()
        )
        command_fresh = (
            self.command_time is not None
            and now - self.command_time <= self.get_parameter("cmd_timeout").value
        )
        return states_fresh and command_fresh

    def publish_safe_command(self):
        output = Twist()
        if self.interlock.evaluate(
            self.conditions_healthy(),
            self.get_parameter("latch_faults").value,
        ):
            max_x = self.get_parameter("max_linear_x").value
            max_z = self.get_parameter("max_angular_z").value
            output.linear.x = max(-max_x, min(max_x, self.command.linear.x))
            output.angular.z = max(-max_z, min(max_z, self.command.angular.z))
        self.publisher.publish(output)


def main():
    rclpy.init()
    node = VelocityGate()
    try:
        rclpy.spin(node)
    except (ExternalShutdownException, KeyboardInterrupt):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
