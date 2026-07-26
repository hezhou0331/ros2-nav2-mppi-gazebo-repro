# ATEC A2 + P7 建模工作区

`建模/sim_src` 是本仓库的一部分，不是独立 ROS 工作区。请在克隆后的仓库根目录
构建并加载 `install/setup.bash`。该目录不单独构成 ROS 工作区，也不应单独
source 其他工作区的 `install/setup.bash`。

```text
ros2-nav2-mppi-gazebo-repro/
├── src/independent_nav_bringup/       # 单雷达建图、定位、Nav2 与仿真安全边界
└── 建模/sim_src/src/
    └── atec_a2_p7_description/        # A2、本地 P7 v3 UMI 模型、仿真场地
```

当前模型是 Unitree A2 四足机器狗加装 P7 机械臂。机械臂的仿真安装位置在
`base_link` 中为 `x=0, y=0, z=0.145 m`，即车背中心；该数值只是模型装配
基准，不是可直接制造或上真机的尺寸。最终安装板、螺孔、紧固件、线束、质量
分布和机械臂朝向必须按厂商图纸和实物复核。

机器人只配置一颗头部原生位置的 3D 雷达：`front_lidar_link`。该 link 与其
相对 `base_link` 的固定变换来自随模型导入的 A2 URDF；其子 frame
`front_lidar_sensor_link` 仅校正仿真传感器的轴方向。该单雷达发布
`/lidar/points`，并投影为 `/scan`：局部 VoxelLayer 直接使用点云，SLAM、
AMCL、全局代价地图和 collision monitor 使用投影扫描。这是同一颗雷达的两种
消息表示，不是两颗传感器。不要增加第二颗仿真雷达或把雷达移动到机械臂安装板
上，除非实机传感器方案变更。

模型来源、可复现方式、仿真假设和实机安全限制见
[`atec_a2_p7_description/docs/MODEL_AND_SAFETY.md`](sim_src/src/atec_a2_p7_description/docs/MODEL_AND_SAFETY.md)。
