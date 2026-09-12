# 连接 M1 与 ORIN

## SDK 手册补充的网络适用范围

新增 [M1/L2 SDK 说明核查](SDK_MANUAL_REVIEW.md)：手册的 Wi-Fi 网关为 `.234.1`，有线目标为 `.168.168`，并区分高层 0.1.0 及以前的 8081 与 0.1.1 的 8082。我们的 Orin 已经从 eth1/192.168.168.10 直连，不执行手册 Wi-Fi 添加路由步骤。手册没有狗内 SSH 凭据；传感器仍通过 `.100:7447` 接收。

## 已打通的传感器连接

2026-09-12 19:45 起已接通真实前后点云和 IMU：狗内导航板 `192.168.168.100:7447` 的 Zenoh 服务 → 外接 Orin → `/m1_sensors/*`。接收数据不需要狗内板 SSH；建图、定位和运动尚未验收。

实际路径：Linux 主机公钥 SSH → 外接 Orin（eth1）→ `tcp/192.168.168.100:7447` → Zenoh 四路原始传感器 → Orin 本机 ROS。读取传感器不需要 `.100` SSH 认证；查询或修改板内驱动配置仍需要适当管理访问。

接收入口和停止方法见 [预检说明](../m1_preflight/README.md)，测得的时钟/单位问题见 [导航记录](ROAMERX.md)。本接收器仅在 Orin localhost 发布 ROS，Linux 开发机不会自动发现这些话题。

原始 0/1/2 包复核、主机身份边界、视频实测和传感器位置见 [M1 接口核查](M1_INTERFACES.md)。包内不含狗内主机的 SSH 凭据；`nvidia` 仅确认用于 Orin。

## 登录 ORIN

```bash
ssh nvidia@100.68.24.27
```

也可运行 `ssh nvidia` 或仓库 `scripts/connect_orin.sh`。已配置本机 Ed25519 公钥免密登录，并用不复用会话的全新连接验证通过；后续无需 Orin 密码。

本机 `/home/hezhou/.ssh/config` 已添加 `Host nvidia`，对应 `nvidia@100.68.24.27:22`。VS Code 已安装 Remote SSH 扩展：按 Ctrl+Shift+P，执行 `Remote-SSH: Connect to Host...`，选择 `nvidia`，登录后打开 `/home/nvidia/Workspace/ljy/navigation`。

该目录实际位于 NVMe `/mnt/nvme/workspace/ljy/navigation`。旧兼容链接实测已悬空，旧构建缓存引用失效路径。新的验证使用 `build_preflight/` 与 `install_preflight/`，不再依赖该链接。远端 `M1_WORKSPACE.md` 是项目入口说明，`README.md` 保留厂商原文。

建议依次阅读：

- `README.md`：厂商说明。
- `src/navigation/src/robot_navigo/launch/navigation_bringup.launch.py`：启动入口，只阅读，当前不要直接启动。
- `src/navigation/src/robot_navigo/params/navigo_params.yaml`：导航参数。
- `src/navigation/src/navigo_navfn_planner/`：全局规划。
- `src/navigation/src/navigo_mppi_controller/`：局部控制。
- `experiments/navfn/`：本次独立离线算法验证。

原 SSH 配置备份：`/home/hezhou/.ssh/config.bak-m1-20260912-152930`。

2026-09-12 已成功登录：`nvidia-desktop`，NVIDIA Jetson AGX Orin leetop gitKit，Ubuntu 22.04.5 / aarch64 / L4T R36.4.7；ROS 2 Humble 位于 `/opt/ros/humble`。

## 网络路径

```text
本机 --Tailscale--> ORIN 100.68.24.27
                    eth1 192.168.168.10/24
                      ├── 192.168.168.168（文档：运控主机；头部视频已验证）
                      └── 192.168.168.100（文档：导航主机；SSH 可达、登录未确认）
```

ORIN 的 Wi-Fi 地址是 `192.168.22.144/22`。eth1 另有 `192.168.25.100/24` 和 `192.168.234.10/24`。这些是实测快照，不应重配网络来复现。

从 ORIN ping `192.168.168.168` 成功，约 0.8 ms；该地址 TCP 22 返回 OpenSSH 横幅。它与 SDK 文档机器人地址一致，但尚未登录确认控制板身份和账户。Tailscale 共享 ORIN 不代表开放整个机器人子网。拿到控制板账户后可通过 `ssh -J nvidia@100.68.24.27 用户名@192.168.168.168` 登录。

## 已有环境

- `/home/nvidia/ros2_ws` 链接至 `/mnt/nvme/home/ros2_ws`。
- 现有 `src/fastlio_terrain_navigation` 是 Humble 地形导航，README 使用 X30 模型，输入 `/cloud_registered` 和 `/Odometry`，尚未验证 M1 对接。
- 默认 ROS 发现环境未发现业务节点，只有 `/parameter_events`、`/rosout`；不能据此排除其他 domain 或环境运行节点。
- `/home/nvidia/codex4nav` 初次检查为空。
- 系统盘仅约 1.5 GB 空闲；NVMe 约 110 GB。新的试编译使用独立 NVMe 目录。

## 底层 SDK 边界

`vendor/sdk/arm64/docs/usage_zh.md` 的示例地址为 UDP `192.168.168.168:8083`。本任务未重新握手；当前 Orin 已有的历史记录证明低层 48.3 Hz 状态收帧，详情见 M1_INTERFACES.md。

接入/断开 SDK 会切换控制权并清零电机参数；示例会发送阻尼指令，不能作为只读连接测试。文档要求 RK3588 >= v0.2.3、App >= v1.1.7 并启用 Low-Level SDK，当前均未核验。轮足使用 `ZsM1Client`，点足使用 `ZsM1fClient`。

代码统一归入 ORIN 的 `Workspace/ljy/navigation`；Workspace 根目录的旧 `navigation` 路径实测不存在，新构建使用实际工作区路径。

公钥配置备份：本机 `/home/hezhou/.ssh/config.bak-m1-key-20260912-170046`。Orin 授权公钥只追加，没有删除其他已授权公钥。

实际 eth1 连接配置名为 `arm-p7-direct`，保留现有名称和地址。导航入口是 `source m1_preflight/env.sh`；不要套用转发 Mac 总结中的 locomotion Python 3.11 环境。
