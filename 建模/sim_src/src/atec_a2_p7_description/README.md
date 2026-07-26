# ATEC A2 + P7 Description

此 ROS 2 包提供 ATEC 导航赛的仿真模型：Unitree A2 四足机器人，P7 机械臂固定在机身背部中心。活动的模型入口为 `urdf/atec_a2_p7.urdf.xacro`，活动的赛道入口为 `worlds/atec_practice_world.sdf`。

```text
base_link
  -> a2_p7_mount_link       (x=0, y=0, arm_mount_z=0.145 m)
    -> p7_base_link
```

`arm_mount_z`、安装板尺寸/质量和红色防护边均为仿真假设，不是实机装配图。参赛前必须根据 A2 预留孔位、转接板叠层、紧固件、载荷和急停方案完成设计复核。

## Commands

从仓库根目录构建后：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch atec_a2_p7_description display_robot.launch.py
ros2 launch atec_a2_p7_description sim_world.launch.py use_gui:=true
```

仿真导航接口为 `/sim/cmd_vel`、`/odom`、`/lidar/points` 和 `/scan`。坐标链为
`a2/odom -> base_link -> front_lidar_link -> front_lidar_sensor_link`：前一个雷达
frame 保留导入 A2 的原生安装位置，后一个仿真子 frame 只将传感器轴校正为
x 前、y 左、z 上。导航栈把同一颗雷达的点云投影为 `/scan`；SLAM/AMCL
使用该扫描，局部/全局代价地图和 collision monitor 使用按机体足迹过滤后的
`/collision_scan`。

## Fidelity Boundary

- Gazebo `VelocityControl` 仅是平面移动代理；它不是 A2 步态、SDK、执行器或实机速度协议。
- 腿部在导航姿态由位置控制器保持，P7 采用供应商零位；两者都不是已验证的实机导航姿态。
- P7 高面数碰撞网格已换为简化几何，UMI 夹爪的 14 个被动关节固定，只保留一个仿真夹爪开度自由度。
- 练习世界的地形、摩擦、噪声、物品和箱体是赛规的代表性近似。抓取物均为静态模型，不能用于验证抓取、提起、运输或计分。

先阅读 [MODEL_AND_SAFETY.md](docs/MODEL_AND_SAFETY.md)，其中定义模型边界、
单雷达链路、居中安装假设和实机安全门槛。详细的来源与生成规则见
[MODEL_PROVENANCE.md](docs/MODEL_PROVENANCE.md)，第三方资产和再分发限制见
[THIRD_PARTY_NOTICES.md](docs/THIRD_PARTY_NOTICES.md)。
