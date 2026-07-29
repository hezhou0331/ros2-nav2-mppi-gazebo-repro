#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
nav_config="$repo_dir/src/independent_nav_bringup/config/nav2_atec_a2_p7.yaml"
slam_config="$repo_dir/src/independent_nav_bringup/config/slam_toolbox_atec_a2.yaml"
platform_config="$repo_dir/src/independent_nav_bringup/platforms/atec_a2_p7.yaml"
adapter_root="$repo_dir/src/atec_a2_sdk2_adapter"
adapter_config="$adapter_root/config/a2_sdk2_adapter.yaml"
mapping_launch="$repo_dir/src/independent_nav_bringup/launch/mapping.launch.py"
navigation_launch="$repo_dir/src/independent_nav_bringup/launch/navigation.launch.py"
hardware_control_launch="$repo_dir/src/independent_nav_bringup/launch/a2_hardware_control.launch.py"

unset CONDA_PREFIX CONDA_DEFAULT_ENV PYTHONPATH
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
set +u
source /opt/ros/jazzy/setup.bash
source "$repo_dir/install/setup.bash"
set -u

model="$repo_dir/建模/sim_src/src/atec_a2_p7_description/urdf/atec_a2_p7.urdf.xacro"
model_urdf=$(mktemp /tmp/atec_a2_p7_validate.XXXXXX.urdf)
trap 'rm -f "$model_urdf"' EXIT
xacro "$model" simulation_plugins:=true -o "$model_urdf"
check_urdf "$model_urdf" >/dev/null
grep -q '<link name="front_lidar_sensor_link"' "$model_urdf"
grep -q '<link name="a2_p7_mount_link"' "$model_urdf"
echo "ATEC A2 + P7 URDF validation passed."

