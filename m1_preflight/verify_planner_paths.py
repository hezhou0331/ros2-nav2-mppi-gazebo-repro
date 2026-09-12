#!/usr/bin/env python3
"""运行真实 RoamerX 规划服务，测试合成障碍绕行与堵塞目标；绝不启动控制器。"""
import argparse,json,os,signal,subprocess,time,math
from pathlib import Path
import yaml
import rclpy
from rclpy.action import ActionClient
from nav2_msgs.action import ComputePathToPose
from lifecycle_msgs.srv import ChangeState
from lifecycle_msgs.msg import Transition
from geometry_msgs.msg import TransformStamped,PoseStamped
from tf2_ros import StaticTransformBroadcaster


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
 if os.environ.get('ROS_DOMAIN_ID')!='178' or os.environ.get('ROS_LOCALHOST_ONLY')!='1':p.error('只允许 localhost/domain 178')
 root=a.output_dir.resolve();root.mkdir(parents=True,exist_ok=True)
 # 10×10 m 合成地图：墙阻断直线，顶部留通道；所有尺寸仅为软件测试。
 grid=bytearray([254]*10000)
 for y in range(76):
  for x in range(49,52):grid[y*100+x]=0
 (root/'map.pgm').write_bytes(b'P5\n100 100\n255\n'+b''.join(bytes(grid[y*100:(y+1)*100]) for y in reversed(range(100))))
 (root/'map.yaml').write_text(yaml.safe_dump(dict(image='map.pgm',mode='trinary',resolution=.1,origin=[0.,0.,0.],negate=0,occupied_thresh=.65,free_thresh=.196)))
 data=yaml.safe_load(a.fixture.read_text())
 params=data['m1_preview']
 params['map_server']['ros__parameters'].update(yaml_filename=str(root/'map.yaml'),frame_id='test_map')
 cm=params['global_costmap']['global_costmap']['ros__parameters']
 cm.update(global_frame='test_map',robot_base_frame='test_base')
 cm['static_layer'].update(map_topic='/m1_preview/map',map_subscribe_transient_local=True)
 params['planner_server']['ros__parameters']['GridBased']['tolerance']=0.0
 (root/'params.yaml').write_text(yaml.safe_dump(data,sort_keys=False))
 rclpy.init();node=rclpy.create_node('m1_planner_path_checker');broadcaster=StaticTransformBroadcaster(node)
 tr=TransformStamped();tr.header.stamp=node.get_clock().now().to_msg();tr.header.frame_id='test_map';tr.child_frame_id='test_base';tr.transform.translation.x=2.;tr.transform.translation.y=2.;tr.transform.rotation.w=1.;broadcaster.sendTransform(tr)
 processes=[];logs=[];report={'scope':'synthetic obstacle map; real RoamerX ComputePathToPose; no controller/hardware','passed':False,'cases':{},'motion_outputs':False}
 def future_result(future,seconds):
  rclpy.spin_until_future_complete(node,future,timeout_sec=seconds)
  if not future.done() or future.result() is None:raise RuntimeError('请求超时')
  return future.result()
 def transition(name,tid):
  c=node.create_client(ChangeState,'/m1_preview/'+name+'/change_state')
  try:
   if not c.wait_for_service(timeout_sec=20):raise RuntimeError(name+' 生命周期不可用')
   req=ChangeState.Request();req.transition.id=tid
   if not future_result(c.call_async(req),30).success:raise RuntimeError(name+' 生命周期转换失败')
  finally:node.destroy_client(c)
 def pose(x,y):
  out=PoseStamped();out.header.frame_id='test_map';out.header.stamp=node.get_clock().now().to_msg();out.pose.position.x=x;out.pose.position.y=y;out.pose.orientation.w=1.;return out
 try:
  for package,name in [('navigo_map_server','map_server'),('navigo_path_planner','planner_server')]:
   log=(root/(name+'.log')).open('w');logs.append(log)
   processes.append(subprocess.Popen(['ros2','run',package,name,'--ros-args','-r','__ns:=/m1_preview','--params-file',str(root/'params.yaml')],stdout=log,stderr=subprocess.STDOUT,start_new_session=True))
  for name in ('map_server','planner_server'):transition(name,Transition.TRANSITION_CONFIGURE)
  for name in ('map_server','planner_server'):transition(name,Transition.TRANSITION_ACTIVATE)
  client=ActionClient(node,ComputePathToPose,'/m1_preview/compute_path_to_pose')
  if not client.wait_for_server(timeout_sec=20):raise RuntimeError('规划动作不可用')
  for name,target in [('detour',(8.,2.)),('blocked_goal',(5.05,2.))]:
   goal=ComputePathToPose.Goal();goal.start=pose(2.,2.);goal.goal=pose(*target);goal.use_start=True;goal.planner_id='GridBased'
   handle=future_result(client.send_goal_async(goal),10)
   if not handle.accepted:raise RuntimeError(name+' 未接受规划请求')
   result=future_result(handle.get_result_async(),30);points=[(p.pose.position.x,p.pose.position.y) for p in result.result.path.poses]
   case={'status':result.status,'points':len(points)}
   if name=='detour':
    collisions=sum(not(0<=x<10 and 0<=y<10) or grid[int(y/.1)*100+int(x/.1)]==0 for x,y in points)
    length=sum(math.hypot(x2-x,y2-y) for (x,y),(x2,y2) in zip(points,points[1:]))
    case.update(collisions=collisions,length_m=length,max_y=max((y for x,y in points),default=0),goal_error_m=math.dist(points[-1],target) if points else None)
    case['passed']=result.status==4 and len(points)>2 and collisions==0 and case['max_y']>7.6 and case['goal_error_m']<.2
    (root/'detour_path.json').write_text(json.dumps(points))
   else:case['passed']=result.status==6 and not points
   report['cases'][name]=case
  report['root_velocity_publishers']={t:node.count_publishers(t) for t in ['/cmd_vel','/cmd_vel_raw','/cmd_vel_smoothed']}
  report['passed']=all(c['passed'] for c in report['cases'].values()) and not any(report['root_velocity_publishers'].values())
 except Exception as e:report['error']=str(e)
 finally:
  for process in processes:
   if process.poll() is None:
    os.killpg(process.pid,signal.SIGINT)
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=5)
  for log in logs:log.close()
  report['timestamp_unix']=time.time();(root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2));node.destroy_node();rclpy.shutdown()
 return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
