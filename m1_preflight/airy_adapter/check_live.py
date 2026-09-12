#!/usr/bin/env python3
"""逐帧比较 raw 与适配输出；只读 ROS，记录长测结果并严格报告建图缺项。"""
import argparse
import json
import struct
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Imu, PointCloud2
from prepare_mapping import validate_transform


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds', type=float, default=180)
    p.add_argument('--profile', type=Path, required=True)
    p.add_argument('--status', type=Path, required=True)
    p.add_argument('--bridge-status', type=Path, required=True)
    p.add_argument('--calibration', type=Path, default=Path(__file__).with_name('calibration.json'))
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if not 20 <= a.seconds <= 480:
        p.error('观察时间必须为 20–480 秒，保留时钟配置有效期余量')
    profile = json.loads(a.profile.read_text())
    if not 0 <= time.time() - profile['audit_timestamp_unix'] < profile['valid_for_seconds'] - a.seconds:
        p.error('时钟配置无法覆盖完整观察窗口，请重新审计')
    rclpy.init()
    node = Node('m1_airy_live_preflight', enable_rosout=False, start_parameter_services=False)
    qos = QoSProfile(depth=200, reliability=ReliabilityPolicy.BEST_EFFORT)
    rows, subscriptions, parse_errors = {}, [], []
    start = time.monotonic()
    bridge_before = json.loads(a.bridge_status.read_text())

    def callback(key, offset):
        def receive(data):
            # CDR 封装后第一个字段是 Header.stamp；只读头，避免拷贝数 MB 点云干扰测速。
            try:
                if data[:2] != b'\x00\x01' or len(data) < 12:
                    raise ValueError('仅支持已验证的 little-endian CDR Header')
                sec, ns = struct.unpack_from('<iI', data, 4)
                if ns >= 10**9:
                    raise ValueError('非法纳秒字段')
                rows[key].append((time.monotonic() - start, sec * 10**9 + ns - offset))
            except Exception as error:
                parse_errors.append(str(error))
        return receive

    for side in ('front', 'rear'):
        for kind, cls in (('points', PointCloud2), ('imu', Imu)):
            for stage in ('raw', 'adapted'):
                key = f'{side}/{kind}/{stage}'
                rows[key] = []
                topic = f'/m1_sensors/{side}/{kind}_raw' if stage == 'raw' else f'/m1_airy/{side}/{kind}'
                subscriptions.append(node.create_subscription(cls, topic, callback(key, 0 if stage == 'raw' else profile['offset_ns'][side]), qos, raw=True))
    try:
        while time.monotonic() - start < a.seconds:
            rclpy.spin_once(node, timeout_sec=.02)
        bridge_after = json.loads(a.bridge_status.read_text())
        adapter = json.loads(a.status.read_text())
        metrics = {}
        failures = []
        for side in ('front', 'rear'):
            for kind in ('points', 'imu'):
                key = f'{side}/{kind}'
                raw, adapted = rows[key + '/raw'], rows[key + '/adapted']
                # 排除发现期及尾部在途帧，再按精确整数时间戳求交集。
                window = [s for t, s in raw if 5 <= t <= a.seconds - 2]
                raw_set = set(window)
                adapted_set = {s for _, s in adapted}
                missing = raw_set - adapted_set
                gaps = [(b[1] - aa[1]) * 1e-9 for aa, b in zip(raw, raw[1:])]
                regressions = sum(g <= 0 for g in gaps)
                hz = (len(raw) - 1) / (raw[-1][0] - raw[0][0]) if len(raw) > 1 else 0
                metric = dict(raw_count=len(raw), adapted_count=len(adapted), raw_receive_hz=hz,
                              interior_raw_unique=len(raw_set), interior_missing_adapted=len(missing),
                              source_nonincreasing=regressions, max_source_gap_s=max(gaps, default=None))
                topic = f'/m1_sensors/{side}/{kind}_raw'
                before, after = bridge_before['streams'][topic], bridge_after['streams'][topic]
                metric['bridge_published_delta'] = after['count'] - before['count']
                metric['bridge_error_delta'] = after['errors'] - before['errors']
                metrics[key] = metric
                if not raw_set or missing or regressions or hz < (9 if kind == 'points' else 190):
                    failures.append(key + ': 帧率、逐帧对应或时间连续性未通过')
        if parse_errors or adapter['errors'] or adapter['clock_fault']:
            failures.append('解析或适配器时钟保护触发')
        if not adapter['running'] or not adapter.get('output_enabled',False) or time.time() - adapter['timestamp_unix'] > 5:
            failures.append('适配器状态不新鲜')
        if bridge_after.get('source_fault') or not bridge_after.get('forwarding_enabled',False):
            failures.append('源发布者身份保护已锁定原始转发')
        if not bridge_after['running'] or time.time() - bridge_after['timestamp_unix'] > 5 or any(v['seconds_since_receive'] is None or v['seconds_since_receive'] > 1 for v in bridge_after['streams'].values()):
            failures.append('原始接收器状态不新鲜')
        roots = {t: node.count_publishers(t) for t in ('/cmd_vel', '/cmd_vel_raw', '/cmd_vel_smoothed')}
        if any(roots.values()):
            failures.append('观察域根速度话题有发布者')
        missing_calibration = []
        calibration = json.loads(a.calibration.read_text())
        for side in ('front', 'rear'):
            for field in ('base_from_lidar', 'imu_from_lidar'):
                try:
                    validate_transform(calibration[side][field], side + '/' + field)
                except (ValueError, KeyError, TypeError) as error:
                    missing_calibration.append(str(error))
        report = dict(timestamp_unix=time.time(), duration_s=time.monotonic()-start,
                      streams=metrics, input_transport_passed=not failures, input_failures=failures,
                      parse_errors=parse_errors, adapter_status=adapter, bridge_status=bridge_after,
                      root_velocity_publishers=roots, calibration_failures=missing_calibration,
                      hardware_synchronized=False, cross_lidar_fusion_ready=False,
                      mapping_ready=False, navigation_ready=False, motion_outputs=False,
                      note='不启动建图。传输窗口通过也不证明实际外参或硬件同步；速度话题检查仅限本进程可发现的共享内存 ROS 图，不能证明其他传输或狗内没有控制流。')
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({k: v for k, v in report.items() if k not in ('adapter_status', 'bridge_status')}, ensure_ascii=False, indent=2))
        return 0 if not failures else 2
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
