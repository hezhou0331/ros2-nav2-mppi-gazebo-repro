#!/usr/bin/python3
"""Simulation-only supervisor: explicitly publishes false, then enables navigation."""

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Bool


class SimulationSupervisor(Node):
    def __init__(self):
        super().__init__("simulation_supervisor")
        self.start = self.get_clock().now().nanoseconds / 1e9
        self.publisher = self.create_publisher(Bool, "/nav/enable", 10)
        self.create_timer(0.10, self.publish)

    def publish(self):
        elapsed = self.get_clock().now().nanoseconds / 1e9 - self.start
        # Keep false long enough for all launch-time DDS endpoints to discover it.
        self.publisher.publish(Bool(data=elapsed >= 5.0))


def main():
    rclpy.init()
    node = SimulationSupervisor()
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
