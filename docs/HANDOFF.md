# 完整交接与恢复指南

交接版本：`m1-preflight-20260913`；源码分支：`m1-navigation-preflight-20260913`。本文面向第一次接手项目的人。先阅读 [当前情况说明](CURRENT_STATUS.md)，再按本页恢复源码、数据和测试环境。

**可以接手的功能是构建、离线验证和只读输入预检；真实安装外参、硬件同步及运动闭环尚未完成。当前不存在一个已经验证可直接让机器狗自主导航的整机启动命令。**

## 1. 交接包含什么

| 内容 | 获取位置 | 用途 |
| --- | --- | --- |
| 自编代码、配置、补丁、锁文件和测试 | Git 仓库 `scripts/`、`m1_preflight/`、`experiments/` | 接收、适配、预检、坐标与规划验证 |
| 从连接到最新检查的全部阶段说明 | `AGENTS.md`、`docs/ROAMERX.md`、`docs/M1_INTERFACES.md` 等 | 包括无数据、构建兼容、缺帧、错误回调、来源变化等历史尝试 |
| 小型验证报告与图 | `docs/evidence/`、`docs/media/` | 对照成功/失败结论及限制 |
| 原始 SDK、模型、位置表、使用说明 | `vendor/` | 原始压缩包、两架构 SDK、URDF/STL/XLSX、DOCX；保留厂商条款 |
| 固定上游完整已检出源码与 Git 元数据 | Release `m1-pinned-sources-20260913.tar.gz` | RoamerX、rslidar_sdk、rs_driver、rslidar_msg；无需重新从上游下载 |
| Orin 真实录包、CDR、测量、历史失败日志、构建日志 | Release `m1-orin-evidence-20260913.tar.gz` | 完整恢复录包回放及历史核查材料 |
| 开发机历史产物与说明书提取结果 | Release `m1-host-evidence-20260913.tar.gz` | 与 Orin 产物分开放置，避免同名报告互相覆盖 |
| ARM64 固定依赖缓存与 cv_bridge 源码 | Release `m1-arm64-dependency-cache-20260913.tar.gz` | 避免固定软件包版本从软件源下架后无法获取 |
| 原 Orin 软件包版本清单 | Release `orin-packages-20260913.tsv` | 对照原验证环境，不是自动安装脚本 |
| 附件完整性 | Release `SHA256SUMS` | 下载后逐项校验 |

原 A2/P7 仿真代码与展示材料仍在 Git 历史中；本次分支记录工作区转为 M1 的改动。需要旧版本时使用另一份 checkout，不要把旧 A2 控制入口混回 M1 部署。

未把有绝对路径的编译安装目录当成可移植程序发布；它们应由固定源码和缓存重建。SSH 私钥、登录密码不属于交接内容。后台接收器不断刷新的状态用交接快照保存，锁和 PID 文件不恢复到另一台机器。

## 2. 下载与核对

有 GitHub CLI 的电脑上：

```bash
gh repo clone hezhou0331/ros2-nav2-mppi-gazebo-repro m1-navigation -- --branch m1-navigation-preflight-20260913
cd m1-navigation
mkdir -p handoff-assets
gh release download m1-preflight-20260913 \
  --repo hezhou0331/ros2-nav2-mppi-gazebo-repro \
  --dir handoff-assets
(cd handoff-assets && sha256sum -c SHA256SUMS)
/usr/bin/python3 scripts/check_handoff.py
```

