#!/usr/bin/env python3
"""下载按校验值固定的 PCAP 软件包，仅解包到传感器工作区。"""
import hashlib
import json
import subprocess
from pathlib import Path

if subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip() != 'arm64':
    raise SystemExit('Run sensor dependency preparation on the ARM64 Orin.')

here = Path(__file__).resolve().parent
root = here.parent / 'sensors'
cache = root / 'deps_cache'
cache.mkdir(parents=True, exist_ok=True)
for package in json.loads((here / 'pcap_dependencies.lock.json').read_text()):
    archive = cache / package['filename']
    if not archive.exists():
        subprocess.run(['apt-get', 'download', f"{package['name']}:arm64={package['version']}"],
                       cwd=cache, check=True)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != package['sha256']:
        raise RuntimeError(f'Package SHA256 mismatch: {archive}')
    subprocess.run(['dpkg-deb', '-x', str(archive), str(root / 'deps')], check=True)
    print(f"Verified and extracted {package['name']} {package['version']}")
