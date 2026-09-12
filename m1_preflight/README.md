# M1 真机前预检

2026-09-13 更新：[静止复检](../docs/STATIONARY_CHECK.md)的三分钟输入窗口通过，源端到接收的缺口仍有记录；完整预检因真实外参缺失退出 2，硬件同步未验收。以下历史结果按各自窗口解释。

上一轮结果：20 项录包故障检查、7 项 ROS 节点保护测试通过；真实预检因后点云 0.300004 秒间隔触发锁定，输入稳定性仍未通过。下文早期成功记录不代表当前整项验收通过。详见 [输入故障检查](../docs/INPUT_FAULT_TESTS.md)。

## 已新增输入适配

[AIRY 输入适配操作](airy_adapter/README.md) 包含时钟只读审计、固定偏移、IMU 单位转换、异常保护与原生解码构建。真实录包和 30 秒在线测试已通过；缺少真实外参时建图配置检查会拒绝。当前没有完成硬件同步与完整实机前置验收。用户新 SDK 文档的版本/控制权规则见 [文档核查](../docs/SDK_MANUAL_REVIEW.md)。

## 真实前后雷达接收（已验证）

Orin 已运行四路只读接收器；不用启动控制 SDK 或取得 `.100` SSH。先查看 `artifacts/real_sensors/bridge_status.json` 的更新时间、`seconds_since_receive` 与错误计数。状态是快照，进程异常退出时可能留下旧文件，不能只看 running 字段。

在 Orin 工作区首次准备或手动启动：

```bash
cd /home/nvidia/Workspace/ljy/navigation
/usr/bin/python3 m1_preflight/prepare_zenoh.py
bash m1_preflight/run_sensor_bridge.sh
```

重复启动会由进程锁拒绝；前台使用 Ctrl+C 停止。现有后台进程的 PID 存在 `artifacts/real_sensors/live_bridge.pid`，停它之前用 `ps -p <PID> -o args=` 确认是本工作区的 `zenoh_sensor_bridge.py`，再向该 PID 发送 TERM。未安装开机启动服务。

真实接口是 `tcp/192.168.168.100:7447`，原生 Zenoh 键前缀 24；依赖固定 Python Zenoh 1.10.1 私有 wheel。输出为 `/m1_sensors/{front,rear}/{points_raw,imu_raw}`，只在 ROS domain 0 / localhost-only / Fast DDS 下可见。独立观察应使用相同设置：

```bash
source m1_preflight/env.sh
ROS_DOMAIN_ID=0 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp   /usr/bin/python3 m1_preflight/observe.py --seconds 12 --output artifacts/real_sensors/observer_latest.json
```

原始点云约各 10 Hz、IMU 约各 200 Hz。接收器不改时间戳、frame 或 IMU 单位；前时钟快约 154 秒，后时钟存在运行时长式计时及跨采样回退，加速度单位 g、姿态默认。**这些 raw 话题尚不能直接送入 LIO/导航。** 后续要处理时间、SI 单位、完整外参与 RoamerX 字段适配。

实录 rosbag：`artifacts/real_sensors/bag_20260912_live/`（6.548 秒、2724 条）。验证证据见 [导航记录](../docs/ROAMERX.md)。本接收器没有运动输出。

功能与实现原理先读 [中文项目说明](../docs/PROJECT_GUIDE.md)，本页集中维护操作步骤。

这些工具同步到 Orin 的 `/home/nvidia/Workspace/ljy/navigation/m1_preflight`。
本机用 `ssh nvidia` 公钥登录。真实设备状态与待确认项以项目 `AGENTS.md` 为准。

## 只读检查

在 Orin 工作区执行：

```bash
cd /home/nvidia/Workspace/ljy/navigation
source m1_preflight/env.sh
/usr/bin/python3 m1_preflight/inspect_network.py --output artifacts/m1_network_snapshot.json
/usr/bin/python3 m1_preflight/observe.py --seconds 12 --output artifacts/orin_sensor_snapshot.json
```

