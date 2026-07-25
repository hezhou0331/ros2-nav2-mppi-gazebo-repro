# ROS 2 Jazzy + Gazebo + Nav2 MPPI 复现实验

基于 TurtleBot3 的二维导航复现实验，使用 AMCL、NavFn、Nav2 MPPI 和 VoxelLayer，在 Gazebo Sim 中完成差速机器人定位、全局规划与局部避障。

## 环境

- Ubuntu 24.04
- ROS 2 Jazzy
- Gazebo Sim 8
- TurtleBot3 Waffle
- Nav2 1.3

原始实验环境是 Ubuntu 22.04 + ROS 2 Humble。本仓库针对 Ubuntu 24.04 + Jazzy 验证；Nav2 核心流程相同，但用于目标 Humble 设备时仍需重新验证参数和接口。

## 安装

ROS 2 Jazzy 尚未安装时，先按照 ROS 2 官方文档添加软件源，然后运行：

```bash
./install_dependencies.sh
```

脚本会安装 Nav2、MPPI、SLAM Toolbox、点云投影、Gazebo bridge、RViz 和 TurtleBot3 仿真组件。

## 1. 启动仿真

本机 VS Code 是 Snap 版本。集成终端会继承 Snap core20 的 GTK/GIO 环境，直接启动 Ubuntu 24.04 的 RViz/Gazebo 会产生 `libpthread.so.0: undefined symbol: __libc_pthread_init`。因此请使用已经准备好的干净环境启动脚本：

```bash
./run_nav.sh
```

脚本会自动加载 ROS、设置 TurtleBot3 型号、清除 Snap 污染的动态库环境，然后启动 Gazebo、RViz 和 Nav2。

无图形界面测试时使用：

```bash
NAV_GUI=0 ./run_nav.sh
```

当前配置使用官方 TurtleBot3 世界和静态地图，局部控制器为 MPPI，局部代价地图包含 VoxelLayer。终端保持运行，不要关闭。

## 2. 其他终端中的 ROS 命令

只运行不带 GUI 的 `ros2 topic`、`ros2 action` 等命令时，正常加载环境即可：

```bash
source /opt/ros/jazzy/setup.bash
```

## 3. 在 RViz 中设置初始位姿和目标

1. 在 RViz 点击 `2D Pose Estimate`，在机器人当前位置点击并拖动，发布初始位姿。
2. 等待地图、激光、TF 和 AMCL 稳定，确认 `map -> odom -> base_link` 链路存在。
3. 点击 `Nav2 Goal`，在地图上点击目标位置并拖动设置朝向。
4. 观察机器人是否沿全局路径运动并绕开障碍；再次发送第二个目标，检查连续导航。

AMCL 没有初始位姿时会看到 `AMCL cannot publish a pose`，这是预期现象，不是 Gazebo 故障。

## 4. 命令行检查

新开终端并加载环境：

```bash
source /opt/ros/jazzy/setup.bash

ros2 topic list | grep -E '(^/scan$|/odom|/tf|cmd_vel|costmap|plan)'
ros2 topic hz /scan
ros2 topic echo /amcl_pose --once
ros2 lifecycle get /controller_server
ros2 param get /controller_server FollowPath.plugin
ros2 param get /controller_server FollowPath.batch_size
```

预期关键结果：

```text
FollowPath.plugin: nav2_mppi_controller::MPPIController
FollowPath.batch_size: 512
```

发送目标也可以使用 ROS 2 action（姿态四元数这里表示 yaw=0）：

```bash
ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose \
  "{pose: {header: {frame_id: map}, pose: {position: {x: 1.0, y: 0.0, z: 0.0}, orientation: {w: 1.0}}}}"
```

目标坐标必须位于地图可通行区域；不确定时优先使用 RViz 点击目标。

## 5. 当前参数与 demo2 的对应关系

`mppi_waffle.yaml` 已设置：

- MPPI DiffDrive 控制器
- `batch_size: 512`
- `iteration_count: 5`
- `wz_max: 0.8`
- `wz_std: 0.40`
- `PreferForwardCritic.cost_weight: 5.0`
- `visualize: false`
- 局部和全局 VoxelLayer
- NavFn 全局规划器，`use_astar: false`
- AMCL + 静态地图 + NavigateToPose

为了满足 Jazzy MPPI 的时间约束，控制频率设为 20 Hz，`model_dt` 为 0.05 秒。这样控制周期不大于模型步长，控制器可以正常激活。

## 6. 从官方 LaserScan 仿真迁移到 PointCloud2

当前 TurtleBot3 仿真默认提供 `/scan`（LaserScan），所以 VoxelLayer 的观测源也是 LaserScan。这已经能复现“MPPI 读取 Costmap、VoxelLayer 参与避障”的控制链，但还不是你记录里的 `/lidar/points` 三维点云链。

接入真实或自定义仿真的 PointCloud2 后，需要在 VoxelLayer 的观测源改为：

```yaml
observation_sources: points
points:
  topic: /lidar/points
  data_type: PointCloud2
  marking: true
  clearing: true
  obstacle_max_range: 3.0
  raytrace_max_range: 3.5
  min_obstacle_height: 0.05
  max_obstacle_height: 2.0
```

AMCL 仍然继续使用 `/scan`。如果只有 PointCloud2，没有 LaserScan，则保留 `pointcloud_to_laserscan` 节点把点云投影成 `/scan`，同时让 VoxelLayer 直接订阅原始点云。

## 7. 故障排查

- `AMCL cannot publish a pose`：在 RViz 发布 `2D Pose Estimate`。
- `libpthread.so.0: undefined symbol: __libc_pthread_init`：从 Snap 版 VS Code 终端直接启动了 GUI；改用 `./run_nav.sh`。
- `Controller period more then model dt`：确保 `controller_frequency >= 1/model_dt`；本配置是 20 Hz 与 0.05 s。
- 没有 `/scan`：检查 `TURTLEBOT3_MODEL=waffle` 和 Gazebo bridge 是否启动。
- 没有 `map -> odom`：确认 `slam:=False` 时使用的地图存在，并已经发布初始位姿。
- RViz/Gazebo 黑屏或很慢：先用 `headless:=True use_rviz:=False` 验证节点，再单独启动图形界面。
- 机器人不动：检查 `/cmd_vel`、控制器 lifecycle，以及是否把目标放在障碍物或未知区域。

## 8. 复现实验记录

每次实验建议保存：

```bash
ros2 bag record -o ~/bags/mppi_run /tf /tf_static /scan /odom /amcl_pose /plan /cmd_vel
```

记录参数文件、Gazebo 世界、目标点、成功/失败结果和导航耗时。先完成 10 次静态目标导航，再加入动态障碍和连续目标测试。

## 参数校验

```bash
./validate_config.sh
```

该检查验证 YAML 语法、MPPI 插件、关键低资源参数、20 Hz 时间约束以及 VoxelLayer 是否启用。

## 许可证

本仓库使用 Apache License 2.0。`mppi_waffle.yaml` 基于 TurtleBot3 Navigation2 的 Waffle 参数修改，详见 `NOTICE`。
