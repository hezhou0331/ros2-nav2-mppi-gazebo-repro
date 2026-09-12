#!/usr/bin/env python3
"""只读对比设备时间、Zenoh 发布序号和本机 ROS 接收；保留原始测量供复核。"""
import argparse,json,struct,threading,time,os,bisect
from pathlib import Path
import numpy as np
import zenoh,rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile,ReliabilityPolicy
from sensor_msgs.msg import Imu,PointCloud2


def header_ns(data):
 if len(data)<12 or data[:2]!=b'\x00\x01':raise ValueError('未知 CDR Header 格式')
 sec,ns=struct.unpack_from('<iI',data,4)
 if ns>=10**9:raise ValueError('非法纳秒字段')
 return sec*10**9+ns


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seconds',type=float,default=180);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if not 20<=a.seconds<=600:p.error('观察时间需为 20–600 秒')
 if os.environ.get('ROS_LOCALHOST_ONLY')!='1':p.error('需要 localhost ROS')
 rclpy.init();node=Node('m1_gap_auditor',enable_rosout=False,start_parameter_services=False)
 rows={};ros={};errors=[];lock=threading.Lock();start=time.monotonic_ns();subs=[]
 def zenoh_cb(key):
  def cb(sample):
   try:
    now=time.monotonic_ns();data=sample.payload.to_bytes();stamp=header_ns(data);att=sample.attachment.to_bytes() if sample.attachment else b''
    if len(att)!=33 or att[16]!=16:raise ValueError('未知发布序号 attachment 格式')
    seq,pub=struct.unpack_from('<qq',att)
    with lock:rows[key].append([stamp,seq,pub,now,att[17:].hex()])
   except Exception as e:
    with lock:errors.append(str(e))
  return cb
 def ros_cb(key):
  def cb(data):ros[key].append([header_ns(data),time.monotonic_ns()])
  return cb
 config=zenoh.Config()
 for k,v in {'mode':'client','connect/endpoints':['tcp/192.168.168.100:7447'],'scouting/multicast/enabled':False}.items():config.insert_json5(k,json.dumps(v))
 with zenoh.open(config) as session:
  zs=[]
  for side in ('front','rear'):
   for kind,cls in [('points',PointCloud2),('imu',Imu)]:
    key=side+'/'+kind;rows[key]=[];ros[key]=[];src=side+'_lidar'+('/imu' if kind=='imu' else '')
    zs.append(session.declare_subscriber(f'24/{src}/sensor_msgs::msg::dds_::{cls.__name__}_/TypeHashNotSupported',zenoh_cb(key)))
    subs.append(node.create_subscription(cls,f'/m1_sensors/{side}/{kind}_raw',ros_cb(key),QoSProfile(depth=200,reliability=ReliabilityPolicy.BEST_EFFORT),raw=True))
  while (time.monotonic_ns()-start)*1e-9<a.seconds:rclpy.spin_once(node,timeout_sec=.02)
  for z in zs:z.undeclare()
 end=time.monotonic_ns();summary={}
 for key,rr in rows.items():
  events=[];threshold=.015 if key.endswith('imu') else .15
  for prev,current in zip(rr,rr[1:]):
   ds=(current[0]-prev[0])*1e-9;dq=current[1]-prev[1];same=current[4]==prev[4]
   if ds>threshold or ds<=0 or dq!=1 or not same:
    label=('publisher_changed' if not same else 'device_time_nonincreasing' if ds<=0 else 'publication_sequence_gap' if dq>1 else 'publication_sequence_nonincreasing' if dq<=0 else 'device_time_gap_with_contiguous_publications')
    events.append({'kind':label,'device_gap_s':ds,'sequence_delta':dq,'publisher_gap_s':(current[2]-prev[2])*1e-9,'receive_gap_s':(current[3]-prev[3])*1e-9,'device_ns':current[0],'receive_monotonic_ns':current[3]})
  ros_stamps=sorted({s for s,m in ros[key]});missing_total=0;seen_elsewhere=0;seen_events=0
  previous_by_stamp={b[0]:aa[0] for aa,b in zip(rr,rr[1:])}
  for event in events:
   if event['kind']=='publication_sequence_gap':
    found=max(0,bisect.bisect_left(ros_stamps,event['device_ns'])-bisect.bisect_right(ros_stamps,previous_by_stamp[event['device_ns']]))
    event['missing_publications_seen_by_ros']=found
    missing_total+=event['sequence_delta']-1;seen_elsewhere+=found;seen_events+=int(found>0)
  ros_set={s for s,m in ros[key]};interior={r[0] for r in rr if start+5*10**9<=r[3]<=end-2*10**9}
  gaps=np.diff([r[0] for r in rr])*1e-9
  summary[key]={'zenoh_count':len(rr),'ros_count':len(ros[key]),'device_gap_quantiles_s':np.quantile(gaps,[.5,.99,1]).tolist() if len(gaps) else [],'publisher_ids':sorted(set(r[4] for r in rr)),'interior_zenoh_unique':len(interior),'not_seen_in_independent_ros_receiver':len(interior-ros_set),'missing_sequence_samples':missing_total,'missing_sequence_samples_seen_by_ros':seen_elsewhere,'gap_events_seen_by_other_client':seen_events,'event_counts':{kind:sum(e['kind']==kind for e in events) for kind in sorted(set(e['kind'] for e in events))},'events':events}
 result={'timestamp_unix':time.time(),'duration_s':(end-start)*1e-9,'streams':summary,'errors':errors,'motion_outputs':False,'interpretation':'连续发布序号下设备时间有缺口：缺口已存在于发布前或设备时钟；序号缺口仅定位到发布序号到探针之间，不能单独证明网络丢包。两条独立订阅的差异包含不同客户端/ROS传输。'}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 a.output.with_suffix('.samples.json').write_text(json.dumps({'columns':['device_ns','sequence','publisher_wall_ns','receive_monotonic_ns','publisher_gid'],'zenoh':rows,'ros':ros}))
 print(json.dumps(result,ensure_ascii=False,indent=2));node.destroy_node();rclpy.shutdown()
if __name__=='__main__':main()
