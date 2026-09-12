# M1 / ORIN 项目协作

## GitHub 完整交接（2026-09-13）

- 用户明确上传整个项目、全部代码、从连接到当前的历史尝试，供他人接手。交接入口 `docs/HANDOFF.md`，当前说明 `docs/CURRENT_STATUS.md`。分支 `m1-navigation-preflight-20260913`，Release 标签 `m1-preflight-20260913`；发布完成情况以 GitHub 实际状态为准。
- 仓库包含厂商原始包、两架构 SDK、模型和说明书；Release 包含固定源码、两份真实录包/CDR、成功与失败日志、构建日志及 ARM64 依赖缓存。未导出 SSH 私钥/密码或其他工程代码。文件和附件 SHA-256 已核对。
- 新增 `scripts/prepare_workspace.py` 补齐新克隆缺少的 src/sensors/src 路径，支持固定缓存离线准备；干净目录及重复执行通过。`scripts/check_handoff.py` 核对 101 份厂商资料及数据入口。重新解压数据后 21 项基础检查和 20 项故障回放通过；未声称重新安装全新 OS 后全量编译。


## 静止检查复核（2026-09-13，优先于下方历史状态）

- 用户授权独立连续性、可读配置、时钟和静态几何检查；需要物理测量、移动标定或建图采集时通知。未建立 SDK 会话、未发布运动、未启动建图。
- 开始时接收器已因后 IMU `source_publisher_changed` 锁住；保留 `source_change_before_stationary.json`。60 秒独立源观察发现四路 GID 均已不同于旧记录，窗口内新 GID 各自稳定、无重复/回退，后雷达计时起点改变。支持源发布者重建/重启的可能，不能确定是哪个进程或整机重启。
- 确认来源稳定及无本任务 SLAM/适配进程后，仅显式重启自己的接收器，重新审计时钟；没有修改狗内服务、网口或系统时间。接收器新增有界最近 20 次缺口、回调/发布最大耗时及故障源身份记录。
- **本次 180.108 秒输入窗口通过**：点云前/后 9.95984/9.95962 Hz，IMU 199.879/199.865 Hz；内部原始唯一帧 1723/1723/34576/34575 均找到适配输出，缺失 0、无适配故障。窗口内最大点云间隔约 200 ms、IMU 20 ms。完整预检仍因四组真实外参缺失退出 2；不是建图或整机准备通过。
- 源端到接收之间缺口仍存在：接收器重启后的准备阶段又记录后点云 0.299999 秒间隔（在正式适配窗口之前）；不得用上述窗口通过覆盖既有 300 ms 故障，`source_gap_root_cause_fully_resolved=false`。静态直接源观察缺失序号数前点云 3、后点云 2、两 IMU 各 5，未见连续序号下大时间缺口。
- Orin eth1 累计 errors/dropped/missed 仍为 0，不能据此排除发送队列、Zenoh 或应用层问题。新增回调统计显示此接收器本窗口点云回调最大约 23 ms、发布约 5 ms；不能凭此唯一归因源端。
- 两轮只读时钟审计相距 421.178 秒，板间偏移从约 -152.5564 秒变为 -152.5827 秒，变化范围 -28.506 至 -23.971 ms；不是单一永久常数，不能推断是哪台钟调整或当作硬件同步误差。Orin NTP 显示同步，仅证明 Orin 自身状态。600 秒软件 profile 不代表长期同步精度保证。
- 新静止采样前/后 IMU 加速度模长中位数约 1.0022/0.9995 g，方向靠近原始 +Y（偏角约 1.25°/2.35°）。陀螺平均向量非零，可能含零偏，未直接减去或当作真实旋转速度。原始 frame 共名不证明轴对齐，不能套机身 +Z。
- 前后各 20 份 CDR，0.2–15 m 内有限点约 2.18万–2.75万。前雷达主要平面离原点约 0.685–0.696 m、法向接近 -Z；后雷达主平面多接近 -X。平面未标注地面/墙体，不据此写外参。首版新探针组织点云轴拼接错误已修正为 height×width×xyz 展平，同批 CDR 重算并通过已知倾斜平面验证；生产转换未受影响。
- 重读可访问标准参数和 tf_static：rslidar 参数服务仍超时，其他节点仅常规参数；静态边仍只见默认 map→odom，没有雷达安装变换；未取得设备 DIFOP。没有登录 .100 文件系统，不能说已查遍板内配置。完整静止报告见 `docs/STATIONARY_CHECK.md`。
- 当前本任务有限时适配器已正常停止（state=stopped），原始接收器继续只读运行，PID 以远端 pid 文件并核对 cmdline 为准。接下来需设备标定/驱动配置可读入口或现场安装测量，之后才考虑移动标定和建图采集。


## 最新输入缺口与保护状态（优先于早期通过记录）

