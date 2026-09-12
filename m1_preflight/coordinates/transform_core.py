"""导航坐标链纯几何：T_A_B 将 B 中的点变到 A；不重命名坐标冒充变换。"""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'airy_adapter'))
from prepare_mapping import validate_transform


def matrix(rotation, translation):
    out=np.eye(4);out[:3,:3]=rotation;out[:3,3]=translation
    return out


def inverse(t):
    return matrix(t[:3,:3].T,-t[:3,:3].T@t[:3,3])


def quaternion_matrix(q):
    q=np.asarray(q,dtype=float)
    if q.shape!=(4,) or not np.isfinite(q).all() or abs(np.linalg.norm(q)-1)>1e-3:
        raise ValueError('需要有效单位四元数 xyzw')
    x,y,z,w=q/np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])


def load_calibration(value):
    b=matrix(*validate_transform(value['base_from_lidar'],'base ← lidar'))
    i=matrix(*validate_transform(value['imu_from_lidar'],'imu ← lidar'))
    # base←IMU = base←LiDAR × LiDAR←IMU，反向平移必须随旋转一起求逆。
    return b,i,b@inverse(i)


def compose_navigation(map_from_imu,odom_from_base,base_from_imu,global_ns,odom_ns):
    if abs(int(global_ns)-int(odom_ns))>20_000_000:
        raise ValueError('全局位姿与局部里程计时间差超过 20 ms')
    for t in (map_from_imu,odom_from_base,base_from_imu):
        if t.shape!=(4,4) or not np.isfinite(t).all() or not np.allclose(t[3],[0,0,0,1]):
            raise ValueError('无效齐次变换')
        if not np.allclose(t[:3,:3].T@t[:3,:3],np.eye(3),atol=1e-5) or not np.isclose(np.linalg.det(t[:3,:3]),1,atol=1e-5):
            raise ValueError('变换旋转不是右手正交矩阵')
    map_from_base=map_from_imu@inverse(base_from_imu)
    return map_from_base@inverse(odom_from_base),map_from_base
