# 离线规划验证代码

- `main.cpp`：生成三种合成栅格，调用上游原始 NavFn，独立检查路径和不可达结果。没有 ROS 节点或机器人控制连接。
- `CMakeLists.txt`：直接编译上游 `navfn.cpp`，不复制或替换算法。
- `plot.py`：读取输出 CSV，绘制三种场景的规划曲线。

本机在项目根目录运行 `./scripts/run_navfn_demo.sh`。

ORIN 在独立验证目录执行：

```bash
cd /home/nvidia/Workspace/ljy/navigation
source /opt/ros/humble/setup.bash
cmake -S experiments/navfn -B build/navfn \
  -DUPSTREAM="$PWD" -DCMAKE_BUILD_TYPE=Release \
  -DPython3_EXECUTABLE=/usr/bin/python3
cmake --build build/navfn -j2
./build/navfn/roamerx_offline_demo artifacts/navfn
```

0 和 1 场景必须找到路径，2 场景必须返回无路径；程序退出码 0 表示这些预期和路径采样检查均通过。这里的 0.5 m 排除距离是合成测试设定，未代表 M1 的测量尺寸。输出不代表真实运动轨迹。
