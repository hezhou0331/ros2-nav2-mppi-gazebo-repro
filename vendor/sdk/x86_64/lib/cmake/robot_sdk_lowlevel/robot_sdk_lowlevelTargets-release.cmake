#----------------------------------------------------------------
# Generated CMake target import file for configuration "Release".
#----------------------------------------------------------------

# Commands may need to know the format version.
set(CMAKE_IMPORT_FILE_VERSION 1)

# Import target "robot_sdk_lowlevel::robot_sdk_lowlevel" for configuration "Release"
set_property(TARGET robot_sdk_lowlevel::robot_sdk_lowlevel APPEND PROPERTY IMPORTED_CONFIGURATIONS RELEASE)
set_target_properties(robot_sdk_lowlevel::robot_sdk_lowlevel PROPERTIES
  IMPORTED_LINK_DEPENDENT_LIBRARIES_RELEASE "Boost::system"
  IMPORTED_LOCATION_RELEASE "${_IMPORT_PREFIX}/lib/librobot_sdk_lowlevel.so.0.0.1"
  IMPORTED_SONAME_RELEASE "librobot_sdk_lowlevel.so.0"
  )

list(APPEND _IMPORT_CHECK_TARGETS robot_sdk_lowlevel::robot_sdk_lowlevel )
list(APPEND _IMPORT_CHECK_FILES_FOR_robot_sdk_lowlevel::robot_sdk_lowlevel "${_IMPORT_PREFIX}/lib/librobot_sdk_lowlevel.so.0.0.1" )

# Commands beyond this point should not need to know the version.
set(CMAKE_IMPORT_FILE_VERSION)