观察器保留当前 ROS domain/RMW 设置，不会启动驱动、发布速度或调用 SDK。
报告含点云字段、消息数、接收频率、时间戳年龄和 TF 是否可查。
出现话题名不代表有数据，先看发布者数量和样本数；传感器时钟未同步时，时间戳年龄也需结合时钟配置解释。
点云样本未到达之前，不修改雷达目的地址、伪造逐点时间或发布假外参。

拿到狗内板卡的正确 SSH 账号后，可将 `board_inventory.sh` 通过已认证连接输入给板内 bash；它只读取设备、网络、服务、进程和选定 ROS 环境变量。
优先查 `192.168.168.100`（mDNS 名 `orin-nx.local`）上的现有雷达和定位配置。

## 独立依赖与构建

```bash
/usr/bin/python3 m1_preflight/prepare_dependencies.py
bash m1_preflight/build_cv_bridge.sh
bash m1_preflight/build.sh
```

依赖包版本与 SHA-256 固定在 `dependencies.lock.json`。
只使用现有官方 apt 源下载并解包到 `deps/`，不调用 apt install，不改系统库或服务。
`prepare_dependencies.py --check` 只校验缓存。
若官方源不再提供锁定版本，脚本失败并保留现场，不自动换版本。

新产物位于 `build_preflight/`、`install_preflight/`、`log_preflight/`。
旧构建目录含失效的迁移路径，不能继续拿它的缓存证明当前工程可构建。
OpenCV 使用独立的 4.8 开发包和运行库；LCM 用单独 CMake 查找模块导入。
系统 cv_bridge 链接 OpenCV 4.5，因此将官方 cv_bridge 3.2.1 固定源码编译到 `deps/cv_bridge/`，避免在同一导航进程混入两版 OpenCV。源码提交见 `cv_bridge.lock.json`。
导航使用 Humble 的 `/usr/bin/python3`（3.10）；转发资料中的 locomotion Python 3.11 虚拟环境属于另一工程，不在本导航终端加载。
重试失败包可执行 `bash m1_preflight/build.sh --packages-select robot_slam navigo_waypoint_follower robot_navigo`。

## 隔离导航配置

`prepare_preview.py` 从固定上游参数生成新的 YAML，要求显式给出：

- 已验证地图 YAML；
- 真实里程计和 LaserScan 话题；
- odom 与机身坐标系名称；
- 以米为单位、相对机身原点的实际外形多边形。

使用 `/usr/bin/python3 m1_preflight/prepare_preview.py --help` 查看参数。
它统一真实时钟、替换仿真里程计、修正地图持久订阅和速度平滑链路，并按给定外形设置膨胀范围。
生成参数用于预检；0.2 m/s、0.3 rad/s 是计算限值，没有做 M1 速度标定。

```bash
source m1_preflight/env.sh
ros2 launch m1_preflight/navigation_preview.launch.py params_file:=/绝对路径/preview.yaml
```

所有节点在 `/m1_preview`，生命周期默认不激活。
计算速度经过 `/m1_preview/cmd_vel_raw` 和 `/m1_preview/cmd_vel`，
启动文件没有厂商 UDP/LCM 桥接、SDK、模式切换发布器、雷达驱动或假 TF。
它不会建立实际整机速度控制通道。
真实传感器、TF、地图验收通过后，再按阶段进行规划/控制测试；现场运动另行确认控制接口和现场条件。

观察器的合成点云/IMU/TF 自测与定位进程的无输入加载检查均已在 Orin 隔离 ROS 域运行。
这些检查不等于已接通真实传感器，也不等于定位精度或运动验收通过。

## 历史低层记录核查

用户移交的 8083 通信结果可通过已存在的记录复核，不需要重新握手：

```bash
/usr/bin/python3 m1_preflight/audit_recorded_state.py   /mnt/nvme/atec/probe/stand_pose_150555.jsonl   /mnt/nvme/atec/probe/stand_pose_r2.jsonl   --output artifacts/recorded_state_audit.json
```

