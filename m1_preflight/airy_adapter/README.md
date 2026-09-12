# M1 AIRY 输入适配

2026-09-13 更新：[静止复检](../../docs/STATIONARY_CHECK.md)的三分钟输入窗口通过，源端到接收的缺口仍有记录；完整预检因真实外参缺失退出 2，硬件同步未验收。以下历史结果按各自窗口解释。

上一轮结果：20 项录包故障检查、7 项 ROS 节点保护测试通过；真实预检因后点云 0.300004 秒间隔触发锁定，输入稳定性仍未通过。下文早期成功记录不代表当前整项验收通过。详见 [输入故障检查](../../docs/INPUT_FAULT_TESTS.md)。

当前完成原始数据到软件验证输入的转换，以及 RoamerX 原生 XYZIRT 解码。**尚未完成双雷达硬件同步和实机外参确认，不能据此启动完整导航。** 真实采集始终保留 `/m1_sensors/*_raw`；本适配器仅输出本机 `/m1_airy/{front,rear}/{points,imu}`。

## 已验证的处理

- `audit_clocks.py` 只订阅四路传感器并读取 `robot_tf/use_sim_time` 参数。用 Zenoh 响应的发布端时间与本机请求前后时间，估计板间时差区间，不修改系统时钟或雷达配置。
- `prepare_clock_profile.py` 为每个雷达生成固定偏移，同雷达点云和 IMU 共用偏移；前雷达映射至 Orin 时钟，后雷达用发布端时间估计相对时钟原点。**后者含未测定的驱动延迟差，不能标记为精确同步。** 偏移有效期 10 分钟；真实高精度融合仍需 PTP/GPS 状态或独立时延标定。
- `adapter_core.py` 保留帧内时间间隔；同时平移点云头与逐点绝对秒。加速度乘 9.80665，协方差乘其平方；角速度保持 rad/s。无姿态估计时 `orientation_covariance[0]=-1`。IMU 改为独立 `rslidar_head_imu` / `rslidar_tail_imu` 坐标名，未生成虚假 TF。
- 回退、重复、明显跳变、主机墙钟跳变和过期时间配置停止适配输出；锁住后需重新审计并重启，不能沿用旧地图状态。
- `airy_preprocess.h` 直接读 XYZIRT，过滤非有限坐标，检查 96 线和 0–0.12 秒逐点时间，排序后转为 RoamerX 内部毫秒。`lidar_type=5` 为新增 AIRY 分支，不生成 Livox tag。既有 Livox 分支保留。
- `calibration.json` 中的机身平移仅为厂家标称，旋转及 LiDAR–IMU 标定保持 null。`prepare_mapping.py` 检查来源、矩阵和方向，缺项时拒绝生成建图配置。变换定义为 `p_IMU = R_IMU_LiDAR * p_LiDAR + T_IMU_LiDAR`。

## Orin 操作

在新的 bash 终端，位于 `/home/nvidia/Workspace/ljy/navigation`：

```bash
source m1_preflight/env.sh
export PYTHONPATH="$M1_WORKSPACE/deps/zenoh1101:${PYTHONPATH:-}"
/usr/bin/python3 m1_preflight/airy_adapter/audit_clocks.py
/usr/bin/python3 m1_preflight/airy_adapter/prepare_clock_profile.py \
  --audit artifacts/real_sensors/clock_audit.json \
  --output artifacts/real_sensors/clock_profile.json
bash m1_preflight/airy_adapter/run_adapter.sh --seconds 30
```

四路 raw 接收器应先运行。适配器不自启、不发布速度。30 秒在线验收已结束，原始接收器仍运行。不要使用旧 profile 长期启动：过期后停止输出是预期行为。

独立编译及离线验证：

```bash
bash m1_preflight/airy_adapter/build_airy.sh
/usr/bin/python3 m1_preflight/airy_adapter/test_adapter.py
/usr/bin/python3 m1_preflight/airy_adapter/validate_recording.py \
  --bag artifacts/real_sensors/bag_20260912_live \
  --output artifacts/real_sensors/adapter_recording_check.json
install_airy/robot_slam/lib/robot_slam/m1_airy_native_audit \
  artifacts/real_sensors/adapter_recording_check_cdr/front_adapted.cdr artifacts/real_sensors/adapter_recording_check_cdr/rear_adapted.cdr
```

源码副本、构建及安装分别为 `src_airy/robot_slam`、`build_airy`、`install_airy/robot_slam`；固定上游 `src/slam/src` 和原 `install_preflight` 未修改。重复准备会逐文件比较，拒绝覆盖不一致源码。

取得真实标定后可运行以下配置生成检查；**当前应明确报缺少标定并退出**：

