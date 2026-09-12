"""RoamerX 进程预检：所有速度输出保留在 /m1_preview/*。
不加载 SDK、UDP/LCM 桥接、传感器驱动、虚假 TF 或运动模式发布器。
"""
from pathlib import Path
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def start(context):
    config = Path(LaunchConfiguration('params_file').perform(context)).resolve()
    if not config.is_file():
        raise RuntimeError('Generate a preview parameter file with prepare_preview.py first.')
    nodes = [
        ('navigo_map_server', 'map_server', 'map_server'),
        ('navigo_path_controller', 'controller_server', 'controller_server'),
        ('navigo_path_planner', 'planner_server', 'planner_server'),
        ('navigo_behaviors', 'behavior_server', 'behavior_server'),
        ('navigo_velocity_optimizer', 'velocity_smoother', 'velocity_optimizer'),
        ('navigo_bt_navigator', 'bt_navigator', 'bt_navigator'),
        ('navigo_waypoint_follower', 'waypoint_follower', 'waypoint_follower'),
    ]
    actions = []
    for package, executable, name in nodes:
        remaps = [('cmd_vel', '/m1_preview/cmd_vel_raw'),
                  ('cmd_vel_smoothed', '/m1_preview/cmd_vel'),
                  ('mode_switch_cmd', '/m1_preview/mode_switch_cmd')]
        actions.append(Node(package=package, executable=executable, name=name,
                            namespace='m1_preview', output='screen',
                            parameters=[str(config)], remappings=remaps))
    # 默认不激活：可在生命周期激活前检查参数与插件。
    actions.append(Node(package='nav2_lifecycle_manager', executable='lifecycle_manager',
                        name='lifecycle_manager_preview', namespace='m1_preview', output='screen',
                        parameters=[{'autostart': False,
                                     'node_names': [name for _, _, name in nodes]}]))
    return actions


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('params_file', description='Generated preview YAML path'),
        OpaqueFunction(function=start),
    ])
