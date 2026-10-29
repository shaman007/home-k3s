#!/usr/bin/env python3
"""Check a disposable cache-pilot fixture on every public Traefik replica.

Requires reconciled pilot manifests and an existing publicly readable fixture
with Cache-Control: public,max-age=30, restricted to /mastodon/cache-pilot/.
--purge clears only the pilot cache on every replica. --expect-missing checks
origin deletion after purge. No S3 credentials or deletion commands are used.
"""
import argparse
import hashlib
import http.client
import json
import socket
import ssl
import subprocess
import time

HOST = 's3.andreybondarenko.com'


class DirectTLS(http.client.HTTPSConnection):
    def connect(self):
        self.sock = self._context.wrap_socket(socket.create_connection(('127.0.0.1', self.port), timeout=10), server_hostname=self.host)


def fetch(port, path, method='GET'):
    conn = DirectTLS(HOST, port=port, timeout=10, context=ssl.create_default_context())
    try:
        conn.request(method, path, headers={'X-Mastodon-Cache-Pilot': '1'})
        response = conn.getresponse()
        body = response.read()
        return response.status, response.getheader('Cache-Status', ''), hashlib.sha256(body).hexdigest()
    finally:
        conn.close()


def wait_port(process, port):
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError('port-forward exited')
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError('port-forward did not become ready')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path', default='/mastodon/cache-pilot/fixture.txt')
    parser.add_argument('--purge', action='store_true')
    parser.add_argument('--expect-missing', action='store_true')
    args = parser.parse_args()
    if not args.path.startswith('/mastodon/cache-pilot/') or '?' in args.path:
        parser.error('Only query-free disposable /mastodon/cache-pilot/ fixtures are accepted')
    raw = subprocess.run(['kubectl', 'get', 'pods', '-n', 'traefik', '-l', 'app.kubernetes.io/instance=traefik-traefik', '-o', 'json', '--request-timeout=15s'], check=True, capture_output=True).stdout
    pods = [p['metadata']['name'] for p in json.loads(raw)['items'] if p.get('status', {}).get('phase') == 'Running' and not p['metadata'].get('deletionTimestamp')]
    if not pods:
        raise RuntimeError('No running public Traefik replicas')
    for pod in pods:
        # Kubernetes chooses an available local port; no fixed-port collision.
        process = subprocess.Popen(['kubectl', 'port-forward', '-n', 'traefik', pod, ':443', '--address', '127.0.0.1', '--pod-running-timeout=15s', '--request-timeout=15s'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            line = process.stdout.readline()
            if not line.startswith('Forwarding from 127.0.0.1:'):
                raise RuntimeError('Could not start loopback port-forward')
            port = int(line.split('127.0.0.1:', 1)[1].split(' ', 1)[0])
            wait_port(process, port)
            if args.purge:
                status, _, _ = fetch(port, '/souin-api/__mastodon_cache_pilot/flush', 'PURGE')
                if status != 204:
                    raise RuntimeError(f'{pod}: purge returned {status}')
            first = fetch(port, args.path)
            if args.expect_missing:
                if first[0] not in (403, 404):
                    raise RuntimeError(f'{pod}: deleted/restricted fixture still served ({first[0]})')
                print(pod, 'deleted/restricted fixture unavailable:', first[0])
                continue
            if args.purge and 'hit' in first[1].lower():
                raise RuntimeError(f'{pod}: fixture still a cache hit immediately after purge')
            second = fetch(port, args.path)
            if first[0] != 200 or second[0] != 200 or first[2] != second[2] or 'hit' not in second[1].lower():
                raise RuntimeError(f'{pod}: no verified repeat cache hit')
            print(pod, 'repeat hit verified; identical body; Cache-Status:', second[1])
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    main()