从 [Release 页面](https://github.com/hezhou0331/ros2-nav2-mppi-gazebo-repro/releases/tag/m1-preflight-20260913) 也可直接下载。不要把 GitHub 自动生成的源码 ZIP 当作已包含 Release 大附件。

## 3. 在新目录恢复源码

在仓库根目录解压固定源码，脚本只检查版本、补丁和路径，不启动节点：

```bash
tar --no-same-owner -xzf handoff-assets/m1-pinned-sources-20260913.tar.gz
/usr/bin/python3 scripts/prepare_workspace.py --offline
```

它建立 `src → third_party/genisom_roamerx_open/src` 和 `sensors/src → ../third_party`，与原构建脚本布局兼容。重复执行可行；遇到已有不同目录或源码修改会拒绝覆盖。

如果未下载源码附件，可以用 `/usr/bin/python3 scripts/prepare_workspace.py` 按锁文件在线获取。`upstream.lock.json` 固定 RoamerX；`m1_preflight/airy_sources.lock.json` 固定 AIRY 源码。CyanTempest/Navigation 当时不可读取，没有任何未取得的代码被宣称已经集成。

## 4. Orin 环境与构建

已经验证的平台是 Ubuntu 22.04 / ARM64 / ROS 2 Humble、Jetson Orin；开发机是 x86_64 / ROS 2 Jazzy。完整 ARM64 部署步骤应在前者执行，并放在 NVMe。新机器需先具备 ROS Humble 开发环境、colcon/CMake/C++ 编译器、PCL 等系统依赖及 Python numpy/scipy/yaml/rosbag2；具体版本对照随附软件包清单。依赖缓存只覆盖我们额外固定的包，不是完整操作系统镜像。

不要在导航终端加载 locomotion 工程的 Python 3.11 环境；这里使用系统 `/usr/bin/python3` 和 `/opt/ros/humble`。

```bash
# 在新的 bash 终端、仓库根目录中执行。
tar --no-same-owner -xzf handoff-assets/m1-arm64-dependency-cache-20260913.tar.gz
source m1_preflight/env.sh
/usr/bin/python3 m1_preflight/prepare_dependencies.py
bash m1_preflight/build_cv_bridge.sh
bash m1_preflight/build.sh
bash m1_preflight/build_sensors.sh
bash m1_preflight/airy_adapter/build_airy.sh
/usr/bin/python3 m1_preflight/prepare_zenoh.py
```

这里仅解包私有依赖并构建，不执行系统 apt install，也不启动雷达或机器人。`build_airy.sh` 生成独立 `src_airy/robot_slam`，不覆盖锁定上游。首次全量构建的时间与结果见 `docs/evidence/build_readiness.json` 和 Release 中的 `log_preflight/`。

## 5. 恢复数据并离线复现

选一个全新的目录存放原始证据，避免覆盖正在运行工作区的状态文件：

```bash
mkdir -p handoff-data/orin handoff-data/host
tar --no-same-owner -xzf handoff-assets/m1-orin-evidence-20260913.tar.gz -C handoff-data/orin
tar --no-same-owner -xzf handoff-assets/m1-host-evidence-20260913.tar.gz -C handoff-data/host
/usr/bin/python3 scripts/check_handoff.py --data-root handoff-data/orin
```

在 ROS Humble 新终端中，以下测试不连接机器人：

```bash
source /opt/ros/humble/setup.bash
/usr/bin/python3 m1_preflight/airy_adapter/test_adapter.py
/usr/bin/python3 m1_preflight/coordinates/test_transforms.py
/usr/bin/python3 m1_preflight/airy_adapter/test_difop.py
/usr/bin/python3 m1_preflight/airy_adapter/verify_fault_replay.py \
  --bag handoff-data/orin/artifacts/real_sensors/bag_before_mapping_30s \
  --output artifacts/handoff_fault_replay.json
```

预期：适配 11 项、坐标 6 项、DIFOP 4 项；真实录包基线 12264 条消息，20 项故障回放通过。传感器录包不是建成的地图，也没有真实自主导航成功数据。

实际 ROS 节点隔离测试、原生 AIRY CDR 验证、合成地图规划分别见 [AIRY 说明](../m1_preflight/airy_adapter/README.md)、[坐标说明](../m1_preflight/coordinates/README.md)、[项目指南](PROJECT_GUIDE.md)。测试使用 localhost 和独立 domain，不能直接连接运动后端。

## 6. 接入已有 M1

现有路径：开发机通过 Tailscale SSH 进入外接 Orin，再经 eth1 到狗内 `.100:7447` 的 Zenoh 服务。新接手者需获得外接 Orin 的访问授权并配置自己的公钥；仓库中的内网地址不能让未授权电脑自动登录。

已有 Orin 项目位置 `/home/nvidia/Workspace/ljy/navigation`，实际位于 NVMe；那里可能已经有原始接收器，不应直接再启动一份。先检查 `artifacts/real_sensors/bridge_status.json` 的更新时间、四路接收年龄、`forwarding_enabled` 和 `source_fault`。PID 只用于本机，并必须核对 cmdline。

确认没有已有接收器后，`bash m1_preflight/run_sensor_bridge.sh` 才是我们自己的四路只读入口。运行 `bash m1_preflight/airy_adapter/run_preflight.sh` 会重审时钟并做有限时输入检查；**当前真实外参仍缺失，整体应拒绝进入建图**。需要现场核实设备标定和安装后才能继续。

不要直接运行厂商整机 launch、低层 SDK 握手或运动示例。低层握手本身可能接管执行器，与有没有发送运动指令无关。

## 7. 按时间了解所有尝试

1. [连接记录](CONNECTION.md)：公钥、两块板卡、网段与现有工作区。
2. [接口核查](M1_INTERFACES.md) 和 [SDK 说明核查](SDK_MANUAL_REVIEW.md)：SDK 边界、历史低层数据与独立实测的区别。
3. [RoamerX 验证](ROAMERX.md)：从无数据、20 包构建、插件隔离，到 Zenoh 接收、AIRY 适配、共享内存改进的记录。
4. [故障检查](INPUT_FAULT_TESTS.md)：20 项回放、7 项 ROS 检查、首次回调失败与修复、真实 300 ms 缺口。
5. [静止复核](STATIONARY_CHECK.md)：来源改变、显式恢复、三分钟窗口通过、时差变化、静态几何与仍缺标定。
6. `AGENTS.md`：协作约定和事实索引；带“最新”说明的上方记录优先于下方历史快照。

Release 内 `artifacts/fault_ros/` 保留首次失败，`artifacts/fault_ros_fixed/` 为修复后结果；`artifacts/real_sensors/` 保留前后时钟审计、接收器状态、录包、CDR 和预检；`log_preflight/`、`log_airy/`、`log_cv_bridge/`、`sensors/log/` 为构建尝试。失败材料未删除或改写成通过。

## 8. 本次交接自身的验证

固定源码附件已在干净目录解压，离线准备首次和重复执行均通过；101 份厂商输入已逐项校验。Orin 数据附件重新解压后，使用系统 ROS Humble 复跑 11 项适配、6 项几何、4 项 DIFOP 和 20 项真实录包故障测试，全部通过，基线 12264 条消息。详见 [交接检查](evidence/handoff_verification.json) 与 [重放结果](evidence/handoff_fault_replay.json)。

没有重新安装一台全新操作系统并重复全部编译；原 20 包成功构建日志与版本清单已交付，接手者仍须匹配操作系统/ROS/架构并检查依赖。构建和数据验证通过也不替代现场标定及运动验收。
