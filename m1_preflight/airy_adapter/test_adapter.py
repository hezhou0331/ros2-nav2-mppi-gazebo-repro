"""单位、协方差、时间异常以及外参方向校验；不访问任何机器人服务。"""
import copy,unittest
import numpy as np
from sensor_msgs.msg import Imu,PointCloud2,PointField
from adapter_core import *
from prepare_mapping import validate_transform
class Tests(unittest.TestCase):
    def imu(self):
        m=Imu();m.header.stamp.sec=100;m.linear_acceleration.y=1.;m.angular_velocity.z=.25
        m.linear_acceleration_covariance=[.01,0.,0.,0.,.02,0.,0.,0.,.03];return m
    def test_si_covariance_orientation_and_raw(self):
        m=self.imu();n=convert_imu(m,123,'imu')
        self.assertEqual(m.linear_acceleration.y,1.)
        self.assertAlmostEqual(n.linear_acceleration.y,G)
        self.assertAlmostEqual(n.linear_acceleration_covariance[0],.01*G*G)
        self.assertEqual(n.angular_velocity.z,.25);self.assertEqual(n.orientation_covariance[0],-1)
        self.assertEqual(n.header.frame_id,'imu');self.assertEqual(stamp_ns(n)-stamp_ns(m),123)
    def test_unknown_covariance(self):
        m=self.imu();m.linear_acceleration_covariance=[0.]*9
        self.assertEqual(list(convert_imu(m,0,'imu').linear_acceleration_covariance),[0.]*9)
    def test_nonfinite_imu(self):
        m=self.imu();m.angular_velocity.x=float('nan')
        with self.assertRaises(ValueError):convert_imu(m,0,'imu')
    def check_fault(self,source,wall,mono):
        g=ClockGuard();g.check('front/imu',100000000000,100000000000,100010000000,1000000000)
        with self.assertRaises(ValueError):g.check('front/imu',source,source,wall,mono)
        with self.assertRaises(ValueError):g.check('front/imu',101000000000,101000000000,101010000000,2000000000)
    def test_backward_clock_latches(self):self.check_fault(99000000000,100020000000,1010000000)
    def test_duplicate_clock_latches(self):self.check_fault(100000000000,100020000000,1010000000)
    def test_forward_step_latches(self):self.check_fault(102000000000,102010000000,1010000000)
    def test_host_clock_jump_latches(self):self.check_fault(100010000000,100120000000,1010000000)
    def test_valid_clock(self):
        g=ClockGuard()
        for i in range(100):g.check('front/imu',100000000000+i*5000000,100000000000+i*5000000,100010000000+i*5000000,1000000000+i*5000000)
        self.assertIsNone(g.fault)
    def test_missing_calibration_rejected(self):
        with self.assertRaises(ValueError):validate_transform({'verified':False},'front')
    def test_reflected_rotation_rejected(self):
        with self.assertRaises(ValueError):validate_transform({'verified':True,'evidence':'test only','translation_m':[0,0,0],'rotation':np.diag([1,1,-1]).tolist()},'front')
    def test_cloud_layout_shift_and_no_mutation(self):
        m=PointCloud2();m.header.stamp.sec=100;m.height=1;m.width=2;m.point_step=26;m.row_step=52
        for name,kind,offset in [('x',7,0),('y',7,4),('z',7,8),('intensity',7,12),('ring',4,16),('timestamp',8,18)]:
            m.fields.append(PointField(name=name,datatype=kind,offset=offset,count=1))
        m.data=bytes(52);arr=cloud_view(m);arr['x']=1;arr['timestamp']=[100.001,100.099];arr['ring']=[0,95]
        original=bytes(m.data);out=convert_cloud(m,1789213127760000000)
        self.assertEqual(bytes(m.data),original)
        np.testing.assert_allclose(cloud_view(out)['timestamp']-stamp_ns(out)*1e-9,[[.001,.099]],atol=5e-7)
        bad=copy.deepcopy(m);cloud_view(bad)['timestamp'][0,0]=99
        with self.assertRaises(ValueError):convert_cloud(bad,0)
        bad=copy.deepcopy(m);bad.fields[-1].datatype=7
        with self.assertRaises(ValueError):convert_cloud(bad,0)
if __name__=='__main__':unittest.main()
