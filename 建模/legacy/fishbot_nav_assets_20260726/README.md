# Fishbot 地图归档

`fishbot_world.pgm` 和 `fishbot_world.yaml` 是从旧 Fishbot 四轮仿真迁入的历史
地图资产，保留在此处仅供复查旧实验。

它们与 ATEC A2 + P7 的练习场地、单雷达坐标链和 `0.60 m` 临时导航包络不兼容，
不得传给仓库根目录的 `run_navigation.sh`。新的地图应由 A2+P7 的
`run_mapping.sh` 生成，并保存为 `maps/atec_practice_world.*`。