- 用户明确本轮先完成缺口定位、运行保护、故障回放，现场测试后续配合；未授权本轮运动。结果汇总 `docs/INPUT_FAULT_TESTS.md`。
- `audit_gaps.py` 用 180 秒设备时间/发布序号/发送时间/独立 ROS 接收对照。前点云/前 IMU/后点云/后 IMU 发现序号缺口事件 35/51/11/63；缺失序号数 37/158/12/181，其中其他接收链在对应时间区间收到 6/102/7/111 个样本。全部异常为序号缺口，没有连续序号下的设备时间断档；仅定位到序号分配到探针之间，尚不能唯一归因发送队列、Zenoh 或客户端，不能宣称物理雷达漏采。双路探针增加负载，数据仅适用于该窗口。
- 线上改用 `AdapterEngine` / `InputGuard`：四路有效后才输出，独立定时检查；IMU 静默 100 ms、点云静默 350 ms、相邻接收样本设备时间差 50/250 ms 超限均锁定全部适配输出。错 frame/字段/非有限数据、回退重复、主机跳时、过期 profile 和发布者变化也锁定，数据恢复不自动清除。
- 时钟 profile 最多 600 秒；启动等待 5 秒。消息年龄 IMU ≤250 ms、点云 ≤500 ms，允许超前最多 50 ms。阈值是软件预检界限，不是硬实时或建图精度验收。每轮循环最大空闲等待 10 ms，Linux 调度可使实际检测更慢。
- Humble 已安装 rclpy 不支持带 MessageInfo 的双参数回调，底层 take_message 的信息也仅含发送/接收时间；已修复为单参数回调 + ROS 发现图唯一发布者 GID 检查，不能称逐消息来源认证。首次失败日志保留 artifacts/fault_ros；修复后 artifacts/fault_ros_fixed 全部通过。
- 原始 Zenoh 接收器增加逐消息 attachment GID/序号核查。源 GID 改变、序号重复/倒退或解析错误锁住原始转发，状态包含 forwarding_enabled/source_fault/source_gid/sequence_gaps；序号缺口只记录。已核对进程身份后显式重启自己的接收器，未重启狗内服务或 SDK；原脚本/状态备份在 artifacts/real_sensors/bridge_before_source_guard.*。
- 真实 12264 条基线及故障回放共 20 项通过（含未来配置、设备时钟突跳）；实际 ROS domain 180 七项故障测试通过，IMU 断流实测 101.2 ms，所有故障后队列排空再观察无新输出，数据恢复不自动续发。原 11 项适配检查也通过。
- **新版真实三分钟输入预检未通过稳定性**：约 126 秒时后点云出现 0.300004 秒间隔，超过 0.25 秒阈值并锁住输出。最终前/后点云输出 1233/1258、IMU 25273/25264，有限时进程随后结束。保护按预期生效，但不能把这次结果记成稳定性通过；不要用先前无此保护的通过结果覆盖当前故障。
- 原始接收器继续运行，forwarding_enabled=true、source_fault=null；适配器已退出且故障状态保留。恢复必须先排查原因、结束旧定位/建图、显式重启所需进程、重新审计时钟并初始化，不能只清空故障字段。run_preflight.sh 现在先拒绝不新鲜/已锁定的原始接收状态。
- 新证据 `gap_audit.json`、`fault_replay.json`、`fault_ros.json`、`guarded_preflight.json`、`guarded_adapter_status.json`、`guarded_bridge_status.json`。真实外参、同步状态及现场定位仍未验收，hardware_preflight_complete=false。


## 最新独立准备验证（2026-09-12）

- 用户授权继续独立完成资料检索、源码核查、适配、录包分析、预检、坐标链接入及隔离规划，现场操作留到准备确认后；没有运动授权、未触发 SDK/标定动作。
- 新增 `m1_preflight/coordinates/`：按实际外参计算 base←IMU、map←base、map←odom，限定 localhost/domain 179 私有 TF 图。6 项几何测试与 ROS 消息验证通过（401 条变换、2 条静态边、时间回退拒绝）；使用真实缺项 calibration.json 会在创建 ROS 节点前退出 2。它是可执行软件准备，**不是实机坐标链已经接通**。
- 新增 `verify_planner_paths.py`：localhost/domain 178 仅启动地图和规划器；真实 RoamerX ComputePathToPose 服务给出绕墙路径 292 点/14.65 m，点级占用检查无碰撞，墙内目标正确 aborted；根速度话题无发布者。不是实际地图或控制器闭环验收。
- 新录包命令持续 30 秒，NVMe `artifacts/real_sensors/bag_before_mapping_30s` 实际 12264 条消息：前后点云 291/292、IMU 5841/5840。全部转换通过，逐点相对时间误差仍 ≤0.477 μs；IMU 无重复/回退，内部覆盖点云最少 13/14 条 IMU。各一路有一次 >15 ms 间隔，最大 40/35 ms；前点云最大间隔约 0.20 秒。不能将单位/格式通过描述为源采样连续性完全通过。
- 新录包的两个 CDR 经原生 AIRY C++ 路径通过。验证器新增间隔统计，后续导出 CDR 位于每个报告独立的 `<stem>_cdr/` 子目录。
- AIRY 固定驱动 `decoder_RSAIRY.hpp::decodeDifopPkt` 明确读取出厂 IMU quaternion/translation 到 device_info，可通过 `LidarDriver::getDeviceInfo` 取得；当前 ROS 四路原始消息不携带这些字段。新增纯文件 `extract_airy_difop.py` 和 4 项测试，保留未核实标志、不自动生成实机外参。既有 PCAP 仅 24 字节头，未找到 DIFOP。
- 只读 TF 缓存查询没有返回安装变换，实时 tf_static 仍只有默认 map→odom。收到 21 字节 ArcModuleState 消息，但当前上游没有对应 IDL，因此只统计长度，未解读或执行 perception_calibration_cmd。没有把“收到标定状态”写成“标定完成”。
- 复核已存真实 mc_odom/current_pose CDR：父 odom、子 base_link，有 twist 数值；这是历史样本，物理单位、动态精度和新鲜时间接入仍未验收。不能拿 current_pose 的 odom 父坐标冒充全局 map 位姿。
- 上游 SLAM 的 map/body 位姿由 IMU 状态给出；其 covariance 在 publish 之后更新，定位还混用置信度/协方差及零 twist。坐标适配仅消费位姿，不复制这些值作为标准速度/协方差，未修改上游源码。
- 新搜到厂商公开 zsibot_roamerx_lite 的 SLAM 配置仍是 Livox 类型/4 线与既有外参，不作为 AIRY 标定；odometry_calibration.xml 是实际走方形的动作树，未运行。CyanTempest/Navigation 仍不可读取，没有切换导航栈。
- 新增证据 `coordinate_ros_check.json`、`planner_paths.json`、`bag_before_mapping_30s_check.json`、`bag_before_mapping_native.jsonl`、`calibration_routes.json`、`difop_search.json`、`odom_samples_audit.json`。21 项单元检查通过（11 适配 + 6 几何 + 4 DIFOP）；hardware_preflight_complete 仍为 false，实机外参、驱动变换配置、同步状态及实际定位链是剩余缺口。


