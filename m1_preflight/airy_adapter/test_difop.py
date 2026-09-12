"""使用明确合成的网络字节序包验证解析与坏包拒绝，不声称取得实机标定。"""
import struct,unittest,tempfile
from pathlib import Path
from extract_airy_difop import *
class Difop(unittest.TestCase):
 def packet(self):
  data=bytearray(LENGTH);data[:8]=MAGIC;data[-2:]=bytes.fromhex('0ff0');data[292:298]=bytes.fromhex('010203040506');struct.pack_into('>7f',data,1092,0,0,0,1,.00425,-.02,.03);return data
 def test_big_endian(self):
  d=decode(self.packet());self.assertEqual(d['serial_hex'],'010203040506');self.assertAlmostEqual(d['translation_as_reported'][0],.00425,8);self.assertFalse(d['verified_for_current_robot'])
 def test_bad_quaternion(self):
  d=self.packet();struct.pack_into('>f',d,1104,0)
  with self.assertRaises(ValueError):decode(d)
 def test_bad_tail(self):
  d=self.packet();d[-1]=0
  with self.assertRaises(ValueError):decode(d)
 def test_chunk_boundary(self):
  with tempfile.TemporaryDirectory() as root:
   p=Path(root)/'synthetic.bin';p.write_bytes(b'\0'*(1024*1024-100)+self.packet());d=scan_file(p)
   self.assertEqual(len(d['candidates']),1);self.assertEqual(d['candidates'][0]['file_offset'],1024*1024-100)
if __name__=='__main__':unittest.main()
