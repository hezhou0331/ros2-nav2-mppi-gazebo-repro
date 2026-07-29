import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node


def _adapter_node(context):
    config_file = LaunchConfiguration("config_file").perform(context)
    if not config_file or not os.path.isfile(config_file):
        raise ValueError(f"config_file does not exist: {config_file}")
    overrides = {}
    network_interface = LaunchConfiguration("network_interface").perform(context)
    dds_domain_id = LaunchConfiguration("dds_domain_id").perform(context)
    if network_interface:
        overrides["network_interface"] = network_interface
    if dds_domain_id:
        try:
            overrides["dds_domain_id"] = int(dds_domain_id)
        except ValueError as exc:
            raise ValueError("dds_domain_id must be an integer") from exc

    parameters = [config_file]
    if overrides:
        parameters.append(overrides)
    return [
        Node(
            package="atec_a2_sdk2_adapter",
            executable="a2_sdk2_adapter",
            name="a2_sdk2_adapter",
            output="screen",
            parameters=parameters,
        )
    ]


def generate_launch_description():
    package_share = get_package_share_directory("atec_a2_sdk2_adapter")
    default_config = PathJoinSubstitution(
        [package_share, "config", "a2_sdk2_adapter.yaml"]
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "network_interface",
                default_value="",
                description=(
                    "Optional override for the A2 Ethernet interface; an empty "
                    "value preserves the config file"
                ),
            ),
            DeclareLaunchArgument(
                "dds_domain_id",
                default_value="",
                description=(
                    "Optional DDS domain override; an empty value preserves "
                    "the config file"
                ),
            ),
            DeclareLaunchArgument("config_file", default_value=default_config),
            OpaqueFunction(function=_adapter_node),
        ]
    )
