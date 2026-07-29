# A2 运动后端状态

审计日期：2026-07-27。

## 当前结论

| 路径 | 当前状态 | 可接受结论 |
| --- | --- | --- |
| Gazebo `VelocityControl` | 导航回归已通过 | 仅是刚体平面代理，不是四足步态 |
| `atec_a2_sdk2_adapter` | 官方 Sport API 边界和硬件控制 launch 已实现 | SDK-free 测试通过；未连接 Orin、PLC bridge 或实体 A2 |
| 官方 A2 MuJoCo + RL | 模型、训练任务和部署代码存在 | 缺少 A2 策略权重，且当前 DDS bridge 类型需修正和验证 |

因此，导航膨胀半径和软件闭环已验收，官方实机运动接口已进入独立的
fail-closed 控制边界，但 Gazebo 滑行代理尚未被真实 A2 步态替换。

## 本地资产清点

在 `/home/hezhou/公共/ATEC` 递归检查 `onnx/pt/pth/jit/ckpt`：

- 共 150 个候选权重，其中 4 个 ONNX、146 个 PT；
- A2 路径命中 0；
- 148 个是 Unitree B2/B2 + Piper 运动资产；
- 其余两个分别是视觉模型和 ACT 机械臂策略。

B2 策略不能直接用于 A2。即使二者都是 12 个腿部输出，观察维度、机体惯量、
关节默认位姿、PD 增益、载荷和训练运行时均不相同。把 B2 权重接到 A2 plant
不能作为兼容控制器或 A2 验收证据。

## 官方可行路径

审计固定到以下上游提交：

| 仓库 | 提交 | 已确认内容 |
| --- | --- | --- |
| `unitreerobotics/unitree_mujoco` | `ae6a8403e272733e9996ef59990880330496177f` | `unitree_robots/a2` MJCF、场景和网格 |
| `unitreerobotics/unitree_rl_mjlab` | `1425b15f73bd4095f0df53709d7c389c3eb9e790` | `Unitree-A2-Flat`、47 维观察、12 维动作、A2 C++ 部署参数 |
| `unitreerobotics/unitree_sdk2` | `21d0a3b2c46ee48c8fdf2783becb6be3beb0a59b` | G1 wrapper 使用的 HG `LowCmd/LowState` 及 `rt/lowcmd`、`rt/lowstate` DDS 契约 |

模型来源和部署模拟器源码必须分开理解：独立 `unitree_mujoco` checkout 提供
A2 MJCF 模型参考；当前 RL 部署的构建和源码检查目标是固定提交的
`unitree_rl_mjlab/simulate/`，不是独立 `unitree_mujoco` 仓库中的
`simulate/` 源码。后续补丁和构建均须落在前者，避免检查了一个模拟器而实际
运行另一个模拟器。

RL 仓库的 A2 路径只有
`deploy/robots/a2/config/policy/velocity/v0/params/deploy.yaml`，没有
`exported/policy.onnx`，上游 release 和公开模型检索也未找到可直接使用的 A2
权重。必须先训练、回放并导出 A2 策略。

当前三组固定上游资产还不能未经修改直接组成 A2 部署闭环：

- A2 部署端 `Types.h` 使用 G1/HG `LowCmd/LowState`；
- MuJoCo bridge 以 `m->nu > 20` 选择 G1，否则选择 Go2；A2 的 12 个执行器会
  进入 Go2 bridge；
- `velocity_commands` 直接读取手柄 `ly/lx/rx`，没有 Nav2 命令、超时归零或
  自动模式安全契约；
- 官方 A2 plant 未包含本仓库的 P7 安装板、载荷和重心变化。
- A2 部署的 `gait_phase` 在命令范数低于 `0.10` 时归零，而本仓库 Nav2 的
  `min_approach_linear_velocity` 和 `regulated_linear_scaling_min_speed` 是
  `0.05 m/s`。未定义并验证两侧的单位、死区和低速行为前，Nav2 可能发出
  步态侧不按预期执行的低速命令。

这些问题必须通过固定提交的补丁、DDS 类型匹配测试和物理仿真验证解决，不能
用配置声明替代。

## 静态预检

取得三个固定提交并生成 A2 policy 后，在仓库根目录运行：

```bash
/usr/bin/python3 tools/validate_a2_official_simulation.py \
  --unitree-rl-mjlab /absolute/path/to/unitree_rl_mjlab \
  --unitree-mujoco /absolute/path/to/unitree_mujoco \
  --unitree-sdk2 /absolute/path/to/unitree_sdk2 \
  --policy-sha256 <64-character-lowercase-sha256>
```

该工具的唯一可接受范围是 `scope=static_source_contract_only`。它检查 checkout
提交、policy 文件和 SHA-256、A2 电机数、DDS 类型/话题的源码契约、
`unitree_rl_mjlab/simulate/` 的 A2 bridge 路由，以及命令观察代码是否从手柄
改到显式命令源。命令源检查只证明**静态源码路由**，不证明 ROS/DDS 消息已在
运行时送达，也不验证时间戳、超时、限速、重新武装或唯一发布者。

即使报告返回 `ready=true`，也不是编译、运行时 DDS 互通、A2 步态、P7 载荷、
Nav2 闭环或实体 A2 验证。`--allow-unpinned-policy` 只适合清点已有 policy；未
固定 policy SHA-256 的结果不能进入替换验收。

## 替换验收门槛

1. 建立隔离的 MuJoCo/mjlab 训练环境，并为 RTX 4060 8 GB 缩小并行环境数量。
2. 在包含 A2 + P7 载荷参数的训练任务中训练并导出固定 SHA-256 的
   `policy.onnx`。
3. 修正并验证 A2 控制器、`unitree_rl_mjlab/simulate/` 与固定 `unitree_sdk2`
   的 LowCmd/LowState DDS 类型。
4. 将策略速度输入从手柄改为带 DDS/ROS 接收时间、限速、超时和重新武装的
   `/platform/cmd_vel` bridge，并解决 Nav2 `0.05 m/s` 与步态命令范数 `0.10`
   阈值之间的低速契约。
5. 在 MuJoCo 中验证站立、零命令、前进、转向、失联停止和跌倒保护，再接 Nav2
   重跑建图与双目标导航。
6. 实体 A2 仍须另做支撑架、机器人侧 watchdog、物理急停、载荷和停止距离验收。

在第 2 至第 5 项完成前，仓库继续保留 Gazebo 平面代理作为导航软件回归后端，
并明确标记 `gait_controller_verified: false`。
