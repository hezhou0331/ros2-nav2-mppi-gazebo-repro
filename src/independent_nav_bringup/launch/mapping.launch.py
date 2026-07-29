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
            # Preserve the useful lower environment returns; close A2/P7 echoes are
            # rejected by the 0.40 m radial limit below.
            "min_height": -0.50,
            "max_height": 0.12,
            "angle_min": -3.14159,
            "angle_max": 3.14159,
            "angle_increment": 0.00872665,
            "scan_time": 0.1,
            "range_min": 0.40,
            "range_max": 8.0,
            # A finite max-range return lets SLAM clear open floor in this sparse
            # course. The patrol gate excludes these synthetic max-range samples.
            "use_inf": False,
            "inf_epsilon": 0.0,
        }],
        output="screen",
    )


def safety_nodes(require_map: bool):
    # Safety timeouts must use wall time even if Gazebo is paused or /clock resets.
    params = {"use_sim_time": False}
    return [
        Node(package="independent_nav_bringup", executable="scan_qos_relay.py",
             parameters=[params], output="screen"),
        Node(
            package="independent_nav_bringup",
            executable="velocity_gate.py",
            # Conservative limits for the A2 + centered P7 navigation proxy.
            parameters=[params | {
                "max_linear_x": 0.15,
                "max_angular_z": 0.25,
                # The automated simulation supervisor does not perform a rearm cycle.
                "latch_faults": False,
            }],
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
    use_gui = LaunchConfiguration("use_gui")
    use_rviz = LaunchConfiguration("use_rviz")
    rviz_config = LaunchConfiguration("rviz_config")
    spawn_x = LaunchConfiguration("spawn_x")
    spawn_y = LaunchConfiguration("spawn_y")
    spawn_z = LaunchConfiguration("spawn_z")
    spawn_yaw = LaunchConfiguration("spawn_yaw")

    simulation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(a2_p7_share / "launch" / "sim_world.launch.py")),
        launch_arguments={
            "use_gui": use_gui,
            "spawn_x": spawn_x,
            "spawn_y": spawn_y,
            "spawn_z": spawn_z,
            "spawn_yaw": spawn_yaw,
        }.items(),
    )
    slam = Node(
        package="slam_toolbox",
        executable="async_slam_toolbox_node",
        parameters=[str(package_share / "config" / "slam_toolbox_atec_a2.yaml")],
        output="screen",
    )
    slam_lifecycle_manager = Node(
        package="nav2_lifecycle_manager",
        executable="lifecycle_manager",
        name="lifecycle_manager_slam",
        parameters=[{
            "use_sim_time": True,
            "autostart": True,
            # slam_toolbox in this Jazzy package does not provide a Nav2 bond.
            "bond_timeout": 0.0,
            "node_names": ["slam_toolbox"],
        }],
        output="screen",
    )
    rviz = Node(
        package="rviz2", executable="rviz2",
        arguments=["-d", rviz_config],
        parameters=[{"use_sim_time": True}], output="screen",
        condition=IfCondition(use_rviz),
    )
    return LaunchDescription([
        DeclareLaunchArgument("use_gui", default_value="false"),
        DeclareLaunchArgument("use_rviz", default_value="true"),
        DeclareLaunchArgument(
            "rviz_config",
            default_value=str(package_share / "rviz" / "atec_mapping_demo.rviz"),
            description="RViz configuration; use atec_mapping_showcase_3d.rviz for a live 3D LiDAR view.",
        ),
        DeclareLaunchArgument("spawn_x", default_value="-5.8"),
        DeclareLaunchArgument("spawn_y", default_value="0.0"),
        DeclareLaunchArgument("spawn_z", default_value="0.56"),
        DeclareLaunchArgument("spawn_yaw", default_value="0.0"),
        simulation,
        projection_node(),
        slam,
        slam_lifecycle_manager,
        *safety_nodes(require_map=False),
        rviz,
    ])
