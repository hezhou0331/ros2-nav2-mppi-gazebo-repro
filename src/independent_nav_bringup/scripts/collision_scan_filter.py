#!/usr/bin/python3
"""Remove scan returns that are physically inside the simulated robot body."""

import math

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import LaserScan


DEFAULT_FOOTPRINT_RADIUS_M = 0.60
DEFAULT_SENSOR_OFFSET_X_M = 0.33767
DEFAULT_SENSOR_OFFSET_Y_M = 0.0


def filter_ranges(
    ranges,
    angle_min,
    angle_increment,
    footprint_radius_m,
    sensor_offset_x_m,
    sensor_offset_y_m,
):
    """Replace returns whose endpoints fall inside the base-frame footprint."""
    filtered = []
    for index, value in enumerate(ranges):
        if not math.isfinite(value):
            filtered.append(value)
            continue
        angle = angle_min + index * angle_increment
        base_x = sensor_offset_x_m + value * math.cos(angle)
        base_y = sensor_offset_y_m + value * math.sin(angle)
        filtered.append(
            math.inf
            if math.hypot(base_x, base_y) <= footprint_radius_m
            else value
        )
    return filtered


class CollisionScanFilter(Node):
    def __init__(self):
        super().__init__("collision_scan_filter")
        defaults = {
            "footprint_radius_m": DEFAULT_FOOTPRINT_RADIUS_M,
            "sensor_offset_x_m": DEFAULT_SENSOR_OFFSET_X_M,
            "sensor_offset_y_m": DEFAULT_SENSOR_OFFSET_Y_M,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)
        self.footprint_radius_m = float(
            self.get_parameter("footprint_radius_m").value
        )
        self.sensor_offset_x_m = float(
            self.get_parameter("sensor_offset_x_m").value
        )
        self.sensor_offset_y_m = float(
            self.get_parameter("sensor_offset_y_m").value
        )
        if not math.isfinite(self.footprint_radius_m) or self.footprint_radius_m <= 0.0:
            raise ValueError("footprint_radius_m must be finite and greater than zero")
        if not all(
            math.isfinite(value)
            for value in (self.sensor_offset_x_m, self.sensor_offset_y_m)
        ):
            raise ValueError("sensor offsets must be finite")

        reliable_qos = QoSProfile(
            depth=10, reliability=QoSReliabilityPolicy.RELIABLE
        )
        self.publisher = self.create_publisher(
            LaserScan, "/collision_scan", reliable_qos
        )
        self.create_subscription(
            LaserScan, "/scan", self.scan_callback, reliable_qos
        )
        self.get_logger().info(
            "Filtering costmap and collision-monitor endpoints inside the %.2f m "
            "base-frame footprint."
            % self.footprint_radius_m
        )

    def scan_callback(self, message):
        filtered = LaserScan()
        filtered.header = message.header
        filtered.angle_min = message.angle_min
        filtered.angle_max = message.angle_max
        filtered.angle_increment = message.angle_increment
        filtered.time_increment = message.time_increment
        filtered.scan_time = message.scan_time
        filtered.range_min = message.range_min
        filtered.range_max = message.range_max
        filtered.ranges = filter_ranges(
            message.ranges,
            message.angle_min,
            message.angle_increment,
            self.footprint_radius_m,
            self.sensor_offset_x_m,
            self.sensor_offset_y_m,
        )
        filtered.intensities = message.intensities
        self.publisher.publish(filtered)


def main():
    rclpy.init()
    node = CollisionScanFilter()
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
