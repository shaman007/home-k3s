#!/usr/bin/env python3
"""Verify dual listeners and projected Secret rotation on an isolated OpenBao binary.

No cluster access, production credentials, initialization or unseal is performed.
The server uses in-memory storage and loopback-only listeners, then is terminated.
"""
import argparse
import hashlib
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import time

HOSTNAME = 'openbao-api.int.andreybondarenko.com'

def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def certificate(directory):
    directory.mkdir()
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                    '-subj', '/CN=' + HOSTNAME, '-addext', 'subjectAltName=DNS:' + HOSTNAME,
                    '-days', '1', '-keyout', str(directory/'tls.key'),
                    '-out', str(directory/'tls.crt')], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert((directory/'tls.crt').read_text())).hexdigest()


def fingerprint(context, port):
    with socket.create_connection(('127.0.0.1', port), timeout=2) as connection:
        with context.wrap_socket(connection, server_hostname=HOSTNAME) as tls:
            return hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='openbao-tls-fixture-', dir='/tmp') as temporary:
        root = Path(temporary)
        first = certificate(root/'first')
        second = certificate(root/'second')
        (root/'current').symlink_to(root/'first', target_is_directory=True)
        trust = root/'trust.pem'
        trust.write_text((root/'first/tls.crt').read_text() + (root/'second/tls.crt').read_text())
        context = ssl.create_default_context(cafile=str(trust))
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        old_port, new_port = free_port(), free_port()
        config = root/'server.hcl'
        config.write_text(f'''disable_mlock = true
api_addr = "https://127.0.0.1:{old_port}"
cluster_addr = "https://127.0.0.1:{free_port()}"
storage "inmem" {{}}
listener "tcp" {{
 address = "127.0.0.1:{old_port}"
 tls_cert_file = "{root}/first/tls.crt"
 tls_key_file = "{root}/first/tls.key"
 tls_disable_client_certs = true
}}
listener "tcp" {{
 address = "127.0.0.1:{new_port}"
 tls_cert_file = "{root}/current/tls.crt"
 tls_key_file = "{root}/current/tls.key"
 tls_disable_client_certs = true
 tls_auto_reload = true
 tls_auto_reload_interval = "5s"
}}
''')
        with (root/'server.log').open('w+') as log:
            process = subprocess.Popen([str(args.binary.resolve()), 'server', '-config=' + str(config)],
                                       stdout=log, stderr=log,
                                       env={k:v for k,v in os.environ.items() if not k.startswith(('VAULT_', 'BAO_'))})
            try:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError('Fixture server exited before becoming ready')
                    try:
                        if fingerprint(context, old_port) == first and fingerprint(context, new_port) == first:
                            break
                    except (OSError, ssl.SSLError):
                        pass
                    time.sleep(0.2)
                else:
                    raise RuntimeError('Dual TLS listeners did not become ready')
                (root/'next').symlink_to(root/'second', target_is_directory=True)
                (root/'next').replace(root/'current')
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if fingerprint(context, new_port) == second:
                        break
                    time.sleep(0.5)
                else:
                    raise RuntimeError('Projected certificate rotation was not reloaded')
                assert fingerprint(context, old_port) == first, 'Original listener changed unexpectedly'
                assert process.poll() is None, 'Server exited after reload'
                print('PASS: dual listeners, hostname verification, projected-file rotation, automatic reload, original listener preserved')
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

if __name__ == '__main__':
    main()
