# fishbot_xacro_description

这是一个 ROS 2 Jazzy + Gazebo Sim 8 的四轮小车仿真包。它用 Xacro 描述机器人，用 Gazebo 计算物理和传感器，用 ros2_control 驱动车轮，并可继续启动 SLAM 与 Nav2 导航。

新手先不要试图一次读完所有文件。推荐按下面顺序阅读：

1. `urdf/fishbot.urdf.xacro`：先认识小车由哪些零件、关节组成。
2. `launch/sim_world.launch.py`：理解 Xacro 如何展开为 URDF 并送入 Gazebo。
3. `config/controllers.yaml`：理解 `/cmd_vel` 为什么能让轮子转起来。
4. `urdf/plugins/gazebo_sensor_plugin.xacro`：理解 `/scan` 激光数据从哪里来。
5. `worlds/fishbot_world.sdf`：最后再修改仿真场景。

## 文件作用一览

```text
fishbot_xacro_description/
├── package.xml
├── CMakeLists.txt
├── README.md
├── urdf/
│   ├── fishbot.urdf.xacro
│   └── plugins/
│       ├── gazebo_control_plugin.xacro
│       └── gazebo_sensor_plugin.xacro
├── launch/
│   ├── display_robot.launch.py
│   ├── sim_world.launch.py
│   └── nav_slam.launch.py
├── config/
│   ├── controllers.yaml
│   └── nav2_params.yaml
├── worlds/
│   └── fishbot_world.sdf
├── scripts/
│   └── twist_odom_tf_bridge.py
└── rviz/
    └── display_robot.rviz
```

| 文件 | 作用 | 新手何时关注 |
| --- | --- | --- |
| `package.xml` | 声明包名和运行依赖，例如 `xacro`、Gazebo、Nav2。 | 构建或启动提示缺少包时。 |
| `CMakeLists.txt` | 安装 launch、URDF、配置、世界文件和 Python 脚本，使 ROS 2 能在 `install/` 中找到它们。 | 新增文件却无法被 launch 找到时。 |
| `urdf/fishbot.urdf.xacro` | 机器人主模型：车体、四个轮子、雷达、关节、质量、碰撞体，并调用两个插件宏。 | **最需要先读的文件**；改外形、尺寸、轮子位置时。 |
| `urdf/plugins/gazebo_control_plugin.xacro` | 定义 `ros2_control` 和 `gz_ros2_control` 插件，让 Gazebo 中的轮关节可被控制器读写。 | 小车不动、控制器无法加载时。 |
| `urdf/plugins/gazebo_sensor_plugin.xacro` | 定义 Gazebo 激光雷达，包括扫描范围、频率、话题及坐标系。 | 没有 `/scan`，或要修改雷达时。 |
| `launch/display_robot.launch.py` | 将 Xacro 展开后交给 `robot_state_publisher`，在 RViz 中仅检查模型与 TF，不启动 Gazebo。 | 改完模型后的第一步检查。 |
| `launch/sim_world.launch.py` | 完整仿真入口：启动世界、展开 Xacro、生成机器人、桥接 ROS/Gazebo 话题、加载控制器。 | **最需要重点理解的启动文件**。 |
| `launch/nav_slam.launch.py` | 在仿真基础上再启动 `slam_toolbox`、Nav2 与 RViz。 | 基础仿真正常后，再学习建图导航。 |
| `config/controllers.yaml` | 配置 `joint_state_broadcaster` 和 `diff_drive_controller`，包含轮半径、轮距、速度限制等。 | **小车运动效果不对时优先看**。 |
| `config/nav2_params.yaml` | Nav2 的代价地图、规划器、控制器等参数。 | 导航路径、避障或速度表现要调整时。 |
| `worlds/fishbot_world.sdf` | Gazebo 世界：物理系统、地面、墙和障碍物。 | 修改练习场地时。 |
| `scripts/twist_odom_tf_bridge.py` | 将常用的 `/cmd_vel` `Twist` 命令转为控制器需要的 `TwistStamped`。 | 自己发布速度命令但小车不动时。 |
| `rviz/display_robot.rviz` | RViz 的显示布局和 RobotModel 配置。 | 只影响 RViz 显示，不影响仿真本身。 |

