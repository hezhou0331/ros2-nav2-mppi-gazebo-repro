#!/usr/bin/env python3
"""检查已有低层 JSONL 记录，不加载 SDK，也不建立网络连接。

仅验证文件内容，不据此确认设备身份、时钟同步或实时导航就绪状态。
不会根据姿态伪造缺失的加速度。
"""
import argparse
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

VECTOR_WIDTHS = {
    'joint_pos_rad': 16, 'joint_vel_rad_s': 16, 'joint_torque_nm': 16,
    'quat_xyzw': 4, 'gyro_rad_s': 3, 'acc_m_s2': 3,
}


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def audit(path):
    counts = dict.fromkeys(VECTOR_WIDTHS, 0)
    invalid = dict.fromkeys(VECTOR_WIDTHS, 0)
    errors = []
    timestamps, norms = [], []
    rows = 0
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for line_number, raw in enumerate(stream, 1):
            digest.update(raw)
            if not raw.strip():
                continue
            rows += 1
            try:
                frame = json.loads(raw)
                if not isinstance(frame, dict):
                    raise ValueError('record must be an object')
            except (ValueError, UnicodeDecodeError) as error:
                errors.append(f'line {line_number}: {error}')
                continue
            stamp = frame.get('timestamp_ms')
            if finite_number(stamp):
                timestamps.append(stamp)
            else:
                errors.append(f'line {line_number}: missing/invalid timestamp_ms')
            for key, width in VECTOR_WIDTHS.items():
                if key not in frame:
                    continue
                value = frame[key]
                if (not isinstance(value, list) or len(value) != width
                        or not all(finite_number(v) for v in value)):
                    invalid[key] += 1
                    continue
                counts[key] += 1
                if key == 'quat_xyzw':
                    norms.append(math.sqrt(sum(v * v for v in value)))
    intervals = [b - a for a, b in zip(timestamps, timestamps[1:])]
    unique = len(set(timestamps))
    span = (timestamps[-1] - timestamps[0]) / 1000 if len(timestamps) > 1 else 0
    # 重复读取同一设备帧不能计为新样本，避免虚增采样频率。
    monotonic = all(dt >= 0 for dt in intervals)
    imu_fields = ['acc_m_s2', 'gyro_rad_s', 'quat_xyzw']
    return {
        'source': str(path.resolve()), 'sha256': digest.hexdigest(), 'rows': rows,
        'valid_vector_rows': counts, 'invalid_vector_rows': invalid,
        'parse_or_timestamp_errors': errors[:20], 'error_count': len(errors),
        'unique_timestamps': unique,
        'duplicate_timestamps': len(timestamps) - unique,
        'backward_timestamp_steps': sum(dt < 0 for dt in intervals),
        'device_time_span_seconds': span,
        'unique_frame_rate_hz': (unique - 1) / span if span > 0 and monotonic else None,
        'median_positive_interval_ms': statistics.median([dt for dt in intervals if dt > 0])
            if any(dt > 0 for dt in intervals) else None,
        'quaternion_norm_range': [min(norms), max(norms)] if norms else None,
        'complete_imu_fields_in_every_row': rows > 0 and all(counts[k] == rows for k in imu_fields),
        'missing_imu_fields': [k for k in imu_fields if counts[k] != rows or rows == 0],
        'clock_alignment_verified': False,
        'navigation_ready': False,
        'note': 'Recorded data only. No SDK initialized. Requires live point cloud, calibrated frames and clock alignment.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recordings', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.resolve() in [p.resolve() for p in args.recordings]:
        parser.error('output must not overwrite an input recording')
    report = {'audited_at': datetime.now(timezone.utc).isoformat(),
              'recordings': [audit(path) for path in args.recordings]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
    return int(any(r['error_count'] or any(r['invalid_vector_rows'].values())
                   or r['backward_timestamp_steps'] or not r['rows'] for r in report['recordings']))


if __name__ == '__main__':
    raise SystemExit(main())
