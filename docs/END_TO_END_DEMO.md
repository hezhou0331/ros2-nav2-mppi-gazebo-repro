# A2 + P7 自动建图、导航与录屏
本文档定义 ATEC A2 + P7 仿真工作区的可重复闭环演示。它只验证 Gazebo 中的平面运动代理、单颗头部雷达建图和 Nav2 规划，不可用于控制真实 A2。

## 前置条件

```bash
git clone https://github.com/hezhou0331/ros2-nav2-mppi-gazebo-repro.git
cd ros2-nav2-mppi-gazebo-repro
./install_dependencies.sh
./build_atec_a2_p7_nav.sh
./validate_atec_a2_p7_nav.sh
```
录屏另需要安装可选工具：

```bash
./tools/install_recording_dependencies.sh
```

该脚本安装 `ffmpeg`、`xvfb`、`openbox`、`wmctrl`、`xdotool`
和 `mesa-utils`。录屏使用独立的 Xvfb 显示器，不会抓取当前桌面。

## 运行

无界面完整验证：

```bash
./run_atec_end_to_end_demo.sh
```

默认工件目录为 `artifacts/atec_demo_<UTC时间戳>_<PID>/`，PID 用于避免
同一秒启动的两次演示相互覆盖。脚本默认为每次运行分配独立的
`ROS_DOMAIN_ID` 和 `GZ_PARTITION`，避免与
已在运行的 ROS/Gazebo 节点串话。如果调用环境已显式设置这两个变量，
脚本会保留指定值并将它们写入 `run_report.json`。

指定工件目录：

```bash
./run_atec_end_to_end_demo.sh \
  --artifact-dir "$PWD/artifacts/manual_demo"
```

录制完整闭环：

```bash
./tools/record_atec_end_to_end_demo.sh
```

录屏脚本强制使用 `use_gui:=true` 和 `use_rviz:=true`，在
`1920x1080` 虚拟显示器中将 Gazebo 与 RViz 平铺为左右两栏，输出
25 fps、H.264、`yuv420p` 的 MP4。

## 流程

1. 单颗 A2 头部 3D 雷达输出 `/lidar/points`，投影为 `/scan`。投影只使用
   `-0.50` 至 `0.12 m` 高度带，并过滤 `0.40 m` 内的 A2/P7 自身回波。
   练习场没有围墙且 Gazebo 提供无漂移里程计，因此本仿真配置关闭扫描匹配，
   并用有限最大量程束清空自由空间，避免稀疏回波把地图拉歪。这不是实机参数；
   真实 A2 必须用实测里程计与雷达重新启用、标定扫描匹配和回环检测。
2. 自动巡航仅向 `/cmd_vel` 发布指令，指令仍通过
   `velocity_gate -> /platform/cmd_vel -> simulation_platform_adapter` 进入 Gazebo。
3. 巡航从 `(-5.8, 0)` 出发，依次走过
   `(-4.9,0)`、`(-4.9,-1.2)`、`(3.3,-1.2)`、`(3.3,1.2)`、
   `(-4.9,1.2)`、`(-4.9,0)`。到点容差为 `0.20 m`，线速度
   `0.12 m/s`，角速度不超过 `0.22 rad/s`。
4. 脚本保存 `maps/atec_practice_world.{pgm,yaml}`，停止建图进程组，以同一地图
   重启 Gazebo、AMCL 和 Nav2。保存后只把机器人实际巡航折线周围 `0.65 m`
   的扫掠区域清为自由，去除单雷达看到的机身自回波；不会改动未经过区域或
   把比赛红色边界改成墙，并写出 `map_footprint_cleanup.json`。
5. 任务节点通过 `/navigate_to_pose` 依次执行 `map(-2.5,-0.5,0)` 与
   `map(2.5,0.7,0)`。每个目标必须返回 `SUCCEEDED`，且 `map -> base_link`
   的最终距离不超过 `0.35 m`。

## 验收与工件

成功运行会在 `artifacts/atec_demo_<UTC时间戳>_<PID>/` 中写入：

```text
maps/atec_practice_world.{pgm,yaml}
run_report.json
recording_report.json                         # 仅录屏模式
mapping_patrol.json
navigation_mission.json
map_validation.json
map_footprint_cleanup.json
demo_report.json
logs/
atec_a2_p7_end_to_end.mp4                  # 仅录屏模式
atec_a2_p7_end_to_end.mp4.ffprobe.json     # 仅录屏模式
atec_a2_p7_end_to_end.mp4.visual.json      # 左右半屏像素检查
atec_a2_p7_end_to_end_thumbnail.png        # 仅录屏模式
atec_a2_p7_end_to_end.mp4.sha256           # 仅录屏模式
```

`run_report.json` 是编排层总报告，无论成功或失败都会原子替换写入。
它记录起止时间、退出码、当前/失败阶段、工件路径以及实际使用的
`ROS_DOMAIN_ID` 和 `GZ_PARTITION`。即使建图、地图保存、导航或校验中途失败，
也可以从该文件机器可读地定位中断点。
`recording_report.json` 是录屏包装层总报告，同样会在所有退出路径上原子写入。
它记录失败阶段、退出码以及视频、`ffprobe`、左右画面、缩略图、哈希和
内层 `run_report.json` 的路径/存在性。只有内层演示通过且所有媒体工件校验完成后，
该报告才会标记为成功。
建图阶段会拒绝空地图：保存的 PGM 至少为 `100x100`，已知像素不少于
`500`，占用像素不少于 `20`。录屏结束后通过 `ffprobe` 校验
H.264、`yuv420p`、`1920x1080` 和时长；随后在视频中点分别检查左侧
Gazebo 与右侧 RViz 画面的亮度范围和方差，拒绝空白或近似纯色的半屏，
并严格校验平均帧率为 25 fps。随后提取同一时刻的缩略图供人工核对。
窗口平铺采样记录保存在
`logs/window_layout.tsv`。

## 排障

- 建图阶段报环境回波不足：检查 `/lidar/points`、`/scan` 和
  `front_lidar_sensor_link` TF，不要将 `range_min` 降回 `0.40 m` 以下。
- 地图质量校验失败：查看 `mapping_patrol.json`、`map_validation.json` 与
  `logs/mapping_launch.log`；失败时脚本不会继续进入 AMCL/Nav2。
- 录屏无法启动：运行依赖安装脚本，并查看 `logs/xvfb.log`、`logs/openbox.log`
  和 `logs/ffmpeg.log`。录屏强制软件 GL，不依赖当前用户桌面。

## 真机边界

Gazebo `VelocityControl`、`simulation_platform_adapter.py` 和本文档的自动任务都仅是
仿真工具。真实 A2 + P7 还需要厂商速度接口、watchdog、急停/手柄接管、
实测雷达外参、P7 安装板负载与实机低速验收，才能进入实际比赛测试。
