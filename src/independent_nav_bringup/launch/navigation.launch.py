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


def safety_nodes(require_map: bool):
    # The gate and adapter use wall time, matching the future Orin safety contract.
    params = {"use_sim_time": False}
    return [
        Node(package="independent_nav_bringup", executable="scan_qos_relay.py",
             parameters=[params], output="screen"),
        Node(
            package="independent_nav_bringup",
            executable="collision_scan_filter.py",
            # Official A2 lidar x offset, evaluated against the same 0.60 m
            # circular footprint used by both Nav2 costmaps.
            parameters=[params | {
                "footprint_radius_m": 0.60,
                "sensor_offset_x_m": 0.33767,
                "sensor_offset_y_m": 0.0,
            }],
            output="screen",
        ),
        Node(
            package="independent_nav_bringup",
            executable="velocity_gate.py",
            # Conservative limits for the A2 + centered P7 navigation proxy.
            parameters=[params | {"max_linear_x": 0.15, "max_angular_z": 0.25}],
            output="screen",
        ),
        Node(package="independent_nav_bringup", executable="navigation_health.py",
             parameters=[params | {"require_map": require_map, "timeout": 2.0}],
             output="screen"),
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
    simulation_localization = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name="simulation_map_to_odom",
        arguments=[
            "--x", "0", "--y", "0", "--z", "0",
            "--roll", "0", "--pitch", "0", "--yaw", "0",
            "--frame-id", "map", "--child-frame-id", "a2/odom",
        ],
        output="screen",
    )
    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(nav2_share / "launch" / "bringup_launch.py")),
        launch_arguments={
            "slam": "False",
            "map": map_yaml,
            "use_sim_time": "True",
            "params_file": str(package_share / "config" / "nav2_atec_a2_p7.yaml"),
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
        # Mapping is built directly in Gazebo's drift-free odom coordinates.
        # Real hardware must remove this identity TF and let AMCL own map -> odom.
        simulation_localization,
        projection_node(),
        *safety_nodes(require_map=True),
        nav2,
        rviz,
    ])
