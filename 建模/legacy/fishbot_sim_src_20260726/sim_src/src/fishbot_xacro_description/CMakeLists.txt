cmake_minimum_required(VERSION 3.8)
project(fishbot_xacro_description)

# ament_cmake 是 ROS 2 CMake 类型功能包的构建基础。
find_package(ament_cmake REQUIRED)

# 本包只有描述文件，不编译 C++。这里把资源安装到 install/share，
# 这样 ros2 launch 才能通过包名找到它们。
install(
  DIRECTORY config launch rviz urdf worlds
  DESTINATION share/${PROJECT_NAME}
)

install(
  PROGRAMS scripts/twist_odom_tf_bridge.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME twist_odom_tf_bridge.py
)

# 生成 ROS 2 功能包的元数据。
ament_package()
