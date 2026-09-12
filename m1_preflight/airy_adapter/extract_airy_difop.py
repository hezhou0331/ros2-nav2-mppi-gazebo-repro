#!/usr/bin/env python3
"""从已有文件提取 AIRY DIFOP 候选，读取序列号/时钟标志/IMU 标定原值。

不打开网络，不写 calibration.json。包身份、单位、变换方向及设备对应关系需核实。
"""
import argparse,hashlib,json,struct
from pathlib import Path
import numpy as np

MAGIC=bytes.fromhex('a5ff005a11115555')
LENGTH=1248


def decode(data):
 if len(data)!=LENGTH or data[:8]!=MAGIC or data[-2:]!=bytes.fromhex('0ff0'):
  raise ValueError('不是完整的已知 AIRY DIFOP 布局')
 # 固定驱动 decoder_RSAIRY.hpp 使用 ntohl + float 位重解释，即大端 IEEE754。
 values=struct.unpack_from('>7f',data,1092);q=np.array(values[:4]);t=np.array(values[4:])
 if not np.isfinite(q).all() or not np.isfinite(t).all() or abs(np.linalg.norm(q)-1)>.01:
  raise ValueError('IMU 标定包含非法数值或四元数不是单位长度')
 return {'serial_hex':data[292:298].hex(),'source_ip':'.'.join(map(str,data[10:14])),
         'destination_ip':'.'.join(map(str,data[14:18])),
         'msop_port':int.from_bytes(data[24:26],'big'),'difop_port':int.from_bytes(data[28:30],'big'),
         'sync_mode_raw':data[301],'sync_status_raw':data[302],
         'imu_relative_to_lidar_quaternion_xyzw':q.tolist(),'translation_as_reported':t.tolist(),
         'packet_sha256':hashlib.sha256(data).hexdigest(),'verified_for_current_robot':False}


def scan_file(path):
 result=[];errors=[];seen=set();offset=0;carry=b''
 with path.open('rb') as stream:
  while True:
   chunk=stream.read(1024*1024)
   if not chunk:break
   data=carry+chunk;base=offset-len(carry);at=0
   while True:
    at=data.find(MAGIC,at)
    if at<0 or at+LENGTH>len(data):break
    position=base+at
    if position not in seen:
     seen.add(position)
     try:result.append({'file_offset':position,**decode(data[at:at+LENGTH])})
     except ValueError as e:errors.append({'file_offset':position,'error':str(e)})
    at+=1
   carry=data[-(LENGTH-1):];offset+=len(chunk)
 return {'source_file':str(path.resolve()),'file_bytes':offset,'candidates':result,'rejected':errors,
         'note':'扫描的是候选包；需核对传输封装、设备/型号与单位。没有把未知值写入实机标定。'}


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 result=scan_file(a.input);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
 return 0 if result['candidates'] else 2
if __name__=='__main__':raise SystemExit(main())
