# M1 接口核查与部署准备

## 输入适配及新 SDK 说明补充

2026-09-12：软件时间映射、IMU SI/姿态有效性和原生 AIRY 输入已通过真实录包/在线验证，见 [AIRY 适配结果](ROAMERX.md)。后雷达硬件同步、LiDAR–IMU 标定与安装旋转仍未确认，`calibration.json` 保留 null，建图配置检查拒绝缺项。

新用户文档 [M1/L2 SDK 使用说明核查](SDK_MANUAL_REVIEW.md) 补充：高层 SDK 0.1.0 及以前使用 8081，0.1.1 使用 8082。该文档不定义我们当前 Zenoh 点云通路，也没有 SSH/雷达标定信息；“最新版”和截图设备信息均按历史示例处理。

## 最新实测：真实传感器已接通（19:45 后）

2026-09-12 19:45 起已接通真实前后点云和 IMU：狗内导航板 `192.168.168.100:7447` 的 Zenoh 服务 → 外接 Orin → `/m1_sensors/*`。接收数据不需要狗内板 SSH；建图、定位和运动尚未验收。

| 现有接口 | Orin 接收话题 | 实测频率 | 原始坐标系 |
| --- | --- | --- | --- |
| Zenoh `24/front_lidar/…PointCloud2_…` | `/m1_sensors/front/points_raw` | 约 10 Hz | `rslidar_head` |
| Zenoh `24/front_lidar/imu/…Imu_…` | `/m1_sensors/front/imu_raw` | 约 200 Hz | `rslidar_head` |
| Zenoh `24/rear_lidar/…PointCloud2_…` | `/m1_sensors/rear/points_raw` | 约 10 Hz | `rslidar_tail` |
| Zenoh `24/rear_lidar/imu/…Imu_…` | `/m1_sensors/rear/imu_raw` | 约 200 Hz | `rslidar_tail` |

完整键由 `zenoh_sensor_bridge.py` 的固定白名单生成。M1 控制 SDK 未公开点云接口；RoboSense SDK 提供雷达解码，本次复用了板内已发布数据。标准 ROS CDR 解码和独立 ROS 接收均已通过。

前雷达时间快约 153–154 秒，后雷达运行时长式时间跨采样回退；原始加速度为 g，姿态默认值不能用于姿态融合。完整外参、SLAM 字段/时间适配和可靠里程计仍待完成。证据与录包见 [导航记录](ROAMERX.md)。下面 17:37 表格为历史观察，不再代表实时传感器状态。

核查日期：2026-09-12（北京时间）。本文区分原始资料、网络实测和待确认项。SSH 登录、相机出图、SDK 握手和导航可用是不同的验收项。

## 17:37 后状态更新（用户移交 + 文件复核）

用户提供的新实测总结报告固件 0.2.4、8083 低层通信成功、8082 高层握手与通用状态可通，0.2.1 / 0.1.1 的关节订阅仍失败。本轮没有重复 SDK 握手；已读取 Orin 的历史日志与记录，确认低层约 48.3 Hz 的真实状态帧。因此下文早期“尚未握手”是当时本任务的验证范围，不能解释为设备无法连接。

| 导航准备项 | 最新状态 | 继续推进需要的证据 |
| --- | --- | --- |
| Orin 和狗内网络 | 已通；历史 SDK 状态已读取 | 板内身份/配置仍未通过 SSH 核验 |
| 底盘与 IMU 历史记录 | 两份共 24,550 帧，字段有限数与时间顺序通过 | 原记录缺加速度、关节速度及力矩；不能直接供导航使用 |
| 高层 SDK | 用户报告通用状态可读；本地 recorder 0.2.1 实见解析错误 | 验证匹配固件的速度、控制源和 IMU 字段，不能假设订阅成功 |
| 实时点云/IMU/里程计 | 17:37 ROS domain 0 观察 12 秒，均无样本 | 实际驱动、目的地址、端口、ROS 环境；也可先提供原始 PCAP 或含点云/IMU 的 rosbag |
| 坐标与时间 | 未完成 | 雷达安装旋转、IMU 对齐、设备时钟及同步方式 |
| RoamerX 输入适配 | 已定位代码缺口 | AIRY 真实字段和逐点时间；修复完整 TF、有效速度反馈及协方差语义 |
| 运动输出 | 保持隔离 | 前述验收通过后再验证高层速度转换、控制权和指令超时 |

