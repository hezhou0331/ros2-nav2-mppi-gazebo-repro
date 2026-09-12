#!/usr/bin/env python3
"""只读发现 ROS 节点并采样传感器消息，不初始化机器狗 SDK。"""
import argparse
import json
import os
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rosidl_runtime_py.utilities import get_message
from tf2_ros import Buffer, TransformListener


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=float, default=12.0)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 3 <= args.seconds <= 120:
        parser.error('--seconds must be between 3 and 120')
    rclpy.init()
    node = Node('m1_readonly_observer', enable_rosout=False,
                start_parameter_services=False)
    buffer = Buffer()
    listener = TransformListener(buffer, node)
    samples = {}
    subscriptions = []
    supported = {'sensor_msgs/msg/PointCloud2', 'sensor_msgs/msg/Imu',
                 'sensor_msgs/msg/LaserScan', 'nav_msgs/msg/Odometry'}

    def receive(topic, msg):
        item = samples[topic]
        now = time.monotonic()
        item.setdefault('first_received', now)
        item['last_received'] = now
        item['count'] += 1
        item['frame_id'] = msg.header.frame_id
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        item['stamp_age_seconds'] = node.get_clock().now().nanoseconds * 1e-9 - stamp
        if hasattr(msg, 'child_frame_id'):
            item['child_frame_id'] = msg.child_frame_id
        if hasattr(msg, 'fields'):
            item['fields'] = [{'name': field.name, 'datatype': field.datatype,
                               'offset': field.offset, 'count': field.count}
                              for field in msg.fields]
            item['points'] = msg.width * msg.height

    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        for topic, types in node.get_topic_names_and_types():
            if topic in samples or not supported.intersection(types):
                continue
            kind = next(kind for kind in types if kind in supported)
            samples[topic] = {'type': kind, 'count': 0}
            subscriptions.append(node.create_subscription(
                get_message(kind), topic,
                lambda msg, topic=topic: receive(topic, msg), qos_profile_sensor_data))
        rclpy.spin_once(node, timeout_sec=0.2)
    for item in samples.values():
        first = item.pop('first_received', None)
        last = item.pop('last_received', None)
        if first is not None and last > first:
            item['observed_hz'] = (item['count'] - 1) / (last - first)
    transforms = {}
    for target, source in [('map', 'odom'), ('odom', 'base_link'), ('map', 'base_link')]:
        try:
            tf = buffer.lookup_transform(target, source, rclpy.time.Time())
            transforms[f'{target} <- {source}'] = {
                'available': True, 'stamp': tf.header.stamp.sec}
        except Exception as error:
            transforms[f'{target} <- {source}'] = {'available': False, 'reason': str(error)}
    report = {
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'scope': 'Read-only snapshot in the selected ROS domain; absence is not proof of no device.',
        'ros_domain_id': os.environ.get('ROS_DOMAIN_ID', '0'),
        'rmw': os.environ.get('RMW_IMPLEMENTATION', 'default'),
        'ros_localhost_only': os.environ.get('ROS_LOCALHOST_ONLY', '0'),
        'nodes': sorted(node.get_node_names()),
        'topics': {topic: {'types': types, 'publishers': node.count_publishers(topic),
                           'subscribers': node.count_subscribers(topic)}
                   for topic, types in node.get_topic_names_and_types()},
        'samples': samples, 'transforms': transforms,
        'hardware_navigation_verified': False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(report, indent=2, ensure_ascii=False))
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
