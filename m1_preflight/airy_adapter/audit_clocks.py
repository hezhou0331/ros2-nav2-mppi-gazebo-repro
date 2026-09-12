"""读取源时钟、Zenoh 发布时钟与只读参数响应时间；不修改任何时钟。"""
import json,time,struct,uuid,threading
from pathlib import Path
import zenoh,numpy as np
from rclpy.serialization import serialize_message,deserialize_message
from rcl_interfaces.srv import GetParameters
from sensor_msgs.msg import Imu,PointCloud2
cfg=zenoh.Config()
for k,v in {'mode':'client','connect/endpoints':['tcp/192.168.168.100:7447'],'scouting/multicast/enabled':False}.items():cfg.insert_json5(k,json.dumps(v))
rows={};requests=[];lock=threading.Lock();gid=uuid.uuid4().bytes
sources=[('front_lidar',PointCloud2),('front_lidar/imu',Imu),('rear_lidar',PointCloud2),('rear_lidar/imu',Imu)]
def callback(name,cls):
 def f(sample):
  now=time.time_ns();mono=time.monotonic_ns();msg=deserialize_message(sample.payload.to_bytes(),cls)
  a=sample.attachment.to_bytes() if sample.attachment else b''
  stamp=msg.header.stamp.sec*10**9+msg.header.stamp.nanosec
  pub=struct.unpack_from('<q',a,8)[0] if len(a)==33 else None
  row=[stamp,pub,now,mono,a[17:].hex()]
  with lock:rows.setdefault(name,[]).append(row)
 return f
with zenoh.open(cfg) as z:
 subs=[z.declare_subscriber(f'24/{name}/sensor_msgs::msg::dds_::{cls.__name__}_/TypeHashNotSupported',callback(name,cls)) for name,cls in sources]
 for i in range(20):
  t0=time.time_ns();m0=time.monotonic_ns()
  for reply in z.get('24/robot_tf/get_parameters/rcl_interfaces::srv::dds_::GetParameters_/TypeHashNotSupported',payload=serialize_message(GetParameters.Request(names=['use_sim_time'])),attachment=struct.pack('<qq',i+1,t0)+b'\x10'+gid,timeout=1.0):
   t1=time.time_ns();m1=time.monotonic_ns()
   if reply.ok and reply.ok.attachment:
    a=reply.ok.attachment.to_bytes();s=struct.unpack_from('<q',a,8)[0];requests.append([t0,s,t1,m1-m0])
  time.sleep(.5)
 time.sleep(5)
 for sub in subs:sub.undeclare()
metrics={}
for name,rr in rows.items():
 a=np.array([v[:4] for v in rr],dtype=np.int64);ds=np.diff(a[:,0])*1e-9;delay=(a[:,1]-a[:,0])*1e-9;network=(a[:,2]-a[:,1])*1e-9
 metrics[name]={'count':len(a),'source_hz':(len(a)-1)/((a[-1,0]-a[0,0])*1e-9),'regressions':int((ds<0).sum()),'publisher_minus_source_s_quantiles':np.quantile(delay,[0,.01,.5,.99,1]).tolist(),'local_minus_publisher_s_quantiles':np.quantile(network,[0,.01,.5,.99,1]).tolist(),'publisher_gids':sorted(set(v[4] for v in rr))}
q=np.array(requests,dtype=np.int64);lo=(q[:,0]-q[:,1])*1e-9;hi=(q[:,2]-q[:,1])*1e-9
result={'timestamp_unix':time.time(),'columns':['device_ns','publisher_ns','receive_wall_ns','receive_monotonic_ns','publisher_gid'],'streams':rows,'clock_queries':requests,'summary':metrics,'local_minus_board_interval_s':[float(max(lo)),float(min(hi))],'best_rtt_s':float(min(q[:,3])*1e-9)}
Path('artifacts/real_sensors/clock_audit.json').write_text(json.dumps(result))
print(json.dumps({k:v for k,v in result.items() if k not in ['streams','clock_queries']},indent=2))