历史复核证据见 `docs/evidence/recorded_state_audit.json`（本机仓库）；最新 ROS 观察见 `docs/evidence/orin_sensor_snapshot_current.json`。低层探针即使不发命令也会接管控制，不能作为非侵入在线检查。用户报告的 500 Hz 命令、力矩语义等不由这两份只有位置/姿态/角速度的文件独立证明。

## 原始 0、1、2 包复核

原编号由整理前备份内的路径核实，当前归档在本机 `vendor/archives/`。

| 原目录 | 原始文件 | 内容与用途 |
| --- | --- | --- |
| `0/` | `robot_sdk_lowlevel-0.0.1-ubuntu22.04-x86_64.zip` | x86_64 低层 SDK，现位于 `vendor/sdk/x86_64/` |
| `1/` | `ZG_M1_A0_V1_0.rar` | URDF、STL、ROS 1 展示文件和传感器位置表，现位于 `vendor/robot_description/ZG_M1_A0_V1_0/` |
| `2/` | `robot_sdk_lowlevel-0.0.1-ubuntu22.04-arm64.zip` | Orin 使用的 ARM64 低层 SDK，现位于 `vendor/sdk/arm64/` |

两份 ZIP 各 42 个条目，解压文件逐一与原包字节比对一致；RAR 共 43 个条目，其中 37 个普通文件逐一比对一致。已检查 SDK 中英文说明、头文件、示例及模型包表格，未找到 SSH 登录凭据、雷达驱动或建图定位程序。两个 SDK 包是相同接口的不同架构构建，不是高层和低层两套 SDK。

归档 SHA-256：

```text
37caf0a191449058a8c017a4c53cd3aca88af58b13794813af799af198b32490  robot_sdk_lowlevel-0.0.1-ubuntu22.04-x86_64.zip
bf0541be5481477ef43a6c1094324ce4e349bb8bd82142b79ddee0a1c93c3b3e  ZG_M1_A0_V1_0.rar
98517f548409615826a5eafe2d63c806b699279aad80047fcfb240377fba2cb0  robot_sdk_lowlevel-0.0.1-ubuntu22.04-arm64.zip
```

## 主机与协议

| 目标 | 资料说明 | 本次实测 / 限制 |
| --- | --- | --- |
| `100.68.24.27` | 用户提供的 Orin | 已以 `nvidia` 登录，主机名 `nvidia-desktop` |
| `192.168.168.168` | 官方 M1 网络文档中的运控主机 | Orin 可达，SSH 服务可达；尚未登录核验硬件和固件版本 |
| `192.168.168.100` | 官方 M1 网络文档中的导航主机 | TCP 22 返回 OpenSSH 横幅；角色仍需登录实机确认 |
| `.168:8554/front` | 头部相机 RTSP | 完整地址为 `rtsp://192.168.168.168:8554/front`；H.264、1920×1080、流标称 25 fps，连续解码 5 帧成功 |
| `.168:8081` | 官方 M1 高层 WebSocket | TCP 连接成功，尚未完成 SDK 协议握手 |
| `.168:8082` | 官方 M1 高层 UDP | 文档确认端口；尚未完成协议握手 |
| `.168:8083` | 原始 0/2 包的低层 UDP | 示例明确地址和端口；未调用 Initialize，未接管控制权 |

