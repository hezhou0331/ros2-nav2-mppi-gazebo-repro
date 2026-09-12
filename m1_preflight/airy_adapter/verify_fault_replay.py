#!/usr/bin/env python3
"""基于已有真实录包注入故障，运行线上同一个 AdapterEngine；只使用虚拟时钟。"""
import argparse,copy,json,time
from pathlib import Path
import rosbag2_py
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import Imu,PointCloud2
from adapter_core import stamp_ns,set_stamp,cloud_view
from adapter_engine import AdapterEngine
from stream_guard import InputFault,InputGuard,SourceIdentityGuard


def main():
 p=argparse.ArgumentParser();p.add_argument('--bag',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 reader=rosbag2_py.SequentialReader();reader.open(rosbag2_py.StorageOptions(uri=str(a.bag),storage_id='sqlite3'),rosbag2_py.ConverterOptions('',''))
 events=[];first=None;offsets={};wall0=1_800_000_000*10**9;mono0=10**9
 while reader.has_next():
  topic,data,record=reader.read_next();parts=topic.strip('/').split('/')
  if len(parts)!=3 or parts[0]!='m1_sensors':continue
  side,rawkind=parts[1:];kind='imu' if rawkind=='imu_raw' else 'points'
  if first is None:first=record
  dt=record-first
  msg=deserialize_message(data,Imu if kind=='imu' else PointCloud2)
  if kind=='imu' and side not in offsets:offsets[side]=wall0+dt-stamp_ns(msg)
  events.append((dt,side,kind,msg))
 profile={'audit_timestamp_unix':wall0*1e-9,'valid_for_seconds':600,'offset_ns':offsets}
 cases={}
 variants={'baseline':None,'imu_stop':'stream_timeout','cloud_stop':'stream_timeout','all_stop':'stream_timeout','reconnect_after_stop':'stream_timeout','missing_startup_imu':'startup_missing','duplicate':'source_nonincreasing','out_of_order':'source_nonincreasing','device_clock_jump':'stale_or_future','delayed_message':'stale_or_future','wrong_frame':'frame_changed','wrong_cloud_field':'invalid_measurement','wrong_point_time':'invalid_measurement','nonfinite_imu':'invalid_measurement','publisher_restart':'publisher_changed','host_clock_jump':'host_clock_jump','profile_expired':'profile_expired'}
 for name,expected in variants.items():
  pr=copy.deepcopy(profile)
  if name=='profile_expired':pr['valid_for_seconds']=1.5
  engine=AdapterEngine(pr,wall0,mono0);outputs=0;after_fault=0;injected=False;previous={};tick=0;delayed=None
  limit=events[-1][0] if name=='baseline' else 6_000_000_000 if name=='missing_startup_imu' else 3_000_000_000
  def run(dt,side,kind,msg,gid='test-publisher'):
   nonlocal outputs,after_fault
   wall=wall0+dt+(100_000_000 if name=='host_clock_jump' and dt>=10**9 else 0)
   already=engine.guard.fault is not None
   try:
    out=engine.process(side,kind,msg,wall,mono0+dt,gid)
    if out is not None:
     outputs+=1;after_fault+=int(already)
   except InputFault:pass
  for dt,side,kind,original in events:
   if dt>limit:break
   while tick<=dt:
    w=wall0+tick+(100_000_000 if name=='host_clock_jump' and tick>=10**9 else 0)
    try:engine.guard.tick(w,mono0+tick)
    except InputFault:pass
    tick+=10_000_000
   if delayed and dt>=delayed[0]:run(dt,*delayed[1:]);delayed=None
   skip=(name=='missing_startup_imu' and side=='rear' and kind=='imu') or (dt>=10**9 and ((name=='imu_stop' and side=='front' and kind=='imu') or (name=='cloud_stop' and side=='front' and kind=='points') or name=='all_stop' or (name=='reconnect_after_stop' and side=='front' and kind=='imu' and dt<1_500_000_000)))
   if skip:continue
   msg=original;gid='test-publisher';key=side+'/'+kind
   target=side=='front' and kind==('points' if name in ('wrong_cloud_field','wrong_point_time') else 'imu')
   if dt>=10**9 and target and not injected:
    injected=True
    if name=='delayed_message':delayed=(dt+400_000_000,side,kind,msg);continue
    if name in ('duplicate','out_of_order','device_clock_jump','wrong_frame','wrong_cloud_field','wrong_point_time','nonfinite_imu'):
     msg=copy.deepcopy(original)
     if name=='duplicate':set_stamp(msg,previous[key])
     elif name=='out_of_order':set_stamp(msg,previous[key]-5_000_000)
     elif name=='device_clock_jump':set_stamp(msg,stamp_ns(msg)+200_000_000)
     elif name=='wrong_frame':msg.header.frame_id='wrong_body'
     elif name=='wrong_cloud_field':msg.fields[-1].name='wrong_timestamp'
     elif name=='wrong_point_time':cloud_view(msg)['timestamp'][:]+=1.0
     elif name=='nonfinite_imu':msg.linear_acceleration.x=float('nan')
    if name=='publisher_restart':gid='restarted-publisher'
   run(dt,side,kind,msg,gid);previous[key]=stamp_ns(original)
  fault=engine.guard.fault
  passed=(fault is None and outputs>1000) if expected is None else (fault is not None and fault['code']==expected and after_fault==0 and not engine.guard.ready)
  cases[name]={'passed':passed,'outputs':outputs,'outputs_after_fault':after_fault,'expected_fault':expected,'fault':fault}
 # 源进程身份检查与 ROS 发布者变化分别验证，确认恢复旧 GID 也不能解除锁定。
 sg=SourceIdentityGuard();sg.observe('front/imu','a'*32,1);sg.observe('front/imu','a'*32,3)
 try:sg.observe('front/imu','b'*32,1)
 except InputFault:pass
 latched=False
 try:sg.observe('front/imu','a'*32,4)
 except InputFault:latched=True
 cases['zenoh_source_restart']={'passed':latched,'fault':sg.fault}
 sg=SourceIdentityGuard();sg.observe('front/imu','a'*32,10)
 try:sg.observe('front/imu','a'*32,10)
 except InputFault:pass
 cases['zenoh_sequence_repeat']={'passed':sg.fault is not None,'fault':sg.fault}
 try:InputGuard({**profile,'audit_timestamp_unix':wall0*1e-9+10},wall0,mono0);rejected=False
 except ValueError:rejected=True
 cases['future_clock_profile']={'passed':rejected}
 result={'timestamp_unix':time.time(),'bag':str(a.bag),'recorded_messages':len(events),'scope':'real recorded messages, virtual delivery/clock faults, production AdapterEngine; no ROS publisher or hardware control','cases':cases,'passed':all(v['passed'] for v in cases.values()),'motion_outputs':False}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
 return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
