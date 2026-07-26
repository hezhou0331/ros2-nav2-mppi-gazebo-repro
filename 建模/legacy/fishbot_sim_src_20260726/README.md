# Fishbot 历史工作区归档

此目录是 2026-07-26 从旧顶层 `建模/` 迁入的 Fishbot 工作区归档。原有源码、
`build/`、`install/` 和 `log/` 均原样保留，未自动删除其中的用户文件或历史记录。
它不再是 ATEC 的构建或运行入口。

ATEC A2 + P7 的当前模型已归入：

```text
/home/hezhou/公共/ros2_nav_repro/建模/sim_src/src/atec_a2_p7_description
```

请从 `/home/hezhou/公共/ros2_nav_repro` 根目录构建，并只加载该仓库的
`install/setup.bash`。不要在新的 ATEC 启动脚本中 source
`建模/legacy/fishbot_sim_src_20260726/sim_src/install/setup.bash`，它仍指向
旧 Fishbot 包。

若需要查阅旧实验，可直接在本归档中查看；不要把其旧地图、模型或构建产物混入
A2+P7 工作区。历史 Fishbot 地图与当前 ATEC 场地和机器人包络不兼容。