## 建图前复检与传输修复（最新，2026-09-12）

- 新增 `m1_preflight/airy_adapter/run_preflight.sh`：刷新时钟审计、180 秒有限时适配、逐帧检查、外参检查；输入/外参缺项返回 2，不启动建图或控制 SDK。原始接收器需先运行，预检只关闭自己启动的适配子进程。
- 复核旧接收器约 2.5 小时数据：点云约 9.83/9.92 Hz，IMU 199.52/199.40 Hz，累计无解析错误/重复/时间回退。该结论仅限连续窗口，不推翻此前后雷达跨采集时间回退的记录。
- 实测默认 Fast DDS 共享区约 512 KiB，小于约 2 MB 点云。修改前 180 秒检查，前/后点云窗口内缺少对应适配输出 126/272 帧。新增 `m1_preflight/fastdds_sensors.xml`：64 MiB SHM、8 MiB 单消息、2048 队列、关闭内置网络传输。只用于我们接收器/适配器/预检进程，没有修改系统 sysctl 或狗内服务。
- 已核对 `/proc/PID/cmdline` 后正常停止并重启自己的原始接收器，保留 `bridge_before_shm.json`；该人工重启产生计数重置，不是设备时钟回退。新 PID 仍以远端 `artifacts/real_sensors/live_bridge.pid` 为准。
- 修改后 180 秒逐帧观察通过：前/后点云 9.9607/9.7660 Hz，IMU 199.4540/199.3128 Hz；去首 5 秒、尾 2 秒后的 raw 唯一帧 1723/1690、IMU 34505/34478，全部找到校正输出对应帧，缺失为 0，适配错误/时钟故障为 0。此为本机接收后链路验收，不宣称源端无丢失：原始点云最大间隔约 0.20 秒，IMU 最大约 45/35 ms。
- 原始接收器继续运行，有限时适配器已退出。根速度话题计数为 0 的结论仅限预检进程可发现的共享内存 ROS 图；不表示狗内或其他传输不存在控制流。本任务没有建立运动链路。
- 搜索记录 `docs/evidence/calibration_search.json`：本机 SDK、模型、微信说明、参考资料以及外接 Orin 可读配置均未找到可核实为本 M1 的完整外参。Orin 的 `ros2_ws/src/fastlio_terrain_navigation` 是 X30 参考工程，未改动、未复用其 0.826 m 安装参数。未登录狗内 .100，不能声称已查过它的文件系统。
- Orin 实测 `NTP=yes`、`NTPSynchronized=yes`，由 systemd-timesyncd 对时；这不能证明板内/雷达同步。最新软件板间偏移约 -153.366 秒，区间半宽 0.923 ms，不代表传感器精度。时钟 profile 仍只有 600 秒有效期。
- 11 项适配测试复跑通过，预检整项退出 2，原因是真实外参缺失；`prepare_mapping.py` 拒绝生成配置。当前 `input_transport_passed=true`，但 `mapping_ready=false`、`hardware_preflight_complete=false`。待取得前雷达完整 base←LiDAR、IMU←LiDAR 以及同步/时延依据后才能完成建图准备验收；双雷达融合还需后雷达标定与相对时差验证。
- 证据：`docs/evidence/live_preflight_before_shm.json`、`live_preflight.json`、`bridge_before_shm.json`、`calibration_search.json`。历史 7.6 Hz 适配记录由本次修复后的窗口更新，不能再作为当前传输效果。

## 最新输入适配状态（2026-09-12，优先于后续早期记录）

