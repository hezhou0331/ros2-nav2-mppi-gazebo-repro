"""只读读取现有导航节点参数；不调用任何 Set/控制服务。"""
import json,struct,time,uuid
from pathlib import Path
import zenoh
from rclpy.serialization import serialize_message,deserialize_message
from rcl_interfaces.srv import ListParameters,GetParameters
from rosidl_runtime_py.convert import message_to_ordereddict
nodes=['rslidar_sdk/param_handle','robot_tf','robot_slam','robot_localization']
c=zenoh.Config()
for k,v in {'mode':'client','connect/endpoints':['tcp/192.168.168.100:7447'],'scouting/multicast/enabled':False}.items():c.insert_json5(k,json.dumps(v))
results={};seq=0;gid=uuid.uuid4().bytes
with zenoh.open(c) as s:
 def request(node,svc,req):
  global seq
  seq+=1;t=time.time_ns();attachment=struct.pack('<qq',seq,t)+b'\x10'+gid
  action='list_parameters' if svc is ListParameters else 'get_parameters'
  key=f'24/{node}/{action}/rcl_interfaces::srv::dds_::{svc.__name__}_/TypeHashNotSupported'
  out=[]
  for reply in s.get(key,payload=serialize_message(req),attachment=attachment,timeout=2.0):
   elapsed=(time.time_ns()-t)/1e9
   if reply.ok:
    try:out.append({'rtt_seconds':elapsed,'response':message_to_ordereddict(deserialize_message(reply.ok.payload.to_bytes(),svc.Response)),'attachment_hex':reply.ok.attachment.to_bytes().hex() if reply.ok.attachment else None})
    except Exception as e:out.append({'error':str(e)})
   else:out.append({'error':str(reply.err)})
  return out
 for node in nodes:
  lists=request(node,ListParameters,ListParameters.Request(depth=0));results[node]={'list':lists};print(node,'list',str(lists)[:240],flush=True)
  if lists and 'response' in lists[0]:
   names=lists[0]['response']['result']['names']
   if names: results[node]['names']=names;results[node]['get']=request(node,GetParameters,GetParameters.Request(names=names))
Path('artifacts/real_sensors/board_parameters.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2)[:12000])
