#!/usr/bin/env python3
"""下载固定版本的 ARM64 构建依赖，仅解包到本工作区。"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Verify cached archives only')
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    root = here.parent
    packages = json.loads((here / 'dependencies.lock.json').read_text())
    if subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip() != 'arm64':
        parser.error('Run this dependency preparation on the ARM64 Orin, not the Jazzy host.')
    downloads = root / 'deps/downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    for package in packages:
        archive = downloads / package['filename']
        if not archive.exists() and not args.check:
            subprocess.run(['apt-get', 'download',
                            f"{package['package']}:{package['architecture']}={package['version']}"],
                           cwd=downloads, check=True)
        if not archive.is_file():
            raise SystemExit(f'Missing dependency archive: {archive.name}')
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != package['sha256']:
            raise SystemExit(f'Checksum mismatch: {archive.name}; preserve and inspect this file.')
        if not args.check:
            subprocess.run(['dpkg-deb', '-x', str(archive), str(root / 'deps')], check=True)
        print(f"Verified {package['package']} {package['version']}")
    print('Archive check complete.' if args.check else 'Workspace dependencies ready; no system packages installed.')


if __name__ == '__main__':
    main()
