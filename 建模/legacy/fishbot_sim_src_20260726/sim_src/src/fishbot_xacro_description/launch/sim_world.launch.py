from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    """启动 Gazebo Sim、生成机器人，并连接 ROS 2 与 Gazebo 话题。

    这是完整仿真的入口：世界、机器人模型、控制器、话题桥都会在这里启动。
    """
    package_share = Path(get_package_share_directory("fishbot_xacro_description"))
    ros_gz_share = Path(get_package_share_directory("ros_gz_sim"))
    world = package_share / "worlds" / "fishbot_world.sdf"
    model = package_share / "urdf" / "fishbot.urdf.xacro"
    robot_name = LaunchConfiguration("robot_name")
    use_gui = LaunchConfiguration("use_gui")
    command_topic = LaunchConfiguration("command_topic")
    gz_args = LaunchConfiguration("gz_args")

    # 将 Xacro 展开成 URDF 字符串，供 ROS 和 Gazebo Sim 使用。
    robot_description = Command([
        "xacro ", str(model), " robot_name:=", robot_name,
    ])

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(ros_gz_share / "launch" / "gz_sim.launch.py")),
        # -s: 只启动 server，避免当前机器的 Gazebo GUI 图形库冲突影响仿真。
        # 去掉 -s 后可以尝试启动 Gazebo GUI。
        launch_arguments={
            "gz_args": gz_args,
            "on_exit_shutdown": "true",
        }.items(),
    )

    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[{"robot_description": robot_description, "use_sim_time": True}],
        output="screen",
    )

    spawn_robot = Node(
        package="ros_gz_sim",
        executable="create",
        # 从 Xacro 生成的 URDF 字符串创建一个 Gazebo 实体。
        # z=0.15 让模型从地面上方落下，避免初始时穿入地面。
        arguments=[
            "-world", "fishbot_world",
            "-string", robot_description,
            "-name", robot_name,
            "-x", "0", "-y", "0", "-z", "0.15",
        ],
        output="screen",
    )

    bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=[
            # 语法说明：
            #   ROS_TOPIC@ROS_MSG]GZ_MSG 表示 ROS -> Gazebo
            #   ROS_TOPIC@ROS_MSG[GZ_MSG 表示 Gazebo -> ROS
            # 底盘命令只走 ControlTopicBridge -> ros2_control；不要在这里再桥接
            # /cmd_vel，否则会绕过 independent_nav_bringup 的速度安全门。
            # odom、tf、scan、clock 是仿真状态和传感器数据，需要从 Gazebo 发回 ROS。
            "/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry",
            "/tf@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V",
            "/scan_raw@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan",
            "/lidar/points/points@sensor_msgs/msg/PointCloud2[gz.msgs.PointCloudPacked",
            "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock",
        ],
        remappings=[
            # 对外保持常见 ROS 名称，初学时更容易用 ros2 topic echo 调试。
            ("/odometry", "/odom"),
            ("/lidar/points/points", "/lidar/points"),
        ],
        output="screen",
    )

    control_topic_bridge = Node(
        package="fishbot_xacro_description",
        executable="twist_odom_tf_bridge.py",
        # diff_drive_controller 使用 TwistStamped，本节点把常见的 Twist /cmd_vel 转过去。
        parameters=[{"use_sim_time": True, "command_topic": command_topic}],
        output="screen",
    )

    # gz_ros2_control 在 spawn 时才创建 controller_manager，因此延迟加载控制器。
    spawn_controllers = TimerAction(
        period=6.0,
        actions=[
            Node(
                package="controller_manager",
                executable="spawner",
                arguments=[
                    "joint_state_broadcaster",
                    "--controller-manager", "/controller_manager",
                ],
                output="screen",
            ),
            Node(
                package="controller_manager",
                executable="spawner",
                arguments=[
                    "diff_drive_controller",
                    "--controller-manager", "/controller_manager",
                ],
                output="screen",
            ),
        ],
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            "robot_name",
            default_value="fishbot",
            description="Gazebo entity name and the TF prefix used by the robot.",
        ),
        DeclareLaunchArgument(
            "gz_args",
            default_value=PythonExpression([
                "'-r -v 3 ", str(world), "' if '", use_gui,
                "' == 'true' else '-r -s -v 3 ", str(world), "'",
            ]),
            # -r 表示启动后自动运行仿真；-v 3 表示日志详细程度。
            description="Arguments passed to gz sim. Usually leave this unchanged and use use_gui.",
        ),
        DeclareLaunchArgument(
            "use_gui",
            default_value="false",
            description="Start the Gazebo GUI. false starts server-only mode.",
        ),
        DeclareLaunchArgument(
            "command_topic",
            default_value="/cmd_vel",
            description="Twist topic that is allowed to drive the Gazebo base.",
        ),
        gazebo,
        robot_state_publisher,
        bridge,
        control_topic_bridge,
        # Gazebo 需要少量启动时间才能提供创建实体的服务。
        TimerAction(period=3.0, actions=[spawn_robot]),
        spawn_controllers,
    ])
