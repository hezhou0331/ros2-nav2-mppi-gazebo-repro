from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (
    Command,
    EnvironmentVariable,
    LaunchConfiguration,
    PythonExpression,
)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    package_share = Path(get_package_share_directory("atec_a2_p7_description"))
    ros_gz_share = Path(get_package_share_directory("ros_gz_sim"))
    bridge_config = package_share / "config" / "gz_bridge.yaml"
    model = package_share / "urdf" / "atec_a2_p7.urdf.xacro"
    world = package_share / "worlds" / "atec_practice_world.sdf"
    use_gui = LaunchConfiguration("use_gui")
    mount_z = LaunchConfiguration("arm_mount_z")
    description_command = Command([
        "xacro ", str(model),
        " simulation_plugins:=true",
        " arm_mount_z:=", mount_z,
    ])
    description = ParameterValue(description_command, value_type=str)

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(ros_gz_share / "launch" / "gz_sim.launch.py")),
        launch_arguments={
            "gz_args": PythonExpression([
                "'-r -v 3 ", str(world), "' if '", use_gui,
                "' == 'true' else '-r -s -v 3 ", str(world), "'",
            ]),
            "on_exit_shutdown": "true",
        }.items(),
    )
    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[{"robot_description": description, "use_sim_time": True}],
        output="screen",
    )
    navigation_stow_state = Node(
        package="joint_state_publisher",
        executable="joint_state_publisher",
        name="navigation_stow_joint_state_publisher",
        parameters=[{
            "robot_description": description,
            "use_sim_time": True,
            "rate": 30,
            "zeros.FL_hip_joint": 0.0,
            "zeros.FL_thigh_joint": 0.45,
            "zeros.FL_calf_joint": -0.90,
            "zeros.FR_hip_joint": 0.0,
            "zeros.FR_thigh_joint": 0.45,
            "zeros.FR_calf_joint": -0.90,
            "zeros.RL_hip_joint": 0.0,
            "zeros.RL_thigh_joint": 0.45,
            "zeros.RL_calf_joint": -0.90,
            "zeros.RR_hip_joint": 0.0,
            "zeros.RR_thigh_joint": 0.45,
            "zeros.RR_calf_joint": -0.90,
        }],
        output="screen",
    )
    spawn = Node(
        package="ros_gz_sim",
        executable="create",
        arguments=[
            "-world", "atec_practice_world",
            "-string", description_command,
            "-name", "atec_a2_p7",
            "-x", "-5.8", "-y", "0", "-z", "0.56",
        ],
        output="screen",
    )
    bridge = Node(
        package="ros_gz_bridge",
        executable="bridge_node",
        parameters=[{"config_file": str(bridge_config)}],
        output="screen",
    )

    return LaunchDescription([
        DeclareLaunchArgument("use_gui", default_value="false"),
        DeclareLaunchArgument(
            "arm_mount_z",
            default_value="0.145",
            description="Simulation-only mount datum; not a manufacturing value.",
        ),
        # Gazebo resolves URDF package:// mesh URIs as model://<package>/... .
        # The parent of the package share directory is therefore a resource root.
        SetEnvironmentVariable(
            "GZ_SIM_RESOURCE_PATH",
            [
                EnvironmentVariable("GZ_SIM_RESOURCE_PATH", default_value=""),
                ":",
                str(package_share.parent),
            ],
        ),
        gazebo,
        robot_state_publisher,
        navigation_stow_state,
        bridge,
        TimerAction(period=3.0, actions=[spawn]),
    ])
