from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """启动仿真 + Nav2 SLAM 导航。

    sim_world.launch 负责“机器人能动、传感器有数据”；
    Nav2 bringup 负责“建图、规划路径、避障和到点导航”。
    """
    package_share = Path(get_package_share_directory("fishbot_xacro_description"))
    nav2_share = Path(get_package_share_directory("nav2_bringup"))

    sim_launch = package_share / "launch" / "sim_world.launch.py"
    nav2_launch = nav2_share / "launch" / "bringup_launch.py"
    params_file = package_share / "config" / "nav2_params.yaml"
    rviz_config = nav2_share / "rviz" / "nav2_default_view.rviz"

    use_rviz = LaunchConfiguration("use_rviz")
    use_gui = LaunchConfiguration("use_gui")

    sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(sim_launch)),
        launch_arguments={
            # 这里固定机器人名字为 fishbot，因此配置文件里的 frame 名称也使用 fishbot 前缀。
            "robot_name": "fishbot",
            "use_gui": use_gui,
        }.items(),
    )

    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(nav2_launch)),
        launch_arguments={
            # slam=True 表示不加载已有地图，而是边走边建图。
            "slam": "True",
            # 仿真必须使用 /clock，否则 ROS 节点会使用真实电脑时间，时间轴会不一致。
            "use_sim_time": "True",
            "params_file": str(params_file),
            "autostart": "True",
            "use_composition": "False",
        }.items(),
    )

    rviz = Node(
        package="rviz2",
        executable="rviz2",
        arguments=["-d", str(rviz_config)],
        parameters=[{"use_sim_time": True}],
        output="screen",
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            "use_rviz",
            default_value="true",
            description="Start RViz with the Nav2 default view.",
        ),
        DeclareLaunchArgument(
            "use_gui",
            default_value="false",
            description="Start the Gazebo GUI in addition to RViz.",
        ),
        sim,
        # 等 Gazebo、机器人和 TF 基本就绪后再启动 Nav2，减少启动顺序导致的报错。
        TimerAction(period=6.0, actions=[nav2]),
        TimerAction(period=8.0, actions=[rviz], condition=IfCondition(use_rviz)),
    ])
