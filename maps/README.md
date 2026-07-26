# ATEC 地图

此目录只应保存由 A2 + P7 ATEC 练习场地生成的地图。通过仓库根目录的
`./run_mapping.sh` 建图后，使用：

```bash
ros2 run independent_nav_bringup save_map.py \
  --output /home/hezhou/公共/ros2_nav_repro/maps/atec_practice_world
```

随后将 `maps/atec_practice_world.yaml` 传给 `./run_navigation.sh`。

地图必须来自 A2 + P7 ATEC 练习场地，并与当前雷达链路和 `0.60 m` 临时导航包络
一起校验；不要把其他机器人或其他场地的地图复制到这里。
