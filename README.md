# ATEC A2 + P7 | ROS 2 Nav2 + MPPI Gazebo Reproduction

> **ATEC 2026 导航仿真与验证仓库**
>
> 用一颗 A2 头部 3D 雷达，在 Gazebo 中复现 **点云投影、SLAM 建图、AMCL 定位、Nav2 规划、MPPI 控制和安全速度门**的完整闭环。

<p align="center">
  <img src="https://img.shields.io/badge/ROS%202-Jazzy-22314E?logo=ros" alt="ROS 2 Jazzy" />
  <img src="https://img.shields.io/badge/Gazebo-Harmonic-FF6F00" alt="Gazebo Harmonic" />
  <img src="https://img.shields.io/badge/Nav2-MPPI-0F766E" alt="Nav2 MPPI" />
  <img src="https://img.shields.io/badge/Platform-Unitree%20A2%20%2B%20P7-7C3AED" alt="A2 P7" />
</p>

## 一句话介绍

这是一个面向汇报和回归测试的导航系统复现工程：**传感器只接入导航计算机，Nav2 只输出安全速度，平台控制通过独立 adapter 隔离**。当前 Gazebo 运动部分是平面代理，用于验证导航软件链路，不代表真实 A2 步态控制器。

## 你可以展示什么

| 展示主题 | 仓库中的实现 | 汇报时的结论 |
| --- | --- | --- |
| 单雷达导航 | `/lidar/points -> /scan` | 一颗 3D 雷达同时服务 2D SLAM 和 3D 局部障碍层 |
| 建图与重定位 | `slam_toolbox` + `AMCL` | 建图、保存地图、重启后定位是两个明确阶段 |
| 全局与局部规划 | `NavFn` + `MPPIController` | 全局路径负责绕行，MPPI 负责实时跟踪和避障 |
| 安全控制 | `velocity_gate.py` | Nav2 不直连底盘，enable/ready/healthy 任一失效即归零 |
| 可重复验收 | `run_atec_end_to_end_demo.sh` | 自动巡航、保存地图、导航目标和 JSON 工件全部可审计 |

## 演示视频

### A2 + P7 仿真模型

<p align="center">
  <video controls width="720" src="https://cdn.jsdelivr.net/gh/hezhou0331/ros2-nav2-mppi-gazebo-repro@main/docs/media/atec_a2_p7_robot_showcase.mp4">
    A2 + P7 仿真模型视频
  </video>
</p>

<p align="center">
  GitHub 页面内直接播放；<a href="docs/media/atec_a2_p7_robot_showcase.gif">GIF 预览</a> · <a href="docs/media/atec_a2_p7_robot_showcase.mp4">下载完整 MP4</a>
</p>

该视频展示仓库中实际使用的 Unitree A2、背载 P7 机械臂与 UMI 夹爪组合模型。README 使用精简 GIF 自动预览，完整视频保留原始分辨率。

## 系统总览

```mermaid
flowchart LR
    L["单颗 A2 头部 3D LiDAR"] --> P["/lidar/points<br/>PointCloud2"]
    P --> V["局部 VoxelLayer"]
    P --> C["pointcloud_to_laserscan"]
    C --> S["/scan<br/>LaserScan"]
    S --> SLAM["slam_toolbox<br/>建图"]
    S --> AMCL["AMCL<br/>已知地图定位"]
    S --> SF["0.60 m 机体内部回波过滤"]
    SF --> GC["Global Costmap"]
    SF --> CM["Collision Monitor"]
    O["/odom<br/>Gazebo/LIO"] --> TF["TF: map -> odom -> base_link"]
    SLAM --> TF
    AMCL --> TF
    TF --> GC
    GC --> NF["NavFn<br/>全局规划"]
    V --> LC["Local Costmap"]
    LC --> MPPI["MPPI<br/>局部控制"]
    NF --> MPPI
    MPPI --> VS["Velocity Smoother"]
    VS --> CM
    CM --> CMD["/cmd_vel"]
    CMD --> G["velocity_gate<br/>限速 + 超时归零"]
    G --> PC["/platform/cmd_vel"]
    PC --> A["platform adapter"]
    A --> SIM["/sim/cmd_vel<br/>Gazebo proxy"]
```

### TF 责任边界

```mermaid
flowchart LR
    M["map"] -->|slam_toolbox 或 AMCL，二选一| D["a2/odom"]
    D -->|Gazebo 里程计；实机由 LIO/融合里程计| B["base_link"]
    B --> X["front_lidar_link"]
    X --> Y["front_lidar_sensor_link"]
```

同一时刻只能有一个节点发布 `map -> a2/odom`。建图阶段使用 slam_toolbox，导航阶段使用 AMCL；平台 adapter 不得发布定位 TF。

## 关键设计

### 一颗雷达，两种数据表示

`/lidar/points` 是原始 3D 点云：用于局部 VoxelLayer，保留高度信息。`/scan` 是从同一颗雷达投影出的二维扫描：用于 slam_toolbox、AMCL 和全局代价地图。投影高度带为 `-0.50 ~ 0.12 m`，最小量程 `0.40 m`，用于过滤 A2/P7 自身回波。

### Nav2 不直接控制机器人

```mermaid
sequenceDiagram
    participant N as Nav2 / MPPI
    participant G as velocity_gate
    participant A as platform adapter
    participant R as Robot/Gazebo
    N->>G: /cmd_vel
    G->>G: 检查 enable + ready + healthy
    G->>A: /platform/cmd_vel（限幅）
    A->>R: 厂商协议或仿真命令
    Note over G,A: 指令超过 200 ms 未更新时持续输出零
```

