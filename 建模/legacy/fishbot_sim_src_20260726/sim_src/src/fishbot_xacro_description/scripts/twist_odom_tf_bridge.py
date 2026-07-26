#!/usr/bin/python3
"""Keep the existing /cmd_vel, /odom and /tf names usable with ros2_control.

新手说明：
diff_drive_controller 默认订阅 /diff_drive_controller/cmd_vel，消息类型是
TwistStamped；但很多教程和键盘遥控工具发布的是 /cmd_vel，消息类型是 Twist。
这个小节点负责做“话题名 + 消息类型”的适配。
"""

import rclpy
from geometry_msgs.msg import Twist, TwistStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from tf2_msgs.msg import TFMessage


class ControlTopicBridge(Node):
    """在常见 ROS 话题和 ros2_control 控制器话题之间转发数据。"""

    def __init__(self):
        super().__init__("fishbot_control_topic_bridge")
        # command_topic 允许 launch 文件决定听哪个速度命令话题，默认就是 /cmd_vel。
        self.declare_parameter("command_topic", "/cmd_vel")

        # 控制器真正接收的速度话题。TwistStamped 比 Twist 多了时间戳和坐标系。
        self.cmd_pub = self.create_publisher(
            TwistStamped, "/diff_drive_controller/cmd_vel", 10
        )
        # 对外重新发布为常见的 /odom 和 /tf，方便 RViz、Nav2 和命令行调试使用。
        self.odom_pub = self.create_publisher(Odometry, "/odom", 10)
        self.tf_pub = self.create_publisher(TFMessage, "/tf", 10)

        # 订阅外部命令，例如 teleop_twist_keyboard 或 Nav2 发出的 /cmd_vel。
        self.create_subscription(
            Twist, self.get_parameter("command_topic").value, self.cmd_callback, 10
        )
        # 订阅 diff_drive_controller 计算出的里程计和 TF。
        self.create_subscription(
            Odometry,
            "/diff_drive_controller/odom",
            self.odom_callback,
            10,
        )
        self.create_subscription(
            TFMessage,
            "/diff_drive_controller/tf",
            self.tf_callback,
            10,
        )

    def cmd_callback(self, msg):
        """把普通 Twist 包装成控制器需要的 TwistStamped。"""
        stamped = TwistStamped()
        # 使用当前 ROS 时间；仿真模式下该时间来自 /clock。
        stamped.header.stamp = self.get_clock().now().to_msg()
        stamped.header.frame_id = "fishbot_base_link"
        stamped.twist = msg
        self.cmd_pub.publish(stamped)

    def odom_callback(self, msg):
        """把控制器里程计重新发布到 /odom。"""
        self.odom_pub.publish(msg)

    def tf_callback(self, msg):
        """把控制器 TF 重新发布到 /tf。"""
        self.tf_pub.publish(msg)


def main():
    # ROS 2 Python 节点的标准入口：初始化、创建节点、持续处理回调。
    rclpy.init()
    node = ControlTopicBridge()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
