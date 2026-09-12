#!/usr/bin/env python3
"""真实 rosbag 离线验证全部四路；检查单位、帧内时间、IMU 覆盖与原始数据不变。"""
import argparse,json,collections,hashlib
from pathlib import Path
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message,serialize_message
from sensor_msgs.msg import Imu,PointCloud2
from adapter_core import stamp_ns,convert_cloud,convert_imu,cloud_view
p=argparse.ArgumentParser();p.add_argument('--bag',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
a.output.parent.mkdir(parents=True,exist_ok=True)
reader=rosbag2_py.SequentialReader();reader.open(rosbag2_py.StorageOptions(uri=str(a.bag),storage_id='sqlite3'),rosbag2_py.ConverterOptions('',''))
counts=collections.Counter();acc={s:[] for s in ['front','rear']};imus={s:[] for s in acc};clouds={s:[] for s in acc};max_error=0.;exported=set();rows=[]
while reader.has_next():
 topic,data,record_ns=reader.read_next();parts=topic.strip('/').split('/')
 if len(parts)!=3 or parts[0]!='m1_sensors':continue
 side,kind=parts[1:];cls=Imu if kind=='imu_raw' else PointCloud2;msg=deserialize_message(data,cls);source=stamp_ns(msg)
 # 测试一个非整秒固定偏移；不把离线回放时间当作真实同步证据。
 offset=-153388000123 if side=='front' else 1789213127750000123
 if cls is Imu:
  out=convert_imu(msg,offset,f'rslidar_{side}_imu');assert out.orientation_covariance[0]==-1
  v=out.linear_acceleration;acc[side].append(float(np.linalg.norm([v.x,v.y,v.z])));imus[side].append(source)
 else:
  raw=bytes(msg.data);out=convert_cloud(msg,offset);assert bytes(msg.data)==raw
  q=cloud_view(msg);valid=np.isfinite(q['x']) & np.isfinite(q['y']) & np.isfinite(q['z'])
  r=q['timestamp'][valid]-source*1e-9
  changed=cloud_view(out)['timestamp'][valid]-stamp_ns(out)*1e-9
  error=float(np.max(np.abs(r-changed)));max_error=max(max_error,error);assert error<1e-6
  clouds[side].append([source,source+int(np.max(r)*1e9),int(valid.sum())])
  if side not in exported:
   export_dir=a.output.parent/(a.output.stem+'_cdr');export_dir.mkdir(exist_ok=True)
   (export_dir/f'{side}_adapted.cdr').write_bytes(serialize_message(out));exported.add(side)
 assert stamp_ns(out)-source==offset
 counts[topic]+=1
report={'counts':dict(counts),'max_relative_point_time_error_seconds':max_error,'raw_input_preserved':True,
 'orientation_unavailable_marked':True,'hardware_synchronization_verified':False,'navigation_ready':False,'sensors':{}}
for side in acc:
 ts=np.array(imus[side],dtype=np.int64);g=np.array(acc[side]);cs=clouds[side]
 interior=[c for c in cs if c[0]>=ts[0] and c[1]<=ts[-1]]
 cover=[int(((ts>=c[0]) & (ts<=c[1])).sum()) for c in interior]
 report['sensors'][side]={'imu_accel_norm_m_s2_quantiles':np.quantile(g,[0,.5,1]).tolist(),
  'imu_regressions':int((np.diff(ts)<0).sum()),
  'imu_duplicate_stamps':int((np.diff(ts)==0).sum()),
  'imu_source_hz':float((len(ts)-1)/((ts[-1]-ts[0])*1e-9)),
  'imu_gap_seconds_quantiles':np.quantile(np.diff(ts)*1e-9,[.5,.99,1]).tolist(),
  'cloud_gap_seconds_quantiles':np.quantile(np.diff([c[0] for c in cs])*1e-9,[.5,.99,1]).tolist(),
  'imu_gaps_above_15ms':int((np.diff(ts)>15_000_000).sum()),'cloud_frames':len(cs),'cloud_finite_points_min':min(c[2] for c in cs),
  'clouds_with_recorded_imu_coverage':len(interior),'boundary_clouds':len(cs)-len(interior),
  'imu_samples_per_covered_scan_min':min(cover) if cover else 0}
a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
