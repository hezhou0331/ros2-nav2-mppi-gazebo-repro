#!/usr/bin/python3
"""Gazebo-only adapter implementing the shared platform topic boundary."""

import rclpy
from geometry_msgs.msg import Twist
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Bool


class SimulationPlatformAdapter(Node):
    def __init__(self):
        super().__init__("simulation_platform_adapter")
        self.command_time = None
        self.command = Twist()
        self.output = self.create_publisher(Twist, "/sim/cmd_vel", 10)
        self.ready = self.create_publisher(Bool, "/platform/ready", 10)
        self.create_subscription(Twist, "/platform/cmd_vel", self.command_callback, 10)
        self.create_timer(0.05, self.publish)

    def command_callback(self, msg):
        self.command = msg
        self.command_time = self.get_clock().now().nanoseconds / 1e9

    def publish(self):
        now = self.get_clock().now().nanoseconds / 1e9
        safe_command = Twist()
        if self.command_time is not None and now - self.command_time <= 0.20:
            safe_command = self.command
        self.ready.publish(Bool(data=True))
        self.output.publish(safe_command)


def main():
    rclpy.init()
    node = SimulationPlatformAdapter()
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
