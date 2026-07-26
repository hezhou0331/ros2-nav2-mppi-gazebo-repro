# ATEC 地图

此目录只应保存由 A2 + P7 ATEC 练习场地生成的地图。通过仓库根目录的
`./run_mapping.sh` 建图后，使用：

```bash
ros2 run independent_nav_bringup save_map.py \
  --output /home/hezhou/公共/ros2_nav_repro/maps/atec_practice_world
```

随后将 `maps/atec_practice_world.yaml` 传给 `./run_navigation.sh`。

旧 `fishbot_world.*` 来自四轮 Fishbot 场地，不匹配 A2 + P7 的练习世界、雷达链路
或 `0.60 m` 的临时导航包络；不得用于本工作区的 ATEC 导航。
