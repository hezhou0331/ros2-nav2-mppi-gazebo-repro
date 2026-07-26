cmake_minimum_required(VERSION 3.8)
project(independent_nav_bringup)

find_package(ament_cmake REQUIRED)

install(DIRECTORY config launch platforms docs rviz DESTINATION share/${PROJECT_NAME})
install(PROGRAMS
  scripts/velocity_gate.py
  scripts/navigation_health.py
  scripts/scan_qos_relay.py
  scripts/save_map.py
  scripts/simulation_platform_adapter.py
  scripts/simulation_supervisor.py
  scripts/mapping_patrol.py
  scripts/navigation_mission.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
