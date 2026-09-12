"""非零平移、旋转及机身杆臂的坐标方向测试；不将测试标定写入实机配置。"""
import unittest
import numpy as np
from transform_core import *

class Geometry(unittest.TestCase):
 def test_rotated_sensor_lever_arm(self):
  r=quaternion_matrix([0,0,np.sin(np.pi/4),np.cos(np.pi/4)])
  base_imu=matrix(r,[.4,.1,.2]);map_base=matrix(r,[3,2,1]);odom_base=matrix(np.eye(3),[1,0,0])
  mt,bt=compose_navigation(map_base@base_imu,odom_base,base_imu,1_000_000_000,1_000_000_000)
  np.testing.assert_allclose(bt,map_base,atol=1e-12)
  np.testing.assert_allclose(mt@odom_base,map_base,atol=1e-12)
 def test_calibration_inverse(self):
  r=quaternion_matrix([0,0,1,0])
  c={'base_from_lidar':{'rotation':r.tolist(),'translation_m':[1,2,3],'verified':True,'evidence':'synthetic fixture'},'imu_from_lidar':{'rotation':np.eye(3).tolist(),'translation_m':[.1,.2,.3],'verified':True,'evidence':'synthetic fixture'}}
  b,i,bi=load_calibration(c);np.testing.assert_allclose(bi@i,b)
 def test_time_mismatch(self):
  with self.assertRaises(ValueError):compose_navigation(np.eye(4),np.eye(4),np.eye(4),0,21_000_000)
 def test_missing_calibration(self):
  with self.assertRaises(ValueError):load_calibration({'base_from_lidar':{'verified':False}})
 def test_invalid_rotation(self):
  bad=np.eye(4);bad[0,0]=-1
  with self.assertRaises(ValueError):compose_navigation(bad,np.eye(4),np.eye(4),0,0)
 def test_zero_quaternion(self):
  with self.assertRaises(ValueError):quaternion_matrix([0,0,0,0])
if __name__=='__main__':unittest.main()
