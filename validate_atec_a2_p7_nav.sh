#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
nav_config="$repo_dir/src/independent_nav_bringup/config/nav2_atec_a2_p7_mppi.yaml"
slam_config="$repo_dir/src/independent_nav_bringup/config/slam_toolbox_atec_a2.yaml"
platform_config="$repo_dir/src/independent_nav_bringup/platforms/atec_a2_p7.yaml"
mapping_launch="$repo_dir/src/independent_nav_bringup/launch/mapping.launch.py"
navigation_launch="$repo_dir/src/independent_nav_bringup/launch/navigation.launch.py"

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
  "$repo_dir"/src/independent_nav_bringup/scripts/*.py
/usr/bin/python3 "$repo_dir/src/independent_nav_bringup/test/test_automation_nodes.py"
/usr/bin/python3 - "$nav_config" "$slam_config" "$platform_config" \
  "$mapping_launch" "$navigation_launch" \
  "$repo_dir/src/independent_nav_bringup/rviz/atec_mapping_demo.rviz" \
  "$repo_dir/src/independent_nav_bringup/rviz/atec_navigation_demo.rviz" <<'PY'
import sys

import yaml

(
    nav_path,
    slam_path,
    platform_path,
    mapping_launch_path,
    navigation_launch_path,
    mapping_rviz_path,
    navigation_rviz_path,
) = sys.argv[1:]
with open(nav_path, encoding="utf-8") as stream:
    nav = yaml.safe_load(stream)
with open(slam_path, encoding="utf-8") as stream:
    slam = yaml.safe_load(stream)
with open(platform_path, encoding="utf-8") as stream:
    platform = yaml.safe_load(stream)["platform"]

controller = nav["controller_server"]["ros__parameters"]
mppi = controller["FollowPath"]
assert mppi["plugin"] == "nav2_mppi_controller::MPPIController"
assert mppi["motion_model"] == "DiffDrive"
assert mppi["vx_max"] == 0.15
assert mppi["wz_max"] == 0.25
assert mppi["batch_size"] == 512
assert mppi["iteration_count"] == 5
assert mppi["visualize"] is False
assert 1.0 / controller["controller_frequency"] <= mppi["model_dt"]

local = nav["local_costmap"]["local_costmap"]["ros__parameters"]
global_map = nav["global_costmap"]["global_costmap"]["ros__parameters"]
assert local["robot_radius"] == 0.60
assert global_map["robot_radius"] == 0.60
assert local["voxel_layer"]["plugin"] == "nav2_costmap_2d::VoxelLayer"
assert local["voxel_layer"]["points"]["topic"] == "/lidar/points"
assert local["voxel_layer"]["points"]["data_type"] == "PointCloud2"
assert local["voxel_layer"]["points"]["obstacle_min_range"] == 0.40
assert local["voxel_layer"]["points"]["raytrace_min_range"] == 0.40
assert global_map["obstacle_layer"]["scan"]["topic"] == "/scan"
assert global_map["obstacle_layer"]["scan"]["data_type"] == "LaserScan"
assert global_map["obstacle_layer"]["scan"]["obstacle_min_range"] == 0.40
assert global_map["obstacle_layer"]["scan"]["raytrace_min_range"] == 0.40
assert nav["amcl"]["ros__parameters"]["laser_min_range"] == 0.40
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
assert 'name="collision_pointcloud_to_laserscan"' in navigation_source
assert '("scan", "/collision_scan")' in navigation_source
assert '"target_frame": "base_link"' in navigation_source
assert '"min_height": 0.15' in navigation_source
assert '"max_height": 2.0' in navigation_source

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
assert platform["adapter_verified"] is False

print("ATEC A2 + P7 navigation configuration validation passed.")
PY

ros2 pkg prefix pointcloud_to_laserscan >/dev/null
ros2 pkg prefix nav2_mppi_controller >/dev/null
ros2 pkg prefix ros_gz_sim >/dev/null
ros2 pkg prefix action_msgs >/dev/null
ros2 pkg prefix lifecycle_msgs >/dev/null
ros2 pkg prefix nav2_msgs >/dev/null
ros2 pkg prefix tf2_ros >/dev/null
ros2 pkg prefix atec_a2_p7_description >/dev/null
ros2 pkg prefix independent_nav_bringup >/dev/null
bash -n "$repo_dir/run_atec_end_to_end_demo.sh" \
  "$repo_dir/tools/install_recording_dependencies.sh" \
  "$repo_dir/tools/verify_recording.sh" \
  "$repo_dir/tools/record_atec_end_to_end_demo.sh"
/usr/bin/python3 -m py_compile \
  "$repo_dir/tools/validate_demo_artifacts.py" \
  "$repo_dir/tools/clear_mapping_patrol_footprint.py"
grep -q 'run_report.json' "$repo_dir/run_atec_end_to_end_demo.sh"
grep -q 'ROS_DOMAIN_ID' "$repo_dir/run_atec_end_to_end_demo.sh"
grep -q 'failed_stage' "$repo_dir/run_atec_end_to_end_demo.sh"
grep -q 'run_report.json' "$repo_dir/docs/END_TO_END_DEMO.md"
grep -q 'recording_report.json' "$repo_dir/tools/record_atec_end_to_end_demo.sh"
grep -q 'recording_report.json' "$repo_dir/docs/END_TO_END_DEMO.md"
grep -q 'Fraction(25, 1)' "$repo_dir/tools/verify_recording.sh"
grep -q 'atec_demo_.*_\$\$' "$repo_dir/run_atec_end_to_end_demo.sh"
grep -q 'atec_demo_.*_\$\$' "$repo_dir/tools/record_atec_end_to_end_demo.sh"
"$repo_dir/run_atec_end_to_end_demo.sh" --help >/dev/null
"$repo_dir/tools/record_atec_end_to_end_demo.sh" --help >/dev/null
echo "ROS dependency and workspace package validation passed."
