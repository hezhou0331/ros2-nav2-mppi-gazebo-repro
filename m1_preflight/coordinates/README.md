# 坐标链接入准备

当前为隔离软件验证，限定 ROS domain 179 / localhost。真实标定文件缺项时拒绝启动，不向真实导航 TF 图发布。

## 坐标约定与来源

`T_A_B` 将 B 系坐标转换为 A 系。RoamerX `mapping_alg.h::set_posestamp` 发布惯性状态位置和旋转，`mapping_alg.cpp::publish_odometry` 的父子名为 map/body；不能把该 body 直接改名为 base_link。

- `T_base_imu = T_base_lidar × inverse(T_imu_lidar)`。
- `T_map_base = T_map_imu × inverse(T_base_imu)`。
- `T_map_odom = T_map_base × inverse(T_odom_base)`。

最后一步需要与全局位姿时间对应的局部里程计。当前软件检查最大差 20 ms、消息年龄不超过 0.5 秒、拒绝重复/回退。20 ms 是隔离软件阈值，不是已验收的传感器同步误差。物理部署前应明确同步精度、插值方式和定位跳变处理。

`preview_node.py` 订阅 `/m1_coordinates/global_imu`（Odometry，map/body）与 `/m1_coordinates/local_odom`（Odometry，odom/base_link），输出私有 `/m1_coordinates/tf`、`tf_static` 和 `global_base_pose`。静态链为 base_link→rslidar_head→rslidar_head_imu。局部 odom→base_link 应由局部里程计的唯一发布者负责，本节点不重复发布。

不生成速度或复制不可靠协方差。源码复核发现上游 SLAM 先 publish 后更新 pose covariance，定位输出还把置信度装进 covariance 并写零 twist；这些不能直接作为控制器的标准速度/协方差。当前节点只消费位姿，未对上游做隐蔽修改。

## 运行验证

在 Orin 导航工作区的新 bash 终端：

```bash
source m1_preflight/env.sh
export ROS_DOMAIN_ID=179 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
/usr/bin/python3 m1_preflight/coordinates/test_transforms.py
/usr/bin/python3 m1_preflight/coordinates/verify_ros.py
```

测试标定只写入 artifacts/coordinates/synthetic_calibration.json。不得复制到真实 calibration.json。六项几何测试通过；ROS 验证收到 401 条正确变换，静态边正确，注入的时间回退被拒绝。真实 calibration.json 启动拒绝已验证。

下一步是取得真实外参，将校正后的真实全局位姿和局部里程计在隔离图中对齐检查，再接入导航；当前尚未完成实机 TF 验收。
