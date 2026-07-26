#!/usr/bin/python3
"""Unit-level checks for automation-node readiness, failure, and cancellation."""

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mapping_patrol = load_script("mapping_patrol")
navigation_health = load_script("navigation_health")
navigation_mission = load_script("navigation_mission")


class FakeLogger:
    def info(self, _message):
        pass

    def warn(self, _message):
        pass

    def error(self, _message):
        pass


class CallbackFuture:
    def __init__(self, result, done=True):
        self._result = result
        self.is_done = done
        self.callbacks = []

    def add_done_callback(self, callback):
        self.callbacks.append(callback)

    def result(self):
        return self._result

    def done(self):
        return self.is_done


class CancelFuture:
    def __init__(self, done=False):
        self.is_done = done

    def done(self):
        return self.is_done


class FakeGoalHandle:
    def __init__(self, accepted=True):
        self.accepted = accepted
        self.cancel_calls = 0
        self.cancel_future = CancelFuture()

    def cancel_goal_async(self):
        self.cancel_calls += 1
        return self.cancel_future


class FakeActionClient:
    def __init__(self, ready=True):
        self.ready = ready

    def server_is_ready(self):
        return self.ready


class FakeLifecycleClient:
    def __init__(self, ready=True, response=None):
        self.ready = ready
        self.calls = 0
        self.future = CallbackFuture(response)

    def service_is_ready(self):
        return self.ready

    def call_async(self, _request):
        self.calls += 1
        return self.future


class NavigationHealthReadinessTests(unittest.TestCase):
    def test_old_map_remains_valid_while_live_inputs_are_fresh(self):
        now = 100.0
        last_seen = {"scan": 99.8, "odom": 99.5, "map": 1.0}
        self.assertTrue(
            navigation_health.inputs_healthy(
                last_seen, now=now, timeout=0.75, require_map=True
            )
        )

    def test_live_inputs_still_expire(self):
        now = 100.0
        for stale_key in ("scan", "odom"):
            with self.subTest(stale_key=stale_key):
                last_seen = {"scan": 99.8, "odom": 99.8, "map": 1.0}
                last_seen[stale_key] = 90.0
                self.assertFalse(
                    navigation_health.inputs_healthy(
                        last_seen, now=now, timeout=0.75, require_map=True
                    )
                )

    def test_required_map_must_be_received_once(self):
        last_seen = {"scan": 99.8, "odom": 99.8, "map": None}
        self.assertFalse(
            navigation_health.inputs_healthy(
                last_seen, now=100.0, timeout=0.75, require_map=True
            )
        )
        self.assertTrue(
            navigation_health.inputs_healthy(
                last_seen, now=100.0, timeout=0.75, require_map=False
            )
        )

    def test_map_subscription_is_reliable_and_transient_local(self):
        qos = navigation_health.map_subscription_qos()
        self.assertEqual(qos.depth, 1)
        self.assertEqual(
            qos.reliability, navigation_health.QoSReliabilityPolicy.RELIABLE
        )
        self.assertEqual(
            qos.durability, navigation_health.DurabilityPolicy.TRANSIENT_LOCAL
        )


class MappingPatrolFailureTests(unittest.TestCase):
    def make_patrol(self, status):
        patrol = object.__new__(mapping_patrol.MappingPatrol)
        patrol.finished = False
        patrol.success = False
        patrol.phase = "patrolling"
        patrol.waypoint_index = 0
        patrol.report = {
            "success": False,
            "phase": "patrolling",
            "reason": None,
            "error": None,
            "finished_at": None,
            "waypoint_results": [
                {"status": status, "started_at": "start", "finished_at": None}
            ],
        }
        return patrol

    def call_finish(self, patrol):
        with (
            mock.patch.object(mapping_patrol.MappingPatrol, "_publish_stop"),
            mock.patch.object(
                mapping_patrol.MappingPatrol, "_readiness_snapshot", return_value={}
            ),
            mock.patch.object(
                mapping_patrol.MappingPatrol, "get_logger", return_value=FakeLogger()
            ),
        ):
            patrol._finish(False, "test failure")

    def test_running_waypoint_becomes_failed(self):
        patrol = self.make_patrol("RUNNING")
        self.call_finish(patrol)
        waypoint = patrol.report["waypoint_results"][0]
        self.assertEqual(waypoint["status"], "FAILED")
        self.assertIsNotNone(waypoint["finished_at"])
        self.assertFalse(patrol.report["success"])

    def test_timed_out_waypoint_remains_timed_out(self):
        patrol = self.make_patrol("TIMED_OUT")
        patrol.report["waypoint_results"][0]["finished_at"] = "timeout"
        self.call_finish(patrol)
        waypoint = patrol.report["waypoint_results"][0]
        self.assertEqual(waypoint["status"], "TIMED_OUT")
        self.assertEqual(waypoint["finished_at"], "timeout")


