# ATEC A2 + P7 地形代理评估

本文记录 2026-07-26 对上坡、下坡和 170 mm 台阶进行的三组 Gazebo 地形诊断。三组测试均使用 Gazebo Sim `VelocityControl` 驱动的 **rigid planar proxy（刚体平面运动代理）**，而不是 A2 四足步态控制器。

## 结论

| 项目 | 水平进度 | 高度变化 | 最大绝对俯仰 | 代理阈值结果 | 能否证明四足能力 |
| --- | ---: | ---: | ---: | --- | --- |
| 上坡 `ramp_up` | 0.7406 m | -0.1538 m | 0.8339 rad | 失败 | 不能 |
| 下坡 `ramp_down` | 2.7995 m | -0.3161 m | 0.2400 rad | 通过 | 不能 |
| 上台阶 `stairs_up` | 0.7345 m | -0.1739 m | 1.0674 rad | 失败 | 不能 |

只有下坡试验达到了该平面代理的诊断阈值。这个“通过”仅说明代理模型在该场景中按判据移动到坡下，不能表述为 A2 已完成下坡步态验证。上坡和台阶试验均失败，姿态和高度数据表明刚体代理未正确越过对应地形。

## 共同测试边界

三组报告都明确记录：

```text
simulation_proxy: gz-sim-velocity-control-system
is_quadruped_gait_validation: false
safe_for_real_robot: false
real_a2_capability: unverified
```

速度指令经过了仓库的安全接口链：

```text
/cmd_vel -> velocity_gate -> /platform/cmd_vel -> /sim/cmd_vel
```

这可以检查 ROS 2 命令路由、速度门和仿真场景交互，但代理没有实现腿部关节控制、落足规划、接触力控制、机身姿态稳定或 A2 厂商步态接口。因此三组结果均不可直接用于实机，也不能作为 A2+P7 的爬坡、下坡或上台阶能力证明。

## 分项结果

### 上坡

- 原始工件：`artifacts/terrain_repo_ramp_up_20260726_v1/`
- 指令：0.10 m/s，34 s，期望沿负 `x` 方向前进
- 水平进度：0.7406 m
- 高度变化：-0.1538 m
- 最大绝对俯仰：0.8339 rad
- 判定：`proxy_failed`

代理没有达到地形诊断阈值，本结果不能声称完成上坡。

### 下坡

- 原始工件：`artifacts/terrain_repo_ramp_down_20260726_v1/`
- 指令：0.08 m/s，30 s，期望沿正 `x` 方向前进
- 水平进度：2.7995 m
- 高度变化：-0.3161 m
- 最大绝对俯仰：0.2400 rad
- 判定：`proxy_pass`

代理达到本次诊断阈值，但报告原文同时注明 `this is not gait proof`。它不能证明真实四足机器人可安全下坡。

### 170 mm 台阶

- 原始工件：`artifacts/terrain_repo_stairs_up_20260726_v1/`
- 指令：0.08 m/s，38 s，期望沿正 `x` 方向前进
- 水平进度：0.7345 m
- 高度变化：-0.1739 m
- 最大绝对俯仰：1.0674 rad
- 判定：`proxy_failed`

代理没有达到地形诊断阈值，本结果不能声称完成上台阶。

## 稳定证据

- [上坡代理报告](evidence/terrain_ramp_up_probe.json)
- [下坡代理报告](evidence/terrain_ramp_down_probe.json)
- [170 mm 台阶代理报告](evidence/terrain_stairs_up_probe.json)

`docs/evidence/` 中的文件是上述原始工件中 `terrain_probe.json` 的原样副本。后续只有接入 A2 SDK2/厂商步态控制器、完成载荷与重心复核并制定实机安全验收后，才可以开展真正的四足地形能力验证。
