cmake_minimum_required(VERSION 3.16)

if (CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
  project(robot_sdk_lowlevel_zs_m1f_example LANGUAGES CXX)
  set(CMAKE_CXX_STANDARD 17)
  set(CMAKE_CXX_STANDARD_REQUIRED ON)
endif()

get_filename_component(_robot_sdk_release_prefix "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
list(PREPEND CMAKE_PREFIX_PATH "${_robot_sdk_release_prefix}")
find_package(robot_sdk_lowlevel CONFIG REQUIRED)

add_executable(lowlevel_sdk_zs_m1f_example
  sdk_example.cpp
)

target_link_libraries(lowlevel_sdk_zs_m1f_example
  PRIVATE
    robot_sdk_lowlevel::robot_sdk_lowlevel
)