- 已实现并验证 `m1_preflight/airy_adapter/`：真实数据的软件时间映射、加速度 SI 转换、无姿态标记、独立 IMU frame，以及 RoamerX 原生 AIRY XYZIRT 解码。**尚未确认实机外参及硬件同步，真机导航前置准备未全通过。**
- 时间审计通过 Zenoh 只读 GetParameters 响应的发送时刻估计板间偏移，并保存原始测量；没有改 Orin/狗内系统时钟或雷达同步配置。初次板间偏移约 -153.388 秒，复测约 -153.381 秒；复测时差区间半宽约 0.77 ms，仅是板间时间测量范围，不能视为传感器同步精度。
- `prepare_clock_profile.py` 同雷达点云/IMU 共用固定偏移。后雷达相对时钟原点通过两路 IMU 发布时间估计，驱动延迟差的系统误差未知，`hardware_synchronized=false`、`cross_lidar_fusion_ready=false`。不能用它宣称双雷达精确同步。配置有效期 600 秒；回退、重复、跳变、主机时钟改变或过期会停止输出。
- IMU 加速度乘 9.80665，协方差乘其平方；角速度仍为 rad/s。orientation_covariance[0]=-1 表示未提供姿态；改用 `rslidar_head_imu` / `rslidar_tail_imu`，不伪造到点云/机身的 TF。RoamerX 内部另有重力模长归一化，已记录，不能再次无条件乘重力。
- AIRY 适配新增类型 5，明确读 x/y/z/intensity/ring/timestamp（绝对秒），有限点及 96 线检查后按时间排序，curvature 写帧内毫秒。排序必须在 syncData 使用最后点时间前完成。未伪造 Livox tag，未直接复用 avia_handler。
- 原上游保持不变：Orin `src/slam/src/src/mapping_alg.cpp` 与本机固定 checkout SHA-256 都为 cf57f712b1ff43a3344d1927f577e1c99a48ee1a0bebf517d0c00b3dd1d2746e。补丁应用于 Orin `src_airy/robot_slam`，安装 `install_airy/robot_slam`；robot_slam 及原生 CDR 验证程序编译成功（3min25s），不覆盖原 20 包安装树。
- 11 项软件测试通过，包含 SI/协方差、原始数据不变、时钟回退/重复/跳变锁定、错误外参与字段拒绝。完整真实录包 2724 条转换通过，122 帧点云每帧至少 18 条同雷达 IMU，帧内时间最大误差 0.477 微秒。原生 C++ 四份 CDR 输入通过，错字段/错时间拒绝通过。
- 30 秒在线适配收到前/后 IMU 5965/5969、点云各 258，错误和时钟故障为 0；独立观察校正后年龄为 IMU 15–17 ms、点云约 155 ms。观察到点云约 7.6 Hz，少于源端约 10 Hz，不能宣称全链路无丢帧。适配测试进程已退出，原始接收器继续运行。
- 只读订阅狗内 TF 得到 map→odom 与 odom→base_link，没有雷达/IMU 安装变换；标准参数读取未得到外参，rslidar param_handle 超时。不能把已发现 TF 误写为本机导航 TF 验收完成。
- `calibration.json` 只保存厂家标称机身平移 ±0.4043/0/-0.0377 m；base←lidar 旋转与 imu←lidar 变换仍为 null。`prepare_mapping.py` 会拒绝缺少核实标定和来源；当前拒绝已验证。不得把 URDF collision 的零旋转、旧 Livox 外参或默认单位矩阵写成实机标定。
- 新收到并归档 `vendor/manuals/M1_L2_SDK_guide.docx`，SHA-256 ff439a5f700102b7b79b277cdd89fe604ef3028c0197c8dd50937482a29b6b05。完整阅读 14 页/18 图，记录 `docs/SDK_MANUAL_REVIEW.md`：文档的高层 0.1.0 及以前为 8081、0.1.1 为 8082；0.1.1“最新版”为历史说法。说明书明确控制权互斥和 z 站立动作，不能运行 example_control 当只读探针。
- 新说明书没有 SSH 登录、点云接口、同步配置或安装外参；其中固件截图是示例，不能证明本机固件。现有 eth1 直连无需复制文档 Wi-Fi 路由操作。通用 ShakeHand failed 不能单独证明控制权占用。
- 所有适配结果见 `docs/evidence/airy_adaptation_readiness.json`、`adapter_recording_check.json`、`adapter_live_observer.json`、`native_airy_check.jsonl`、`clock_audit_summary.json`。完整前置验收仍等待实机安装标定与雷达同步状态/误差依据；没有运行建图或运动。

## 当前实机状态（2026-09-12 19:45 后，优先于下文历史记录）

2026-09-12 19:45 起已接通真实前后点云和 IMU：狗内导航板 `192.168.168.100:7447` 的 Zenoh 服务 → 外接 Orin → `/m1_sensors/*`。接收数据不需要狗内板 SSH；建图、定位和运动尚未验收。

