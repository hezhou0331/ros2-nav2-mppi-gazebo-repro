from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """只显示机器人模型，不启动 Gazebo。

    这个 launch 适合检查 Xacro 是否能正确展开、TF 树是否完整、
    RViz 里模型外观是否和预期一致。
    """
    # 获取构建后安装目录，而不是依赖当前终端在哪个文件夹运行。
    package_share = Path(get_package_share_directory("fishbot_xacro_description"))
    default_model = package_share / "urdf" / "fishbot.urdf.xacro"
    default_rviz = package_share / "rviz" / "display_robot.rviz"
    model = LaunchConfiguration("model")
    robot_name = LaunchConfiguration("robot_name")

    # 运行 xacro，并将 robot_name 作为命令行参数传给 xacro:arg。
    # 输出的完整 URDF XML 字符串将成为 robot_description 参数。
    robot_description = Command([
        "xacro ", model, " robot_name:=", robot_name,
    ])

    return LaunchDescription([
        DeclareLaunchArgument(
            "model",
            default_value=str(default_model),
            description="Xacro model path. Usually keep the default value.",
        ),
        DeclareLaunchArgument(
            "robot_name",
            default_value="fishbot",
            description="Prefix used for the robot link and joint names.",
        ),
        Node(
            # 发布 URDF 中父子 link 的坐标变换 TF。
            # RViz 的 RobotModel 正是通过 robot_description 和 TF 把模型画出来。
            package="robot_state_publisher",
            executable="robot_state_publisher",
            parameters=[{"robot_description": robot_description}],
            output="screen",
        ),
        Node(
            # 生成关节角度并提供图形化滑块。
            # fixed 关节不会出现在滑块里，continuous/revolute 关节会出现。
            package="joint_state_publisher_gui",
            executable="joint_state_publisher_gui",
            output="screen",
        ),
        Node(
            # 加载预设 RViz 配置并显示 RobotModel。
            package="rviz2",
            executable="rviz2",
            arguments=["-d", str(default_rviz)],
            output="screen",
        ),
    ])
