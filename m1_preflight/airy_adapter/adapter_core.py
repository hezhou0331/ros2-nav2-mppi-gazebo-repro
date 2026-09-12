"""M1 传感器适配纯逻辑：设备时间映射、回退保护、SI 单位及原生 XYZIRT。

每个雷达的点云/IMU 共用固定偏移，保留测量时间间隔；不逐条替换为到达时间。
后雷达偏移仅为软件估计，不能据此宣称双雷达硬件同步或启动融合。
"""
import copy
import math
import time
import numpy as np

G = 9.80665


def stamp_ns(msg):
    return msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec


def set_stamp(msg, ns):
    if not 0 <= ns < 2147483647 * 1_000_000_000:
        raise ValueError('时间超出 ROS stamp 范围')
    msg.header.stamp.sec, msg.header.stamp.nanosec = divmod(int(ns), 1_000_000_000)


def cloud_view(msg):
    expected = {'x': (7, '<f4'), 'y': (7, '<f4'), 'z': (7, '<f4'),
                'intensity': (7, '<f4'), 'ring': (4, '<u2'), 'timestamp': (8, '<f8')}
    fields = {f.name: f for f in msg.fields}
    if msg.is_bigendian or not msg.width or not msg.height:
        raise ValueError('未支持的字节序或空点云')
    if msg.row_step < msg.width * msg.point_step or len(msg.data) != msg.row_step * msg.height:
        raise ValueError('点云数据长度不符合行布局')
    names, formats, offsets = [], [], []
    for name, (kind, fmt) in expected.items():
        f = fields.get(name)
        if f is None or f.datatype != kind or f.count != 1 or f.offset + np.dtype(fmt).itemsize > msg.point_step:
            raise ValueError('XYZIRT 字段不匹配: ' + name)
        names.append(name); formats.append(fmt); offsets.append(f.offset)
    dtype = np.dtype(dict(names=names, formats=formats, offsets=offsets, itemsize=msg.point_step))
    return np.ndarray((msg.height, msg.width), dtype=dtype, buffer=msg.data,
                      strides=(msg.row_step, msg.point_step))


def convert_cloud(msg, offset_ns):
    out = copy.deepcopy(msg)
    points = cloud_view(out)
    valid = np.isfinite(points['x']) & np.isfinite(points['y']) & np.isfinite(points['z'])
    if np.count_nonzero(valid) < 2:
        raise ValueError('点云有效点不足')
    relative = points['timestamp'][valid] - stamp_ns(msg) * 1e-9
    if (not np.all(np.isfinite(relative)) or np.min(relative) < -1e-6 or
            np.max(relative) > .12 or np.max(points['ring'][valid]) >= 96 or
            not np.all(np.isfinite(points['intensity'][valid]))):
        raise ValueError('点云逐点时间/线束/强度异常')
    # 头时间和逐点绝对秒同步平移；原始无效点保持无效，不制造数据。
    points['timestamp'][:] += offset_ns * 1e-9
    set_stamp(out, stamp_ns(msg) + offset_ns)
    return out


def convert_imu(msg, offset_ns, imu_frame):
    out = copy.deepcopy(msg)
    for field in ['linear_acceleration', 'angular_velocity']:
        vec = getattr(out, field)
        if not all(math.isfinite(getattr(vec, axis)) for axis in 'xyz'):
            raise ValueError('IMU 包含非有限测量')
    if not all(math.isfinite(v) for v in out.linear_acceleration_covariance):
        raise ValueError('加速度协方差异常')
    for axis in 'xyz':
        setattr(out.linear_acceleration, axis, getattr(out.linear_acceleration, axis) * G)
    # 协方差单位由 g² 转为 (m/s²)²；全零仍表示未知，-1 仍表示未提供。
    if out.linear_acceleration_covariance[0] != -1:
        out.linear_acceleration_covariance = [v * G * G for v in out.linear_acceleration_covariance]
    out.orientation.x = out.orientation.y = out.orientation.z = 0.0
    out.orientation.w = 1.0
    out.orientation_covariance = [-1.0] + [0.0] * 8
    # 驱动原先错误地与点云共用 frame；单独命名，待取得真实标定再建立 TF。
    out.header.frame_id = imu_frame
    set_stamp(out, stamp_ns(msg) + offset_ns)
    return out


class ClockGuard:
    """任一时钟回退/跳变后锁住输出，必须重新审计并重启，不能静默续接旧地图。"""
    def __init__(self):
        self.last = {}
        self.fault = None

    def check(self, stream, source_ns, mapped_ns, wall_ns, monotonic_ns):
        if self.fault:
            raise ValueError(self.fault)
        previous = self.last.get(stream)
        reason = None
        if previous:
            ds = (source_ns - previous[0]) * 1e-9
            dm = (monotonic_ns - previous[1]) * 1e-9
            dw = (wall_ns - previous[2]) * 1e-9
            if ds <= 0: reason = '设备时间重复或回退'
            elif abs(ds - dm) > .5: reason = '设备时钟跳变或传输间断'
            elif abs(dw - dm) > .05: reason = '主机墙钟跳变'
        age = (wall_ns - mapped_ns) * 1e-9
        if not -.05 <= age <= 1.0: reason = '映射时间超出接收新鲜度范围'
        if reason:
            self.fault = stream + ': ' + reason
            raise ValueError(self.fault)
        self.last[stream] = (source_ns, monotonic_ns, wall_ns)
