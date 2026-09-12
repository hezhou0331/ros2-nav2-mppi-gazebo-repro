# robot_sdk_lowlevel C++ SDK 0.0.1

This release package contains:

- `lib/`: shared library and CMake package configuration
- `include/`: public headers
- `docs/`: Chinese and English SDK documentation
- `example/`: C++ example programs

Use with CMake:

```cmake
find_package(robot_sdk_lowlevel CONFIG REQUIRED)
target_link_libraries(your_target PRIVATE robot_sdk_lowlevel::robot_sdk_lowlevel)
```
