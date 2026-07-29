#!/usr/bin/python3
"""Unit-level checks for automation-node readiness, failure, and cancellation."""

import importlib.util
import math
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
LAUNCH_DIR = Path(__file__).resolve().parents[1] / "launch"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_launch(name):
    path = LAUNCH_DIR / f"{name}.launch.py"
    spec = importlib.util.spec_from_file_location(f"{name}_launch", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mapping_patrol = load_script("mapping_patrol")
navigation_health = load_script("navigation_health")
navigation_mission = load_script("navigation_mission")
collision_scan_filter = load_script("collision_scan_filter")
velocity_gate = load_script("velocity_gate")
hardware_control_launch = load_launch("a2_hardware_control")


class HardwareControlLaunchTests(unittest.TestCase):
    @staticmethod
    def launch_configurations(values):
        def make_configuration(name):
            return SimpleNamespace(perform=lambda _context: values[name])

        return mock.patch.object(
            hardware_control_launch,
            "LaunchConfiguration",
            side_effect=make_configuration,
        )

    def test_missing_adapter_config_fails_before_nodes_are_constructed(self):
        values = {
            "network_interface": "enp2s0",
            "adapter_config": "/missing/adapter.yaml",
        }
        with (
            self.launch_configurations(values),
            mock.patch.object(
                hardware_control_launch.os.path,
                "isfile",
                return_value=False,
            ),
            mock.patch.object(
                hardware_control_launch,
                "validate_wired_network_interface",
            ) as validate_interface,
            mock.patch.object(hardware_control_launch, "Node") as node,
        ):
            with self.assertRaisesRegex(ValueError, "adapter_config does not exist"):
                hardware_control_launch._hardware_nodes(None, Path("/adapter"))
        validate_interface.assert_not_called()
        node.assert_not_called()

    def test_invalid_network_interface_fails_before_sdk_or_nodes(self):
        values = {
            "network_interface": "lo",
            "adapter_config": "/adapter/config.yaml",
        }
        with (
            self.launch_configurations(values),
            mock.patch.object(
                hardware_control_launch.os.path,
                "isfile",
                return_value=True,
            ),
            mock.patch.object(
                hardware_control_launch,
                "validate_wired_network_interface",
                side_effect=RuntimeError("not wired"),
            ),
            mock.patch.object(
                hardware_control_launch,
                "verify_pinned_sdk2_installation",
            ) as verify_revision,
            mock.patch.object(hardware_control_launch, "Node") as node,
        ):
            with self.assertRaisesRegex(RuntimeError, "not wired"):
                hardware_control_launch._hardware_nodes(None, Path("/adapter"))
        verify_revision.assert_not_called()
        node.assert_not_called()

    def test_unverified_sdk_revision_fails_before_nodes_are_constructed(self):
        values = {
            "network_interface": "enp2s0",
            "adapter_config": "/adapter/config.yaml",
        }
        with (
            self.launch_configurations(values),
            mock.patch.object(
                hardware_control_launch.os.path,
                "isfile",
                return_value=True,
            ),
            mock.patch.object(
                hardware_control_launch,
                "validate_wired_network_interface",
            ),
            mock.patch.object(
                hardware_control_launch,
                "verify_pinned_sdk2_installation",
                side_effect=RuntimeError("wrong revision"),
            ),
            mock.patch.object(hardware_control_launch, "Node") as node,
        ):
            with self.assertRaisesRegex(RuntimeError, "wrong revision"):
                hardware_control_launch._hardware_nodes(None, Path("/adapter"))
        node.assert_not_called()

    def test_successful_preflight_constructs_only_adapter_and_velocity_gate(self):
        values = {
            "network_interface": "enp2s0",
            "adapter_config": "/adapter/config.yaml",
            "dds_domain_id": "0",
            "input_cmd_topic": "/cmd_vel",
        }
        with (
            self.launch_configurations(values),
            mock.patch.object(
                hardware_control_launch.os.path,
                "isfile",
                return_value=True,
            ),
            mock.patch.object(
                hardware_control_launch,
                "validate_wired_network_interface",
            ),
            mock.patch.object(
                hardware_control_launch,
                "verify_pinned_sdk2_installation",
            ),
            mock.patch.object(
                hardware_control_launch,
                "PythonLaunchDescriptionSource",
                return_value="adapter_source",
            ),
            mock.patch.object(
                hardware_control_launch,
                "IncludeLaunchDescription",
                return_value="adapter",
            ) as include,
            mock.patch.object(
                hardware_control_launch,
                "Node",
                return_value="velocity_gate",
            ) as node,
        ):
            actions = hardware_control_launch._hardware_nodes(
                None,
                Path("/adapter"),
            )

        self.assertEqual(actions, ["adapter", "velocity_gate"])
        include.assert_called_once()
        node.assert_called_once()
        node_kwargs = node.call_args.kwargs
        self.assertEqual(node_kwargs["package"], "independent_nav_bringup")
        self.assertEqual(node_kwargs["executable"], "velocity_gate.py")


class VelocityGateTests(unittest.TestCase):
    def make_armed_interlock(self):
        interlock = velocity_gate.RearmInterlock()
        interlock.update_enable(False)
        interlock.update_enable(True)
        self.assertTrue(interlock.evaluate(True, latch_faults=True))
        return interlock

    def test_planar_twist_requires_all_six_components_to_be_finite(self):
        command = velocity_gate.Twist()
        command.linear.x = 0.1
        command.angular.z = 0.2
        self.assertTrue(velocity_gate.is_planar_twist(command))

        fields = (
            ("linear", "x"),
            ("linear", "y"),
            ("linear", "z"),
            ("angular", "x"),
            ("angular", "y"),
            ("angular", "z"),
        )
        for vector_name, field_name in fields:
            with self.subTest(field=f"{vector_name}.{field_name}"):
                invalid = velocity_gate.Twist()
                invalid.linear.x = 0.1
                invalid.angular.z = 0.2
                setattr(getattr(invalid, vector_name), field_name, math.nan)
                self.assertFalse(velocity_gate.is_planar_twist(invalid))

    def test_planar_twist_rejects_any_nonzero_unsupported_dof(self):
        fields = (
            ("linear", "y"),
            ("linear", "z"),
            ("angular", "x"),
            ("angular", "y"),
        )
        for vector_name, field_name in fields:
            with self.subTest(field=f"{vector_name}.{field_name}"):
                command = velocity_gate.Twist()
                setattr(getattr(command, vector_name), field_name, 1.0e-12)
                self.assertFalse(velocity_gate.is_planar_twist(command))

    def test_watchdog_uses_monotonic_clock(self):
        gate = object.__new__(velocity_gate.VelocityGate)
        with mock.patch.object(velocity_gate.time, "monotonic", return_value=123.5):
            self.assertEqual(gate.now(), 123.5)

    def test_dds_receive_timestamp_preserves_executor_queue_age(self):
        received_at = velocity_gate.monotonic_receive_time(
            {"received_timestamp": 100_000_000_000},
            monotonic_now=500.0,
            wall_time_ns=100_250_000_000,
        )
        self.assertAlmostEqual(received_at, 499.75)

    def test_rearm_interlock_latches_fault_until_disable(self):
        interlock = velocity_gate.RearmInterlock()
        self.assertFalse(interlock.evaluate(True, latch_faults=True))

        interlock.update_enable(False)
        interlock.update_enable(True)
        self.assertTrue(interlock.evaluate(True, latch_faults=True))
        self.assertFalse(interlock.evaluate(False, latch_faults=True))
        self.assertTrue(interlock.fault_latched)
        self.assertFalse(interlock.evaluate(True, latch_faults=True))

        interlock.update_enable(False)
        interlock.update_enable(True)
        self.assertTrue(interlock.evaluate(True, latch_faults=True))

    def test_simulation_mode_does_not_latch_transient_fault(self):
        interlock = velocity_gate.RearmInterlock()
        interlock.update_enable(False)
        interlock.update_enable(True)
        self.assertTrue(interlock.evaluate(True, latch_faults=False))
        self.assertFalse(interlock.evaluate(False, latch_faults=False))
        self.assertTrue(interlock.evaluate(True, latch_faults=False))

    def test_invalid_command_clears_previous_command_and_latches(self):
        gate = object.__new__(velocity_gate.VelocityGate)
        gate.command = velocity_gate.Twist()
        gate.command.linear.x = 0.1
        gate.command_time = 10.0
        gate.interlock = self.make_armed_interlock()
        gate.get_parameter = mock.Mock(return_value=SimpleNamespace(value=True))

        invalid = velocity_gate.Twist()
        invalid.angular.x = 0.01
        gate.command_callback(
            invalid,
            {"received_timestamp": time.time_ns()},
        )

        self.assertIsNone(gate.command_time)
        self.assertEqual(gate.command.linear.x, 0.0)
        self.assertTrue(gate.interlock.fault_latched)
        self.assertTrue(gate.interlock.await_disable)

    def test_invalid_command_latches_after_disable_even_before_first_motion(self):
        gate = object.__new__(velocity_gate.VelocityGate)
        gate.command = velocity_gate.Twist()
        gate.command_time = None
        gate.interlock = velocity_gate.RearmInterlock()
        gate.interlock.update_enable(False)
        gate.interlock.update_enable(True)
        gate.get_parameter = mock.Mock(return_value=SimpleNamespace(value=True))

        invalid = velocity_gate.Twist()
        invalid.linear.y = 0.01
        gate.command_callback(
            invalid,
            {"received_timestamp": time.time_ns()},
        )

        self.assertTrue(gate.interlock.fault_latched)
        self.assertTrue(gate.interlock.await_disable)

    def test_stale_queued_command_is_cleared_and_latched(self):
        gate = object.__new__(velocity_gate.VelocityGate)
        gate.command = velocity_gate.Twist()
        gate.command_time = None
        gate.interlock = self.make_armed_interlock()
        parameters = {
            "cmd_timeout": 0.20,
            "input_cmd_topic": "/cmd_vel",
            "latch_faults": True,
        }
        gate.get_parameter = lambda name: SimpleNamespace(value=parameters[name])
        gate.get_logger = mock.Mock()
        gate.now = mock.Mock(return_value=100.0)

        command = velocity_gate.Twist()
        command.linear.x = 0.1
        with mock.patch.object(velocity_gate.time, "time_ns", return_value=1_000_000_000):
            gate.command_callback(
                command,
                {"received_timestamp": 700_000_000},
            )

        self.assertIsNone(gate.command_time)
        self.assertEqual(gate.command.linear.x, 0.0)
        self.assertTrue(gate.interlock.fault_latched)


class CollisionScanFilterTests(unittest.TestCase):
    def test_filter_uses_base_frame_endpoint_not_sensor_range(self):
        # At the official +0.33767 m lidar offset, a 0.40 m front return is
        # outside the footprint while an equally close rear return is inside.
        ranges = [0.40, 0.80, 1.10, math.inf, math.nan]

        filtered = collision_scan_filter.filter_ranges(
            ranges,
            angle_min=0.0,
            angle_increment=math.pi,
            footprint_radius_m=0.60,
            sensor_offset_x_m=0.33767,
            sensor_offset_y_m=0.0,
        )

        self.assertEqual(filtered[0], 0.40)
        self.assertTrue(math.isinf(filtered[1]))
        self.assertEqual(filtered[2:4], [1.10, math.inf])
        self.assertTrue(math.isnan(filtered[4]))


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

    def test_transition_message_includes_wall_ages_and_missing_input(self):
        message = navigation_health.health_transition_message(
            previous_health=None,
            healthy=False,
            last_seen={"scan": 99.75, "odom": None, "map": None},
            now=100.0,
            timeout=2.0,
            require_map=True,
        )
        self.assertIn("scan_age=0.250s", message)
        self.assertIn("odom_age=None", message)
        self.assertIn("map_received=false", message)
        self.assertIn("timeout=2.000s", message)

    def test_transition_message_suppresses_unchanged_health(self):
        self.assertIsNone(
            navigation_health.health_transition_message(
                previous_health=False,
                healthy=False,
                last_seen={"scan": None, "odom": None, "map": None},
                now=100.0,
                timeout=2.0,
                require_map=True,
            )
        )

    def test_simulation_launches_use_two_second_health_timeout(self):
        for launch_name in ("mapping.launch.py", "navigation.launch.py"):
            with self.subTest(launch=launch_name):
                source = (LAUNCH_DIR / launch_name).read_text(encoding="utf-8")
                self.assertIn(
                    '{"require_map": require_map, "timeout": 2.0}', source
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
