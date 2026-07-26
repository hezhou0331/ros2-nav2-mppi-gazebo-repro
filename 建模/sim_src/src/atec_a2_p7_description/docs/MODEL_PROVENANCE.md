# Model Provenance

## A2

`ATEC/导航参考资料` 不含可用于仿真的 A2 URDF 或网格，且其中的 Deep Robotics 模型不是 A2，不能作为替代。本地 `ATEC/现有的资料/A2_dog/a2.MD` 确认目标为 Unitree A2（12 DOF、站立外廓约 `0.820 x 0.440 x 0.570 m`、约 42 kg）并指向 Unitree 官方来源。因此本包从 `unitree_ros` 导入 A2 描述，固定来源为：

- Repository: `https://github.com/unitreerobotics/unitree_ros`
- Commit: `aa0f5c68b5aba347bad409e71b6430407da758d7`
- Imported files: `robots/a2_description/urdf/a2.urdf`, `a2.xml`, and `meshes/`

本包的 `urdf/vendor/a2.urdf` 和 `urdf/vendor/a2.xml` 保留为原始供应商输入；`urdf/components/a2.urdf.xacro` 由 `tools/generate_components.py` 生成并只改写包内网格 URI。已验证的原始 A2 URDF SHA-256 是 `041d2ba0...b724f`，MJCF 是 `fd6b42b8...7c479`。

## P7 And UMI Gripper

P7 v3 与 UMI 夹爪来自团队提供的本地资料：`ATEC/现有的资料/p7_arm_v3_umi_gripper/`。其原始 URDF 保存在 `urdf/vendor/p7_arm_v3_umi_gripper_v3.urdf`；已验证 SHA-256 为 `ab41de5a...8b01d`。`tools/generate_components.py` 生成带 `p7_` 前缀的组件，避免与 A2 的 `base_link` 冲突。

资料包未提供明确的再分发许可证。P7/UMI 网格仅能在团队获准使用的环境中使用，公开分发、发布镜像或提交竞赛材料前必须取得供应商书面确认。

## Center-Back Mount

仿真安装关系固定为 `base_link -> a2_p7_mount_link -> p7_base_link`，坐标为 `x=0, y=0`，默认 `arm_mount_z=0.145 m`。安装板为 `0.30 x 0.24 x 0.018 m`、质量 `1.20 kg`，两条红色边为可视化防护假设。

这些数值未由 A2 预留螺孔图、实测壳体、转接板、紧固件、载荷计算、线缆约束或急停方案验证。它们不能直接用于加工、安装或参赛申报。

## Simulation Transformations

- A2 视觉网格和原始链接/关节来自上游 A2 URDF。
- P7 视觉网格来自团队资料；碰撞改为低复杂度基本体以保持 Gazebo 可运行。
- UMI 资料中的 14 个连续被动关节没有完整耦合信息，因此在导航仿真中固定；唯一棱柱夹爪关节采用仿真 effort/velocity 参数。
- `VelocityControl` 和 `OdometryPublisher` 只提供平面移动/里程计代理。它们不验证 A2 步态稳定性、腿部动力学、P7 负载能力、实机传感器标定或 Unitree 控制协议。

生成组件的命令：

```bash
python3 tools/generate_components.py
```

只应在原始 vendor 文件更新后重新生成，并重新检查 URDF、碰撞和来源哈希。
