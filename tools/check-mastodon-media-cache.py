#!/usr/bin/env python3
"""Verify a disposable fixture against every production media-cache replica.

Use only /mastodon/cache-pilot/ fixtures. This helper reads media and creates
loopback port-forwards; it does not create/delete objects or purge cache data.
For lifecycle tests, warm, change/delete/restrict the fixture at S3, then rerun
with --expect-missing, --expect-private, or --expect-body-sha256 as appropriate.
"""
import argparse
import hashlib
import http.client
import json
import socket
import subprocess
import time

HOST = 's3.andreybondarenko.com'


def fetch(port, path, headers=None):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=15)
    try:
        connection.request('GET', path, headers={'Host': HOST, **(headers or {})})
        response = connection.getresponse()
        body = response.read()
        return response.status, response.getheader('X-Media-Cache', ''), hashlib.sha256(body).hexdigest()
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path', default='/mastodon/cache-pilot/fixture.txt')
    expectation = parser.add_mutually_exclusive_group()
    expectation.add_argument('--expect-missing', action='store_true')
    expectation.add_argument('--expect-private', action='store_true')
    parser.add_argument('--expect-body-sha256')
    args = parser.parse_args()
    if not args.path.startswith('/mastodon/cache-pilot/') or '?' in args.path:
        parser.error('Only query-free disposable /mastodon/cache-pilot/ fixtures are accepted')
    raw = subprocess.run(['kubectl', 'get', 'pods', '-n', 'seaweedfs', '-l', 'app=mastodon-media-cache', '-o', 'json', '--request-timeout=15s'], check=True, capture_output=True).stdout
    pods = [p['metadata']['name'] for p in json.loads(raw)['items'] if p.get('status', {}).get('phase') == 'Running' and not p['metadata'].get('deletionTimestamp')]
    if len(pods) != 2:
        raise RuntimeError(f'Expected two running cache replicas, found {len(pods)}')
    for pod in pods:
        process = subprocess.Popen(['kubectl', 'port-forward', '-n', 'seaweedfs', pod, ':8080', '--address', '127.0.0.1', '--pod-running-timeout=15s', '--request-timeout=15s'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            line = process.stdout.readline()
            if not line.startswith('Forwarding from 127.0.0.1:'):
                raise RuntimeError('Could not start loopback port-forward')
            port = int(line.split('127.0.0.1:', 1)[1].split(' ', 1)[0])
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError('port-forward exited')
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=.1):
                        break
                except OSError:
                    time.sleep(.1)
            first = fetch(port, args.path)
            if args.expect_missing or args.expect_private:
                expected = 404 if args.expect_missing else 403
                if first[0] != expected:
                    raise RuntimeError(f'{pod}: expected {expected}, got {first[0]}')
                print(pod, 'origin revocation verified:', expected)
                continue
            second = fetch(port, args.path)
            if first[0] != 200 or second[0] != 200 or first[2] != second[2] or second[1] != 'HIT':
                raise RuntimeError(f'{pod}: repeat hit and identical body not verified')
            if args.expect_body_sha256 and second[2] != args.expect_body_sha256:
                raise RuntimeError(f'{pod}: body does not match the current object')
            for path, headers in [(args.path + '?verification=1', {}), (args.path, {'Range': 'bytes=0-0'}), (args.path, {'Cookie': 'cache-verification=1'})]:
                status, cache, _ = fetch(port, path, headers)
                if cache != 'BYPASS' or status not in (200, 206):
                    raise RuntimeError(f'{pod}: query/range/cookie bypass not verified')
            print(pod, 'repeat HIT, identical body and query/range/cookie bypass verified')
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    main()