工具只读取文件，检查字段、有限数、重复/倒退时间戳及唯一帧频率，并保存源文件 SHA-256。退出码 0 只表示文件检查通过，不代表导航可用。现有两份记录为 5,800 / 18,750 帧，约 48.3 Hz；缺少加速度、关节速度和力矩字段，不能直接回放成完整导航 IMU。缺失量不会补零。

低层 probe 即使不发送运动命令，Initialize 也会接管执行器；不能为“验证在线”再次调用它。现有采集文件只支持历史通信证据，500 Hz 命令和力矩等结论另外来自用户移交总结。

## AIRY 官方驱动准备

驱动版本、子模块与消息包固定在 `airy_sources.lock.json`；补丁 `patches/rslidar_point_type.patch` 只将硬编码点类型改为可配置项。使用 XYZIRT 保留 ring 与逐点 timestamp，启用 IMU 数据解析。未修改解码协议。

在 Orin 工作区准备源码（默认放 `sensors/src/`）：

```bash
python3 m1_preflight/fetch_airy_sources.py
```

Orin 源码已放在 `sensors/src/{rslidar_sdk,rslidar_msg}`；在导航工作区运行：

```bash
bash m1_preflight/build_sensors.sh
```

构建仅在 `sensors/build`、`sensors/install`、`sensors/deps` 和 artifacts 写入；PCAP 开发包/运行库按版本和 SHA-256 下载后独立解包，不安装系统包。驱动编译不会打开雷达端口或接管机器人。

**尚未生成实机启动配置。** 官方默认配置是 RSM1，不能直接启动。拿到 AIRY 实测配置后，需填写 RSAIRY、MSOP/DIFOP/IMU 端口、绑定/组播地址、独立前后雷达话题、frame_id 与时钟策略；不要用默认端口猜测现有雷达配置。

验收时先查看实际 PointCloud2 字段与设备时钟，确认 IMU 加速度/角速度有效、点云与 IMU 时间重叠。前后两雷达分别验收，不把不同雷达时钟或坐标系混在一起。确认外参后再接 RoamerX 的预处理。

加载传感器库环境使用 `source m1_preflight/sensor_env.sh`；该脚本不启动驱动。导航环境 `env.sh` 和传感器环境分开，避免忘记加载 `rslidar_msg` 时误判动态库丢失。

## 软件预检结果

全量 20 个 RoamerX 包、AIRY 两个包已构建通过。`verify_preview.py` 在 Orin localhost-only / domain 176 使用合成地图，将七个导航节点逐一从 unconfigured 配置至 inactive，插件加载通过；没有激活控制器或发送目标。
速度平滑模块的独立合成指令验证显示输出限幅有效，输入中断后归零。完整证据见 `../docs/ROAMERX.md`。
这些结果不包含真实雷达、建图、定位精度或 M1 运动验收。

驱动获取脚本已验证全新目录与重复执行两种情况，证据 `../docs/evidence/airy_fetch_check.json`。现有 Orin 源码已经逐文件核对并补齐对应版本元数据。

## 每次建图前重新检查输入

在 Orin 导航工作区运行 `bash m1_preflight/airy_adapter/run_preflight.sh`，见 [AIRY 预检说明](airy_adapter/README.md)。自动刷新时间审计、观察三分钟并核查外参；原始接收器需先运行。当前缺少真实外参，整项预检应明确退出 2。入口不启动建图或运动。

## 实际规划服务与坐标链软件验证

`verify_planner_paths.py` 在 ROS domain 178 / localhost 激活地图和规划器，使用合成障碍地图测试 ComputePathToPose。没有启动控制器/厂商桥接。绕墙路径与墙内目标拒绝均通过；这比插件加载检查多验证了真实规划调用，但仍不是实机导航闭环。

```bash
source m1_preflight/env.sh
export ROS_DOMAIN_ID=178 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
/usr/bin/python3 m1_preflight/verify_planner_paths.py \
  --fixture artifacts/preview_config_fixture.yaml --output-dir artifacts/planner_paths
```

坐标链的方向、接口及 domain 179 测试入口见 [坐标准备](coordinates/README.md)。真实外参和全局定位缺失时，不把合成测试输入接到机器人。
