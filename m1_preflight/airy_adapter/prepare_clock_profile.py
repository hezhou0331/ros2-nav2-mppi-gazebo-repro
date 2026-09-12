#!/usr/bin/env python3
"""由时钟审计生成固定的软件映射；后雷达仅估计，不标记为硬件同步。"""
import argparse,json,time
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--audit',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
x=json.loads(a.audit.read_text());lo,hi=x['local_minus_board_interval_s']
if not 0 <= hi-lo < .01:raise SystemExit('板间时钟测量区间冲突或过宽')
for name in ['front_lidar/imu','rear_lidar/imu']:
 if x['summary'][name]['count']<1000 or x['summary'][name]['regressions']:raise SystemExit('审计样本不足或时钟回退')
front=int(round((lo+hi)*.5*1e9))
# 相同驱动的 IMU 发布延迟差只能提供偏移估计，不能独立证明测量同步。
f=np.array([[v[0],v[1]] for v in x['streams']['front_lidar/imu']],dtype=np.int64)
r=np.array([[v[0],v[1]] for v in x['streams']['rear_lidar/imu']],dtype=np.int64)
relative=int(round(float(np.quantile(r[:,1]-r[:,0],.01)-np.quantile(f[:,1]-f[:,0],.01))))
out={'created_unix':time.time(),'audit_timestamp_unix':x['timestamp_unix'],'valid_for_seconds':600,
 'method':'fixed per-device offset; board offset bounded by read-only RPC response time; rear relative epoch estimated from publisher timestamps',
 'local_minus_board_interval_s':[lo,hi],'board_mapping_half_width_ms':(hi-lo)*500,
 'offset_ns':{'front':front,'rear':front+relative},'hardware_synchronized':False,'cross_lidar_fusion_ready':False,
 'rear_estimator_systematic_error_bound_ms':None,
 'note':'仅供隔离输入验证；不能把小的网络抖动解释为小的传感器同步误差。过期、回退和跳变均停止输出。'}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False,indent=2))
