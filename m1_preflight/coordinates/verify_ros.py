#!/usr/bin/env python3
"""用明确合成标定验证坐标节点、TF 消息、时间错配拒绝；不连接真实输入。"""
import json,os,subprocess,sys,time
from pathlib import Path
import numpy as np
import rclpy
from nav_msgs.msg import Odometry
from tf2_msgs.msg import TFMessage
from rclpy.qos import QoSProfile,DurabilityPolicy
from transform_core import matrix,quaternion_matrix,load_calibration
from scipy.spatial.transform import Rotation

if os.environ.get('ROS_DOMAIN_ID')!='179' or os.environ.get('ROS_LOCALHOST_ONLY')!='1':raise SystemExit('需要隔离 domain 179')
root=Path('artifacts/coordinates');root.mkdir(parents=True,exist_ok=True)
r=quaternion_matrix([0,0,np.sin(np.pi/4),np.cos(np.pi/4)])
cal={'front':{'base_from_lidar':{'rotation':r.tolist(),'translation_m':[.4,.1,.2],'verified':True,'evidence':'SYNTHETIC TEST ONLY'},'imu_from_lidar':{'rotation':np.eye(3).tolist(),'translation_m':[.01,.02,.03],'verified':True,'evidence':'SYNTHETIC TEST ONLY'}}}
(root/'synthetic_calibration.json').write_text(json.dumps(cal));_,_,bi=load_calibration(cal['front'])
process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('preview_node.py')),'--calibration',str(root/'synthetic_calibration.json'),'--status',str(root/'node_status.json'),'--seconds','10'],stdout=(root/'node.log').open('w'),stderr=subprocess.STDOUT)
rclpy.init();node=rclpy.create_node('coordinate_fixture');samples=[];statics=[]
subs=[node.create_subscription(TFMessage,'/m1_coordinates/tf',lambda x:samples.extend(x.transforms),10),node.create_subscription(TFMessage,'/m1_coordinates/tf_static',lambda x:statics.extend(x.transforms),QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL))]
pubs=[node.create_publisher(Odometry,'/m1_coordinates/local_odom',10),node.create_publisher(Odometry,'/m1_coordinates/global_imu',10)]
map_base=matrix(r,[3,2,1]);odom_base=matrix(np.eye(3),[1,0,0]);map_imu=map_base@bi

def msg(t,parent,child,ns):
 m=Odometry();m.header.frame_id=parent;m.child_frame_id=child;m.header.stamp.sec,m.header.stamp.nanosec=divmod(ns,10**9)
 m.pose.pose.position.x,m.pose.pose.position.y,m.pose.pose.position.z=map(float,t[:3,3]);q=Rotation.from_matrix(t[:3,:3]).as_quat();m.pose.pose.orientation.x,m.pose.pose.orientation.y,m.pose.pose.orientation.z,m.pose.pose.orientation.w=map(float,q);return m
start=time.monotonic()
while time.monotonic()-start<7:
 ns=node.get_clock().now().nanoseconds
 pubs[0].publish(msg(odom_base,'odom','base_link',ns))
 for _ in range(2):rclpy.spin_once(node,timeout_sec=.005)
 pubs[1].publish(msg(map_imu,'map','body',ns))
 rclpy.spin_once(node,timeout_sec=.03)
# 注入仍新鲜但倒退 200ms 的全局时间戳；必须拒绝生成 map←odom。
ns=node.get_clock().now().nanoseconds-200_000_000
pubs[1].publish(msg(map_imu,'map','body',ns))
while process.poll() is None:rclpy.spin_once(node,timeout_sec=.1)
status=json.loads((root/'node_status.json').read_text());valid=[]
for t in samples:
 tr=t.transform;rr=quaternion_matrix([tr.rotation.x,tr.rotation.y,tr.rotation.z,tr.rotation.w]);mt=matrix(rr,[tr.translation.x,tr.translation.y,tr.translation.z]);valid.append(np.allclose(mt@odom_base,map_base,atol=1e-8))
result={'scope':'synthetic nonzero extrinsics; isolated ROS domain 179','samples':len(samples),'all_transforms_correct':bool(valid) and all(valid),'static_edges':sorted(set((t.header.frame_id,t.child_frame_id) for t in statics)),'invalid_time_rejected':any('时间重复或回退' in e for e in status['errors']),'node_status':status,'hardware_tf_verified':False,'motion_outputs':False}
result['passed']=bool(valid) and all(valid) and len(result['static_edges'])==2 and result['invalid_time_rejected'] and process.returncode==0
(root/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2));node.destroy_node();rclpy.shutdown()
raise SystemExit(0 if result['passed'] else 1)
