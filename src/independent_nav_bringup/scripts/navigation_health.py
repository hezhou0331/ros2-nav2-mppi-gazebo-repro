#!/usr/bin/python3
"""Publish /nav/healthy from live sensor freshness and static input readiness."""

import rclpy
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool


def inputs_healthy(last_seen, now, timeout, require_map):
    """Return whether live inputs are fresh and a required map was received once."""
    live_inputs_fresh = all(
        last_seen[key] is not None and now - last_seen[key] <= timeout
        for key in ("scan", "odom")
    )
    map_ready = not require_map or last_seen["map"] is not None
    return live_inputs_fresh and map_ready


def health_transition_message(
    previous_health, healthy, last_seen, now, timeout, require_map
):
    """Describe a health transition, or suppress an unchanged state."""
    if previous_health is not None and previous_health == healthy:
        return None

    def format_age(key):
        seen_at = last_seen[key]
        if seen_at is None:
            return "None"
        return f"{max(0.0, now - seen_at):.3f}s"

    return (
        f"/nav/healthy changed to {str(healthy).lower()}: "
        f"scan_age={format_age('scan')}, odom_age={format_age('odom')}, "
        f"map_received={str(last_seen['map'] is not None).lower()}, "
        f"require_map={str(require_map).lower()}, timeout={timeout:.3f}s"
    )


def map_subscription_qos():
    """Match the transient-local map publisher so late subscribers receive its map."""
    return QoSProfile(
        depth=1,
        reliability=QoSReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
    )


class NavigationHealth(Node):
    def __init__(self):
        super().__init__("navigation_health")
        self.declare_parameter("require_map", True)
        self.declare_parameter("timeout", 0.75)
        self.last_seen = {"scan": None, "odom": None, "map": None}
        self.last_published_health = None
        self.publisher = self.create_publisher(Bool, "/nav/healthy", 10)
        self.create_subscription(LaserScan, "/scan", self.mark("scan"), 10)
        self.create_subscription(Odometry, "/odom", self.mark("odom"), 10)
        self.create_subscription(
            OccupancyGrid, "/map", self.mark("map"), map_subscription_qos()
        )
        self.create_timer(0.10, self.publish)

    def mark(self, key):
        def callback(_msg):
            self.last_seen[key] = self.get_clock().now().nanoseconds / 1e9
        return callback

    def publish(self):
        now = self.get_clock().now().nanoseconds / 1e9
        timeout = self.get_parameter("timeout").value
        require_map = self.get_parameter("require_map").value
        healthy = inputs_healthy(
            self.last_seen,
            now,
            timeout,
            require_map,
        )
        transition = health_transition_message(
            self.last_published_health,
            healthy,
            self.last_seen,
            now,
            timeout,
            require_map,
        )
        if transition is not None:
            # rclpy caches severity per Python call site, so keep INFO and WARN
            # on distinct lines instead of selecting a bound method dynamically.
            if healthy:
                self.get_logger().info(transition)
            else:
                self.get_logger().warn(transition)
            self.last_published_health = healthy
        self.publisher.publish(Bool(data=healthy))


def main():
    rclpy.init()
    node = NavigationHealth()
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