高层端口和双主机职责来源：[官方 M1 网络架构](https://github.com/zsibot/genisom_robot_sdk/blob/main/docs/en/sdk_network_en.md)。低层地址来源：本机 `vendor/sdk/arm64/docs/usage_zh.md` 的“最小示例”和“运行基础连通性示例”。这些资料不提供当前实机的 SSH 凭据。`nvidia` 只确认用于 Orin；已试凭据未通过狗内两台主机认证，不重复猜测，也不修改 SSH 服务。

Orin 实测路由经 `eth1`，源地址 `192.168.168.10`；网口另有 `192.168.25.100/24`、`192.168.234.10/24`。保持现有配置。一次 8 秒被动采样在 eth1 未捕获 `192.168.168.0/24` 的 UDP 包；这只描述该观察窗口，不能证明狗内部没有雷达流量。默认 ROS 发现环境只见 `/parameter_events`、`/rosout`，不能排除其他 domain 或主机上的节点。

相机测试使用现存脚本 `/mnt/nvme/pi05/ATEC-pi0.5/examples/airbot/check_cameras.py`，解释器为 `/mnt/nvme/pi05/official-20260910/robot-venv/bin/python`，只选择 RTSP 相机。没有连接 D405 或 AIRBOT。相机通过以太网取图，与 USB-CAN 机械臂控制独立。

## 原始传感器位置表

来源：本机 `vendor/robot_description/ZG_M1_A0_V1_0/中狗传感器位置信息.xlsx`，`Sheet1`，位置相对机身 **BASE 原点**，单位 **mm**。

| 传感器 | x / y / z（mm） | 原表范围和限制 |
| --- | --- | --- |
| 运控 IMU ICM42688 | `0 / 0 / 44.2` | A5:E5；V4 的 z 是 36.2，V5 以后为 44.2 |
| 车规 IMU LUA300C | `0 / 0 / 56.9` | A6:E6；备注“目前未开发固件”，不能预设可用 |
| 前 AIRY 雷达 | `404.3 / 0 / -37.7` | A7:E7；需规格书 |
| 后 AIRY 雷达 | `-404.3 / 0 / -37.7` | A11:E11；需规格书 |
| 前 IMX415 相机 | `412.3 / 0 / 37.8` | A8:E8；需规格书 |
| 后 IMX415 相机 | `-412.3 / 0 / 37.8` | A12:E12；需规格书 |

Sheet2、Sheet3 为空。表内没有安装旋转、雷达 IP/端口、驱动配置、点云字段或时间同步配置。上述为该模型的标称配置，实机版本、实际装配和传感器在线状态仍需核验。不要把表中毫米直接写入以米为单位的 TF，也不要把缺失的旋转填零。包内有传感器 STL，不代表 URDF 已建立对应传感器坐标系。

## 接入选择与下一步

1. **控制板与接口**：取得狗内主机正确登录方式后，只读核对主机型号、固件版本、已有服务、监听端口、驱动和配置文件位置。SDK 访问本身无需 SSH，但查看板内代码和现有传感器配置需要系统访问权限。原始 SDK 要求 RK3588 软件至少 v0.2.3、MidDogController App 至少 v1.1.7 且启用 Low-Level；这只适用于低层接入，不应为传统导航先开启低层。
2. **真实点云 / IMU**：优先检查 `.100` 上已有驱动及输出，确认 AIRY 型号、网络目的地址、ROS domain、话题、QoS、频率、时间戳单位、逐点时间、坐标系。高层 SDK 另有 IMU 上报接口，但不能预设它与雷达已同步。没有点云样本前不承诺 SLAM 兼容。
3. **建图定位**：RoamerX SLAM 默认 `/front_lidar`、`/front_lidar/imu`，定位默认 `/livox/lidar`、`/livox/imu`，导航默认 `/odom/mujoco_odom`。审查点类型与实测数据、时间同步和外参后再适配；不能只重命名话题。先录真实数据并离线回放，验收连续里程计、地图保存/加载和 TF `map → odom → base_link`。
4. **隔离规划和控制**：保留上游算法，禁用原来的执行器桥接，将导航速度输出接入仅记录的接收端。原桥接使用 UDP 43997/43988，不能仅改成 8082；M1 官方 `Move` 使用归一化输入和速度等级，与 ROS Twist 的 m/s、rad/s 不同。必须另行实现单位转换、指令过期停止和控制权检查，并用断流、异常数值、定位丢失等测试验证。
5. **现场低速实机**：前述验收通过后，由现场人员确认场地、急停和控制权，再单独执行运动测试。本次未启动真实传感器驱动或控制桥接；定位进程与导航插件仅做隔离软件检查，未发送真实运动命令。

原始低层 SDK 初始化和断开会切换控制权并清零电机参数，示例主动发送电机阻尼命令，不能作为只读探针。传统导航优先核对官方高层 SDK 与实机固件的兼容性；参考 [官方 SDK API](https://github.com/zsibot/genisom_robot_sdk/blob/main/docs/zh/sdk_client_api_zh.md)。Orin 上另有 `/mnt/nvme/atec/ATEC-locomotion` 的高层遥测采集代码可只读参考，但尚无本任务真实采集通过的证据，不能直接运行它的低层探针。

## 本轮新增定位结果（17:02–17:09）

- `.100` 两次 mDNS 反查为 `orin-nx.local`。已知 TCP 端口复测结果保存在 [网络实测](evidence/m1_network_snapshot.json)。板内 OS/硬件/固件及驱动目录仍需正确登录，主机名不是硬件型号证明。
- 本机到 Orin 已配置 Ed25519 公钥认证；`ssh nvidia` 与完整 IP 均已在全新连接下通过。未改动狗内两板的授权或网络。
- Orin domain 0 连续 12 秒观察没有点云、IMU 或里程计样本；TF 链不可用。见 [ROS 实测](evidence/orin_sensor_snapshot.json)。另一次 eth1 全 UDP 12 秒采样 0 包，不能据此排除交换机上流向其他主机的单播雷达数据。
- `third_party/genisom-robot-sdk` 的现有 Orin 路径是 `/mnt/nvme/atec/ATEC-locomotion/third_party/genisom-robot-sdk`；本地库版本 0.2.1，`ImuData` 没有设备时间戳。旧版握手/控制权行为需要单独核对，不运行带可选 `TakeControl` 的既有 observer 来证明被动观测。
- RoamerX 的 `Preprocess::process` 固定调用 Livox 解码；实际字段是 `timestamp/line/tag`，不能以参数枚举存在其他型号就认定支持 AIRY。SLAM 当前输出 `/slam_odom` 和 `map → body`；定位输出的速度固定为零。这些接入限制已记入 `AGENTS.md`，待真实数据后再实现适配。

RoboSense 官方提供 [AIRY 对应驱动配置](https://github.com/RoboSense-LiDAR/rslidar_sdk/blob/main/config/config.yaml)：型号选择 `RSAIRY`，IMU 解析需编译选项和非零 `imu_port`。其 [XYZIRT 字段说明](https://github.com/RoboSense-LiDAR/rs_driver/blob/main/doc/howto/18_about_point_layout_CN.md) 包含 `ring` 和逐点 `timestamp`，与 RoamerX 的 Livox 字段不同。[AIRY 手册](https://robosense-robotics.github.io/product-manual/en/Airy/) 提供 IMU 数据流、同步和标定数据说明。下一步优先读取 `.100` 的现有驱动配置，确认是否已有 AIRY 内置 IMU 数据流；不把官方默认端口、话题或标称外参写成当前机器的实测配置。

可复用检查工具：`m1_preflight/inspect_network.py`（只连接已知 TCP 服务）、`m1_preflight/observe.py`（仅订阅 ROS）和 `m1_preflight/board_inventory.sh`（取得正确 SSH 登录后，在板内读取身份、进程、端口和 ROS 环境）。

## 17:37–17:48 复核与准备结果

转发总结按参考资料处理。Orin 上两份已有 JSONL 分别为 5,800 / 18,750 唯一状态帧，约 48.3 Hz；16 关节角、姿态和角速度可读，缺少加速度、关节速度及力矩，不能直接替代导航 IMU。见 [历史文件审计](evidence/recorded_state_audit.json)。

最新 domain 0 观察仍无真实点云、IMU、里程计或 TF 发布。固件 0.2.4、高层 SDK 0.1.1 握手与 500 Hz 命令属于转发结论，本任务未重测；已有高层 0.2.1 日志有 current_state 解析失败和零样本。

软件侧完整 20 个导航包、AIRY 两包编译通过，匹配 OpenCV/cv_bridge 的依赖已修复，7 个导航节点隔离配置通过。配置与实机接入边界见 [导航验证](ROAMERX.md)。狗内导航板有效登录及雷达配置仍缺失，这是接通真实点云的当前阻塞。

- 2026-09-12 SDK 雷达接口复核：已检查 ARM64 低层 client.h/types.h、Orin 高层 0.2.1 与 0.1.1 的 sdk_client.hpp/sdk_callback.hpp/sdk_type.hpp，以及官方当前 API 文档，未发现公开的雷达点云/原始包订阅接口。高层 SetImuConfig/OnImuData 是 IMU，ObstacleAvoidance 是停障开关，不能代替点云。雷达数据走独立 RoboSense rslidar_sdk/rs_driver 或已有 ROS 发布链路；编译成功不代表已取得实机数据。

## 本次资料追查

见 [搜索范围与结论](evidence/calibration_search.json)。可读资料仍缺当前 M1 完整安装/内部 IMU 标定；狗内数据可读不等于已登录其文件系统。外接 Orin 网络对时已启用，但板内及雷达同步仍未确认。本机传输共享内存修复及三分钟逐帧通过结果见 [导航验收记录](ROAMERX.md)。