## 最重要的三条链路

### 1. Xacro 如何变成仿真里的机器人

`fishbot.urdf.xacro` 不是 Gazebo 直接运行的程序，而是一份可复用的 URDF 模板。`sim_world.launch.py` 中会执行：

```bash
xacro fishbot.urdf.xacro robot_name:=fishbot
```

Xacro 会展开变量、四次轮子宏和两个插件文件，得到一段完整的 URDF XML；该结果保存为 `robot_description`。之后同一份 URDF 同时交给 ROS 和 Gazebo：

```text
fishbot.urdf.xacro
  -> xacro 展开
  -> robot_description（完整 URDF）
     ├-> robot_state_publisher：发布机器人各 link 的 TF
     └-> ros_gz_sim create：在 Gazebo 世界生成 fishbot 实体
```

因此，模型外观、碰撞、质量、关节都应先改 `fishbot.urdf.xacro`，而不是直接改 launch 文件。

### 2. 速度命令如何让小车运动

```text
/cmd_vel (geometry_msgs/Twist)
  -> twist_odom_tf_bridge.py
  -> /diff_drive_controller/cmd_vel (TwistStamped)
  -> diff_drive_controller
  -> gz_ros2_control
  -> Gazebo 中四个轮关节旋转
```

这里涉及三处文件：主 Xacro 文件提供轮关节名称；控制插件把这些关节交给 `ros2_control`；`controllers.yaml` 告诉差速控制器左右轮分别是哪几个、轮子多大、两侧轮距多宽。

### 3. 激光数据如何回到 ROS 2

```text
gazebo_sensor_plugin.xacro 中的 gpu_lidar
  -> Gazebo /scan
  -> ros_gz_bridge
  -> ROS 2 /scan (sensor_msgs/LaserScan)
  -> SLAM / Nav2 使用
```

`fishbot_world.sdf` 中的 `Sensors` 系统必须存在，否则模型虽然包含雷达配置，也不会实际生成传感器数据。

## 常用操作

构建并加载工作区：

```bash
conda deactivate
source /opt/ros/jazzy/setup.bash
cd /home/hezhou/公共/建模/sim_src
colcon build --packages-select fishbot_xacro_description --symlink-install
source install/setup.bash
```

先只检查 Xacro 模型：

```bash
ros2 launch fishbot_xacro_description display_robot.launch.py
```

启动基础仿真：

```bash
ros2 launch fishbot_xacro_description sim_world.launch.py
```

打开 Gazebo 图形界面：

```bash
ros2 launch fishbot_xacro_description sim_world.launch.py use_gui:=true
```

启动 SLAM 和导航：

```bash
ros2 launch fishbot_xacro_description nav_slam.launch.py
```

发送一条速度命令测试：

```bash
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.3}, angular: {z: 0.5}}"
```

## 修改需求时该找哪里

| 想修改什么 | 优先修改的文件 |
| --- | --- |
| 车体长宽高、轮子半径、轮子位置、雷达安装位置 | `urdf/fishbot.urdf.xacro` |
| 雷达量程、角度、频率 | `urdf/plugins/gazebo_sensor_plugin.xacro` |
| 小车最大速度、加速度、轮距、控制器参数 | `config/controllers.yaml` |
| 墙、障碍物、地面和物理世界 | `worlds/fishbot_world.sdf` |
| ROS 和 Gazebo 的话题桥接、生成位置、启动顺序 | `launch/sim_world.launch.py` |
| 建图和导航行为 | `config/nav2_params.yaml`、`launch/nav_slam.launch.py` |

## 排查顺序

模型改完却看不到：先运行 `display_robot.launch.py`，确认 Xacro 能正确展开。

模型能显示却无法生成到 Gazebo：检查 `sim_world.launch.py` 的 `ros_gz_sim create` 输出。

小车不动：依次检查 `/cmd_vel`、`ros2 control list_controllers` 和 `controllers.yaml`。

没有雷达：检查 `/scan`、`ros_gz_bridge` 输出，以及 `fishbot_world.sdf` 是否启用了 `Sensors`。

Gazebo GUI 出现 EGL 或图形库错误时，可先保持 `use_gui:=false`。仿真服务、话题桥和 RViz 仍可用于验证模型和导航。