- 已检查本机原始 0/1/2 包、低层 ARM64/x86 SDK 和 Orin 高层 0.2.1/0.1.1 头文件：M1 控制 SDK 没有公开点云订阅接口。此次通过现有 Zenoh 数据服务接入，不是低层 SDK 握手或新启动雷达 UDP 驱动。
- 确认端点 `tcp/192.168.168.100:7447`；源键前缀 `24`，实测键形如 `24/front_lidar/sensor_msgs::msg::dds_::PointCloud2_/TypeHashNotSupported`。四个源名是 `front_lidar`、`front_lidar/imu`、`rear_lidar`、`rear_lidar/imu`。这是读取的实际键，不等同于已登录确认板内 ROS 配置。
- `m1_preflight/zenoh_sensor_bridge.py` 仅订阅以上四路，转发到 `/m1_sensors/{front,rear}/{points_raw,imu_raw}`；保留原始字段、时钟和数值。ROS domain 0 / localhost-only / Fast DDS / sensor-data QoS。无 Zenoh 发布者、应用 RPC、SDK 控制会话、TF 或运动输出。单进程锁避免重复接收。
- 实际前/后点云各约 10 Hz、IMU 各约 200 Hz；frame 为 `rslidar_head` / `rslidar_tail`。点云含 x/y/z/intensity float32、ring uint16、timestamp float64，point_step=26、96 线，逐点时间为设备绝对秒。首帧有限点分别 20,710 / 21,684，约占组织化点槽 25%，其余非有限点不能当作障碍。
- **导航输入仍需适配**：前雷达/当前里程计时间比 Orin 墙钟快约 153–154 秒；后雷达使用运行时长式秒数，跨两次采样出现大幅回退（单次窗口内未回退），原因未确认。不得直接混合前后雷达、使用到达时刻伪装同步或修改系统时钟来掩盖问题。
- 原始 IMU 静止加速度模长约 1；已审查固定版 AIRY 解码器：加速度单位 g、角速度 rad/s，ROS 发布器直接复制，没有乘 9.80665。姿态为默认单位四元数，不能当作实测姿态。需单独完成 SI 单位、有效性、时间与坐标适配后供 LIO 使用。
- 原始 CDR 反序列化、独立 ROS 订阅、rosbag 记录均通过；6.548 秒 rosbag 共 2,724 条（前点云 60、后点云 62、前 IMU 1307、后 IMU 1295）。证据 `docs/evidence/zenoh_samples.json`、`ros_receiver_check.json`、`pointcloud_quality.json`、`real_sensor_bag_metadata.yaml`，图片 `docs/media/m1_live_pointcloud.png`。地图定位、TF 和运动仍未通过，保留 navigation_ready=false。
- Orin 接收进程以工作区 `m1_preflight/run_sensor_bridge.sh` 启动，当前 PID 见 `artifacts/real_sensors/live_bridge.pid`，状态每 2 秒写 `bridge_status.json`。不是开机服务；不要因本文记录的 PID 再利用而盲目杀进程。原始录包位于 NVMe `artifacts/real_sensors/bag_20260912_live/`。
- Zenoh Python 1.10.1 使用工作区私有 wheel、锁定 SHA-256（`zenoh_probe.lock.json`），与官方 PyPI 校验一致；系统旧 zenoh_bridge_dds 0.5.0-dev 协议不兼容，不能作为当前入口。`prepare_zenoh.py` 不替换系统依赖。
- `.100` / `192.168.1.102` 回应相同 MAC，提示同一网络接口别名；尚未登录确认内部配置。原始雷达 UDP 地址/目的端口及安装外参仍未知，但不再阻塞现有四路数据接收。保留机器网络、控制源和服务不变。

以下带时间的记录保留当时状态；其中“无真实数据”“必须先取得 .100 SSH”已被上述实测更新。

- 本仓库聚焦 M1 连接与 RoamerX 导航验证。架构入口是 README.md；连接见 docs/CONNECTION.md；导航结论见 docs/ROAMERX.md。
- 修改前检查 git status；有 .codegraph/ 时优先用 CodeGraph，否则用 rg。保留用户改动。
- 本地原 A2 + P7 项目已获用户授权清理，不再恢复为活动架构。不得据此删除 ORIN 上已有工程。
- `vendor/` 保留厂商 SDK、模型和原始包，保持来源与许可证。0/1/2 已按用途重命名。
- 上游导航置于 `third_party/genisom_roamerx_open`，固定提交；不把下载、编译成功描述成实机可用。适配应单独记录，不静默改上游协议。
- ORIN：`ssh nvidia@100.68.24.27`，Ubuntu 22.04 / ARM64 / ROS 2 Humble；已配置本机 Ed25519 公钥免密登录（`ssh nvidia` 或完整地址，两个全新连接验证通过），不要再次询问 Orin 密码，不把密码写文件。SDK 文档机器人地址是 `192.168.168.168`，控制板身份和登录账户待确认。
- 本机是 ROS 2 Jazzy；Humble 的构建验证放 ORIN 的 `/home/nvidia/Workspace/ljy/navigation`（实际为 NVMe `/mnt/nvme/workspace/ljy/navigation`）。不要覆盖 `/home/nvidia/ros2_ws`。
- 用户已授权整理本机仓库和尝试导航方案；可下载源码、检查依赖、独立编译及不连接执行器的验证。修改文档后核对路径；脚本检查语法；导航改动运行对应隔离验证并记录失败原因。
- 不把 lowlevel SDK Initialize 或示例当成只读操作：它们切换电机控制权。不得因“试用导航”直接发布机器人速度、启动 UDP/LCM 执行器桥接或自动运动。
- 运动验证需明确现场条件、机型、控制接口、急停和用户运动授权。保持现有服务和网络不变，不自动执行上游安装/启动脚本；先审查它们的系统修改和控制行为。
- 精简文档：README 说明怎么开始，CONNECTION 保留连接事实，ROAMERX 保留适配结论和验证证据。构建产物、媒体和临时日志不提交。

- 已验证的离线入口：`./scripts/run_navfn_demo.sh`。它在合成地图上直接运行上游 NavFn，不启动 ROS 节点或执行器。完整导航构建状态以 docs/ROAMERX.md 和 docs/evidence/ 为准。

## 2026-09-12 已确认接口与资料边界

