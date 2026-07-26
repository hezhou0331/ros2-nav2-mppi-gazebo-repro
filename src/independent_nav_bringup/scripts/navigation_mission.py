#!/usr/bin/python3
"""Execute the fixed two-goal Nav2 demonstration mission and write a JSON report."""

import argparse
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseWithCovarianceStamped
from lifecycle_msgs.msg import State
from lifecycle_msgs.srv import GetState
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.time import Time
from std_msgs.msg import Bool
from tf2_ros import Buffer, TransformException, TransformListener


GOAL_TOLERANCE_M = 0.35
AMCL_STATE_SERVICE = "/amcl/get_state"
BT_NAVIGATOR_STATE_SERVICE = "/bt_navigator/get_state"
LIFECYCLE_STATE_QUERY_INTERVAL_S = 0.5
GOALS = (
    (-2.5, -0.5, 0.0),
    (2.5, 0.7, 0.0),
)
STATUS_NAMES = {
    GoalStatus.STATUS_UNKNOWN: "UNKNOWN",
    GoalStatus.STATUS_ACCEPTED: "ACCEPTED",
    GoalStatus.STATUS_EXECUTING: "EXECUTING",
    GoalStatus.STATUS_CANCELING: "CANCELING",
    GoalStatus.STATUS_SUCCEEDED: "SUCCEEDED",
    GoalStatus.STATUS_CANCELED: "CANCELED",
    GoalStatus.STATUS_ABORTED: "ABORTED",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, payload):
    """Atomically replace a report file, leaving no partial JSON on interruption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(temporary, path)


class NavigationMission(Node):
    """Wait for Nav2 lifecycle and safety readiness, then execute two goals."""

    def __init__(self, args):
        super().__init__("atec_navigation_mission")
        self.args = args
        self.output_path = Path(args.output).expanduser()
        self.started_monotonic = time.monotonic()
        self.finished = False
        self.success = False
        self.report_written = False
        self.phase = "waiting_for_readiness"
        self.current_goal_index = 0
        self.goal_started_monotonic = None
        self.verify_started_monotonic = None
        self.goal_handle = None
        self.send_goal_future = None
        self.result_future = None
        self.cancel_future = None
        self.cancel_pending = False
        self.amcl_received_monotonic = None
        self.amcl_state_id = None
        self.amcl_state_label = None
        self.amcl_state_error = None
        self.amcl_state_future = None
        self.amcl_state_query_monotonic = None
        self.bt_navigator_state_id = None
        self.bt_navigator_state_label = None
        self.bt_navigator_state_error = None
        self.bt_navigator_state_future = None
        self.bt_navigator_state_query_monotonic = None
        self.last_transform_error = None
        self.safety = {
            "nav_enable": {"value": False, "received_monotonic": None},
            "platform_ready": {"value": False, "received_monotonic": None},
            "nav_healthy": {"value": False, "received_monotonic": None},
        }

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self, spin_thread=False)
        self.action_client = ActionClient(self, NavigateToPose, args.action_name)
        self.amcl_state_client = self.create_client(GetState, AMCL_STATE_SERVICE)
        self.bt_navigator_state_client = self.create_client(
            GetState, BT_NAVIGATOR_STATE_SERVICE
        )
        self.create_subscription(Bool, "/nav/enable", self._safety_callback("nav_enable"), 10)
        self.create_subscription(
            Bool, "/platform/ready", self._safety_callback("platform_ready"), 10
        )
        self.create_subscription(Bool, "/nav/healthy", self._safety_callback("nav_healthy"), 10)
        self.create_subscription(PoseWithCovarianceStamped, "/amcl_pose", self._amcl_callback, 10)
        self.timer = self.create_timer(0.05, self._tick)

        self.report = {
            "success": False,
            "started_at": utc_now(),
            "finished_at": None,
            "reason": None,
            "error": None,
            "phase": self.phase,
            "action_name": args.action_name,
            "goals": [
                {
                    "index": index + 1,
                    "target": {"frame_id": "map", "x": x, "y": y, "yaw": yaw},
                    "status": "PENDING",
                    "status_code": None,
                    "accepted": None,
                    "started_at": None,
                    "finished_at": None,
                    "final_distance_m": None,
                    "final_error_m": None,
                    "distance_error_m": None,
                    "final_pose": None,
                }
                for index, (x, y, yaw) in enumerate(GOALS)
            ],
            "parameters": {
                "goal_tolerance_m": GOAL_TOLERANCE_M,
                "timeout_s": args.timeout,
                "ready_timeout_s": args.ready_timeout,
                "goal_timeout_s": args.goal_timeout,
                "final_pose_timeout_s": args.final_pose_timeout,
                "state_timeout_s": args.state_timeout,
                "amcl_readiness_service": AMCL_STATE_SERVICE,
                "amcl_required_state": "PRIMARY_STATE_ACTIVE",
                "bt_navigator_readiness_service": BT_NAVIGATOR_STATE_SERVICE,
                "bt_navigator_required_state": "PRIMARY_STATE_ACTIVE",
            },
        }
        self.get_logger().info(
            "Waiting for safety state, AMCL and BT Navigator lifecycle ACTIVE, "
            "map->base_link TF, and Nav2 action server."
        )

    def _safety_callback(self, name):
        def callback(message):
            self.safety[name]["value"] = bool(message.data)
            self.safety[name]["received_monotonic"] = time.monotonic()

        return callback

    def _amcl_callback(self, _message):
        self.amcl_received_monotonic = time.monotonic()

    def _amcl_state_callback(self, future):
        try:
            response = future.result()
        except Exception as error:
            self.amcl_state_error = f"{type(error).__name__}: {error}"
            self.amcl_state_future = None
            return
        self.amcl_state_id = int(response.current_state.id)
        self.amcl_state_label = response.current_state.label
        self.amcl_state_error = None
        self.amcl_state_future = None

    def _request_amcl_state(self, now):
        if self.amcl_state_id == State.PRIMARY_STATE_ACTIVE:
            return
        if self.amcl_state_future is not None and not self.amcl_state_future.done():
            return
        if (
            self.amcl_state_query_monotonic is not None
            and now - self.amcl_state_query_monotonic < LIFECYCLE_STATE_QUERY_INTERVAL_S
        ):
            return
        if not self.amcl_state_client.service_is_ready():
            return
        self.amcl_state_query_monotonic = now
        self.amcl_state_future = self.amcl_state_client.call_async(GetState.Request())
        self.amcl_state_future.add_done_callback(self._amcl_state_callback)

    def _bt_navigator_state_callback(self, future):
        try:
            response = future.result()
        except Exception as error:
            self.bt_navigator_state_error = f"{type(error).__name__}: {error}"
            self.bt_navigator_state_future = None
            return
        self.bt_navigator_state_id = int(response.current_state.id)
        self.bt_navigator_state_label = response.current_state.label
        self.bt_navigator_state_error = None
        self.bt_navigator_state_future = None

    def _request_bt_navigator_state(self, now):
        if self.bt_navigator_state_id == State.PRIMARY_STATE_ACTIVE:
            return
        if (
            self.bt_navigator_state_future is not None
            and not self.bt_navigator_state_future.done()
        ):
            return
        if (
            self.bt_navigator_state_query_monotonic is not None
            and now - self.bt_navigator_state_query_monotonic
            < LIFECYCLE_STATE_QUERY_INTERVAL_S
        ):
            return
        if not self.bt_navigator_state_client.service_is_ready():
            return
        self.bt_navigator_state_query_monotonic = now
        self.bt_navigator_state_future = self.bt_navigator_state_client.call_async(
            GetState.Request()
        )
        self.bt_navigator_state_future.add_done_callback(
            self._bt_navigator_state_callback
        )

    def _map_to_base_pose(self):
        try:
            transform = self.tf_buffer.lookup_transform(
                "map", "base_link", Time(), timeout=Duration(seconds=0.0)
            )
        except TransformException as error:
            self.last_transform_error = str(error)
            return None
        translation = transform.transform.translation
        if not all(math.isfinite(value) for value in (translation.x, translation.y)):
            self.last_transform_error = "map->base_link transform contains non-finite translation"
            return None
        self.last_transform_error = None
        return translation.x, translation.y

    def _readiness_issues(self, now):
        self._request_amcl_state(now)
        self._request_bt_navigator_state(now)
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
        if self.amcl_state_id != State.PRIMARY_STATE_ACTIVE:
            if not self.amcl_state_client.service_is_ready():
                issues.append(f"service {AMCL_STATE_SERVICE} unavailable")
            elif self.amcl_state_error:
                issues.append(f"AMCL lifecycle query failed: {self.amcl_state_error}")
            elif self.amcl_state_id is None:
                issues.append(f"waiting for {AMCL_STATE_SERVICE} response")
            else:
                label = self.amcl_state_label or "unknown"
                issues.append(
                    f"AMCL lifecycle state is {label} ({self.amcl_state_id}), expected ACTIVE"
                )
        if self.bt_navigator_state_id != State.PRIMARY_STATE_ACTIVE:
            if not self.bt_navigator_state_client.service_is_ready():
                issues.append(f"service {BT_NAVIGATOR_STATE_SERVICE} unavailable")
            elif self.bt_navigator_state_error:
                issues.append(
                    f"BT Navigator lifecycle query failed: {self.bt_navigator_state_error}"
                )
            elif self.bt_navigator_state_id is None:
                issues.append(f"waiting for {BT_NAVIGATOR_STATE_SERVICE} response")
            else:
                label = self.bt_navigator_state_label or "unknown"
                issues.append(
                    "BT Navigator lifecycle state is "
                    f"{label} ({self.bt_navigator_state_id}), expected ACTIVE"
                )
        if self._map_to_base_pose() is None:
            detail = f": {self.last_transform_error}" if self.last_transform_error else ""
            issues.append("map->base_link transform unavailable" + detail)
        if not self.action_client.server_is_ready():
            issues.append(f"action server {self.args.action_name} unavailable")
        return issues

    def _safety_issues(self, now):
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
        return issues

    def _readiness_snapshot(self, now):
        snapshot = {}
        for name, state in self.safety.items():
            received = state["received_monotonic"]
            snapshot[name] = {
                "value": state["value"],
                "age_s": None if received is None else round(max(0.0, now - received), 3),
            }
        snapshot["amcl_lifecycle"] = {
            "service": AMCL_STATE_SERVICE,
            "service_ready": self.amcl_state_client.service_is_ready(),
            "state_id": self.amcl_state_id,
            "state_label": self.amcl_state_label,
            "active": self.amcl_state_id == State.PRIMARY_STATE_ACTIVE,
            "error": self.amcl_state_error,
        }
        snapshot["bt_navigator_lifecycle"] = {
            "service": BT_NAVIGATOR_STATE_SERVICE,
            "service_ready": self.bt_navigator_state_client.service_is_ready(),
            "state_id": self.bt_navigator_state_id,
            "state_label": self.bt_navigator_state_label,
            "active": self.bt_navigator_state_id == State.PRIMARY_STATE_ACTIVE,
            "error": self.bt_navigator_state_error,
        }
        snapshot["amcl_pose"] = {
            "received": self.amcl_received_monotonic is not None,
            "received_age_s": (
                None
                if self.amcl_received_monotonic is None
                else round(max(0.0, now - self.amcl_received_monotonic), 3)
            ),
            "diagnostic_only": True,
            "required_for_readiness": False,
        }
        pose = self._map_to_base_pose()
        snapshot["map_to_base_link"] = {
            "available": pose is not None,
            "error": self.last_transform_error,
        }
        snapshot["action_server_ready"] = self.action_client.server_is_ready()
        return snapshot

    def _goal_message(self, target):
        goal = NavigateToPose.Goal()
        # Leave the stamp at zero so Nav2 uses the latest map-frame transform;
        # this node deliberately uses wall time while Gazebo uses simulated time.
        goal.pose.header.frame_id = "map"
        goal.pose.pose.position.x = target["x"]
        goal.pose.pose.position.y = target["y"]
        goal.pose.pose.orientation.z = math.sin(target["yaw"] / 2.0)
        goal.pose.pose.orientation.w = math.cos(target["yaw"] / 2.0)
        return goal

    def _send_current_goal(self, now):
        result = self.report["goals"][self.current_goal_index]
        result["status"] = "SENDING"
        result["started_at"] = utc_now()
        self.goal_started_monotonic = now
        self.phase = "awaiting_goal_response"
        target = result["target"]
        self.get_logger().info(
            f"Sending Nav2 goal {result['index']}/{len(GOALS)}: "
            f"map ({target['x']:.2f}, {target['y']:.2f}, yaw {target['yaw']:.2f})"
        )
        self.send_goal_future = self.action_client.send_goal_async(self._goal_message(target))
        self.send_goal_future.add_done_callback(self._goal_response_callback)

    def _goal_response_callback(self, future):
        if self.finished:
            return
        result = self.report["goals"][self.current_goal_index]
        try:
            goal_handle = future.result()
        except Exception as error:
            result["status"] = "SEND_FAILED"
            result["finished_at"] = utc_now()
            self._finish(False, f"failed to send goal {result['index']}: {type(error).__name__}: {error}")
            return
        if not goal_handle.accepted:
            result["accepted"] = False
            result["status"] = "REJECTED"
            result["finished_at"] = utc_now()
            self._finish(False, f"Nav2 rejected goal {result['index']}")
            return
        self.goal_handle = goal_handle
        result["accepted"] = True
        result["status"] = "EXECUTING"
        self.phase = "awaiting_result"
        self.result_future = goal_handle.get_result_async()
        self.result_future.add_done_callback(self._goal_result_callback)

    def _goal_result_callback(self, future):
        if self.finished:
            return
        result = self.report["goals"][self.current_goal_index]
        try:
            wrapped_result = future.result()
        except Exception as error:
            result["status"] = "RESULT_FAILED"
            result["finished_at"] = utc_now()
            self._finish(False, f"failed to receive result for goal {result['index']}: {type(error).__name__}: {error}")
            return

        status_code = int(wrapped_result.status)
        status_name = STATUS_NAMES.get(status_code, f"UNKNOWN_{status_code}")
        result["status_code"] = status_code
        result["action_status"] = status_name
        if status_code != GoalStatus.STATUS_SUCCEEDED:
            result["status"] = status_name
            result["finished_at"] = utc_now()
            details = []
            action_result = wrapped_result.result
            if hasattr(action_result, "error_code"):
                details.append(f"error_code={action_result.error_code}")
            if hasattr(action_result, "error_msg") and action_result.error_msg:
                details.append(f"error_msg={action_result.error_msg}")
            suffix = "" if not details else " (" + ", ".join(details) + ")"
            self._finish(False, f"Nav2 goal {result['index']} returned {status_name}{suffix}")
            return

        result["status"] = "VERIFYING_FINAL_DISTANCE"
        self.phase = "verifying_final_distance"
        self.verify_started_monotonic = time.monotonic()
        self.get_logger().info(
            f"Nav2 goal {result['index']} reported SUCCEEDED; verifying final map-frame distance."
        )

    def _verify_goal_distance(self, now):
        result = self.report["goals"][self.current_goal_index]
        pose = self._map_to_base_pose()
        if pose is None:
            if now - self.verify_started_monotonic > self.args.final_pose_timeout:
                result["status"] = "FINAL_POSE_UNAVAILABLE"
                result["finished_at"] = utc_now()
                self._finish(
                    False,
                    f"no map->base_link transform to verify goal {result['index']} within "
                    f"{self.args.final_pose_timeout:.1f} seconds",
                )
            return

        target = result["target"]
        distance = math.hypot(target["x"] - pose[0], target["y"] - pose[1])
        result["final_pose"] = {"frame_id": "map", "x": round(pose[0], 4), "y": round(pose[1], 4)}
        result["final_distance_m"] = round(distance, 4)
        # Preserve the user-facing distance name and aliases consumed by the
        # end-to-end artifact validator.
        result["final_error_m"] = result["final_distance_m"]
        result["distance_error_m"] = result["final_distance_m"]
        result["finished_at"] = utc_now()
        if distance > GOAL_TOLERANCE_M:
            result["status"] = "DISTANCE_TOLERANCE_FAILED"
            self._finish(
                False,
                f"goal {result['index']} final distance {distance:.3f} m exceeds "
                f"{GOAL_TOLERANCE_M:.2f} m",
            )
            return

        result["status"] = "SUCCEEDED"
        self.get_logger().info(
            f"Completed Nav2 goal {result['index']}/{len(GOALS)} with "
            f"{distance:.3f} m final position error."
        )
        self.current_goal_index += 1
        self.goal_handle = None
        self.result_future = None
        if self.current_goal_index == len(GOALS):
            self._finish(True, "completed both Nav2 demonstration goals")
            return
        self.phase = "dispatching_goal"

    def _request_cancel(self, goal_handle):
        self.cancel_pending = True
        if self.cancel_future is not None:
            return
        try:
            self.cancel_future = goal_handle.cancel_goal_async()
            self.get_logger().warn("Requested cancellation of active Nav2 goal.")
        except Exception as error:
            self.get_logger().error(f"Unable to cancel active Nav2 goal: {error}")

    def _cancel_late_accepted_goal(self, future):
        """Cancel a goal accepted after the mission has already failed."""
        try:
            goal_handle = future.result()
        except Exception:
            return
        if goal_handle.accepted:
            self._request_cancel(goal_handle)

    def _cancel_active_goal(self):
        self.cancel_pending = True
        if self.goal_handle is not None:
            self._request_cancel(self.goal_handle)
            return
        if self.send_goal_future is not None:
            self.send_goal_future.add_done_callback(self._cancel_late_accepted_goal)

    def wait_for_cancel(self):
        """Keep the client alive briefly so a cancellation request reaches Nav2."""
        if not self.cancel_pending:
            return
        deadline = time.monotonic() + 0.5
        while rclpy.ok() and time.monotonic() < deadline:
            if self.cancel_future is not None and self.cancel_future.done():
                return
            rclpy.spin_once(self, timeout_sec=0.05)

    def _finish(self, success, reason):
        if self.finished:
            return
        if not success and self.phase in {"awaiting_goal_response", "awaiting_result"}:
            self._cancel_active_goal()
        self.finished = True
        self.success = bool(success)
        self.phase = "completed" if success else "failed"
        self.report["success"] = self.success
        self.report["phase"] = self.phase
        self.report["reason"] = reason
        self.report["error"] = None if success else reason
        self.report["finished_at"] = utc_now()
        self.report["readiness"] = self._readiness_snapshot(time.monotonic())
        log = self.get_logger().info if success else self.get_logger().error
        log(f"Navigation mission {'completed' if success else 'failed'}: {reason}")

    def _tick(self):
        if self.finished:
            return

        now = time.monotonic()
        if now - self.started_monotonic > self.args.timeout:
            self._finish(False, f"overall timeout after {self.args.timeout:.1f} seconds")
            return

        if self.phase == "waiting_for_readiness":
            issues = self._readiness_issues(now)
            if not issues:
                self.phase = "dispatching_goal"
                self.report["phase"] = self.phase
                self.report["mission_started_at"] = utc_now()
                self.get_logger().info("Navigation readiness checks passed.")
                return
            if now - self.started_monotonic > self.args.ready_timeout:
                self._finish(False, "readiness timeout: " + "; ".join(issues))
            return

        safety_issues = self._safety_issues(now)
        if safety_issues:
            active = self.report["goals"][self.current_goal_index]
            if active["status"] in {"SENDING", "EXECUTING"}:
                active["status"] = "SAFETY_ABORTED"
                active["finished_at"] = utc_now()
            self._finish(False, "safety readiness lost during navigation: " + "; ".join(safety_issues))
            return

        if self.phase == "dispatching_goal":
            self._send_current_goal(now)
            return

        if self.phase in {"awaiting_goal_response", "awaiting_result"}:
            if now - self.goal_started_monotonic > self.args.goal_timeout:
                result = self.report["goals"][self.current_goal_index]
                result["status"] = "TIMED_OUT"
                result["finished_at"] = utc_now()
                self._finish(
                    False,
                    f"goal {result['index']} exceeded {self.args.goal_timeout:.1f} seconds",
                )
            return

        if self.phase == "verifying_final_distance":
            self._verify_goal_distance(now)

    def write_report(self):
        try:
            write_json(self.output_path, self.report)
            self.report_written = True
            self.get_logger().info(f"Wrote navigation report to {self.output_path}")
        except OSError as error:
            self.report_written = False
            self.get_logger().error(f"Unable to write navigation report {self.output_path}: {error}")


def positive_float(value):
    number = float(value)
    if number <= 0.0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Path for the navigation JSON report.")
    parser.add_argument("--action-name", default="/navigate_to_pose")
    parser.add_argument("--timeout", type=positive_float, default=420.0, help="Overall wall-time limit.")
    parser.add_argument(
        "--ready-timeout",
        type=positive_float,
        default=120.0,
        help=(
            "Wall-time limit for AMCL/BT Navigator ACTIVE, current TF, safety state, "
            "and Nav2 discovery."
        ),
    )
    parser.add_argument(
        "--goal-timeout",
        type=positive_float,
        default=180.0,
        help="Wall-time limit for each NavigateToPose goal.",
    )
    parser.add_argument(
        "--final-pose-timeout",
        type=positive_float,
        default=5.0,
        help="Wall-time limit for final map->base_link verification.",
    )
    parser.add_argument(
        "--state-timeout",
        type=positive_float,
        default=0.75,
        help="Maximum accepted age of each safety Bool message.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    rclpy.init()
    node = NavigationMission(args)
    try:
        while rclpy.ok() and not node.finished:
            rclpy.spin_once(node, timeout_sec=0.1)
        if not node.finished:
            node._finish(False, "ROS shutdown before navigation completion")
    except KeyboardInterrupt:
        node._finish(False, "interrupted by operator")
    except Exception as error:  # Keep a usable JSON report for orchestration failures.
        node._finish(False, f"unhandled exception: {type(error).__name__}: {error}")
        node.get_logger().error(node.report["error"])
    finally:
        if not node.success:
            node.wait_for_cancel()
        node.write_report()
        succeeded = node.success and node.report_written
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
