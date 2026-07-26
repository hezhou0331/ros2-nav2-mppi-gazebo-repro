# Platform Adapter Contract

The navigation stack never controls a real robot directly. The future A2 + P7
adapter must subscribe only to `/platform/cmd_vel` and publish `/platform/ready`.
It must reject stale commands within 200 ms, publish `ready=false` for manual
override, estop, communication loss, or a non-automatic mode, and must not
publish `odom -> base_link`. The localization source is the sole owner of that TF.

`simulation_platform_adapter.py` implements this contract only for Gazebo. It is
not a real-robot adapter and must not be connected to a physical platform.

The ATEC reference configuration assumes one head-mounted 3D lidar mounted at
the official `front_lidar_link`. The simulation publishes its point cloud in
the child `front_lidar_sensor_link`, whose axes are suitable for a horizontal
scan. It publishes `/lidar/points`; the launch file projects that single stream
to `/scan` for SLAM and localization, then removes endpoints inside the A2 + P7
footprint to produce `/collision_scan` for both costmaps and Collision Monitor.
Those are representations of one sensor. The real driver extrinsics remain
subject to the final hardware measurement.