- 原编号已从整理前备份核实：0=x86_64 低层 SDK，1=模型/传感器表，2=ARM64 低层 SDK。两份 ZIP 和模型 RAR 的解压文件均与原包比对一致；其中没有 SSH 凭据、雷达驱动或定位程序。详细依据见 [M1 接口核查](docs/M1_INTERFACES.md)。
- `nvidia` 只确认可登录 Orin。官方 M1 文档列运控主机 `192.168.168.168`、导航主机 `192.168.168.100`；两地址 SSH 可达，但均未登录确认，不重复尝试失败凭据或套用其他型号账户。
- 已实际解码头部 `rtsp://192.168.168.168:8554/front` 连续 5 帧，1920×1080；视频连通不代表底盘、点云或定位已接通。Orin 经 eth1、源地址 `192.168.168.10` 访问狗内网络，保持已有地址和服务。
- 原始 SDK 明确低层 UDP 8083；官方 M1 高层文档明确 UDP 8082 / WebSocket 8081。8081 TCP 已连通，三个端口均未完成本任务 SDK 握手，不能写成“协议已验证”。RoamerX 原桥接的 43997/43988 不能直接改端口复用。
- 位置表标称前后 AIRY 雷达、ICM42688 运控 IMU；ICM42688 的 z 为 V4 36.2 mm、V5 以后 44.2 mm。LUA300C 标注未开发固件。实际版本、驱动、时间同步、安装旋转待核实；URDF 未定义这些传感器坐标系，不能仅凭 STL 或位置表生成完整 TF。
- 按“控制板/接口 → 真实点云与 IMU → 建图定位 → 隔离运动输出的规划控制 → 现场低速测试”推进。当前已确认网络和静态资料，未收到本任务真实点云/IMU。默认 ROS 环境无业务话题、8 秒被动采样无目标网段 UDP，只描述该环境和窗口，不推断狗内部没有传感器。
- 优先查狗内导航主机已有传感器配置；SSH 非 SDK 通信前提，但板内代码/服务核查仍需正确系统账号。低层 Initialize 不能用于绕过此缺项。高层 Move 为归一化输入，后续适配必须核对速度等级、单位和超时行为。

## 2026-09-12 部署准备实测补充

- 用户明确目标是打通真机部署准备，先确认板卡、接口和代码位置，依既定五阶段推进；不要用编译通过替代真实传感器或运动验收。
- 本机 `~/.ssh/id_ed25519.pub` 已追加至 Orin `~/.ssh/authorized_keys`；私钥留在本机。`~/.ssh/config` 的 `Host nvidia 100.68.24.27` 使用公钥、`IdentitiesOnly yes`、`PasswordAuthentication no`。原授权列表和配置均有时间戳备份；未修改 Orin SSH 服务策略或其他用户公钥。
- 17:02 在 Orin ROS domain 0/default RMW 连续观察 12 秒，点云/IMU/里程计样本均为 0，TF `map/odom/base_link` 不可用。报告见 `docs/evidence/orin_sensor_snapshot.json`。观察器自身订阅会使 `/tf`、`/tf_static` 出现在图中，必须核对发布者数量，不算传感器输出。
- 本轮再次确认 `.168` 的 TCP 22/8081/8554 和 `.100` 的 TCP 22 可连接；两板 SSH 横幅均为 OpenSSH 8.9p1 Ubuntu-3ubuntu0.13，仅凭横幅不能确认硬件型号。没有板内授权登录，固件版本、服务路径、AIRY IP/端口/输出目的地址仍待查；不重复猜测已有失败账户。
- Orin 已有高层 SDK 位置：`/mnt/nvme/atec/ATEC-locomotion/third_party/genisom-robot-sdk`，库为 `lib/aarch64/librobot_sdk.so.0.2.1`；头文件 `include/robot_sdk/sdk_client.hpp`、`sdk_type.hpp`、`sdk_callback.hpp`。本版本 `ImuData` 只有加速度、角速度、四元数，无设备时间戳，不能拿 Orin 接收时刻冒充同步雷达 IMU 时间。
- 同工程 `atec_deploy/atec_deploy/robots/genisom_observer/genisom_joint_observer.cpp` 虽注释称 passive，实际有可选 `take` 分支和 `TakeControl`，也会修改关节及运动数据上报开关；不能直接当只读探针。其旧版控制权文档还说明 SDK 先连接可能获得控制权，不能将 SDK Connect 默认视为完全被动。
- RoamerX 真正的点云解码在 `src/slam/src/include/process/lidar_process.h` 与 `src/slam/src/src/process/lidar_process.cpp`：PointCloud2 读成 `livox_pcl::Point`（x/y/z/intensity/timestamp/line/tag），`Preprocess::process` 固定调用 `avia_handler`。虽然枚举有 VELO16/OUST64/MID360，不能靠 `lidar_type` 证明 AIRY 支持。必须先拿真实字段和逐点时间语义再适配，禁止编造缺失时间/tag/外参。
- SLAM `src/slam/src/src/mapping_alg.cpp` 发布 `/slam_odom` 和 TF `map → body`；它不直接提供导航所需的 `map → odom → base_link`。定位 `src/localization/localization/apps/localization_nodelet.cpp::publish_odometry` 将 twist 三项写为 0、把置信度放在 pose.covariance[0]；不能直接把它当实测速度及标准协方差输入控制器。定位输入 QoS 默认 reliable，SLAM 输入是 best effort，接实际驱动时分别核查。
- 已确认旧路径 `/mnt/nvme/home/m1_roamerx_eval_51d1e9d` 是悬空链接，指向不存在的 `/home/nvidia/Workspace/navigation`，旧 CMake 缓存重编译失败。新构建使用实际 NVMe 目录下的 `build_preflight` / `install_preflight` / `log_preflight`；不删除旧工程、不依赖已失效缓存。构建最终状态见 `docs/ROAMERX.md`。
- 新增 `m1_preflight/observe.py` 是无 SDK、无速度发布的 ROS 观察器；`env.sh` 与 `build.sh` 供 Orin Humble 独立环境使用。本机 Jazzy 不用于证明完整 Humble 栈可运行。

