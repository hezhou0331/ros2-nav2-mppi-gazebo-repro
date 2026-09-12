#!/usr/bin/env python3
"""仅 domain 179 坐标链接入验证；输入须同一时间基准，真实外参缺项拒绝启动。

不复制上游的零速度/置信度协方差，不发布 Odometry 或运动指令。
私有 TF 输出待实际里程计和标定验收后才能接入导航。
"""
import argparse,json,os,time
from pathlib import Path
from collections import deque
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile,ReliabilityPolicy,DurabilityPolicy
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped,PoseStamped
from tf2_msgs.msg import TFMessage
from scipy.spatial.transform import Rotation
from transform_core import matrix,quaternion_matrix,load_calibration,compose_navigation,inverse


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--calibration',type=Path,required=True)
 p.add_argument('--status',type=Path,required=True)
 p.add_argument('--seconds',type=float,default=60)
 a=p.parse_args()
 if os.environ.get('ROS_DOMAIN_ID')!='179' or os.environ.get('ROS_LOCALHOST_ONLY')!='1':p.error('仅允许 localhost/domain 179 的隔离坐标验证')
 if not 0<a.seconds<=600:p.error('隔离验证时长必须在 0–600 秒内')
 try:b,i,bi=load_calibration(json.loads(a.calibration.read_text())['front'])
 except (ValueError,KeyError,TypeError) as error:p.error('真实外参检查未通过：'+str(error))
 rclpy.init();node=Node('m1_coordinate_preview',enable_rosout=False,start_parameter_services=False)
 dynamic=node.create_publisher(TFMessage,'/m1_coordinates/tf',10)
 static=node.create_publisher(TFMessage,'/m1_coordinates/tf_static',QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL))
 pose_pub=node.create_publisher(PoseStamped,'/m1_coordinates/global_base_pose',10)
 queue=deque(maxlen=200);count=0;errors=[];last={};start=time.monotonic()
 def stamp(msg):return msg.header.stamp.sec*10**9+msg.header.stamp.nanosec
 def pose_matrix(msg):
  pp=msg.pose.pose;p=pp.position;q=pp.orientation
  return matrix(quaternion_matrix([q.x,q.y,q.z,q.w]),[p.x,p.y,p.z])
 def tf(parent,child,t,stamp):
  out=TransformStamped();out.header.frame_id=parent;out.child_frame_id=child;out.header.stamp=stamp
  out.transform.translation.x,out.transform.translation.y,out.transform.translation.z=map(float,t[:3,3])
  q=Rotation.from_matrix(t[:3,:3]).as_quat()
  out.transform.rotation.x,out.transform.rotation.y,out.transform.rotation.z,out.transform.rotation.w=map(float,q)
  return out
 static.publish(TFMessage(transforms=[tf('base_link','rslidar_head',b,node.get_clock().now().to_msg()),tf('rslidar_head','rslidar_head_imu',inverse(i),node.get_clock().now().to_msg())]))
 def check(msg,key,parent,child):
  ns=stamp(msg)
  if (msg.header.frame_id,msg.child_frame_id)!=(parent,child):raise ValueError(key+': 坐标名不符')
  if not -.05<=(node.get_clock().now().nanoseconds-ns)*1e-9<=.5:raise ValueError(key+': 时间不新鲜')
  if ns<=last.get(key,-1):raise ValueError(key+': 时间重复或回退')
  last[key]=ns
  return ns,pose_matrix(msg)
 def odom(msg):
  try:queue.append(check(msg,'odom','odom','base_link'))
  except ValueError as e:errors.append(str(e))
 def global_pose(msg):
  nonlocal count
  try:
   ns,t=check(msg,'global','map','body')
   if not queue:raise ValueError('尚无局部里程计')
   ons,ot=min(queue,key=lambda v:abs(v[0]-ns))
   mt,bt=compose_navigation(t,ot,bi,ns,ons)
   # 只发 map←odom；odom←base 应由实际局部里程计的唯一发布者负责。
   dynamic.publish(TFMessage(transforms=[tf('map','odom',mt,msg.header.stamp)]))
   out=PoseStamped();out.header=msg.header;tr=tf('map','base_link',bt,msg.header.stamp).transform
   out.pose.position.x=tr.translation.x;out.pose.position.y=tr.translation.y;out.pose.position.z=tr.translation.z;out.pose.orientation=tr.rotation
   pose_pub.publish(out);count+=1
  except ValueError as e:errors.append(str(e))
 qos=QoSProfile(depth=100,reliability=ReliabilityPolicy.BEST_EFFORT)
 subs=[node.create_subscription(Odometry,'/m1_coordinates/local_odom',odom,qos),node.create_subscription(Odometry,'/m1_coordinates/global_imu',global_pose,qos)]
 try:
  while time.monotonic()-start<a.seconds:rclpy.spin_once(node,timeout_sec=.02)
 finally:
  a.status.parent.mkdir(parents=True,exist_ok=True);a.status.write_text(json.dumps({'published':count,'errors':errors[-100:],'error_count':len(errors),'hardware_tf_verified':False,'motion_outputs':False},ensure_ascii=False,indent=2)+'\n')
  node.destroy_node();rclpy.shutdown()
if __name__=='__main__':main()