/usr/bin/python3 -m py_compile "$repo_dir"/src/independent_nav_bringup/launch/*.py \
  "$repo_dir"/src/independent_nav_bringup/scripts/*.py \
  "$adapter_root"/atec_a2_sdk2_adapter/*.py \
  "$adapter_root"/launch/*.py
/usr/bin/python3 "$repo_dir/src/independent_nav_bringup/test/test_automation_nodes.py"
PYTHONPATH="$adapter_root${PYTHONPATH:+:$PYTHONPATH}" \
  /usr/bin/python3 -m pytest -q "$adapter_root/test"
/usr/bin/python3 - "$nav_config" "$slam_config" "$platform_config" "$adapter_config" \
  "$mapping_launch" "$navigation_launch" "$hardware_control_launch" \
  "$repo_dir/src/independent_nav_bringup/rviz/atec_mapping_demo.rviz" \
  "$repo_dir/src/independent_nav_bringup/rviz/atec_navigation_demo.rviz" <<'PY'
import os
import sys

import yaml

(
    nav_path,
    slam_path,
    platform_path,
    adapter_path,
    mapping_launch_path,
    navigation_launch_path,
    hardware_control_launch_path,
    mapping_rviz_path,
    navigation_rviz_path,
) = sys.argv[1:]
with open(nav_path, encoding="utf-8") as stream:
    nav = yaml.safe_load(stream)
with open(slam_path, encoding="utf-8") as stream:
    slam = yaml.safe_load(stream)
with open(platform_path, encoding="utf-8") as stream:
    platform = yaml.safe_load(stream)["platform"]
with open(adapter_path, encoding="utf-8") as stream:
    adapter_params = yaml.safe_load(stream)["a2_sdk2_adapter"]["ros__parameters"]

controller = nav["controller_server"]["ros__parameters"]
rpp = controller["FollowPath"]
assert rpp["plugin"] == (
    "nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController"
)
assert rpp["desired_linear_vel"] == 0.15
assert rpp["rotate_to_heading_angular_vel"] == 0.25
assert rpp["use_rotate_to_heading"] is True
assert rpp["allow_reversing"] is False
assert rpp["use_collision_detection"] is True
assert rpp["max_allowed_time_to_collision_up_to_carrot"] == 1.0
progress = controller["progress_checker"]
assert progress["plugin"] == "nav2_controller::PoseProgressChecker"
assert progress["required_movement_radius"] == 0.05
assert progress["required_movement_angle"] == 0.20
assert progress["movement_time_allowance"] == 20.0

local = nav["local_costmap"]["local_costmap"]["ros__parameters"]
global_map = nav["global_costmap"]["global_costmap"]["ros__parameters"]
assert local["robot_radius"] == 0.60
assert global_map["robot_radius"] == 0.60
assert local["inflation_layer"]["inflation_radius"] == 0.70
assert global_map["inflation_layer"]["inflation_radius"] == 0.70
assert local["obstacle_layer"]["plugin"] == "nav2_costmap_2d::ObstacleLayer"
assert local["obstacle_layer"]["scan"]["topic"] == "/collision_scan"
assert local["obstacle_layer"]["scan"]["data_type"] == "LaserScan"
assert local["obstacle_layer"]["scan"]["obstacle_min_range"] == 0.40
assert local["obstacle_layer"]["scan"]["raytrace_min_range"] == 0.40
assert global_map["obstacle_layer"]["scan"]["topic"] == "/collision_scan"
assert global_map["obstacle_layer"]["scan"]["data_type"] == "LaserScan"
assert global_map["obstacle_layer"]["scan"]["obstacle_min_range"] == 0.40
assert global_map["obstacle_layer"]["scan"]["raytrace_min_range"] == 0.40
assert nav["amcl"]["ros__parameters"]["laser_min_range"] == 0.40
assert nav["amcl"]["ros__parameters"]["tf_broadcast"] is False
collision_scan = nav["collision_monitor"]["ros__parameters"]["scan"]
assert collision_scan["type"] == "scan"
assert collision_scan["topic"] == "/collision_scan"
assert "min_height" not in collision_scan
assert "max_height" not in collision_scan

slam_params = slam["slam_toolbox"]["ros__parameters"]
assert slam_params["odom_frame"] == "a2/odom"
assert slam_params["base_frame"] == "base_link"
assert slam_params["scan_topic"] == "/scan"
assert slam_params["min_laser_range"] == 0.40
assert slam_params["use_scan_matching"] is False
assert slam_params["use_scan_barycenter"] is False
assert slam_params["do_loop_closing"] is False
assert nav["slam_toolbox"]["ros__parameters"]["min_laser_range"] == 0.40
assert nav["slam_toolbox"]["ros__parameters"]["use_scan_matching"] is False

for launch_path in (mapping_launch_path, navigation_launch_path):
    source = open(launch_path, encoding="utf-8").read()
    assert '"min_height": -0.50' in source
    assert '"max_height": 0.12' in source
    assert '"range_min": 0.40' in source
    assert '"use_inf": False' in source
    assert '"inf_epsilon": 0.0' in source

navigation_source = open(navigation_launch_path, encoding="utf-8").read()
assert 'executable="collision_scan_filter.py"' in navigation_source
assert '"footprint_radius_m": 0.60' in navigation_source
assert '"sensor_offset_x_m": 0.33767' in navigation_source
assert 'name="simulation_map_to_odom"' in navigation_source
assert '"--frame-id", "map", "--child-frame-id", "a2/odom"' in navigation_source

hardware_control_source = open(
    hardware_control_launch_path, encoding="utf-8"
).read()
assert 'get_package_share_directory("atec_a2_sdk2_adapter")' in hardware_control_source
assert "OpaqueFunction" in hardware_control_source
assert "validate_wired_network_interface(network_interface)" in hardware_control_source
assert "verify_pinned_sdk2_installation()" in hardware_control_source
assert '"cmd_timeout": 0.08' in hardware_control_source
assert '"state_timeout": 0.25' in hardware_control_source
assert '"max_linear_x": 0.10' in hardware_control_source
assert '"max_angular_z": 0.20' in hardware_control_source
assert '"latch_faults": True' in hardware_control_source
assert '("/nav/enable", "/platform/automatic_mode")' in hardware_control_source
assert "simulation_platform_adapter" not in hardware_control_source
assert "simulation_supervisor" not in hardware_control_source
assert "simulation_map_to_odom" not in hardware_control_source

collision_filter_path = os.path.join(
    os.path.dirname(navigation_launch_path),
    "..",
    "scripts",
    "collision_scan_filter.py",
)
collision_filter_source = open(collision_filter_path, encoding="utf-8").read()
assert 'DEFAULT_FOOTPRINT_RADIUS_M = 0.60' in collision_filter_source
assert 'DEFAULT_SENSOR_OFFSET_X_M = 0.33767' in collision_filter_source
assert 'LaserScan, "/scan"' in collision_filter_source
assert 'LaserScan, "/collision_scan"' in collision_filter_source

for rviz_path in (mapping_rviz_path, navigation_rviz_path):
    with open(rviz_path, encoding="utf-8") as stream:
        assert yaml.safe_load(stream)["Visualization Manager"]["Global Options"]["Fixed Frame"] == "map"

assert platform["name"] == "atec_a2_p7"
assert platform["lidar"]["count"] == 1
assert platform["lidar"]["frame"] == "front_lidar_sensor_link"
assert platform["lidar"]["pointcloud_topic"] == "/lidar/points"
assert platform["lidar"]["scan_topic"] == "/scan"
assert platform["max_linear_x"] == 0.15
assert platform["max_angular_z"] == 0.25
assert platform["footprint_radius_m"] == 0.60
assert platform["adapter_package"] == "atec_a2_sdk2_adapter"
assert platform["automatic_mode_topic"] == "/platform/automatic_mode"
assert platform["manual_override_topic"] == "/platform/manual_override"
assert platform["estop_topic"] == "/platform/estop"
assert platform["adapter_status_topic"] == "/platform/adapter_status"
adapter = platform["adapter"]
assert adapter["interface_status"] == "implemented_not_hardware_verified"
assert adapter["hardware_control_launch"] == (
    "independent_nav_bringup/a2_hardware_control.launch.py"
)
assert adapter["runtime_scope"] == "control_boundary_only"
assert adapter["sdk_repository"] == (
    "https://github.com/unitreerobotics/unitree_sdk2_python"
)
assert adapter["sdk_commit"] == "65691c8a8bc53b98d3976dba4dbf9d5d20b2e7f5"
assert adapter["sdk_python_version"] == "1.0.1"
assert adapter["cyclonedds_python_version"] == "0.10.2"
assert adapter["sport_server_api_version"] == "1.0.0.1"
assert adapter["client"] == "unitree_sdk2py.a2.sport.sport_client.SportClient"
assert adapter["state_topic"] == "rt/lf/sportmodestate"
assert adapter["calls"] == ["Move(vx, 0.0, vyaw)", "StopMove()"]
assert adapter["max_linear_x"] == adapter_params["max_linear_x"] == 0.10
assert adapter["max_angular_z"] == adapter_params["max_angular_z"] == 0.20
assert adapter["command_timeout_s"] == adapter_params["command_timeout_s"] == 0.08
assert adapter["nominal_matched_service_stop_request_s"] == 0.14
assert adapter["unmatched_rpc_return_path_s"] == 0.30
nominal_request_path = (
    adapter_params["command_timeout_s"]
    + adapter_params["control_period_s"]
    + 2.0 * adapter_params["rpc_timeout_s"]
)
unmatched_return_path = (
    adapter_params["command_timeout_s"]
    + adapter_params["control_period_s"]
    + 2.0 * 0.10
)
assert abs(nominal_request_path - adapter["nominal_matched_service_stop_request_s"]) < 1e-12
assert abs(unmatched_return_path - adapter["unmatched_rpc_return_path_s"]) < 1e-12
assert adapter_params["nominal_stop_request_budget_s"] == 0.20
assert adapter_params["shutdown_join_timeout_s"] == 0.50
assert adapter["physical_stop_deadline_guaranteed"] is False
assert adapter["robot_side_watchdog_required"] is True
assert adapter["external_safety_source_required"] is True
assert adapter["dds_receive_timestamp_enforced"] is True
assert adapter["sdk_revision_metadata_enforced"] is True
assert adapter["sdk_critical_file_hashes_enforced"] is True
assert adapter["sport_server_api_version_enforced"] is True
assert adapter["sport_rpc_lease_enabled_upstream"] is False
assert adapter["publisher_identity_enforced_in_node"] is False
assert adapter["isolated_control_network_required"] is True
assert platform["terrain"]["gait_controller_verified"] is False
assert platform["terrain"]["safe_for_real_robot"] is False
assert platform["terrain"]["supported_modes"] == ["flat_navigation"]
assert set(platform["terrain"]["proxy_probe_modes"]) == {
    "ramp_up", "ramp_down", "stairs_up"
}
official_sim = platform["official_simulation_path"]
assert official_sim["unitree_mujoco_commit"] == (
    "ae6a8403e272733e9996ef59990880330496177f"
)
assert official_sim["unitree_rl_mjlab_commit"] == (
    "1425b15f73bd4095f0df53709d7c389c3eb9e790"
)
assert official_sim["training_task"] == "Unitree-A2-Flat"
assert official_sim["a2_policy_available"] is False
assert official_sim["gait_bridge_verified"] is False
assert official_sim["status"] == "blocked_missing_policy_and_bridge_validation"
assert platform["adapter_verified"] is False

print("ATEC A2 + P7 navigation configuration validation passed.")
PY

ros2 pkg prefix pointcloud_to_laserscan >/dev/null
ros2 pkg prefix nav2_regulated_pure_pursuit_controller >/dev/null
ros2 pkg prefix ros_gz_sim >/dev/null
ros2 pkg prefix action_msgs >/dev/null
ros2 pkg prefix lifecycle_msgs >/dev/null
ros2 pkg prefix nav2_msgs >/dev/null
ros2 pkg prefix tf2_ros >/dev/null
ros2 pkg prefix atec_a2_p7_description >/dev/null
ros2 pkg prefix atec_a2_sdk2_adapter >/dev/null
ros2 pkg prefix independent_nav_bringup >/dev/null
bash -n "$repo_dir/run_atec_end_to_end_demo.sh" \
  "$repo_dir/run_atec_terrain_probe.sh" \
  "$repo_dir/tools/install_recording_dependencies.sh" \
  "$repo_dir/tools/verify_recording.sh" \
  "$repo_dir/tools/record_atec_end_to_end_demo.sh"
/usr/bin/python3 -m py_compile \
  "$repo_dir/tools/validate_demo_artifacts.py" \
  "$repo_dir/tools/clear_mapping_patrol_footprint.py"
/usr/bin/python3 -m json.tool \
  "$repo_dir/docs/evidence/navigation_inflation_070_acceptance_summary.json" \
  >/dev/null
grep -q 'run_report.json' "$repo_dir/run_atec_end_to_end_demo.sh"
grep -q 'ROS_DOMAIN_ID' "$repo_dir/run_atec_end_to_end_demo.sh"
grep -q 'failed_stage' "$repo_dir/run_atec_end_to_end_demo.sh"
grep -q 'run_report.json' "$repo_dir/docs/END_TO_END_DEMO.md"
grep -q 'recording_report.json' "$repo_dir/tools/record_atec_end_to_end_demo.sh"
grep -q 'recording_report.json' "$repo_dir/docs/END_TO_END_DEMO.md"
grep -q 'Fraction(25, 1)' "$repo_dir/tools/verify_recording.sh"
grep -q 'atec_demo_.*_\$\$' "$repo_dir/run_atec_end_to_end_demo.sh"
grep -q 'atec_demo_.*_\$\$' "$repo_dir/tools/record_atec_end_to_end_demo.sh"
grep -q -- '--default-signal=INT' "$repo_dir/run_atec_end_to_end_demo.sh"
grep -q -- '--default-signal=INT' "$repo_dir/run_atec_terrain_probe.sh"
"$repo_dir/run_atec_end_to_end_demo.sh" --help >/dev/null
"$repo_dir/run_atec_terrain_probe.sh" --help >/dev/null
"$repo_dir/tools/record_atec_end_to_end_demo.sh" --help >/dev/null
echo "ROS dependency and workspace package validation passed."
