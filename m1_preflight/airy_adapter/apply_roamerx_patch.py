#!/usr/bin/env python3
"""向独立构建副本应用 AIRY 入口；原始锁定 checkout 保持不变。"""
import argparse,hashlib,shutil,difflib,tempfile,subprocess,sys,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
if a.output.resolve()==a.source.resolve():raise SystemExit('必须使用独立源代码副本')
if a.output.exists():
    # 重新生成到临时目录并逐文件比较；有任何变化都不覆盖既有源码。
    with tempfile.TemporaryDirectory(prefix='m1_airy_check_',dir=a.output.parent) as td:
        expected=Path(td)/'expected'
        subprocess.run([sys.executable,__file__,'--source',str(a.source),'--output',str(expected)],check=True)
        for f in expected.rglob('*'):
            if f.is_file():
                actual=a.output/f.relative_to(expected)
                if not actual.is_file() or actual.read_bytes()!=f.read_bytes():
                    raise SystemExit('已有 AIRY 副本与当前补丁不一致：'+str(actual))
        print('AIRY 独立副本与当前源码/补丁一致')
    raise SystemExit(0)
shutil.copytree(a.source,a.output)
f=a.output/'src/mapping_alg.cpp';old=f.read_text();new=old.replace('#include "mapping_alg.h"','#include "mapping_alg.h"\n#include "process/airy_preprocess.h"',1)
start='''        pcl::PointCloud<livox_pcl::Point> pl_orig;
        pcl::fromROSMsg(*msg, pl_orig);

        p_pre->process(pl_orig, ptr);'''
replacement='''        // M1 AIRY 为独立类型 5；明确解析 XYZIRT，不伪造 Livox tag。
        try {
            if (p_pre->lidar_type == 5) {
                m1_airy::decode(*msg, ptr, p_pre->blind, p_pre->point_filter_num);
            } else {
                pcl::PointCloud<livox_pcl::Point> pl_orig;
                pcl::fromROSMsg(*msg, pl_orig);
                p_pre->process(pl_orig, ptr);
            }
        } catch (const std::exception& error) {
            RCLCPP_ERROR(this->get_logger(), "Rejected lidar frame: %s", error.what());
            mtx_buffer.unlock();
            return;
        }'''
if old.count(start)!=1:raise SystemExit('上游回调与预期不符，停止应用补丁')
new=new.replace(start,replacement)
# 回退时必须同时清空点云和时间队列，防止后续帧时间配对错误。
new=new.replace('''            lidar_buffer.clear();
        }
        if (is_first_lidar)''','''            lidar_buffer.clear();
            time_buffer.clear();
            lidar_pushed = false;
        }
        if (is_first_lidar)''',1)
f.write_text(new)
shutil.copy2(Path(__file__).with_name('airy_preprocess.h'),a.output/'include/process/airy_preprocess.h')
patch=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/src/mapping_alg.cpp',tofile='b/src/mapping_alg.cpp'))
(a.output/'m1_airy_changes.patch').write_text(patch)
print('AIRY 分支已准备在独立副本：',a.output)

# 附带离线验证程序，使用完全相同的原生解码函数。
shutil.copy2(Path(__file__).with_name('native_audit.cpp'), a.output/'test/m1_airy_native_audit.cpp')
c=a.output/'CMakeLists.txt'
c.write_text(c.read_text() + '\nadd_executable(m1_airy_native_audit test/m1_airy_native_audit.cpp)\ntarget_link_libraries(m1_airy_native_audit ${PCL_LIBRARIES})\nament_target_dependencies(m1_airy_native_audit ${dependencies})\ninstall(TARGETS m1_airy_native_audit DESTINATION lib/${PROJECT_NAME})\n')
