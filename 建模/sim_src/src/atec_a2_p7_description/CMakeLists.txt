cmake_minimum_required(VERSION 3.8)
project(atec_a2_p7_description)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY config docs launch meshes rviz urdf worlds
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
