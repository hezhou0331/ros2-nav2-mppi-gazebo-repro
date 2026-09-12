#!/usr/bin/env python3
"""仅检查已知 M1 网络地址，不进行 SDK 握手或控制请求。"""
import argparse
import json
import socket
import subprocess
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
              'scope': 'Known TCP endpoints and local network configuration; protocol unverified',
              'hostname': socket.gethostname(), 'endpoints': [], 'mdns': {}}
    for address, ports in [('192.168.168.168', [22, 8081, 8554]),
                           ('192.168.168.100', [22])]:
        for port in ports:
            item = {'address': address, 'tcp_port': port}
            try:
                with socket.create_connection((address, port), timeout=2) as conn:
                    item['connected'] = True
                    if port == 22:
                        item['banner'] = conn.recv(512).decode(errors='replace').strip()
            except OSError as error:
                item.update(connected=False, error=str(error))
            report['endpoints'].append(item)
        try:
            result = subprocess.run(['avahi-resolve-address', address], text=True,
                                    capture_output=True, timeout=3)
            if result.returncode == 0:
                report['mdns'][address] = result.stdout.strip().split()[-1]
        except (OSError, subprocess.TimeoutExpired):
            pass
    for name, command in [('interfaces', ['ip', '-j', 'address']),
                          ('robot_route', ['ip', '-j', 'route', 'get', '192.168.168.168'])]:
        result = subprocess.run(command, text=True, capture_output=True, check=True)
        report[name] = json.loads(result.stdout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