class NavigationCancellationTests(unittest.TestCase):
    def make_mission(self):
        mission = object.__new__(navigation_mission.NavigationMission)
        mission.goal_handle = None
        mission.send_goal_future = None
        mission.cancel_future = None
        mission.cancel_pending = False
        return mission

    def test_active_goal_is_canceled_immediately(self):
        mission = self.make_mission()
        goal_handle = FakeGoalHandle()
        mission.goal_handle = goal_handle
        with mock.patch.object(
            navigation_mission.NavigationMission, "get_logger", return_value=FakeLogger()
        ):
            mission._cancel_active_goal()
        self.assertTrue(mission.cancel_pending)
        self.assertEqual(goal_handle.cancel_calls, 1)
        self.assertIs(mission.cancel_future, goal_handle.cancel_future)

    def test_late_accepted_goal_is_canceled(self):
        mission = self.make_mission()
        goal_handle = FakeGoalHandle()
        send_future = CallbackFuture(goal_handle)
        mission.send_goal_future = send_future
        with mock.patch.object(
            navigation_mission.NavigationMission, "get_logger", return_value=FakeLogger()
        ):
            mission._cancel_active_goal()
            self.assertEqual(len(send_future.callbacks), 1)
            send_future.callbacks[0](send_future)
        self.assertTrue(mission.cancel_pending)
        self.assertEqual(goal_handle.cancel_calls, 1)
        self.assertIs(mission.cancel_future, goal_handle.cancel_future)

    def test_wait_for_cancel_spins_until_future_completes(self):
        mission = self.make_mission()
        mission.cancel_pending = True
        mission.cancel_future = CancelFuture()

        def complete_cancel(_node, timeout_sec):
            self.assertEqual(timeout_sec, 0.05)
            mission.cancel_future.is_done = True

        with (
            mock.patch.object(navigation_mission.rclpy, "ok", return_value=True),
            mock.patch.object(
                navigation_mission.rclpy, "spin_once", side_effect=complete_cancel
            ) as spin_once,
        ):
            mission.wait_for_cancel()
        spin_once.assert_called_once()