```bash
/usr/bin/python3 m1_preflight/airy_adapter/prepare_mapping.py \
  --upstream-config src/slam/src/config/config.yaml \
  --output artifacts/real_sensors/front_mapping.yaml
```

生成配置也不是完成建图验收。SLAM 的 `map → body` 与导航 TF/速度反馈仍需后续集成；本目录未提供可绕过这些条件的整机启动入口。

## 验证与剩余证据

11 项软件测试通过；真实 rosbag 2724 条全部转换，122 帧点云各有至少 18 条帧内 IMU，逐点相对时间最大变化 0.477 微秒。原生 C++ 对四份真实/转换 CDR 解码通过，并拒绝错误字段和错位时间。

30 秒在线适配：前/后 IMU 5965/5969 条，前/后点云各 258 帧，错误与时钟故障为 0。独立观察点云约 7.6 Hz，少于源流约 10 Hz，**不能宣称全链路无丢帧**；长时间负载、传输及队列调优仍需验收。校正后的样本年龄约 IMU 15–17 ms、点云 155 ms。

下一项必须取得的资料是这台机器的 `base_link ← LiDAR` 完整安装变换，以及每个雷达序列号对应的 `IMU ← LiDAR` 出厂标定/DIFOP。现有位置表、URDF collision 和 SDK 使用说明没有这些数据。板内 TF 只观察到 map/odom/base_link，ROS 参数未返回安装变换。