- `.100` 的 mDNS 反查两次返回 `orin-nx.local`（17:06、17:09），这是实测广播主机名，不等于已验证 Jetson 型号。网络证据 `docs/evidence/m1_network_snapshot.json`；本轮 eth1 全 UDP 12 秒采样为 0 包（未限制目标网段）。
- `/opt/robot_app/configs/framework_config.json` 在外接 Orin 上配置了 DDS domain 0、`multi_can_motor_controller` 和 localization 插件；配置存在不等于正在运行，也不能因为含 localization 就启动整套 robot_app，否则可能同时启动电机控制。
- RoboSense 官方 AIRY 驱动入口为 `RoboSense-LiDAR/rslidar_sdk`（内核 `rs_driver`），配置 `lidar_type: RSAIRY`；AIRY 支持独立 IMU 数据流，需 `ENABLE_IMU_DATA_PARSE=ON` 且配置非零 `imu_port`。应优先核查实机是否提供同雷达时钟的内置 IMU，而不是直接使用无设备时间戳的高层 SDK IMU。官方默认端口/话题均不是当前 M1 实测值，不能据此改雷达目的地址。来源见 `docs/M1_INTERFACES.md` 新增链接。
- 观察器已在 Orin loopback / ROS domain 173 的合成点云、IMU、Odometry 及 TF 上验证，能收到 best effort/reliable 样本并统计发布者。该自测不是机器人真实传感器通过。

- 定位构造函数中的 TF listener 创建被注释，默认 `send_tf_transforms=false`；原 `localization.launch.py` 还发布零位 `odom → livox_frame`。实机适配必须恢复真实 TF 接收并明确里程计链，不能使用这个假外参发布器。
- 已完成 localization 在新目录下的完整构建和隔离进程加载，`/load_map_service` 可发现；使用 ROS domain 174 + localhost only、无点云输入，进程已关闭。这只验收二进制/服务加载，不代表定位成功。
- 5 个关键上游文件与 Orin 源码 SHA-256 一致，见 `docs/evidence/interface_source_hashes.json`。未静默修改上游协议或传感器解码器。
- `m1_preflight/navigation_preview.launch.py` 是独立预检入口：所有节点在 `/m1_preview`，默认 lifecycle 不激活，不启动厂商桥接、mode publisher 或假 TF；速度只在 `/m1_preview/cmd_vel_raw` → `/m1_preview/cmd_vel`。`prepare_preview.py` 要求显式给出地图、真实 odom/scan 话题、坐标系和机体外形；0.2 m/s / 0.3 rad/s 是预检计算限值，不是已标定 M1 执行值。

- 全量构建发现 Orin OpenCV 开发包为 NVIDIA 4.8.0，但其引用的 `/usr/lib/libopencv_core.so.4.8.0` 缺失；系统另有 Ubuntu 4.5 库。不能伪造 4.8→4.5 的库软链接。采用在本导航工作区解包匹配的 NVIDIA 4.8 dev/runtime，并显式传入 `OpenCV_DIR=deps/usr/lib/cmake/opencv4`。
- LCM 系统未安装。工作区使用 Ubuntu Jammy ARM64 `liblcm-dev`/`liblcm1` 1.3.1+repack1-2.3；该包没有 lcmConfig.cmake，通过 `m1_preflight/cmake/Findlcm.cmake` 导入真实库，构建传 `CMAKE_MODULE_PATH`，不改上游通信协议。

## 2026-09-12 17:37 后：用户移交与历史实测复核

- 用户转发参考资料报告（非本任务直接实测）：固件 0.2.4，低层 8083 已通，高层 8082 握手/通用状态可通，但 SDK 0.2.1 与 0.1.1 的关节订阅失败。这些不是本任务新执行的握手；此前“本任务未握手”不能推断设备不支持 SDK。
- 已读取 Orin `/mnt/nvme/atec/probe/probe.log` 及两份 JSONL：5,800 帧/119.976 s、18,750 帧/387.984 s，唯一设备时间戳采样率分别 48.3347/48.3242 Hz，无重复和倒退。证据 `docs/evidence/recorded_state_audit.json`。确认历史低层真实状态可读；两份文件没有 acc_m_s2、joint_vel_rad_s、joint_torque_nm，不能宣称已具备完整 IMU 或速度反馈。
- 现有高层 recorder 日志实见 `current_state` 缺失解析错误，SDK 0.2.1 的 IMU/关节/速度计数为 0；不要把控制源解析失败当成允许接管，也不运行 allow-unverified 采集来绕过。
- 17:37 ROS domain 0 再观察 12 秒，无真实点云/IMU/Odometry，TF 无发布者。历史 SDK 数据与实时 ROS 接入分别验收，最新证据 `docs/evidence/orin_sensor_snapshot_current.json`。
- 新增 `audit_recorded_state.py` 为纯文件审计，无 ROS/SDK/网络；缺失加速度不会伪造。不要将用户总结中“只读探针安全”的表述带入操作规程：低层握手会独占执行器，与发不发命令无关。
- AIRY 官方驱动准备位于 Orin 本导航工作区 `sensors/`，固定源码见 `m1_preflight/airy_sources.lock.json`；使用 XYZIRT + ENABLE_IMU_DATA_PARSE。CMake 点类型补丁单独记录，PCAP 依赖只解包到 sensors/deps。默认上游配置为 RSM1，不得直接启动，真实 IP/端口和外参仍待确认。

