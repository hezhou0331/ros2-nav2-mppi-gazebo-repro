#!/usr/bin/python3
"""Convert the sensor-data Best Effort scan output into Nav2's Reliable input."""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import LaserScan


class ScanQosRelay(Node):
    def __init__(self):
        super().__init__("scan_qos_relay")
        sensor_qos = QoSProfile(depth=10, reliability=QoSReliabilityPolicy.BEST_EFFORT)
        reliable_qos = QoSProfile(depth=10, reliability=QoSReliabilityPolicy.RELIABLE)
        self.publisher = self.create_publisher(LaserScan, "/scan", reliable_qos)
        self.create_subscription(LaserScan, "/scan_sensor", self.publisher.publish, sensor_qos)


def main():
    rclpy.init()
    node = ScanQosRelay()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
