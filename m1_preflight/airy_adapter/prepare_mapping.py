#!/usr/bin/env python3
"""完整外参通过校验才生成单前雷达建图配置；不启动建图或运动。

R/T 使用 p_IMU = R * p_LiDAR + T，不能把反向变换直接填入。
"""
import argparse,json
from pathlib import Path
import numpy as np
import yaml

def validate_transform(value,label):
    if not value.get('verified') or not value.get('evidence'):
        raise ValueError(label + ': 缺少已核实标定及来源')
    r=np.array(value.get('rotation'),dtype=float);t=np.array(value.get('translation_m'),dtype=float)
    if r.shape!=(3,3) or t.shape!=(3,) or not np.isfinite(r).all() or not np.isfinite(t).all():
        raise ValueError(label + ': 必须提供有限的 3×3 旋转和三维平移')
    if not np.allclose(r.T@r,np.eye(3),atol=1e-5) or not np.isclose(np.linalg.det(r),1,atol=1e-5):
        raise ValueError(label + ': 旋转不满足正交右手坐标约定')
    return r,t

def main():
    p=argparse.ArgumentParser();p.add_argument('--calibration',type=Path,default=Path(__file__).with_name('calibration.json'));p.add_argument('--upstream-config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:
        c=json.loads(a.calibration.read_text())['front']
        validate_transform(c['base_from_lidar'],'base ← front LiDAR')
        r,t=validate_transform(c['imu_from_lidar'],'front IMU ← front LiDAR')
    except (ValueError,KeyError,TypeError) as e:raise SystemExit('建图前置检查未通过：'+str(e))
    config=yaml.safe_load(a.upstream_config.read_text());params=config['laser_mapping']['ros__parameters']
    params['common'].update(lid_topic='/m1_airy/front/points',imu_topic='/m1_airy/front/imu',time_offset_lidar_to_imu=0.0)
    params['preprocess'].update(lidar_type=5,scan_line=96,timestamp_unit=0,scan_rate=10)
    params['feature_extract_enable']=False
    params['mapping'].update(extrinsic_est_en=False,extrinsic_T=t.tolist(),extrinsic_R=r.reshape(-1).tolist())
    params['publish'].update(path_en=True,map_en=False,world_points_en=True,body_points_en=True)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(yaml.safe_dump(config,sort_keys=False))
    print('已生成单前雷达配置；真实运动、TF 集成和精度仍需独立验收。')
if __name__=='__main__':main()
