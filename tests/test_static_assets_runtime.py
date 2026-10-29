"""Exercise the real WordPress/Nextcloud NGINX configurations with fake PHP.

STATIC_NGINX_BINARY=/path/to/nginx python3 -m unittest tests.test_static_assets_runtime
Requires gzip and add_header_inherit (NGINX >= 1.29.3). All files and servers are
isolated under a temporary directory; no real application data is used.
"""
import gzip
import http.client
import os
from pathlib import Path
import shutil
import socket
import socketserver
import struct
import subprocess
import tempfile
import threading
import time
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
BINARY = os.environ.get('STATIC_NGINX_BINARY')
SOURCE = Path(os.environ.get('STATIC_NGINX_SOURCE', '/tmp/nginx-1.31.8'))
CSS = b'body { color: #123456; background: white; }\n' * 300
JS = b'const example = "public application asset";\n' * 300


def receive(stream, length):
    result = b''
    while len(result) < length:
        part = stream.recv(length - len(result))
        if not part:
            raise ConnectionError('Incomplete FastCGI record')
        result += part
    return result


class PHP(socketserver.BaseRequestHandler):
    def handle(self):
        while True:
            version, kind, request_id, length, padding, _ = struct.unpack('!BBHHBB', receive(self.request, 8))
            receive(self.request, length + padding)
            if kind == 5 and not length:
                break
        body = b'private PHP response'
        payload = b'Content-Type: text/plain\r\nCache-Control: private, no-store\r\nX-Test-PHP: yes\r\n\r\n' + body
        for kind, data in [(6, payload), (6, b''), (3, struct.pack('!IB3s', 0, 0, b'\0\0\0'))]:
            self.request.sendall(struct.pack('!BBHHBB', 1, kind, request_id, len(data), 0, 0) + data)


class PHPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


