#!/usr/bin/env python3
"""raw → 校正输入；定时断流检查与故障锁定，不发布 TF、目标或运动命令。"""
import argparse,json,time,signal,os
from pathlib import Path
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile,ReliabilityPolicy
from sensor_msgs.msg import Imu,PointCloud2
from adapter_engine import AdapterEngine
from stream_guard import InputFault


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile',type=Path,required=True);p.add_argument('--status',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=0)
    a=p.parse_args()
    if a.seconds<0:p.error('seconds 必须非负')
    if os.environ.get('ROS_LOCALHOST_ONLY')!='1':p.error('输入验证仅允许 localhost ROS')
    try:engine=AdapterEngine(json.loads(a.profile.read_text()),time.time_ns(),time.monotonic_ns())
    except (ValueError,KeyError,TypeError) as e:p.error(str(e))
    rclpy.init();node=Node('m1_airy_input_adapter',enable_rosout=False,start_parameter_services=False)
    qos=QoSProfile(depth=100,reliability=ReliabilityPolicy.BEST_EFFORT)
    counts={};publishers=[];subscriptions=[];stop=False;started=time.monotonic();reported_fault=None
    def halt(*_):
        nonlocal stop
        stop=True
    signal.signal(signal.SIGINT,halt);signal.signal(signal.SIGTERM,halt)
    def callback(side,kind,pub):
        def receive(msg):
            try:
                # 此 Humble 版本只把消息传入回调，不含逐帧 GID；核对发现图中的唯一发布者。
                topic=f'/m1_sensors/{side}/{kind}_raw'
                endpoints=node.get_publishers_info_by_topic(topic)
                if not endpoints and side+'/'+kind not in engine.guard.last:
                    return  # 初始发现尚未完成；由启动超时负责停止。
                if len(endpoints)!=1:
                    engine.guard.trip('ambiguous_publishers',side+'/'+kind,'需要唯一 ROS 发布者',time.monotonic_ns())
                gid=bytes(endpoints[0].endpoint_gid).hex()
                out=engine.process(side,kind,msg,time.time_ns(),time.monotonic_ns(),gid)
                # 转换计算期间也可能超过期限，发布前再检查一次。
                if out is not None and engine.guard.tick(time.time_ns(),time.monotonic_ns()):
                    pub.publish(out);key=side+'/'+kind;counts[key]=counts.get(key,0)+1
            except InputFault:pass
            except Exception as e:
                try:engine.guard.trip('processing_error',side+'/'+kind,str(e),time.monotonic_ns())
                except InputFault:pass
        return receive
    for side in ('front','rear'):
        for kind,cls in [('points',PointCloud2),('imu',Imu)]:
            pub=node.create_publisher(cls,f'/m1_airy/{side}/{kind}',qos);publishers.append(pub)
            subscriptions.append(node.create_subscription(cls,f'/m1_sensors/{side}/{kind}_raw',callback(side,kind,pub),qos))
    a.status.parent.mkdir(parents=True,exist_ok=True)
    def report(running):
        nonlocal reported_fault
        health=engine.guard.snapshot(time.monotonic_ns());fault=health['fault']
        out={'timestamp_unix':time.time(),'running':running,'counts':counts,'accepted':engine.accepted,
             'errors':{} if not fault else {fault['stream']:fault['detail']},'clock_fault':None if not fault else fault['code'],
             **health,'hardware_synchronized':False,'extrinsics_verified':False,'navigation_ready':False,'motion_outputs':False}
        if not running:
            out['output_enabled']=False
            if not fault:out['state']='stopped'
        temp=a.status.with_suffix('.tmp');temp.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');temp.replace(a.status)
        if fault and reported_fault is None:
            print('输入输出已锁定：'+json.dumps(fault,ensure_ascii=False),flush=True);reported_fault=fault
    try:
        report(True);next_report=0
        while not stop and rclpy.ok() and (not a.seconds or time.monotonic()-started<a.seconds):
            try:engine.guard.tick(time.time_ns(),time.monotonic_ns())
            except InputFault:pass
            rclpy.spin_once(node,timeout_sec=.01)
            if time.monotonic()>next_report or (engine.guard.fault and reported_fault is None):
                report(True);next_report=time.monotonic()+.25
    except Exception as error:
        try:engine.guard.trip('node_runtime_error','all',str(error),time.monotonic_ns())
        except InputFault:pass
        raise
    finally:
        report(False);node.destroy_node();rclpy.shutdown()
if __name__=='__main__':main()
