#!/usr/bin/env python3
"""domain 180 中对真实适配节点执行断流/重连测试；合成输入，不接真实数据源。"""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
import rclpy
from rclpy.qos import QoSProfile,ReliabilityPolicy
from sensor_msgs.msg import Imu,PointCloud2,PointField
from adapter_core import cloud_view,set_stamp


def main():
 p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
 if os.environ.get('ROS_DOMAIN_ID')!='180' or os.environ.get('ROS_LOCALHOST_ONLY')!='1':p.error('只允许 localhost/domain 180')
 a.output_dir.mkdir(parents=True,exist_ok=True);rclpy.init();node=rclpy.create_node('m1_fault_fixture')
 keys=[(s,k) for s in ('front','rear') for k in ('points','imu')];qos=QoSProfile(depth=100,reliability=ReliabilityPolicy.BEST_EFFORT)
 pubs={};received=[0];subs=[]
 for side,kind in keys:
  cls=Imu if kind=='imu' else PointCloud2;pubs[(side,kind)]=node.create_publisher(cls,f'/m1_sensors/{side}/{kind}_raw',qos)
  subs.append(node.create_subscription(cls,f'/m1_airy/{side}/{kind}',lambda m:received.__setitem__(0,received[0]+1),qos))
 def make(side,kind,ns,bad=False):
  frame='rslidar_head' if side=='front' else 'rslidar_tail'
  if kind=='imu':
   m=Imu();m.header.frame_id='wrong_frame' if bad else frame;set_stamp(m,ns);m.linear_acceleration.z=1.;return m
  m=PointCloud2();m.header.frame_id=frame;set_stamp(m,ns-100_000_000);m.width=2;m.height=1;m.point_step=26;m.row_step=52
  m.fields=[PointField(name=n,offset=o,datatype=t,count=1) for n,o,t in [('x',0,7),('y',4,7),('z',8,7),('intensity',12,7),('ring',16,4),('timestamp',18,8)]];m.data=bytes(52)
  arr=cloud_view(m);arr['x']=1.;arr['timestamp']=[ns*1e-9-.099,ns*1e-9-.001];return m
 cases={}
 try:
  for name,expected in [('imu_stop','stream_timeout'),('cloud_stop','stream_timeout'),('all_stop','stream_timeout'),('wrong_frame','frame_changed'),('publisher_restart','publisher_changed'),('profile_expired','profile_expired'),('startup_missing','startup_missing')]:
   status=a.output_dir/(name+'.json');profile=a.output_dir/(name+'_profile.json')
   profile.write_text(json.dumps({'audit_timestamp_unix':time.time(),'valid_for_seconds':2.5 if name=='profile_expired' else 600,'offset_ns':{'front':0,'rear':0}}))
   received[0]=0;process=None
   with (a.output_dir/(name+'.log')).open('w') as log:
    process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('adapter_node.py')),'--profile',str(profile),'--status',str(status),'--seconds','6'],stdout=log,stderr=subprocess.STDOUT)
    started=time.monotonic();last_send={k:0. for k in keys};last_front_imu_ns=0;changed=False;count_after_settle=None;fault_seen=None;last_counts=None
    try:
     while process.poll() is None and time.monotonic()-started<9:
      now=time.monotonic();elapsed=now-started
      if name=='publisher_restart' and elapsed>=2 and not changed:
       node.destroy_publisher(pubs[('front','imu')]);pubs[('front','imu')]=node.create_publisher(Imu,'/m1_sensors/front/imu_raw',qos);changed=True
      for side,kind in keys:
       if now-last_send[(side,kind)]<(.01 if kind=='imu' else .1):continue
       last_send[(side,kind)]=now
       skip=name=='startup_missing' and side=='rear' and kind=='imu'
       # 2–3 秒断流后恢复，验证恢复不会自动解除锁定。
       if 2<=elapsed<3:
        skip|=name=='all_stop' or (name=='imu_stop' and (side,kind)==('front','imu')) or (name=='cloud_stop' and (side,kind)==('front','points'))
       if skip:continue
       msg=make(side,kind,time.time_ns(),name=='wrong_frame' and elapsed>=2 and (side,kind)==('front','imu'))
       pubs[(side,kind)].publish(msg)
       if (side,kind)==('front','imu') and elapsed<2:last_front_imu_ns=time.monotonic_ns()
      rclpy.spin_once(node,timeout_sec=.002)
      if status.exists():
       h=json.loads(status.read_text())
       if h.get('fault') and fault_seen is None:fault_seen=now
       if fault_seen and now-fault_seen>.3:
        if count_after_settle is None:count_after_settle=received[0];last_counts=h['counts']
    finally:
     if process.poll() is None:process.terminate()
     process.wait(timeout=5)
   h=json.loads(status.read_text());fault=h.get('fault');no_resume=(count_after_settle is not None and received[0]==count_after_settle and h['counts']==last_counts)
   latency=(fault['monotonic_ns']-last_front_imu_ns)*1e-9 if fault and name=='imu_stop' else None
   cases[name]={'passed':bool(fault and fault['code']==expected and no_resume and process.returncode==0 and (latency is None or latency<.25)),
                'fault':fault,'output_samples':received[0],'no_output_after_fault_settle':no_resume,'imu_timeout_latency_s':latency,'process_exit':process.returncode}
  report={'scope':'synthetic ROS messages, production adapter node, localhost/domain 180','cases':cases,'passed':all(v['passed'] for v in cases.values()),'motion_outputs':False,'timestamp_unix':time.time()}
  (a.output_dir/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2))
  return 0 if report['passed'] else 1
 finally:
  node.destroy_node();rclpy.shutdown()
if __name__=='__main__':raise SystemExit(main())
