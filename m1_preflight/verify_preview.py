#!/usr/bin/env python3
"""在本机回环网络上加载并配置导航插件，不激活控制。"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import rclpy
from lifecycle_msgs.srv import GetState, ChangeState
from lifecycle_msgs.msg import Transition

NODES = ['map_server', 'planner_server', 'controller_server', 'behavior_server',
         'velocity_optimizer', 'bt_navigator', 'waypoint_follower']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--params', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or os.environ.get('ROS_DOMAIN_ID') != '176':
        parser.error('This software-only check requires ROS_LOCALHOST_ONLY=1 and ROS_DOMAIN_ID=176.')
    root = Path(__file__).resolve().parent
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {'scope': 'Loopback-only synthetic-map plugin configuration; no navigation goals or hardware',
              'ros_domain_id': 176, 'nodes': {}, 'passed': False, 'hardware_navigation_verified': False}
    process = None
    rclpy.init()
    node = rclpy.create_node('m1_preview_checker')
    def call(service, typ, request, timeout=20):
        client = node.create_client(typ, service)
        try:
            if not client.wait_for_service(timeout_sec=timeout):
                raise RuntimeError(f'Unavailable service: {service}')
            future = client.call_async(request)
            rclpy.spin_until_future_complete(node, future, timeout_sec=timeout)
            if not future.done() or future.result() is None:
                raise RuntimeError(f'Service timed out: {service}')
            return future.result()
        finally:
            node.destroy_client(client)
    try:
        with args.output.with_suffix('.log').open('w') as log:
            process = subprocess.Popen(
                ['ros2', 'launch', str(root / 'navigation_preview.launch.py'),
                 'params_file:=' + str(args.params.resolve())],
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            for name in NODES:
                prefix = '/m1_preview/' + name
                state = call(prefix + '/get_state', GetState, GetState.Request()).current_state
                report['nodes'][name] = {'initial': state.label}
                if state.id != 1:
                    raise RuntimeError(f'{name} was unexpectedly activated/configured: {state.label}')
            for name in NODES:
                request = ChangeState.Request()
                request.transition.id = Transition.TRANSITION_CONFIGURE
                result = call('/m1_preview/' + name + '/change_state', ChangeState, request)
                state = call('/m1_preview/' + name + '/get_state', GetState, GetState.Request()).current_state
                report['nodes'][name].update(configure_success=result.success, final=state.label)
                if not result.success or state.id != 2:
                    raise RuntimeError(f'{name} failed to configure: {state.label}')
            until = time.monotonic() + 2
            while time.monotonic() < until:
                rclpy.spin_once(node, timeout_sec=0.1)
            report['root_velocity_publishers'] = {topic: node.count_publishers(topic)
                for topic in ['/cmd_vel', '/cmd_vel_raw', '/cmd_vel_smoothed']}
            report['discovered_nodes'] = sorted(ns.rstrip('/') + '/' + name
                for name, ns in node.get_node_names_and_namespaces())
            report['passed'] = (all(v == 0 for v in report['root_velocity_publishers'].values())
                                and process.poll() is None)
    except Exception as error:
        report['error'] = str(error)
    finally:
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
        node.destroy_node()
        rclpy.shutdown()
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
