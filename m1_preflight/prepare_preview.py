#!/usr/bin/env python3
"""根据明确输入生成预检配置；不猜测未知的传感器话题或外参。"""
import argparse
import json
import math
from pathlib import Path
import yaml


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--map', type=Path, required=True)
    parser.add_argument('--odom-topic', required=True)
    parser.add_argument('--scan-topic', required=True)
    parser.add_argument('--odom-frame', required=True)
    parser.add_argument('--base-frame', required=True)
    parser.add_argument('--footprint', required=True, help='Measured footprint as JSON [[x,y],...] in metres')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    footprint = json.loads(args.footprint)
    if (not isinstance(footprint, list) or len(footprint) < 3 or
            any(not isinstance(p, list) or len(p) != 2 or
                any(isinstance(v, bool) or not isinstance(v, (int, float)) or
                    not math.isfinite(v) for v in p) for p in footprint)):
        parser.error('footprint must contain at least three finite [x,y] points in metres')
    area = abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(footprint,footprint[1:]+footprint[:1]))) / 2
    if area < 1e-4:
        parser.error('footprint must have positive area')
    for topic in [args.odom_topic, args.scan_topic]:
        if not topic.startswith('/') or any(c.isspace() for c in topic):
            parser.error('topic names must be explicit absolute ROS topic names')
    for frame in [args.odom_frame, args.base_frame]:
        if not frame or frame.startswith('/') or any(c.isspace() for c in frame):
            parser.error('frame names must be nonempty and must not start with /')
    if not args.map.is_file():
        parser.error('map YAML does not exist')
    source = args.upstream / 'src/navigation/src/robot_navigo/params/navigo_params.yaml'
    data = yaml.safe_load(source.read_text())

    def rewrite(value):
        if isinstance(value, dict):
            for key, child in list(value.items()):
                if key == 'use_sim_time': value[key] = False
                elif key == 'odom_topic': value[key] = args.odom_topic
                elif key == 'robot_base_frame': value[key] = args.base_frame
                elif key == 'global_frame' and child == 'odom': value[key] = args.odom_frame
                elif key == 'footprint': value[key] = json.dumps(footprint)
                else: rewrite(child)
        elif isinstance(value, list):
            for child in value: rewrite(child)
    rewrite(data)
    data['map_server']['ros__parameters']['yaml_filename'] = str(args.map.resolve())
    data['local_costmap']['local_costmap']['ros__parameters']['obstacle_layer']['scan']['topic'] = args.scan_topic
    data['global_costmap']['global_costmap']['ros__parameters']['static_layer']['map_subscribe_transient_local'] = True
    radius = max(math.hypot(x, y) for x, y in footprint) + 0.1
    for costmap in ['local_costmap', 'global_costmap']:
        data[costmap][costmap]['ros__parameters']['inflation_layer']['inflation_radius'] = radius
    scan = data['local_costmap']['local_costmap']['ros__parameters']['obstacle_layer']['scan']
    scan.update(obstacle_max_range=8.0, raytrace_max_range=8.5)
    ctrl = data['controller_server']['ros__parameters']
    ctrl['controller_frequency'] = 20.0
    ctrl['FollowPath'].update(vx_max=0.2, vx_min=0.0, vy_max=0.0, wz_max=0.3,
                             batch_size=1000, visualize=False, model_dt=0.05)
    data['velocity_optimizer']['ros__parameters'].update(
        max_velocity=[0.2,0.0,0.3], min_velocity=[0.0,0.0,-0.3],
        max_accel=[0.3,0.0,0.5], max_decel=[-0.3,0.0,-0.5], velocity_timeout=0.3)
    # 这些限值仅用于预检计算，不代表已标定的 M1 运动能力。
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text('# 仅用于预检：不连接执行器；需要提供实测输入。\n' +
                           yaml.safe_dump({'m1_preview': data}, sort_keys=False))
    print(args.output.resolve())


if __name__ == '__main__':
    main()
