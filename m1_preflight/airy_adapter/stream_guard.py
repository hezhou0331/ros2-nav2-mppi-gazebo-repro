"""确定性的输入状态机；定时 tick 独立于消息到达，故障锁定直到重建实例。"""
import math

STREAMS=('front/points','front/imu','rear/points','rear/imu')


class InputFault(ValueError):
    pass


class SourceIdentityGuard:
    """识别源端进程变化；序号缺口允许记录，重复/倒退与 GID 变化锁住转发。"""
    def __init__(self):
        self.last={};self.fault=None

    def observe(self,stream,gid,sequence):
        if self.fault:raise InputFault(self.fault)
        previous=self.last.get(stream)
        reason=None
        if not isinstance(gid,str) or len(gid)!=32 or any(c not in '0123456789abcdef' for c in gid):reason='invalid_source_gid'
        elif not isinstance(sequence,int) or sequence<0:reason='invalid_source_sequence'
        elif previous and gid!=previous[0]:reason='source_publisher_changed'
        elif previous and sequence<=previous[1]:reason='source_sequence_nonincreasing'
        if reason:
            self.fault=stream+': '+reason;raise InputFault(self.fault)
        self.last[stream]=(gid,sequence)


class InputGuard:
    startup_grace_s=5.0
    silence_s={'imu':.10,'points':.35}
    source_gap_s={'imu':.05,'points':.25}
    max_age_s={'imu':.25,'points':.50}

    def __init__(self,profile,wall_ns,mono_ns):
        audit=profile.get('audit_timestamp_unix');valid=profile.get('valid_for_seconds')
        if (not isinstance(audit,(int,float)) or not math.isfinite(audit) or
            not isinstance(valid,(int,float)) or not math.isfinite(valid) or not 0<valid<=600):
            raise ValueError('非法时钟配置有效期')
        if not 0<=wall_ns*1e-9-audit<valid:raise ValueError('时钟配置过期或来自未来')
        offsets=profile.get('offset_ns',{})
        if any(type(offsets.get(s)) is not int for s in ('front','rear')):raise ValueError('缺少整数时钟偏移')
        self.offsets=offsets;self.expires_ns=int((audit+valid)*1e9)
        self.started=mono_ns;self.wall_last=wall_ns;self.mono_last=mono_ns
        self.last={};self.fault=None;self.ready=False

    def trip(self,code,stream,detail,mono_ns):
        if not self.fault:
            self.fault={'code':code,'stream':stream,'detail':detail,'monotonic_ns':mono_ns}
        self.ready=False
        raise InputFault(self.fault['code']+': '+self.fault['stream']+' '+self.fault['detail'])

    def tick(self,wall_ns,mono_ns):
        if self.fault:return False
        if mono_ns<self.mono_last:self.trip('monotonic_regression','all','单调时钟倒退',mono_ns)
        if abs((wall_ns-self.wall_last)-(mono_ns-self.mono_last))>50_000_000:
            self.trip('host_clock_jump','all','主机墙钟跳变超过 50 ms',mono_ns)
        self.wall_last=wall_ns;self.mono_last=mono_ns
        if wall_ns>=self.expires_ns:self.trip('profile_expired','all','重新审计时间后重启，不能续用旧定位状态',mono_ns)
        for stream in STREAMS:
            prev=self.last.get(stream)
            if prev is None:
                if mono_ns-self.started>self.startup_grace_s*1e9:self.trip('startup_missing',stream,'启动等待超过 5 秒',mono_ns)
            elif mono_ns-prev['mono']>self.silence_s[stream.split('/')[1]]*1e9:
                self.trip('stream_timeout',stream,'输入完全断流',mono_ns)
        return self.ready

    def observe(self,stream,source_ns,mapped_ns,wall_ns,mono_ns,publisher_gid):
        self.tick(wall_ns,mono_ns)
        if self.fault:raise InputFault(self.fault['code'])
        kind=stream.split('/')[1];prev=self.last.get(stream)
        age=(wall_ns-mapped_ns)*1e-9
        if not -.05<=age<=self.max_age_s[kind]:self.trip('stale_or_future',stream,'样本年龄超限',mono_ns)
        if not publisher_gid:self.trip('missing_publisher',stream,'没有可核对的 ROS 发布者标识',mono_ns)
        if prev:
            if publisher_gid!=prev['gid']:self.trip('publisher_changed',stream,'ROS 发布者改变，需重新初始化',mono_ns)
            delta=(source_ns-prev['source'])*1e-9
            if delta<=0:self.trip('source_nonincreasing',stream,'设备时间重复或回退',mono_ns)
            if delta>self.source_gap_s[kind]:self.trip('source_gap',stream,f'已收到样本的设备时间间隔 {delta:.6f}s 超过 {self.source_gap_s[kind]:.3f}s',mono_ns)
        self.last[stream]={'source':source_ns,'mono':mono_ns,'gid':publisher_gid}
        self.ready=len(self.last)==len(STREAMS)
        return self.ready

    def snapshot(self,mono_ns):
        return {'state':'fault' if self.fault else 'active' if self.ready else 'waiting',
                'output_enabled':self.ready and not self.fault,'fault':self.fault,
                'stream_age_s':{s:None if s not in self.last else (mono_ns-self.last[s]['mono'])*1e-9 for s in STREAMS},
                'thresholds':{'startup_grace_s':self.startup_grace_s,'silence_s':self.silence_s,'source_gap_s':self.source_gap_s,'max_age_s':self.max_age_s}}