详细证据见 [导航记录](../../docs/ROAMERX.md)。单位与姿态有效性约定来自 [ROS Imu 定义](https://docs.ros2.org/latest/api/sensor_msgs/msg/Imu.html)；雷达同步及出厂 IMU 标定入口见 [AIRY 官方手册](https://robosense-robotics.github.io/product-manual/en/Airy/)。

## 可重复的建图前输入预检

在 Orin 导航工作区运行 `bash m1_preflight/airy_adapter/run_preflight.sh`。入口重新测量时钟，启动有限时适配器，并用 `check_live.py` 观察 180 秒，随后检查外参。只关闭本次启动的适配子进程，原始接收器继续运行。报告为 `artifacts/real_sensors/live_preflight.json`；输入或外参不合格时退出码为 2，不启动建图。`mapping_ready=false` 保留到实际标定、同步误差及建图验收完成。

逐帧观察直接读取序列化消息头，避免完整拷贝点云干扰测试；还原固定时差后，以整数纳秒时间戳匹配 raw/适配输出。剔除首 5 秒发现期和末 2 秒在途帧，报告窗口内缺帧、速率、时间倒退及接收器错误。接收器累计计数差包含状态文件刷新边界，不能直接当成精确丢包数。

本导航的接收器、适配器与预检入口加载 `m1_preflight/fastdds_sensors.xml`：64 MiB SHM、8 MiB 单消息上限、2048 队列，禁用内置网络传输；不改系统 socket 参数或狗内服务。临时观察程序需要保持相同 ROS domain 和 RMW。此前默认共享区仅约 512 KiB，小于约 2 MB 点云；[Fast DDS 2.6 官方说明](https://fast-dds.docs.eprosima.com/en/v2.6.11/fastdds/transport/shared_memory/shared_memory.html) 说明这种配置有丢失风险。以修改前后实测报告评估效果，不能仅凭参数变大宣称无丢帧。

修复后 180 秒测试：前/后点云 9.96/9.77 Hz，IMU 约 199 Hz；匹配窗口内四路缺少对应适配输出均为 0。源时间间隔仍偶有点云 0.20 秒、IMU 45/35 ms，不能宣称源端无丢失。完整预检因缺少实机外参退出 2，未生成建图配置。见 `docs/evidence/live_preflight.json`，其中 running=true 是测试时快照，有限时适配器随后已关闭。

## 出厂标定读取准备与新录包

`extract_airy_difop.py` 只扫描已有文件，不打开网络。按固定 AIRY 驱动及官方手册读取 1248 字节 DIFOP 候选的序列号、网络地址、同步标志和 1092 偏移处 7 个大端 float。结果保留原始方向/平移数值并标记未核实，不自动写 calibration.json；还须核对设备型号、序列号、单位、变换方向及板内驱动是否已经变换点云。现有历史 PCAP 只有 24 字节文件头，没有实际 DIFOP。

```bash
/usr/bin/python3 m1_preflight/airy_adapter/extract_airy_difop.py <已有设备信息包或抓包文件> \
  --output artifacts/real_sensors/difop_candidates.json
```

四项合成包测试包括大端浮点、跨读取块边界、非法四元数和坏尾拒绝。它们证明解析器行为，不证明已读到本机标定。只读 TF 缓存/标定状态探针 `probe_calibration_routes.py` 也没有返回安装变换；标定状态消息的实际类型不在当前消息包中，只记录收到的长度，未猜测字段或触发标定命令。

新增录包 `artifacts/real_sensors/bag_before_mapping_30s`，采集命令持续 30 秒，实际样本时段约 29 秒，共 12264 条。583 帧点云、11681 条 IMU 全部转换通过；内部 580 帧点云具有记录窗口内 IMU 覆盖（前/后至少 13/14 条），另 3 帧是录制边界。IMU 无重复/回退，但各一路有一次超过 15 ms 的间隔（最大 40/35 ms）。新增 `validate_recording.py` 间隔统计，并将 CDR 导出至 `<报告文件名去后缀>_cdr/`，防止不同录包验证混用导出文件。新的前后 CDR 也通过原生 C++ 解码及错误字段/时间拒绝。

## 当前运行保护与故障注入

线上转换入口已改为 `AdapterEngine` + `InputGuard`。等待四路有效数据后才允许输出；定时检查每次循环执行，空闲等待不超过 10 ms。任何关键故障都会锁定全部适配输出，数据恢复也不自动清除。

| 检查 | 当前软件阈值或行为 |
| --- | --- |
| 启动缺流 | 5 秒仍缺一路则锁定；等待期间不输出 |
| IMU 完全断流 | 100 ms |
| 点云完全断流 | 350 ms |
| 设备样本间隔 | IMU >50 ms、点云 >250 ms 锁定 |
| 校正后消息年龄 | IMU >250 ms、点云 >500 ms；超前 >50 ms 锁定 |
| 主机墙钟突跳 | 与单调时钟增量偏差 >50 ms 锁定 |
| 时钟配置 | 有效期最多 600 秒；过期、未来配置拒绝 |
| 数据/来源异常 | 时间重复/回退、错坐标名、错字段、非有限测量、来源变化锁定 |

这些是当前输入预检的软件界限，尚不是实机建图精度或硬件急停保证。Linux 调度阻塞可能延迟定时检查；所有结论需结合测得的时延。100 ms IMU 断流的隔离节点实测约 101 ms 触发。

Humble 兼容性：本机安装版本的 rclpy 回调仅提供消息，底层信息也仅有发送/接收时间。适配器每次处理核对 ROS 图中的唯一发布者 GID，并监测变化；这依赖发现图，不能当成逐消息来源认证。原始 Zenoh 接收器则直接检查每条消息 attachment 中的源 GID 和序号：源 GID 改变或序号重复/倒退会锁住整个原始转发；序号缺口只计数，交给采样间隔保护判定。它保留 `source_fault`、`forwarding_enabled`、`source_gid`、`sequence_gaps`。

恢复步骤：先保存故障状态和日志，排查数据源/传输；停止本次建图、定位及适配会话，确认原因已排除后显式重启受影响的接收器；重新测量时钟，再运行预检，并重新初始化定位。不要仅清空故障字段、延长旧 profile 有效期或自动恢复旧地图状态。预检入口会先拒绝不新鲜或已锁定的接收器。

只读缺口定位：

```bash
source m1_preflight/env.sh
export ROS_DOMAIN_ID=0 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE="$M1_WORKSPACE/m1_preflight/fastdds_sensors.xml"
export PYTHONPATH="$M1_WORKSPACE/deps/zenoh1101:${PYTHONPATH:-}"
/usr/bin/python3 m1_preflight/airy_adapter/audit_gaps.py --seconds 180 \
  --output artifacts/real_sensors/gap_audit.json
```

报告比较设备时间、Zenoh 发布序号/源 GID、发送端时间及 ROS 接收。完整测量在同名 `.samples.json` 文件。发布序号缺口只能定位到“序号分配至接收探针之间”，包含源发送队列、Zenoh 传输及客户端接收；不能单独证明物理雷达漏采。另一独立接收链能收到的缺失帧应单独统计。并行探针会增加接收负载，属于本次测量条件。

离线故障回放（无需机器人在线；使用真实已存录包与虚拟时钟）：

```bash
/usr/bin/python3 m1_preflight/airy_adapter/verify_fault_replay.py \
 --bag artifacts/real_sensors/bag_before_mapping_30s \
 --output artifacts/real_sensors/fault_replay.json
```

实际 ROS 节点故障注入（合成消息，必须使用隔离域）：

```bash
export ROS_DOMAIN_ID=180 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
/usr/bin/python3 m1_preflight/airy_adapter/verify_fault_ros.py --output-dir artifacts/fault_ros
```

错误坐标测试覆盖错误 frame_id；数值合法但安装方向错误的外参仍需标定与现场观测确认。故障输出停止测试包含队列排空后的观察，不能把接收时刻晚于故障时刻的在途消息误判为继续发布。