## 2026-09-12 最终软件准备状态（17:48）

- 用户明确上一份 Mac 部署总结为他人转发参考，需按我们的 Linux 主机标准实现；其中固件、握手、力矩和站立结论仅保留来源标注。当前入口是本机 `ssh nvidia`，不是要求建立 Mac 的 `orin` 配置。
- Orin eth1 的现有 NetworkManager 配置名实测为 `arm-p7-direct`，保留三个静态网段，不因名称含 P7 就删除或重配。
- 本导航使用 `/opt/ros/humble` 和系统 Python 3.10；`/mnt/nvme/atec/ATEC-locomotion/.venv` 的 Python 3.11 属于另一工程。不要在导航终端 source locomotion 的 `/mnt/nvme/atec/env.sh`。
- 完整 20 包已编译通过，证据 `docs/evidence/build_readiness.json`，逐项核对 17:35 全量构建 events.log 返回码为 0。新构建在实际 NVMe 目录；旧悬空链接不作为可用路径。
- 系统 cv_bridge 链接 OpenCV 4.5，已另编译官方 cv_bridge 3.2.1 到 `deps/cv_bridge/` 配合私有 OpenCV 4.8。SLAM、航点插件动态库无缺失，未混用 4.5/4.8；依赖提交、版本及 SHA-256 已锁定。
- AIRY 的 rslidar_msg/rslidar_sdk 两包编译通过，确认 `POINT_TYPE_XYZIRT` 与 `ENABLE_IMU_DATA_PARSE` 生效；未启动驱动。驱动与 PCAP 私有依赖位于 `sensors/`；`sensor_env.sh` 仅加载消息库和运行库。真实网络/时间/外参未取得，不能声称已接通 AIRY。
- domain 176 / localhost-only 使用合成地图，7 个导航节点全部成功配置为 inactive；`/cmd_vel`、`/cmd_vel_raw`、`/cmd_vel_smoothed` 发布者为 0，测试已关闭。证据 `docs/evidence/preview_check.json`。这只验证插件配置与输出隔离，不是整套导航闭环通过。
- domain 175 的原始速度平滑模块合成指令测试通过：最大 0.2 m/s、0.3 rad/s，断流后最终输出零，根速度话题无发布者；见 `docs/evidence/smoother_check.json`。数值是软件预检上限，未验证 M1 制动或物理速度。
- 下一项实机阻塞为狗内导航板 `.100` 的有效登录及现有驱动配置；控制板 `.168` 的登录也未知。外接 Orin 已公钥免密，不能继续问其密码。拿到板内配置后先真实点云/同步 IMU，再建图定位，不用低层握手替代。

- AIRY 获取脚本已修复首次 `--no-checkout` 空工作树问题，首次固定提交检出和重复执行均验证通过，见 `docs/evidence/airy_fetch_check.json`。Orin 318 个源码文件与锁定且带记录补丁的本机源码逐一 SHA-256 相符；已补对应 Git 元数据，Orin 上默认源码准备命令重复运行通过。

- 2026-09-12 SDK 雷达接口复核：已检查 ARM64 低层 client.h/types.h、Orin 高层 0.2.1 与 0.1.1 的 sdk_client.hpp/sdk_callback.hpp/sdk_type.hpp，以及官方当前 API 文档，未发现公开的雷达点云/原始包订阅接口。高层 SetImuConfig/OnImuData 是 IMU，ObstacleAvoidance 是停障开关，不能代替点云。雷达数据走独立 RoboSense rslidar_sdk/rs_driver 或已有 ROS 发布链路；编译成功不代表已取得实机数据。

## 中文项目说明维护

- `docs/PROJECT_GUIDE.md` 是面向项目成员的功能与实现说明，README 提供入口。主要功能、调用链、源码路径、消息接口、单位/坐标系或验证边界变化时，同步更新对应章节和维护日期；具体测试证据仍集中在 `docs/ROAMERX.md`。
- 我们新增或实质修改的代码，对模块职责、关键单位/坐标约定和不明显的实现理由写必要中文注释；不要逐行翻译代码或批量改厂商源码注释。保留上游来源与许可证。
- 文档维护随相关代码任务执行，不表示后台自动更新。同步至 Orin 时适配源码链接并保留原厂 README。

- 新提供 `https://github.com/CyanTempest/Navigation.git` 作为标定参考；Git、已登录 gh 和 GitHub 连接器均不能读取（404/Repository not found），没有审查源码、不能判定解决标定。未切换当前 RoamerX。证据 `docs/evidence/cyantempest_repository_access.json`。