class NavigationMissionReadinessTests(unittest.TestCase):
    def make_mission(
        self,
        now,
        amcl_state,
        bt_navigator_state=navigation_mission.State.PRIMARY_STATE_ACTIVE,
    ):
        mission = object.__new__(navigation_mission.NavigationMission)
        mission.args = SimpleNamespace(state_timeout=0.75)
        mission.amcl_received_monotonic = None
        mission.amcl_state_id = amcl_state
        mission.amcl_state_label = None
        mission.amcl_state_error = None
        mission.amcl_state_future = None
        mission.amcl_state_query_monotonic = None
        mission.amcl_state_client = FakeLifecycleClient(ready=True)
        mission.bt_navigator_state_id = bt_navigator_state
        mission.bt_navigator_state_label = None
        mission.bt_navigator_state_error = None
        mission.bt_navigator_state_future = None
        mission.bt_navigator_state_query_monotonic = None
        mission.bt_navigator_state_client = FakeLifecycleClient(ready=True)
        mission.last_transform_error = None
        mission.action_client = FakeActionClient(ready=True)
        mission.safety = {
            "nav_enable": {"value": True, "received_monotonic": now - 0.1},
            "platform_ready": {"value": True, "received_monotonic": now - 0.1},
            "nav_healthy": {"value": True, "received_monotonic": now - 0.1},
        }
        return mission

    def test_active_lifecycle_state_does_not_require_amcl_pose(self):
        now = 100.0
        mission = self.make_mission(
            now, amcl_state=navigation_mission.State.PRIMARY_STATE_ACTIVE
        )
        with mock.patch.object(
            navigation_mission.NavigationMission,
            "_map_to_base_pose",
            return_value=(-5.8, 0.0),
        ):
            self.assertEqual(mission._readiness_issues(now), [])

    def test_inactive_lifecycle_state_blocks_navigation(self):
        now = 100.0
        mission = self.make_mission(
            now, amcl_state=navigation_mission.State.PRIMARY_STATE_INACTIVE
        )
        mission.amcl_state_label = "inactive"
        mission.amcl_state_query_monotonic = now
        with mock.patch.object(
            navigation_mission.NavigationMission,
            "_map_to_base_pose",
            return_value=(-5.8, 0.0),
        ):
            issues = mission._readiness_issues(now)
        self.assertTrue(any("expected ACTIVE" in issue for issue in issues))

    def test_inactive_bt_navigator_blocks_ready_action_server(self):
        now = 100.0
        mission = self.make_mission(
            now,
            amcl_state=navigation_mission.State.PRIMARY_STATE_ACTIVE,
            bt_navigator_state=navigation_mission.State.PRIMARY_STATE_INACTIVE,
        )
        mission.bt_navigator_state_label = "inactive"
        mission.bt_navigator_state_query_monotonic = now
        with mock.patch.object(
            navigation_mission.NavigationMission,
            "_map_to_base_pose",
            return_value=(-5.8, 0.0),
        ):
            issues = mission._readiness_issues(now)
        self.assertTrue(
            any("BT Navigator lifecycle state" in issue for issue in issues)
        )
        self.assertTrue(any("expected ACTIVE" in issue for issue in issues))

    def test_bt_navigator_query_records_active_response(self):
        now = 100.0
        mission = self.make_mission(
            now,
            amcl_state=navigation_mission.State.PRIMARY_STATE_ACTIVE,
            bt_navigator_state=None,
        )
        response = SimpleNamespace(
            current_state=SimpleNamespace(
                id=navigation_mission.State.PRIMARY_STATE_ACTIVE,
                label="active",
            )
        )
        mission.bt_navigator_state_client = FakeLifecycleClient(
            ready=True, response=response
        )
        mission._request_bt_navigator_state(now)
        self.assertEqual(mission.bt_navigator_state_client.calls, 1)
        future = mission.bt_navigator_state_client.future
        self.assertEqual(len(future.callbacks), 1)
        future.callbacks[0](future)
        self.assertEqual(
            mission.bt_navigator_state_id,
            navigation_mission.State.PRIMARY_STATE_ACTIVE,
        )
        self.assertEqual(mission.bt_navigator_state_label, "active")

    def test_lifecycle_query_records_active_response(self):
        now = 100.0
        mission = self.make_mission(now, amcl_state=None)
        response = SimpleNamespace(
            current_state=SimpleNamespace(
                id=navigation_mission.State.PRIMARY_STATE_ACTIVE,
                label="active",
            )
        )
        mission.amcl_state_client = FakeLifecycleClient(ready=True, response=response)
        mission._request_amcl_state(now)
        self.assertEqual(mission.amcl_state_client.calls, 1)
        future = mission.amcl_state_client.future
        self.assertEqual(len(future.callbacks), 1)
        future.callbacks[0](future)
        self.assertEqual(
            mission.amcl_state_id, navigation_mission.State.PRIMARY_STATE_ACTIVE
        )
        self.assertEqual(mission.amcl_state_label, "active")


if __name__ == "__main__":
    unittest.main()
