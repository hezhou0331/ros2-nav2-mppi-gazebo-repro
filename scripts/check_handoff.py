#!/usr/bin/env python3
"""只读核对交接资料、入口和可选录包；不连接机器人，不发布消息。"""
import argparse,hashlib,json,sys
from pathlib import Path


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data-root',type=Path)
    a=p.parse_args();root=Path(__file__).resolve().parent.parent;errors=[]
    inv=json.loads((root/'vendor/inventory.json').read_text())
    for entry in inv['files']:
        f=root/'vendor'/entry['path']
        if not f.is_file() or f.stat().st_size!=entry['bytes'] or digest(f)!=entry['sha256']:errors.append('vendor/'+entry['path'])
    for name in ['AGENTS.md','docs/CURRENT_STATUS.md','docs/STATIONARY_CHECK.md','docs/INPUT_FAULT_TESTS.md','docs/HANDOFF.md','m1_preflight/airy_adapter/verify_fault_replay.py','scripts/prepare_workspace.py']:
        if not (root/name).is_file():errors.append(name)
    if a.data_root:
        for name in ['artifacts/real_sensors/bag_before_mapping_30s/metadata.yaml','artifacts/real_sensors/bag_20260912_live/metadata.yaml','artifacts/real_sensors/stationary_20260913_01/report.json','artifacts/fault_ros/report.json','artifacts/fault_ros_fixed/report.json']:
            if not (a.data_root/name).is_file():errors.append(str(a.data_root/name))
    result={'vendor_files_checked':len(inv['files']),'errors':errors,'passed':not errors,'robot_accessed':False,'scope':'文件完整性；不代表 ROS 构建、同步、标定或真机导航通过'}
    print(json.dumps(result,ensure_ascii=False,indent=2));return int(bool(errors))

if __name__=='__main__':sys.exit(main())
