#!/usr/bin/env python3
"""准备可移动的源码目录；只取源码/建链接，不安装系统包、不启动传感器或运动。

--offline 使用 Release 中保存的固定源码；默认按锁文件获取公开上游。
已有不同目录或源码版本拒绝覆盖，保留接手者自己的工作。
"""
import argparse,json,subprocess
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--offline',action='store_true')
    a=p.parse_args();root=Path(__file__).resolve().parent.parent
    if not a.offline:
        subprocess.run(['bash',str(root/'scripts/fetch_roamerx.sh')],check=True)
        subprocess.run(['/usr/bin/python3',str(root/'m1_preflight/fetch_airy_sources.py'),'--source-root',str(root/'third_party')],check=True)
    upstream=json.loads((root/'upstream.lock.json').read_text())
    airy=json.loads((root/'m1_preflight/airy_sources.lock.json').read_text())
    repos=[(root/'third_party/genisom_roamerx_open',upstream['commit'])]
    repos += [(root/'third_party'/r['path'],r['commit']) for r in airy['repositories']]
    for path,commit in repos:
        actual=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
        if actual!=commit:raise SystemExit(f'源码版本不符：{path}')
        # 已审查的 SDK CMake 补丁是唯一允许的工作树变更。
        names=subprocess.check_output(['git','-C',str(path),'diff','HEAD','--name-only'],text=True).splitlines()
        if path==root/'third_party/rslidar_sdk':
            if names!=['CMakeLists.txt']:raise SystemExit('AIRY CMake 补丁未应用或有额外修改')
            subprocess.run(['git','-C',str(path),'apply','--reverse','--check',str(root/'m1_preflight'/airy['patch'])],check=True)
        elif names:raise SystemExit(f'源码有未记录修改：{path}')
    for link,target in [(root/'src',root/'third_party/genisom_roamerx_open/src'),(root/'sensors/src',root/'third_party')]:
        if link.is_symlink() and link.resolve()==target.resolve():continue
        if link.exists() or link.is_symlink():raise SystemExit(f'已有目录不覆盖：{link}')
        link.parent.mkdir(parents=True,exist_ok=True)
        import os
        link.symlink_to(os.path.relpath(target,link.parent),target_is_directory=True)
    (root/'artifacts').mkdir(exist_ok=True)
    print('固定源码和构建目录已准备；未运行驱动、导航或控制。')

if __name__=='__main__':main()
