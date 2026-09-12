#!/usr/bin/env python3
"""从 Zenoh 读取 M1 的四路传感器数据，并在本机发布原始 ROS 消息。

不创建 Zenoh 发布者，不调用 RPC/服务，不建立 SDK 控制会话，不发布 TF 或电机指令。
保留设备时间戳、点云字段和 IMU 原始数值。已审查的 AIRY 驱动中，原始 IMU
加速度以 g 为单位，不能直接输入雷达惯性里程计（LIO）。
"""
import argparse
import json
import os
from pathlib import Path
import signal
import struct
import threading
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import Imu, PointCloud2
import zenoh
from airy_adapter.stream_guard import SourceIdentityGuard

STREAMS = (
    ('front_lidar', PointCloud2, '/m1_sensors/front/points_raw'),
    ('front_lidar/imu', Imu, '/m1_sensors/front/imu_raw'),
    ('rear_lidar', PointCloud2, '/m1_sensors/rear/points_raw'),
    ('rear_lidar/imu', Imu, '/m1_sensors/rear/imu_raw'),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', default='tcp/192.168.168.100:7447')
    parser.add_argument('--status', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=0, help='0 runs until interrupted')
    args = parser.parse_args()
    if args.endpoint != 'tcp/192.168.168.100:7447':
        parser.error('Only the verified M1 navigation endpoint is enabled.')
    if args.seconds < 0:
        parser.error('seconds must be nonnegative')
    rclpy.init()
    node = Node('m1_zenoh_sensor_receiver', enable_rosout=False, start_parameter_services=False)
    stats, publishers, subscriptions = {}, [], []
    guard = threading.Lock()
    source_guard = SourceIdentityGuard()
    started = time.monotonic()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    args.status.parent.mkdir(parents=True, exist_ok=True)

    def callback(topic, cls, publisher):
        def receive(sample):
            now = time.monotonic()
            observation = {}
            try:
                with guard:
                    if source_guard.fault:
                        return
                attachment = sample.attachment.to_bytes() if sample.attachment else b''
                if len(attachment) != 33 or attachment[16] != 16:
                    raise ValueError('Unknown Zenoh source identity attachment')
                sequence, publisher_ns = struct.unpack_from('<qq', attachment)
                gid = attachment[17:].hex()
                observation = dict(sequence=sequence, publisher_ns=publisher_ns, source_gid=gid)
                if len(sample.payload) > 32 * 1024 * 1024:
                    raise ValueError('Oversized sensor payload')
                msg = deserialize_message(sample.payload.to_bytes(), cls)
                stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
                with guard:
                    source_guard.observe(topic, gid, sequence)
                    # 身份核对与转发保持同一锁：故障后不让其他回调继续发布。
                    publish_started = time.monotonic()
                    publisher.publish(msg)
                    finished = time.monotonic()
                    item = stats[topic]
                    # 有界诊断统计：区分到达前缺口和本接收器转换/发布耗时。
                    item['max_callback_processing_s'] = max(item.get('max_callback_processing_s', 0), finished - now)
                    item['max_publish_s'] = max(item.get('max_publish_s', 0), finished - publish_started)
                    previous_sequence = item.get('last_sequence')
                    if previous_sequence is not None:
                        item['sequence_gaps'] += max(0, sequence - previous_sequence - 1)
                        source_gap = stamp - item['last_stamp']
                        receive_gap = now - item['last_receive_monotonic']
                        publish_gap = (publisher_ns - item['publisher_stamp_ns']) * 1e-9
                        item['max_device_gap_s'] = max(item.get('max_device_gap_s', 0), source_gap)
                        item['max_receive_gap_s'] = max(item.get('max_receive_gap_s', 0), receive_gap)
                        if sequence - previous_sequence != 1 or source_gap > (.015 if cls is Imu else .15):
                            events = item.setdefault('recent_gaps', [])
                            events.append(dict(device_gap_s=source_gap, receive_gap_s=receive_gap, publisher_gap_s=publish_gap,
                                               sequence_delta=sequence-previous_sequence, device_stamp=stamp))
                            del events[:-20]
                    item.update(source_gid=gid, last_sequence=sequence, publisher_stamp_ns=publisher_ns)
                    item['count'] += 1
                    item.setdefault('first_receive_monotonic', now)
                    if 'last_stamp' in item:
                        item['stamp_regressions'] += int(stamp < item['last_stamp'])
                        item['duplicate_stamps'] += int(stamp == item['last_stamp'])
                    item.update(last_receive_monotonic=now, last_stamp=stamp,
                                frame_id=msg.header.frame_id,
                                device_stamp_age_seconds=time.time() - stamp)
            except Exception as error:
                with guard:
                    source_guard.fault = source_guard.fault or (topic + ': ' + str(error))
                    stats[topic]['errors'] += 1
                    stats[topic]['last_error'] = str(error)
                    stats[topic]['fault_observation'] = observation
        return receive

    def save_status(running):
        now = time.monotonic()
        with guard:
            streams = {k: dict(v) for k, v in stats.items()}
            source_fault = source_guard.fault
        for item in streams.values():
            last = item.get('last_receive_monotonic')
            first = item.get('first_receive_monotonic')
            item['seconds_since_receive'] = None if last is None else now - last
            item['observed_hz'] = ((item['count'] - 1) / (last - first)
                                   if first is not None and last > first else 0)
        report = dict(endpoint=args.endpoint, source_domain_key=24,
                      ros_domain=os.environ.get('ROS_DOMAIN_ID', '0'),
                      ros_localhost_only=os.environ.get('ROS_LOCALHOST_ONLY', '0'),
                      running=running, timestamp_unix=time.time(), streams=streams,
                      forwarding_enabled=running and source_fault is None, source_fault=source_fault,
                      navigation_ready=False, motion_outputs=False,
                      note='Raw source clocks, frames and IMU g-units preserved; calibration pending.')
        temp = args.status.with_suffix('.tmp')
        temp.write_text(json.dumps(report, indent=2) + '\n')
        temp.replace(args.status)

    config = zenoh.Config()
    for key, value in {'mode': 'client', 'connect/endpoints': [args.endpoint],
                       'connect/timeout_ms': 4000,
                       'scouting/multicast/enabled': False}.items():
        config.insert_json5(key, json.dumps(value))
    try:
        with zenoh.open(config) as session:
            for source, cls, topic in STREAMS:
                publisher = node.create_publisher(cls, topic, qos_profile_sensor_data)
                publishers.append(publisher)
                stats[topic] = dict(count=0, errors=0, stamp_regressions=0, duplicate_stamps=0, sequence_gaps=0)
                key = f'24/{source}/sensor_msgs::msg::dds_::{cls.__name__}_/TypeHashNotSupported'
                subscriptions.append(session.declare_subscriber(key, callback(topic, cls, publisher)))
            print('Receiving M1 sensor streams on /m1_sensors/*; no motion output.', flush=True)
            next_report = 0
            while not stop.is_set() and rclpy.ok():
                rclpy.spin_once(node, timeout_sec=0.05)
                if time.monotonic() >= next_report:
                    save_status(True)
                    next_report = time.monotonic() + 2
                if args.seconds and time.monotonic() - started >= args.seconds:
                    break
            for subscription in subscriptions:
                subscription.undeclare()
    finally:
        save_status(False)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
