# ATEC A2 + P7 导航证据

本文以 2026-07-26 完成的 A2 + P7 双目标实体障碍导航回归为历史基线，并补充 2026-07-27 的 `0.70 m` 膨胀半径重验收。结论仅覆盖 Gazebo 中的导航软件闭环；机器人运动由刚体平面代理执行，不代表 Unitree A2 的真实步态、动力学或实机安全性。

## 可视化证据

[![5× 播放的 Gazebo 与 RViz 双目标导航展示](media/atec_a2_p7_navigation_showcase.gif)](media/atec_a2_p7_navigation_showcase.mp4)

- [5× 播放导航展示（MP4）](media/atec_a2_p7_navigation_showcase.mp4)：仅后期播放加速；控制器与平台速度限制未变。
- [展示媒体溯源、声明与 SHA-256 清单](evidence/github_showcase_media_manifest.json)

上方 GIF/MP4 是由一次已保存的 `85.76 s` 成功导航录像制作的 5× 展示剪辑，页面不再提供原速视频入口。该剪辑不是新的控制速度验收，也不应将其画面或下列历史数值混作最新 `0.70 m` 膨胀半径验收。输入、输出、渲染声明和 SHA-256 见 [GitHub 展示媒体清单](evidence/github_showcase_media_manifest.json)。

历史完整录屏于 2026-07-27（中国标准时间）重新独立执行。建图巡航 `6/6` 通过，导航目标 1 和 2 的终点误差分别为 `0.2373 m` 和 `0.2329 m`，录制包装层和内层闭环报告均标记为成功。这些是历史录屏对应的结果；其结构化证据见 [建图巡航报告](evidence/end_to_end_mapping_patrol.json)、[导航任务报告](evidence/end_to_end_navigation_mission.json) 和 [媒体校验清单](evidence/navigation_video_manifest.json)。

## 0.70 m 膨胀半径重验收

2026-07-27 将局部和全局 costmap 的 `inflation_radius` 由 `0.80 m`
调为 `0.70 m`，保持 `robot_radius=0.60 m`。完整重新建图巡航
`6/6` 通过，两个目标均为 `SUCCEEDED`，终点误差为
`0.2406 m` 和 `0.2395 m`。速度门增强后独立执行的第一次
navigation-only 回归两个目标仍为 `SUCCEEDED`，误差为
`0.2353 m` 和 `0.2358 m`。随后在 DDS 接收时间戳和输入 QoS
改动后重跑，两个目标仍为 `SUCCEEDED`，误差为 `0.2390 m`
和 `0.2377 m`。

完整闭环、两次速度门回归、工件 SHA-256 和限制统一记录在
[`navigation_inflation_070_acceptance_summary.json`](evidence/navigation_inflation_070_acceptance_summary.json)。
其中对应本次全闭环的[run 报告](evidence/navigation_inflation_070_e2e/run_report.json)、
[Nav2 任务报告](evidence/navigation_inflation_070_e2e/navigation_mission.json)、
[demo 报告](evidence/navigation_inflation_070_e2e/demo_report.json) 和
[地图验证](evidence/navigation_inflation_070_e2e/map_validation.json) 已导出到 Git 跟踪的
`docs/evidence/` 中；展示地图的 PGM/YAML、巡航报告及 footprint 清理报告见
[建图输入证据目录](evidence/navigation_inflation_070_mapping/)。
本轮未落盘 `/odom` 或 `/plan` 逐点轨迹，因此可以确认双目标绕障导航通过，
但不给出最小净空或精确绕行侧的测量结论。

## 2026-07-26 历史独立回归明细

下列终点误差、速度命令和轨迹数据均属于 2026-07-26 历史独立回归，不是上节 `0.70 m` 重验收的数值。

### 验证结论

两个 `NavigateToPose` 目标均由 Nav2 接受并返回 `SUCCEEDED`，任务报告的总判定为 `success: true`。

| 目标 | 地图坐标 `(x, y)` | 用时 | 最终位置 | 终点误差 | 结果 |
| --- | --- | ---: | --- | ---: | --- |
| 1 | `(-2.5, -0.5)` | 23.70 s | `(-2.7032, -0.3797)` | 0.2361 m | `SUCCEEDED` |
| 2 | `(2.5, 0.7)` | 44.40 s | `(2.3062, 0.8325)` | 0.2347 m | `SUCCEEDED` |

任务容差为 0.35 m。探针记录了 8.9854 m 累计里程；第二段路径为避让实体障碍向侧方绕行，采样轨迹的最大 `y` 为 1.5072 m。任务报告没有错误，运行日志也没有 progress checker 失败。

### 实际控制器

本次运行实际加载的是：

```text
nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController
```

原始工件目录 `artifacts/navigation_static_odom_mppi_20260726_v1/` 中的 `mppi` 是早期命名遗留，不代表本次使用 MPPI。运行日志和当前活动参数文件 `src/independent_nav_bringup/config/nav2_atec_a2_p7.yaml` 均指向 Regulated Pure Pursuit（RPP）。

### 速度命令链

探针同时观测了完整五级命令链：

```text
/cmd_vel_nav -> /cmd_vel_smoothed -> /cmd_vel -> /platform/cmd_vel -> /sim/cmd_vel
```

| 话题 | 样本数 | 非零样本数 | 最大线速度 | 最大角速度 |
| --- | ---: | ---: | ---: | ---: |
| `/cmd_vel_nav` | 683 | 681 | 0.15 m/s | 0.25 rad/s |
| `/cmd_vel_smoothed` | 1367 | 1367 | 0.15 m/s | 0.25 rad/s |
| `/cmd_vel` | 1366 | 1366 | 0.15 m/s | 0.25 rad/s |
| `/platform/cmd_vel` | 1430 | 1366 | 0.15 m/s | 0.25 rad/s |
| `/sim/cmd_vel` | 1429 | 1365 | 0.15 m/s | 0.25 rad/s |

非零命令到达了仿真 adapter，证明 Nav2、速度平滑、碰撞监控和安全速度门之间的接口链路在该次回归中贯通。它不证明真实 A2 底盘 adapter、急停或步态控制已经完成。

### 定位与感知边界

本次 Gazebo 导航使用无漂移仿真里程计和恒等 `map -> a2/odom`。AMCL 已启动并输出诊断位姿，但不发布 TF，也不参与导航就绪条件。局部和全局代价地图使用由单颗 3D 雷达投影并过滤机体自回波得到的 `/collision_scan`。

实机必须移除仿真专用恒等 TF，由已验证的 AMCL/LIO 或融合定位源发布 `map -> odom`，并重新标定雷达外参、自过滤、速度限制和安全链路。

### 稳定证据

- [双目标任务报告](evidence/navigation_two_goal_mission.json)
- [导航话题、轨迹与代价地图探针](evidence/navigation_two_goal_probe.json)
- [完整录屏的建图巡航报告](evidence/end_to_end_mapping_patrol.json)
- [完整录屏的导航任务报告](evidence/end_to_end_navigation_mission.json)
- [视频编码、画面与 SHA-256 清单](evidence/navigation_video_manifest.json)

原始完整日志保留在 `artifacts/navigation_static_odom_mppi_20260726_v1/`。`docs/evidence/` 中的 JSON 是对应报告的原样副本，便于 GitHub 页面和汇报材料使用稳定链接。
