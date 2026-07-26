#!/usr/bin/python3
"""Safety boundary between Nav2 and a platform adapter."""

import math

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Bool


class VelocityGate(Node):
    def __init__(self):
        super().__init__("velocity_gate")
        self.declare_parameter("input_cmd_topic", "/cmd_vel")
        self.declare_parameter("output_cmd_topic", "/platform/cmd_vel")
        self.declare_parameter("cmd_timeout", 0.20)
        self.declare_parameter("state_timeout", 0.50)
        self.declare_parameter("max_linear_x", 0.20)
        self.declare_parameter("max_angular_z", 0.30)
        self.command = Twist()
        self.command_time = None
        self.states = {"enable": False, "ready": False, "healthy": False}
        self.state_times = {name: None for name in self.states}
        self.await_disable = True
        self.armed = False
        self.publisher = self.create_publisher(
            Twist, self.get_parameter("output_cmd_topic").value, 10
        )
        self.create_subscription(
            Twist, self.get_parameter("input_cmd_topic").value, self.command_callback, 10
        )
        self.create_subscription(Bool, "/nav/enable", self.enable_callback, 10)
        self.create_subscription(Bool, "/platform/ready", self.state_callback("ready"), 10)
        self.create_subscription(Bool, "/nav/healthy", self.state_callback("healthy"), 10)
        self.create_timer(0.05, self.publish_safe_command)

    def now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def command_callback(self, msg):
        if all(math.isfinite(value) for value in (msg.linear.x, msg.angular.z)):
            self.command = msg
            self.command_time = self.now()

    def enable_callback(self, msg):
        self.states["enable"] = msg.data
        self.state_times["enable"] = self.now()
        if not msg.data:
            self.await_disable = False

    def state_callback(self, name):
        def callback(msg):
            self.states[name] = msg.data
            self.state_times[name] = self.now()
        return callback

    def healthy(self):
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
        return states_fresh and command_fresh and not self.await_disable

    def publish_safe_command(self):
        output = Twist()
        if self.healthy():
            self.armed = True
            max_x = self.get_parameter("max_linear_x").value
            max_z = self.get_parameter("max_angular_z").value
            output.linear.x = max(-max_x, min(max_x, self.command.linear.x))
            output.angular.z = max(-max_z, min(max_z, self.command.angular.z))
        else:
            self.armed = False
        self.publisher.publish(output)


def main():
    rclpy.init()
    node = VelocityGate()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
