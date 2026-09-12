# M1 / ORIN 导航工作区

**接手项目请先读：[完整交接与恢复指南](docs/HANDOFF.md)。历史记录、代码、厂商资料及原始测试数据均有对应入口。**

**当前进展和剩余问题：[M1 真机导航准备情况说明（2026-09-13）](docs/CURRENT_STATUS.md)。输入窗口已通过，真实外参和硬件同步仍待核实，尚未进入建图或自主行走。**

当前目标：通过 ORIN 接入 M1，验证厂商 RoamerX 传统导航栈。Orin 公钥免密与头部视频已验证，完整 20 个导航包和 AIRY 驱动已编译，隔离插件配置通过；真实前后点云（各约 10 Hz）与 IMU（各约 200 Hz）已接通；软件时间映射、IMU 单位和 AIRY 原生解码已通过验证；坐标链软件验证和实际规划服务的隔离测试也已通过；实机外参、精确同步及建图定位仍待完成。

## 从这里读代码

[中文项目说明与代码阅读指南](docs/PROJECT_GUIDE.md)：功能、整体数据流、核心实现、代码入口与推荐阅读顺序。先读这份说明，再按功能进入源码。

## 先连接

```bash
./scripts/connect_orin.sh
```

ORIN 代码目录：`/home/nvidia/Workspace/ljy/navigation`。VS Code 连接 `nvidia` 后打开此目录，先读远端 `M1_WORKSPACE.md`。

登录账户为 `nvidia@100.68.24.27`，已配置公钥免密登录。连接路径、系统信息见 [连接说明](docs/CONNECTION.md)。

导航环境与操作入口见 [真机前预检](m1_preflight/README.md)。已增加三分钟逐帧输入预检入口及[故障保护验证](docs/INPUT_FAULT_TESTS.md)；[最新静止复检](docs/STATIONARY_CHECK.md)的三分钟输入窗口通过，但准备阶段仍有点云缺口，长期稳定性与同步仍待排查；缺少真实外参时明确拒绝生成建图配置，当前不要直接启动上游整机 launch。

## 查看导航效果

```bash
./scripts/fetch_roamerx.sh   # 首次下载或恢复固定版本
./scripts/run_navfn_demo.sh # 离线运行上游原始规划核心，不连接执行器
```

[验证结论与限制](docs/ROAMERX.md) · [原始 0/1/2 与实机接口核查](docs/M1_INTERFACES.md) · [规划效果图](docs/media/roamerx_navfn_result.png) · [新 SDK 手册核查](docs/SDK_MANUAL_REVIEW.md)。

## 目录

| 目录 | 内容 |
| --- | --- |
| `scripts/` | 连接与导航验证工具 |
| `m1_preflight/` | Orin 构建、只读观察、传感器准备与隔离导航入口 |
| `experiments/navfn/` | 上游原始规划算法的离线验证入口 |
| `docs/` | 连接方法、导航适配与验证结果 |
| `vendor/sdk/{arm64,x86_64}/` | M1 底层 SDK；保留厂商文档和许可证 |
| `vendor/robot_description/` | M1 URDF、网格、传感器位置表 |
| `vendor/archives/` | 原始 0、1、2 压缩包 |
| `third_party/genisom_roamerx_open/` | 独立上游 Git checkout，版本见 `upstream.lock.json` |

M1 模型附带的是 ROS 1/catkin 文件，尚未迁移成 ROS 2 描述包。底层 SDK 是电机接口，不等于 Nav2 所需的整机速度控制接口。

原有 A2 + P7 内容已从本机工作目录移除；Git 历史保留。完整整理前备份位于仓库外 `../backups/ros2_nav_repro_before_m1_20260912.tar.gz`。ORIN 现有工程未删除。