@unittest.skipUnless(BINARY, 'Set STATIC_NGINX_BINARY to exercise real static asset behavior')
class StaticAssetsRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='static-assets-')
        cls.base = Path(cls.temp.name)
        cls.php = PHPServer(('127.0.0.1', 0), PHP)
        threading.Thread(target=cls.php.serve_forever, daemon=True).start()
        cls.processes, cls.logs, cls.ports = [], [], {}
        try:
            for app, config_file, root_path in [
                ('wordpress', 'wordpress/config-map-nginx-config.yaml', '/code'),
                ('nextcloud', 'nextcloud/config-map-nextcloud-config.yaml', '/nextcloud'),
            ]:
                directory = cls.base / app
                directory.mkdir()
                public = directory / 'public'
                public.mkdir()
                fixtures = {
                    'index.php': b'PHP fixture', 'remote.php': b'PHP fixture',
                    'wp-admin/admin.php': b'PHP fixture',
                    'styles/main.css': CSS, 'scripts/main.js': JS,
                    'scripts/module.mjs': JS, 'fonts/sample.woff2': b'font-data',
                    'fonts/sample.ttf': b'ttf-data', 'images/sample.webp': b'webp-data',
                    'images/sample.avif': b'avif-data', 'images/sample.jpeg': b'jpeg-data',
                    'data/user/files/private.png': b'NEVER SERVE',
                    'config/secret.css': b'NEVER SERVE', '.private/secret.js': b'NEVER SERVE',
                    'lib/secret.js': b'NEVER SERVE', '3rdparty/secret.css': b'NEVER SERVE',
                }
                for path, body in fixtures.items():
                    target = public / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(body)
                shutil.copy(SOURCE / 'conf/fastcgi_params', directory / 'fastcgi_params')
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1', 0))
                    port = sock.getsockname()[1]
                text = yaml.safe_load((ROOT / config_file).read_text())['data']['config']
                text = text.replace('listen 8080;', f'listen 127.0.0.1:{port};')
                text = text.replace('root ' + root_path + ';', 'root ' + str(public) + ';')
                text = text.replace('127.0.0.1:9000', '127.0.0.1:' + str(cls.php.server_address[1]))
                text = text.replace('/var/log/nginx/', str(directory) + '/')
                config = ('worker_processes 1;\npid ' + str(directory / 'nginx.pid') + ';\n'
                          'events {}\nhttp {\ninclude ' + str(SOURCE / 'conf/mime.types') + ';\n' + text + '\n}\n')
                path = directory / 'nginx.conf'
                path.write_text(config)
                log = (directory / 'process.log').open('w+')
                cls.logs.append(log)
                check = subprocess.run([BINARY, '-e', 'stderr', '-t', '-p', str(directory), '-c', str(path)], capture_output=True, text=True)
                if check.returncode:
                    raise RuntimeError(check.stderr)
                process = subprocess.Popen([BINARY, '-e', 'stderr', '-p', str(directory), '-c', str(path), '-g', 'daemon off;'], stdout=log, stderr=log)
                cls.processes.append(process)
                cls.ports[app] = port
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError((directory / 'process.log').read_text())
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=.1):
                            break
                    except OSError:
                        time.sleep(.05)
                else:
                    raise RuntimeError('NGINX startup timeout')
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        for process in cls.processes:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for log in cls.logs:
            log.close()
        cls.php.shutdown()
        cls.php.server_close()
        cls.temp.cleanup()

    def get(self, app, path, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.ports[app], timeout=5)
        try:
            connection.request('GET', path, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.headers, response.read()
        finally:
            connection.close()

    def test_wordpress_cache_lifetimes_and_csp(self):
        for query, expected in [('', 'public, max-age=3600'), ('?ver=1.2.3', 'public, max-age=604800')]:
            status, headers, _ = self.get('wordpress', '/styles/main.css' + query)
            self.assertEqual(200, status)
            self.assertEqual([expected], headers.get_all('Cache-Control'))
            self.assertIn('upgrade-insecure-requests', headers['Content-Security-Policy'])
            self.assertNotIn('immutable', headers['Cache-Control'])

    def test_nextcloud_lifetimes_and_security_headers(self):
        for path, expected in [('/styles/main.css', 'public, max-age=15778463'),
                ('/styles/main.css?v=hash', 'public, max-age=15778463, immutable'),
                ('/fonts/sample.woff2', 'public, max-age=604800'),
                ('/fonts/sample.ttf?v=hash', 'public, max-age=15778463, immutable')]:
            status, headers, _ = self.get('nextcloud', path)
            self.assertEqual(200, status)
            self.assertEqual([expected], headers.get_all('Cache-Control'))
            for name in ['Referrer-Policy', 'X-Content-Type-Options', 'X-Download-Options', 'X-Frame-Options', 'X-Permitted-Cross-Domain-Policies', 'X-Robots-Tag', 'X-XSS-Protection']:
                self.assertIsNotNone(headers[name], name)

    def test_gzip_is_negotiated_and_content_is_identical(self):
        for app in self.ports:
            for path, original in [('/styles/main.css', CSS), ('/scripts/main.js', JS)]:
                status, headers, encoded = self.get(app, path, {'Accept-Encoding': 'gzip'})
                self.assertEqual(200, status)
                self.assertEqual('gzip', headers['Content-Encoding'])
                self.assertIn('Accept-Encoding', headers['Vary'])
                self.assertEqual(original, gzip.decompress(encoded))
                self.assertLess(len(encoded), len(original))
                _, plain_headers, plain = self.get(app, path)
                self.assertIsNone(plain_headers['Content-Encoding'])
                self.assertEqual(original, plain)

    def test_etag_revalidation_returns_304(self):
        for app in self.ports:
            _, headers, _ = self.get(app, '/styles/main.css')
            self.assertIsNotNone(headers['ETag'])
            status, _, body = self.get(app, '/styles/main.css', {'If-None-Match': headers['ETag']})
            self.assertEqual(304, status)
            self.assertEqual(b'', body)

    def test_php_and_missing_assets_keep_private_php_responses(self):
        for app in self.ports:
            paths = ['/index.php', '/images/not-present.png', '/scripts/not-present.js']
            paths += ['/wp-admin/admin.php'] if app == 'wordpress' else ['/remote.php/dav/files/user/private.png']
            for path in paths:
                status, headers, body = self.get(app, path)
                self.assertEqual(200, status, (app, path))
                self.assertEqual('yes', headers['X-Test-PHP'], (app, path))
                self.assertEqual(['private, no-store'], headers.get_all('Cache-Control'), (app, path))
                self.assertEqual(b'private PHP response', body)

    def test_nextcloud_private_physical_files_remain_denied(self):
        for path in ['/data/user/files/private.png', '/config/secret.css', '/.private/secret.js', '/lib/secret.js', '/3rdparty/secret.css']:
            status, headers, body = self.get('nextcloud', path)
            self.assertEqual(404, status, path)
            self.assertNotIn(b'NEVER SERVE', body)
            self.assertIsNone(headers['Cache-Control'])

    def test_modern_static_assets_have_cache_policy_and_mjs_mime(self):
        for app in self.ports:
            for path in ['/images/sample.webp', '/images/sample.avif', '/images/sample.jpeg', '/fonts/sample.ttf']:
                status, headers, _ = self.get(app, path)
                self.assertEqual(200, status)
                self.assertIn('public, max-age=', headers['Cache-Control'])
            status, headers, _ = self.get(app, '/scripts/module.mjs')
            self.assertEqual(200, status)
            self.assertEqual('text/javascript', headers['Content-Type'])
            self.assertIn('public, max-age=', headers['Cache-Control'])
