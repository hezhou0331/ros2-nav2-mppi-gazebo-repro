"""线上与故障注入共用的转换入口；任何关键错误都锁定全部输出。"""
from adapter_core import stamp_ns,convert_cloud,convert_imu
from stream_guard import InputGuard,InputFault


class AdapterEngine:
    def __init__(self,profile,wall_ns,mono_ns):
        self.guard=InputGuard(profile,wall_ns,mono_ns)
        self.accepted={}

    def process(self,side,kind,msg,wall_ns,mono_ns,publisher_gid):
        guard=self.guard;stream=side+'/'+kind
        guard.tick(wall_ns,mono_ns)
        if guard.fault:raise InputFault(guard.fault['code'])
        frame='rslidar_head' if side=='front' else 'rslidar_tail'
        if msg.header.frame_id!=frame:guard.trip('frame_changed',stream,'原始坐标名不符',mono_ns)
        offset=guard.offsets[side]
        try:out=convert_cloud(msg,offset) if kind=='points' else convert_imu(msg,offset,frame+'_imu')
        except (ValueError,TypeError,OverflowError) as error:guard.trip('invalid_measurement',stream,str(error),mono_ns)
        ready=guard.observe(stream,stamp_ns(msg),stamp_ns(out),wall_ns,mono_ns,publisher_gid)
        self.accepted[stream]=self.accepted.get(stream,0)+1
        return out if ready else None
