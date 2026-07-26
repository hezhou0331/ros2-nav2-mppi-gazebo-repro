from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    package_share = Path(get_package_share_directory("atec_a2_p7_description"))
    model = package_share / "urdf" / "atec_a2_p7.urdf.xacro"
    rviz = package_share / "rviz" / "display_robot.rviz"
    mount_z = LaunchConfiguration("arm_mount_z")
    description = ParameterValue(
        Command([
            "xacro ", str(model),
            " simulation_plugins:=false",
            " arm_mount_z:=", mount_z,
        ]),
        value_type=str,
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            "arm_mount_z",
            default_value="0.145",
            description="Simulation-only P7 adapter datum in the A2 base_link frame.",
        ),
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            parameters=[{"robot_description": description}],
            output="screen",
        ),
        Node(
            package="joint_state_publisher_gui",
            executable="joint_state_publisher_gui",
            parameters=[{"robot_description": description}],
            output="screen",
        ),
        Node(
            package="rviz2",
            executable="rviz2",
            arguments=["-d", str(rviz)],
            output="screen",
        ),
    ])
