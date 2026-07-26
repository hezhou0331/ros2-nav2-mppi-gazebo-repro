from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def projection_node():
    return Node(
        package="pointcloud_to_laserscan",
        executable="pointcloud_to_laserscan_node",
        name="pointcloud_to_laserscan",
        remappings=[("cloud_in", "/lidar/points"), ("scan", "/scan_sensor")],
        parameters=[{
            "use_sim_time": True,
            # The single A2 head lidar is represented by a PointCloud2 stream.
            "target_frame": "front_lidar_sensor_link",
            "transform_tolerance": 0.2,
            # Match mapping: retain the lower environment band while rejecting close
            # A2/P7 echoes with the 0.40 m radial limit below.
            "min_height": -0.50,
            "max_height": 0.12,
            "angle_min": -3.14159,
            "angle_max": 3.14159,
            "angle_increment": 0.00872665,
            "scan_time": 0.1,
            "range_min": 0.40,
            "range_max": 8.0,
            "use_inf": False,
            "inf_epsilon": 0.0,
        }],
        output="screen",
    )


def collision_projection_node():
    return Node(
        package="pointcloud_to_laserscan",
        executable="pointcloud_to_laserscan_node",
        name="collision_pointcloud_to_laserscan",
        remappings=[("cloud_in", "/lidar/points"), ("scan", "/collision_scan")],
        parameters=[{
            "use_sim_time": True,
            # Collision Monitor consumes LaserScan and cannot apply a height
            # filter itself. Project in base_link so the height band removes
            # floor/self returns before the dynamic footprint check.
            "target_frame": "base_link",
            "transform_tolerance": 0.2,
            "min_height": 0.15,
            "max_height": 2.0,
            "angle_min": -3.14159,
            "angle_max": 3.14159,
            "angle_increment": 0.00872665,
            "scan_time": 0.1,
            "range_min": 0.40,
            "range_max": 8.0,
            "use_inf": True,
            "inf_epsilon": 1.0,
        }],
        output="screen",
    )


def safety_nodes(require_map: bool):
    # The gate and adapter use wall time, matching the future Orin safety contract.
    params = {"use_sim_time": False}
    return [
        Node(package="independent_nav_bringup", executable="scan_qos_relay.py",
             parameters=[params], output="screen"),
        Node(
            package="independent_nav_bringup",
            executable="velocity_gate.py",
            # Conservative limits for the A2 + centered P7 navigation proxy.
            parameters=[params | {"max_linear_x": 0.15, "max_angular_z": 0.25}],
            output="screen",
        ),
        Node(package="independent_nav_bringup", executable="navigation_health.py",
             parameters=[params | {"require_map": require_map}], output="screen"),
        Node(package="independent_nav_bringup", executable="simulation_platform_adapter.py",
             parameters=[params], output="screen"),
        Node(package="independent_nav_bringup", executable="simulation_supervisor.py",
             parameters=[params], output="screen"),
    ]


def generate_launch_description():
    package_share = Path(get_package_share_directory("independent_nav_bringup"))
    a2_p7_share = Path(get_package_share_directory("atec_a2_p7_description"))
    nav2_share = Path(get_package_share_directory("nav2_bringup"))
    map_yaml = LaunchConfiguration("map")
    use_gui = LaunchConfiguration("use_gui")
    use_rviz = LaunchConfiguration("use_rviz")

    simulation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(a2_p7_share / "launch" / "sim_world.launch.py")),
        launch_arguments={"use_gui": use_gui}.items(),
    )
    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(nav2_share / "launch" / "bringup_launch.py")),
        launch_arguments={
            "slam": "False",
            "map": map_yaml,
            "use_sim_time": "True",
            "params_file": str(package_share / "config" / "nav2_atec_a2_p7_mppi.yaml"),
            "autostart": "True",
            "use_composition": "False",
        }.items(),
    )
    rviz = Node(
        package="rviz2", executable="rviz2",
        arguments=["-d", str(package_share / "rviz" / "atec_navigation_demo.rviz")],
        parameters=[{"use_sim_time": True}], output="screen",
        condition=IfCondition(use_rviz),
    )
    return LaunchDescription([
        DeclareLaunchArgument("map", description="Absolute path to a saved map YAML file."),
        DeclareLaunchArgument("use_gui", default_value="false"),
        DeclareLaunchArgument("use_rviz", default_value="true"),
        simulation,
        projection_node(),
        collision_projection_node(),
        *safety_nodes(require_map=True),
        nav2,
        rviz,
    ])
