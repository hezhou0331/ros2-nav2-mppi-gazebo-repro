#!/usr/bin/env python3
"""解包校验值已固定的 wheel，在本工作区准备 Zenoh 客户端。"""
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import zipfile

root = Path(__file__).resolve().parent.parent
if subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip() != 'arm64':
    raise SystemExit('This wheel is pinned for the ARM64 Orin.')
lock = json.loads((root / 'm1_preflight/zenoh_probe.lock.json').read_text())
cache = root / 'deps/downloads'
cache.mkdir(parents=True, exist_ok=True)
archive = cache / lock['filename']
if not archive.exists():
    urllib.request.urlretrieve(lock['url'], archive)
if hashlib.sha256(archive.read_bytes()).hexdigest() != lock['sha256']:
    raise SystemExit('Zenoh wheel checksum mismatch; preserve the file for inspection.')
with zipfile.ZipFile(archive) as wheel:
    wheel.extractall(root / 'deps/zenoh1101')
print('Verified Zenoh client ready; system packages unchanged.')
