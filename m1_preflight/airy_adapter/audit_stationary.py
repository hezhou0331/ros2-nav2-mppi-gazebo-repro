#!/usr/bin/env python3
"""静止阶段只读审计：保留来源序号/三种时间及少量 CDR，绝不发布 ROS 或运动命令。

采集回调只读头和保存有限快照；几何/IMU 统计在断开网络后完成，减少探针负载。
平面只是传感器坐标中的候选平面，不自动当作地面或生成安装外参。
"""
import argparse,json,struct,threading,time
from pathlib import Path
import numpy as np
import zenoh
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import PointCloud2,Imu
from adapter_core import cloud_view


def planes(xyz,seed):
    rng=np.random.default_rng(seed)
    xyz=xyz[rng.choice(len(xyz),min(3500,len(xyz)),replace=False)]
    result=[]
    for _ in range(3):
        if len(xyz)<100:break
        best=None;score=0
        for j in range(90):
            p=xyz[rng.choice(len(xyz),3,replace=False)]
            n=np.cross(p[1]-p[0],p[2]-p[0]);norm=np.linalg.norm(n)
            if norm<1e-8:continue
            n=n/norm;d=-n@p[0];mask=np.abs(xyz@n+d)<.025
            if mask.sum()>score:score=int(mask.sum());best=mask
        if best is None or score<100:break
        pts=xyz[best];center=pts.mean(axis=0)
        _,_,v=np.linalg.svd(pts-center,full_matrices=False);n=v[-1];d=-n@center
        if d<0:n=-n;d=-d
        result.append({'normal_sensor':n.tolist(),'distance_origin_m':float(d),'inliers':score,
                       'remaining_points':len(xyz),'rms_m':float(np.sqrt(np.mean((pts@n+d)**2)))})
        xyz=xyz[~best]
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seconds',type=float,default=60)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not 5<=a.seconds<=600:p.error('duration must be 5..600 seconds')
    a.output.mkdir(parents=True,exist_ok=False)
    rows={};snaps={};errors=[];lock=threading.Lock();start=time.monotonic()
    specs=[(side,kind,('front_lidar' if side=='front' else 'rear_lidar')+('/imu' if kind=='imu' else ''),Imu if kind=='imu' else PointCloud2)
           for side in ('front','rear') for kind in ('points','imu')]
    def cb(name,kind):
        def receive(sample):
            t=time.monotonic_ns();wall=time.time_ns()
            try:
                att=sample.attachment.to_bytes() if sample.attachment else b''
                if len(att)!=33 or att[16]!=16:raise ValueError('invalid attachment')
                seq,pub=struct.unpack_from('<qq',att);raw=sample.payload.to_bytes()
                if raw[:2]!=b'\x00\x01':raise ValueError('expected little-endian CDR')
                sec,ns=struct.unpack_from('<iI',raw,4);stamp=sec*10**9+ns
                row=[stamp,seq,pub,wall,t,att[17:].hex(),time.monotonic_ns()-t]
                with lock:
                    rows[name].append(row)
                    # IMU 全存以核查静止；点云只保留每两秒一帧，最多 20 帧。
                    if kind=='imu' or (len(snaps[name])<20 and (not snaps[name] or t-snaps[name][-1][0]>2_000_000_000)):
                        snaps[name].append((t,raw))
            except Exception as e:
                with lock:errors.append(str(e))
        return receive
    config=zenoh.Config()
    for k,v in {'mode':'client','connect/endpoints':['tcp/192.168.168.100:7447'],'connect/timeout_ms':4000,'scouting/multicast/enabled':False}.items():config.insert_json5(k,json.dumps(v))
    with zenoh.open(config) as session:
        subs=[]
        for side,kind,key,cls in specs:
            name=side+'/'+kind;rows[name]=[];snaps[name]=[]
            subs.append(session.declare_subscriber(f'24/{key}/sensor_msgs::msg::dds_::{cls.__name__}_/TypeHashNotSupported',cb(name,kind)))
        deadline=time.monotonic()+a.seconds
        while time.monotonic()<deadline:time.sleep(.2)
        for sub in subs:sub.undeclare()
    report={'timestamp_unix':time.time(),'duration_s':a.seconds,'errors':errors,'streams':{},'geometry':{},'motion_outputs':False,
            'extrinsics_verified':False,'hardware_sync_verified':False,'notes':['平面未标注地面；不同原始坐标系不能直接比较法向与重力。','静止特征不能确定完整外参或动态时延；探针仍有网络与复制开销。']}
    for side,kind,key,cls in specs:
        name=side+'/'+kind;rr=rows[name];info={'count':len(rr)};report['streams'][name]=info
        if len(rr)<2:continue
        v=np.array([r[:5] for r in rr],dtype=np.int64);gids=[r[5] for r in rr]
        same=np.array([gids[i]==gids[i-1] for i in range(1,len(gids))]);ds=np.diff(v[:,0])*1e-9;dq=np.diff(v[:,1])
        info.update(gids=sorted(set(gids)),gid_changes=int((~same).sum()),sequence_missing=int(np.maximum(dq[same]-1,0).sum()),
                    sequence_repeats_or_reorders=int(((dq<=0)&same).sum()),source_regressions=int((ds<0).sum()),source_duplicates=int((ds==0).sum()),
                    source_gap_s_quantiles=np.quantile(ds,[.5,.99,1]).tolist(),receive_gap_s_quantiles=np.quantile(np.diff(v[:,4])*1e-9,[.5,.99,1]).tolist(),
                    continuous_sequence_large_gaps=int(((dq==1)&same&(ds>(.015 if kind=='imu' else .15))).sum()),
                    publisher_minus_device_s_quantiles=np.quantile((v[:,2]-v[:,0])*1e-9,[0,.5,1]).tolist(),
                    local_minus_publisher_s_quantiles=np.quantile((v[:,3]-v[:,2])*1e-9,[0,.5,1]).tolist(),
                    callback_copy_ms_quantiles=np.quantile([r[6]*1e-6 for r in rr],[.5,.99,1]).tolist())
        if kind=='imu':
            msgs=[deserialize_message(raw,Imu) for _,raw in snaps[name]]
            acc=np.array([[m.linear_acceleration.x,m.linear_acceleration.y,m.linear_acceleration.z] for m in msgs])
            gyro=np.array([[m.angular_velocity.x,m.angular_velocity.y,m.angular_velocity.z] for m in msgs])
            info.update(acc_mean_raw_g=acc.mean(axis=0).tolist(),acc_std_raw_g=acc.std(axis=0).tolist(),
                        acc_norm_raw_g_quantiles=np.quantile(np.linalg.norm(acc,axis=1),[0,.5,.99,1]).tolist(),
                        gyro_mean_rad_s=gyro.mean(axis=0).tolist(),gyro_norm_rad_s_quantiles=np.quantile(np.linalg.norm(gyro,axis=1),[.5,.99,1]).tolist(),
                        frame_ids=sorted(set(m.header.frame_id for m in msgs)))
            np.savez_compressed(a.output/(side+'_imu.npz'),acc_g=acc,gyro_rad_s=gyro)
        else:
            result=[]
            for j,(_,raw) in enumerate(snaps[name]):
                (a.output/f'{side}_{j:02}.cdr').write_bytes(raw)
                m=deserialize_message(raw,PointCloud2);v=cloud_view(m);xyz=np.stack([v[k] for k in ('x','y','z')],axis=-1).reshape(-1,3);xyz=xyz[np.isfinite(xyz).all(axis=1)]
                xyz=xyz[(np.linalg.norm(xyz,axis=1)>.2)&(np.linalg.norm(xyz,axis=1)<15)]
                result.append({'file':f'{side}_{j:02}.cdr','frame_id':m.header.frame_id,'valid_points':len(xyz),
                               'planes':planes(xyz,j) if len(xyz)>100 else []})
            report['geometry'][side]=result
    (a.output/'timing_rows.json').write_text(json.dumps(rows))
    (a.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='geometry'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