`velocity_gate` 的默认仿真限速为 `0.15 m/s` 和 `0.25 rad/s`。这套边界可复用到实机，但 `simulation_platform_adapter.py` 和 Gazebo `VelocityControl` 不能用于真实 A2。

## 目录结构

```text
ros2-nav2-mppi-gazebo-repro/
├── src/independent_nav_bringup/
│   ├── launch/                 # mapping.launch.py / navigation.launch.py
│   ├── config/                 # SLAM、AMCL、Nav2、MPPI 参数
│   ├── scripts/                # gate、health、任务编排、仿真 adapter
│   ├── platforms/              # A2 + P7 / X30 平台契约
│   └── rviz/                   # 建图与导航 RViz 配置
├── 建模/sim_src/                # A2 + P7 URDF、网格、雷达、练习场
├── maps/                       # 保存后的 PGM/YAML 地图
├── docs/END_TO_END_DEMO.md     # 自动闭环与录屏验收
├── run_mapping.sh              # 启动建图
├── run_navigation.sh           # 启动定位与导航
└── run_atec_end_to_end_demo.sh # 一键回归演示
```

## 支持环境

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Ubuntu 24.04 LTS（推荐原生安装） |
| ROS 2 | Jazzy Jalisco |
| 仿真器 | Gazebo Harmonic / Gazebo Sim 8 |
| 导航 | Nav2、NavFn、MPPI Controller、SLAM Toolbox |
| 构建工具 | `colcon`、CMake、Python 3 |

仓库按 ROS 2 Jazzy 的 Debian 软件包进行安装和验证。其他 Ubuntu/ROS 版本需要自行调整软件包名称和依赖，不属于当前复现基线。

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/hezhou0331/ros2-nav2-mppi-gazebo-repro.git
cd ros2-nav2-mppi-gazebo-repro
```

后续命令均在仓库根目录执行，不依赖固定用户名或安装路径。

### 2. 安装依赖

先按照 [ROS 2 Jazzy Ubuntu 安装文档](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html) 配置 ROS 2 软件源，然后执行：

```bash
./install_dependencies.sh
```

该脚本安装 ROS 2 Desktop、Nav2、MPPI Controller、SLAM Toolbox、`ros_gz`、`gz_ros2_control`、机器人状态发布和 Xacro 等运行依赖。

### 3. 构建并验证

```bash
./build_atec_a2_p7_nav.sh
./validate_atec_a2_p7_nav.sh
```

构建脚本会自动定位仓库根目录，因此仓库可以放在任意用户目录。验证脚本检查包结构、模型、TF、启动配置和导航参数。

### 4. 启动建图

```bash
./run_mapping.sh use_gui:=true
```

在仿真中完成一圈巡航后保存地图：

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run independent_nav_bringup save_map.py \
  --output "$PWD/maps/atec_practice_world"
```

### 5. 启动 AMCL + Nav2

```bash
./run_navigation.sh \
  "$PWD/maps/atec_practice_world.yaml" \
  use_gui:=true
```

在 RViz 使用 `2D Pose Estimate` 初始化 AMCL，再使用 `Nav2 Goal` 发送目标。默认出生点为 `(-5.8, 0, 0)`。

### 6. 一键闭环演示

```bash
./run_atec_end_to_end_demo.sh
```

脚本自动完成：

```mermaid
flowchart LR
    A[启动仿真建图] --> B[自动巡航采集扫描]
    B --> C[保存并验证地图]
    C --> D[停止建图栈]
    D --> E[重启 Gazebo + AMCL + Nav2]
    E --> F[发送两个 NavigateToPose 目标]
    F --> G[生成 JSON 验收报告]
```

工件写入 `artifacts/atec_demo_<UTC时间戳>_<PID>/`，重点查看：

- `run_report.json`：总流程、失败阶段、ROS/Gazebo 隔离信息
- `map_validation.json`：地图尺寸、已知像素、占用像素
- `mapping_patrol.json`：巡航航点和到点误差
- `navigation_mission.json`：目标状态和最终位姿误差
- `demo_report.json`：完整闭环验收结论

## 实机边界

本仓库验证的是导航软件闭环，不是 A2 的真实运动学。以下内容进入实机前必须重新完成：

- `base_link -> lidar` 实测外参和时间同步
- LIO/融合里程计及 `odom -> base_link`
- A2 官方连续速度接口、自动模式和手柄抢占
- 200 ms 内 watchdog、实体急停和通信丢失策略
- P7 安装板载荷、重心、footprint 和限速
- 扫描匹配、回环检测、AMCL 噪声参数和地图质量

因此，本仓库适合仿真、录包、离线回放、规划验证和汇报演示；在完成平台 adapter 与 G1-G6 验收前，不得连接实体 A2。

## 进一步阅读

- [自动闭环与录屏验收](docs/END_TO_END_DEMO.md)
- [平台 adapter 契约](src/independent_nav_bringup/docs/PLATFORM_ADAPTER_CONTRACT.md)
- [A2/P7 模型与安全边界](建模/sim_src/src/atec_a2_p7_description/docs/MODEL_AND_SAFETY.md)
- [模型来源与许可证](建模/sim_src/src/atec_a2_p7_description/docs/MODEL_PROVENANCE.md)

## License

详见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。
