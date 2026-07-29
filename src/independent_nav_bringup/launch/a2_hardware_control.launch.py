import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    OpaqueFunction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from atec_a2_sdk2_adapter.sdk2_backend import (
    validate_wired_network_interface,
    verify_pinned_sdk2_installation,
)


def _hardware_nodes(context, adapter_share):
    network_interface = LaunchConfiguration("network_interface").perform(context).strip()
    adapter_config = LaunchConfiguration("adapter_config").perform(context)

    if not adapter_config or not os.path.isfile(adapter_config):
        raise ValueError(f"adapter_config does not exist: {adapter_config}")
    validate_wired_network_interface(network_interface)

    # Refuse to start any command-path process unless the audited SDK revision
    # can be proven from pip's PEP 610 installation metadata.
    verify_pinned_sdk2_installation()

    adapter = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            str(adapter_share / "launch" / "a2_sdk2_adapter.launch.py")
        ),
        launch_arguments={
            "network_interface": network_interface,
            "dds_domain_id": LaunchConfiguration("dds_domain_id"),
            "config_file": adapter_config,
        }.items(),
    )
    velocity_gate = Node(
        package="independent_nav_bringup",
        executable="velocity_gate.py",
        name="a2_hardware_velocity_gate",
        output="screen",
        parameters=[{
            "use_sim_time": False,
            "input_cmd_topic": LaunchConfiguration("input_cmd_topic"),
            "output_cmd_topic": "/platform/cmd_vel",
            "cmd_timeout": 0.08,
            "state_timeout": 0.25,
            "max_linear_x": 0.10,
            "max_angular_z": 0.20,
            "latch_faults": True,
        }],
        # One authoritative false -> true automatic-mode cycle rearms both
        # the gate and the SDK2 adapter. No mock supervisor is launched here.
        remappings=[("/nav/enable", "/platform/automatic_mode")],
    )
    return [adapter, velocity_gate]


def generate_launch_description():
    adapter_share = Path(get_package_share_directory("atec_a2_sdk2_adapter"))

    return LaunchDescription([
        DeclareLaunchArgument(
            "network_interface",
            description="Required A2 Ethernet interface, for example enp2s0",
        ),
        DeclareLaunchArgument(
            "dds_domain_id",
            default_value="",
            description="Optional SDK DDS domain override; config is used when empty",
        ),
        DeclareLaunchArgument(
            "adapter_config",
            default_value=str(adapter_share / "config" / "a2_sdk2_adapter.yaml"),
        ),
        DeclareLaunchArgument("input_cmd_topic", default_value="/cmd_vel"),
        OpaqueFunction(
            function=_hardware_nodes,
            kwargs={"adapter_share": adapter_share},
        ),
    ])
