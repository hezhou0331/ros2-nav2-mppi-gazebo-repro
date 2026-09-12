# Ubuntu Jammy 的 liblcm-dev 提供 pkg-config 元数据，但不含 lcmConfig.cmake。
# 将实际库文件导入为 CMake 目标，不修改上游源码。
find_path(lcm_INCLUDE_DIR NAMES lcm/lcm-cpp.hpp)
find_library(lcm_LIBRARY NAMES lcm)
include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(lcm REQUIRED_VARS lcm_LIBRARY lcm_INCLUDE_DIR)
if(lcm_FOUND AND NOT TARGET lcm)
  add_library(lcm SHARED IMPORTED GLOBAL)
  set_target_properties(lcm PROPERTIES
    IMPORTED_LOCATION "${lcm_LIBRARY}"
    INTERFACE_INCLUDE_DIRECTORIES "${lcm_INCLUDE_DIR}")
endif()
mark_as_advanced(lcm_LIBRARY lcm_INCLUDE_DIR)
