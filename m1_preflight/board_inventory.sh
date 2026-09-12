#!/usr/bin/env bash
# 通过已认证的 SSH 会话在 M1 板卡上执行；仅检查信息，不启动服务。
set -u
printf 'Identity\n'
hostname
uname -m
cat /etc/os-release
if [[ -r /proc/device-tree/model ]]; then tr '\0' '\n' </proc/device-tree/model; fi
if [[ -r /etc/nv_tegra_release ]]; then cat /etc/nv_tegra_release; fi
printf 'Network and listeners\n'
ip -brief address
ip route
ss -ulpn
printf 'Running service names\n'
systemctl list-units --type=service --state=running --no-pager
printf 'Relevant process names\n'
ps -eo pid,comm | grep -Ei 'ros|lidar|livox|lio|slam|robot|lcm|zenoh|mc_|mapping|localization' || true
printf 'Installed software roots\n'
ls /opt
printf 'ROS process environment (selected keys only)\n'
python3 - <<'PY'
from pathlib import Path
keys={b'ROS_DOMAIN_ID',b'ROS_DISTRO',b'RMW_IMPLEMENTATION',b'ROS_LOCALHOST_ONLY',
      b'CYCLONEDDS_URI',b'FASTRTPS_DEFAULT_PROFILES_FILE'}
for path in Path('/proc').glob('[0-9]*/environ'):
    try:
        values=[v.decode(errors='replace') for v in path.read_bytes().split(b'\0')
                if v.split(b'=',1)[0] in keys]
        if values:
            print(path.parent.name, (path.parent/'comm').read_text().strip(), values)
    except (OSError,PermissionError):
        pass
PY
