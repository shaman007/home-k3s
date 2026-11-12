#!/usr/bin/env python3
"""Verify BOTH live TLS listeners of every OpenBao Pod through loopback forwards."""
import argparse
import hashlib
import http.client
import json
from pathlib import Path
import socket
import ssl
import subprocess
import time


def probe(ca_file, hostname, expected_fingerprint=None):
    context = ssl.create_default_context(cafile=str(ca_file))
    pods = json.loads(subprocess.check_output(['kubectl', 'get', 'pods', '-n', 'openbao',
        '-l', 'app.kubernetes.io/name=openbao,component=server', '-o', 'json',
        '--context=admin@home-k8s', '--request-timeout=15s']))['items']
    if len(pods) != 3:
        raise RuntimeError('Expected three OpenBao Pods')
    observations = []
    for pod in pods:
        process = subprocess.Popen(['kubectl', 'port-forward', '-n', 'openbao',
            'pod/' + pod['metadata']['name'], '18200:8200', '18202:8202',
            '--address=127.0.0.1', '--context=admin@home-k8s'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(50):
                if process.poll() is not None:
                    raise RuntimeError('Port forward exited')
                try:
                    with socket.create_connection(('127.0.0.1', 18200), timeout=0.1):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError('Port forward did not become ready')
            for port in (18200, 18202):
                with socket.create_connection(('127.0.0.1', port), timeout=5) as plain:
                    with context.wrap_socket(plain, server_hostname=hostname) as tls:
                        fingerprint = hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest()
                        if expected_fingerprint and fingerprint != expected_fingerprint:
                            raise RuntimeError('Listener has not loaded expected certificate: ' + pod['metadata']['name'])
                        tls.sendall(('GET /v1/sys/health?standbyok=true HTTP/1.1\r\nHost: ' +
                                     hostname + '\r\nConnection: close\r\n\r\n').encode())
                        response = http.client.HTTPResponse(tls)
                        response.begin()
                        health = json.loads(response.read())
                        if response.status != 200 or health.get('sealed') or not health.get('initialized'):
                            raise RuntimeError('OpenBao health is not ready')
                        observations.append({'pod': pod['metadata']['name'], 'uid': pod['metadata']['uid'],
                            'listener': port - 10000, 'sha256': fingerprint,
                            'sealed': health['sealed'], 'standby': health['standby'],
                            'raft_applied_index': health.get('raft_applied_index')})
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    return observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ca-file', required=True, type=Path)
    parser.add_argument('--hostname', default='openbao-api.int.andreybondarenko.com')
    parser.add_argument('--expected-sha256')
    args = parser.parse_args()
    print(json.dumps(probe(args.ca_file, args.hostname, args.expected_sha256), indent=2))


if __name__ == '__main__':
    main()
