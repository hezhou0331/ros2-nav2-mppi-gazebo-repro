#!/usr/bin/env python3
"""获取固定版本的 AIRY 官方源码，并应用已记录的 CMake 构建补丁。"""
import argparse
import json
import subprocess
from pathlib import Path


def git(path, *args, check=True):
    return subprocess.run(['git', '-C', str(path), *args], check=check,
                          capture_output=True, text=True)


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=here.parent / 'sensors/src')
    args = parser.parse_args()
    lock = json.loads((here / 'airy_sources.lock.json').read_text())
    args.source_root.mkdir(parents=True, exist_ok=True)
    # rs_driver 单独固定提交，不自动跟随远端分支更新。
    for repo in lock['repositories']:
        path = args.source_root / repo['path']
        created = False
        if not (path / '.git').exists():
            if path.exists() and any(path.iterdir()):
                raise RuntimeError(f'Nonempty directory without Git metadata: {path}')
            subprocess.run(['git', 'clone', '--no-checkout', '--filter=blob:none',
                            repo['url'], str(path)], check=True)
            created = True
        actual = git(path, 'rev-parse', 'HEAD', check=False).stdout.strip()
        # 即使 HEAD 已是指定提交，--no-checkout 仍会留下空工作树，首次必须检出。
        if created or actual != repo['commit']:
            if not created and git(path, 'status', '--porcelain').stdout.strip():
                raise RuntimeError(f'Preserve local edits; checkout refused: {path}')
            git(path, 'fetch', '--depth', '1', 'origin', repo['commit'])
            git(path, 'checkout', '--detach', repo['commit'])
        if git(path, 'rev-parse', 'HEAD').stdout.strip() != repo['commit']:
            raise RuntimeError(f'Commit verification failed: {path}')
    sdk = args.source_root / 'rslidar_sdk'
    patch = here / lock['patch']
    if git(sdk, 'apply', '--reverse', '--check', str(patch), check=False).returncode:
        git(sdk, 'apply', '--check', str(patch))
        git(sdk, 'apply', str(patch))
    print(f'Pinned sources ready at {args.source_root.resolve()}; no driver was started.')


if __name__ == '__main__':
    main()
