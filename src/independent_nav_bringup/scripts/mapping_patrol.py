#!/usr/bin/python3
"""Drive the simulation proxy through a deterministic mapping patrol route.

This node is intentionally limited to publishing ``/cmd_vel``.  The existing
velocity gate remains the only route to the simulated platform, so an expired
or false safety state still stops the robot outside this demonstration node.
"""

import argparse
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool


COMMAND_RATE_HZ = 20.0
WAYPOINT_TOLERANCE_M = 0.20
MAX_LINEAR_SPEED_MPS = 0.12
MAX_ANGULAR_SPEED_RADPS = 0.22
MIN_ENVIRONMENT_RANGE_M = 0.40
MIN_ENVIRONMENT_RETURNS = 3

# These coordinates are expressed in the simulation's a2/odom frame.  The
# first point is deliberately close to the practice-world spawn pose.
ROUTE = (
    (-4.9, 0.0),
    (-4.9, -1.2),
    (3.3, -1.2),
    (3.3, 1.2),
    (-4.9, 1.2),
    (-4.9, 0.0),
)


def utc_now():
    """Return an ISO-8601 UTC timestamp suitable for a machine-readable report."""
    return datetime.now(timezone.utc).isoformat()


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def normalize_angle(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def write_json(path, payload):
    """Atomically replace a report file, leaving no partial JSON on interruption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(temporary, path)


class MappingPatrol(Node):
    """Follow the fixed ATEC mapping loop while continuously checking safety state."""

    def __init__(self, args):
        super().__init__("atec_mapping_patrol")
        self.args = args
        self.output_path = Path(args.output).expanduser()
        self.started_monotonic = time.monotonic()
        self.finished = False
        self.success = False
        self.report_written = False
        self.phase = "waiting_for_readiness"
        self.waypoint_index = 0
        self.waypoint_started_monotonic = None
        self.odom = None
        self.odom_received_monotonic = None
        self.scan_received_monotonic = None
        self.valid_scan_returns = 0
        self.safety = {
            "nav_enable": {"value": False, "received_monotonic": None},
            "platform_ready": {"value": False, "received_monotonic": None},
            "nav_healthy": {"value": False, "received_monotonic": None},
        }
        self.command_publisher = self.create_publisher(Twist, "/cmd_vel", 10)
        self.create_subscription(Bool, "/nav/enable", self._safety_callback("nav_enable"), 10)
        self.create_subscription(
            Bool, "/platform/ready", self._safety_callback("platform_ready"), 10
        )
        self.create_subscription(Bool, "/nav/healthy", self._safety_callback("nav_healthy"), 10)
        self.create_subscription(Odometry, "/odom", self._odom_callback, 10)
        self.create_subscription(LaserScan, "/scan", self._scan_callback, 10)
        self.timer = self.create_timer(1.0 / COMMAND_RATE_HZ, self._tick)

        routes = [
            {"index": index + 1, "x": point[0], "y": point[1]}
            for index, point in enumerate(ROUTE)
        ]
        self.report = {
            "success": False,
            "started_at": utc_now(),
            "finished_at": None,
            "reason": None,
            "error": None,
            "phase": self.phase,
            "routes": routes,
            "waypoints_completed": 0,
            "waypoint_results": [
                {
                    "index": route["index"],
                    "target": {"x": route["x"], "y": route["y"]},
                    "status": "PENDING",
                    "started_at": None,
                    "finished_at": None,
                    "final_distance_m": None,
                }
                for route in routes
            ],
            "parameters": {
                "command_rate_hz": COMMAND_RATE_HZ,
                "waypoint_tolerance_m": WAYPOINT_TOLERANCE_M,
                "max_linear_speed_mps": MAX_LINEAR_SPEED_MPS,
                "max_angular_speed_radps": MAX_ANGULAR_SPEED_RADPS,
                "timeout_s": args.timeout,
                "ready_timeout_s": args.ready_timeout,
                "waypoint_timeout_s": args.waypoint_timeout,
                "state_timeout_s": args.state_timeout,
                "odom_timeout_s": args.odom_timeout,
                "scan_timeout_s": args.scan_timeout,
                "minimum_environment_range_m": MIN_ENVIRONMENT_RANGE_M,
                "minimum_environment_returns": MIN_ENVIRONMENT_RETURNS,
            },
        }
        self.get_logger().info(
            "Waiting for safety state, /odom, and valid environment returns on /scan."
        )

    def _safety_callback(self, name):
        def callback(message):
            self.safety[name]["value"] = bool(message.data)
            self.safety[name]["received_monotonic"] = time.monotonic()

        return callback

    def _odom_callback(self, message):
        position = message.pose.pose.position
        orientation = message.pose.pose.orientation
        values = (position.x, position.y, orientation.x, orientation.y, orientation.z, orientation.w)
        if not all(math.isfinite(value) for value in values):
            self.get_logger().warn("Ignoring /odom message with non-finite pose values.")
            return
        self.odom = message
        self.odom_received_monotonic = time.monotonic()

    def _scan_callback(self, message):
        lower_bound = max(MIN_ENVIRONMENT_RANGE_M, float(message.range_min))
        upper_bound = float(message.range_max)
        # pointcloud_to_laserscan emits range_max for empty rays so SLAM can
        # clear sparse open space. Do not count those synthetic rays as echoes.
        environment_upper_bound = upper_bound - 0.05
        self.valid_scan_returns = sum(
            1
            for value in message.ranges
            if math.isfinite(value) and lower_bound <= value < environment_upper_bound
        )
        self.scan_received_monotonic = time.monotonic()

    def _readiness_issues(self, now):
        issues = []
        topic_names = {
            "nav_enable": "/nav/enable",
            "platform_ready": "/platform/ready",
            "nav_healthy": "/nav/healthy",
        }
        for name, state in self.safety.items():
            received = state["received_monotonic"]
            if received is None:
                issues.append(f"no message on {topic_names[name]}")
            elif now - received > self.args.state_timeout:
                issues.append(f"stale {topic_names[name]}")
            elif not state["value"]:
                issues.append(f"{topic_names[name]} is false")
        if self.odom is None or self.odom_received_monotonic is None:
            issues.append("no message on /odom")
        elif now - self.odom_received_monotonic > self.args.odom_timeout:
            issues.append("stale /odom")
        if self.scan_received_monotonic is None:
            issues.append("no message on /scan")
        elif now - self.scan_received_monotonic > self.args.scan_timeout:
            issues.append("stale /scan")
        elif self.valid_scan_returns < MIN_ENVIRONMENT_RETURNS:
            issues.append(
                f"/scan has {self.valid_scan_returns} finite returns at or beyond "
                f"{MIN_ENVIRONMENT_RANGE_M:.2f} m; need {MIN_ENVIRONMENT_RETURNS}"
            )
        return issues

    def _readiness_snapshot(self, now):
        snapshot = {}
        for name, state in self.safety.items():
            received = state["received_monotonic"]
            snapshot[name] = {
                "value": state["value"],
                "age_s": None if received is None else round(max(0.0, now - received), 3),
            }
        snapshot["odom"] = {
            "received": self.odom is not None,
            "age_s": (
                None
                if self.odom_received_monotonic is None
                else round(max(0.0, now - self.odom_received_monotonic), 3)
            ),
        }
        snapshot["environment_scan"] = {
            "received": self.scan_received_monotonic is not None,
            "age_s": (
                None
                if self.scan_received_monotonic is None
                else round(max(0.0, now - self.scan_received_monotonic), 3)
            ),
            "minimum_range_m": MIN_ENVIRONMENT_RANGE_M,
            "minimum_returns": MIN_ENVIRONMENT_RETURNS,
            "valid_returns": self.valid_scan_returns,
            "valid": (
                self.scan_received_monotonic is not None
                and now - self.scan_received_monotonic <= self.args.scan_timeout
                and self.valid_scan_returns >= MIN_ENVIRONMENT_RETURNS
            ),
        }
        return snapshot

    def _current_pose(self):
        position = self.odom.pose.pose.position
        orientation = self.odom.pose.pose.orientation
        sin_yaw = 2.0 * (orientation.w * orientation.z + orientation.x * orientation.y)
        cos_yaw = 1.0 - 2.0 * (orientation.y * orientation.y + orientation.z * orientation.z)
        return position.x, position.y, math.atan2(sin_yaw, cos_yaw)

    def _publish_stop(self):
        self.command_publisher.publish(Twist())

    def _start_waypoint(self, now):
        result = self.report["waypoint_results"][self.waypoint_index]
        result["status"] = "RUNNING"
        result["started_at"] = utc_now()
        self.waypoint_started_monotonic = now
        target = result["target"]
        self.get_logger().info(
            f"Starting patrol waypoint {result['index']}/{len(ROUTE)}: "
            f"({target['x']:.2f}, {target['y']:.2f})"
        )

    def _complete_waypoint(self, distance):
        result = self.report["waypoint_results"][self.waypoint_index]
        result["status"] = "SUCCEEDED"
        result["finished_at"] = utc_now()
        result["final_distance_m"] = round(distance, 4)
        self.report["waypoints_completed"] = self.waypoint_index + 1
        self.get_logger().info(
            f"Completed patrol waypoint {result['index']}/{len(ROUTE)} "
            f"with {distance:.3f} m position error."
        )

    def _finish(self, success, reason):
        if self.finished:
            return
        if not success and self.phase == "patrolling":
            current = self.report["waypoint_results"][self.waypoint_index]
            if current["status"] == "RUNNING":
                current["status"] = "FAILED"
                current["finished_at"] = utc_now()
        self.finished = True
        self.success = bool(success)
        self.phase = "completed" if success else "failed"
        self.report["success"] = self.success
        self.report["phase"] = self.phase
        self.report["reason"] = reason
        self.report["error"] = None if success else reason
        self.report["finished_at"] = utc_now()
        self.report["readiness"] = self._readiness_snapshot(time.monotonic())
        self._publish_stop()
        log = self.get_logger().info if success else self.get_logger().error
        log(f"Mapping patrol {'completed' if success else 'failed'}: {reason}")

    def _tick(self):
        if self.finished:
            self._publish_stop()
            return

        now = time.monotonic()
        if now - self.started_monotonic > self.args.timeout:
            self._finish(False, f"overall timeout after {self.args.timeout:.1f} seconds")
            return

        readiness_issues = self._readiness_issues(now)
        if self.phase == "waiting_for_readiness":
            self._publish_stop()
            if not readiness_issues:
                self.phase = "patrolling"
                self.report["phase"] = self.phase
                self.report["patrol_started_at"] = utc_now()
                self._start_waypoint(now)
                return
            if now - self.started_monotonic > self.args.ready_timeout:
                self._finish(
                    False,
                    "readiness timeout: " + "; ".join(readiness_issues),
                )
            return

        if readiness_issues:
            self._finish(False, "safety readiness lost during patrol: " + "; ".join(readiness_issues))
            return

        if now - self.waypoint_started_monotonic > self.args.waypoint_timeout:
            result = self.report["waypoint_results"][self.waypoint_index]
            result["status"] = "TIMED_OUT"
            result["finished_at"] = utc_now()
            self._finish(
                False,
                f"waypoint {result['index']} exceeded {self.args.waypoint_timeout:.1f} seconds",
            )
            return

        x, y, yaw = self._current_pose()
        target_x, target_y = ROUTE[self.waypoint_index]
        delta_x = target_x - x
        delta_y = target_y - y
        distance = math.hypot(delta_x, delta_y)
        if distance <= WAYPOINT_TOLERANCE_M:
            self._publish_stop()
            self._complete_waypoint(distance)
            if self.waypoint_index == len(ROUTE) - 1:
                self._finish(True, "completed all mapping patrol waypoints")
                return
            self.waypoint_index += 1
            self._start_waypoint(now)
            return

        desired_heading = math.atan2(delta_y, delta_x)
        heading_error = normalize_angle(desired_heading - yaw)
        command = Twist()
        command.angular.z = clamp(1.6 * heading_error, -MAX_ANGULAR_SPEED_RADPS, MAX_ANGULAR_SPEED_RADPS)
        # Rotate in place for large errors.  Otherwise slow down as the target is
        # approached so the fixed 0.20 m tolerance is not overshot.
        if abs(heading_error) <= 0.35:
            command.linear.x = min(MAX_LINEAR_SPEED_MPS, max(0.04, 0.40 * distance))
        self.command_publisher.publish(command)

    def publish_stop_burst(self):
        """Give the velocity gate several fresh zero commands before process exit."""
        for _ in range(3):
            self._publish_stop()
            time.sleep(1.0 / COMMAND_RATE_HZ)

    def write_report(self):
        try:
            write_json(self.output_path, self.report)
            self.report_written = True
            self.get_logger().info(f"Wrote patrol report to {self.output_path}")
        except OSError as error:
            self.report_written = False
            self.get_logger().error(f"Unable to write patrol report {self.output_path}: {error}")


def positive_float(value):
    number = float(value)
    if number <= 0.0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Path for the patrol JSON report.")
    parser.add_argument("--timeout", type=positive_float, default=420.0, help="Overall wall-time limit.")
    parser.add_argument(
        "--ready-timeout",
        type=positive_float,
        default=90.0,
        help="Wall-time limit for safety state and odometry discovery.",
    )
    parser.add_argument(
        "--waypoint-timeout",
        type=positive_float,
        default=120.0,
        help="Wall-time limit for each patrol waypoint.",
    )
    parser.add_argument(
        "--state-timeout",
        type=positive_float,
        default=0.75,
        help="Maximum accepted age of each safety Bool message.",
    )
    parser.add_argument(
        "--odom-timeout",
        type=positive_float,
        default=0.75,
        help="Maximum accepted age of an odometry message.",
    )
    parser.add_argument(
        "--scan-timeout",
        type=positive_float,
        default=0.75,
        help="Maximum accepted age of an environment LaserScan message.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    rclpy.init()
    node = MappingPatrol(args)
    try:
        while rclpy.ok() and not node.finished:
            rclpy.spin_once(node, timeout_sec=0.1)
        if not node.finished:
            node._finish(False, "ROS shutdown before patrol completion")
    except KeyboardInterrupt:
        node._finish(False, "interrupted by operator")
    except Exception as error:  # Keep a usable JSON report for orchestration failures.
        node._finish(False, f"unhandled exception: {type(error).__name__}: {error}")
        node.get_logger().error(node.report["error"])
    finally:
        node.publish_stop_burst()
        node.write_report()
        succeeded = node.success and node.report_written
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
