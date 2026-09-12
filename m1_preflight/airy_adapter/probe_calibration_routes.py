#!/usr/bin/env python3
"""只读查询 TF 缓存与订阅标定状态，不触发标定命令或控制模式。"""
import json,time
from pathlib import Path
import zenoh
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.convert import message_to_ordereddict
from tf2_msgs.msg import TFMessage

c=zenoh.Config()
for k,v in {'mode':'client','connect/endpoints':['tcp/192.168.168.100:7447'],'scouting/multicast/enabled':False}.items():
 c.insert_json5(k,json.dumps(v))
results={'timestamp_unix':time.time(),'tf_cached':[],'tf_live':[],'calibration_state':[],'errors':[],'motion_outputs':False}
def collect(field,cls):
 def cb(sample):
  try:
   item=(message_to_ordereddict(deserialize_message(sample.payload.to_bytes(),cls)) if cls else {'payload_bytes':len(sample.payload),'schema_available':False})
   if item not in results[field]:results[field].append(item)
  except Exception as e:results['errors'].append(str(e))
 return cb
with zenoh.open(c) as session:
 key='24/tf_static/tf2_msgs::msg::dds_::TFMessage_/TypeHashNotSupported'
 subs=[session.declare_subscriber(key,collect('tf_live',TFMessage)),session.declare_subscriber('24/arc/calibration_state/robots_dog_msgs::msg::dds_::ArcModuleState_/TypeHashNotSupported',collect('calibration_state',None))]
 # 精确 TF 数据键查询，只能读取缓存；从不查询感知标定命令键。
 for reply in session.get(key,timeout=3.0):
  if reply.ok:collect('tf_cached',TFMessage)(reply.ok)
 time.sleep(10)
 for sub in subs:sub.undeclare()
Path('artifacts/real_sensors/calibration_routes.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(results,ensure_ascii=False,indent=2))
