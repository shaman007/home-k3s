"""Behavior tests for the actual production NGINX configuration.

Run with NGINX_BINARY=/path/to/nginx python3 -m unittest tests.test_media_cache_runtime.
The binary must include http_auth_request and rewrite modules. No containers,
cluster mutations, real media, or S3 credentials are used.
"""
import http.client
import http.server
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.parse
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[1]
BINARY = os.environ.get('NGINX_BINARY')


class Origin(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    objects = {}
    heads = 0

    def log_message(self, *_):
        pass

    def respond(self, head=False):
        parsed = urllib.parse.urlsplit(self.path)
        item = self.objects.get(parsed.path)
        signed = bool(self.headers.get('Authorization') or 'X-Amz-Signature=' in parsed.query)
        status = 404 if item is None else item.get('status', 200)
        if signed and item:
            status = 200
        body = b'missing' if item is None else item['body']
        if item and self.headers.get('If-None-Match') and self.headers.get('If-None-Match') == item.get('etag'):
            status, body = 304, b''
        if item and self.headers.get('Range'):
            status, body = 206, body[:1]
        self.send_response(status)
        if not (head and item and item.get('omit_head_length')):
            self.send_header('Content-Length', str(item.get('head_length', len(body)) if head and item else len(body)))
        if item:
            if item.get('etag'):
                self.send_header('ETag', item.get('head_etag', item['etag']) if head else item['etag'])
            self.send_header('Content-Type', item.get('content_type', 'application/octet-stream'))
            if item.get('cache_control'):
                self.send_header('Cache-Control', item.get('head_control', item['cache_control']) if head else item['cache_control'])
            if item.get('set_cookie'):
                self.send_header('Set-Cookie', 'test=value')
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def do_HEAD(self):
        type(self).heads += 1
        self.respond(head=True)

    def do_GET(self):
        self.respond()


@unittest.skipUnless(BINARY, 'Set NGINX_BINARY to run real proxy behavior tests')
class MediaCacheRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='media-cache-test-')
        cls.directory = Path(cls.temp.name)
        cls.origin = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Origin)
        cls.origin.daemon_threads = True
        threading.Thread(target=cls.origin.serve_forever, daemon=True).start()
        config = next(d['data']['nginx.conf'] for d in yaml.safe_load_all(
            (ROOT / 'seaweedfs/media-cache.yaml').read_text()) if d and d['kind'] == 'ConfigMap')
        cls.ports, cls.processes, cls.logs = [], [], []
        try:
            for replica in range(2):
                directory = cls.directory / str(replica)
                directory.mkdir()
                (directory / 'cache').mkdir()
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1', 0))
                    port = sock.getsockname()[1]
                text = config.replace('listen 8080;', f'listen 127.0.0.1:{port};')
                text = text.replace('s3.seaweedfs.svc.cluster.local:8333', f'127.0.0.1:{cls.origin.server_port}')
                text = text.replace('/var/cache/nginx/media', str(directory / 'cache'))
                text = text.replace('/tmp/nginx.pid', str(directory / 'nginx.pid'))
                text = text.replace('/tmp/client', str(directory / 'client')).replace('/tmp/proxy', str(directory / 'proxy'))
                (directory / 'nginx.conf').write_text(text)
                log = (directory / 'log').open('w+')
                cls.logs.append(log)
                result = subprocess.run([BINARY, '-e', 'stderr', '-t', '-p', str(directory), '-c', str(directory / 'nginx.conf')], capture_output=True, text=True)
                if result.returncode:
                    raise RuntimeError(result.stderr)
                process = subprocess.Popen([BINARY, '-e', 'stderr', '-p', str(directory), '-c', str(directory / 'nginx.conf'), '-g', 'daemon off;'], stdout=log, stderr=log)
                cls.processes.append(process)
                cls.ports.append(port)
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError('Proxy exited; ' + (directory / 'log').read_text())
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=.1):
                            break
                    except OSError:
                        time.sleep(.05)
                else:
                    raise RuntimeError('Proxy startup timeout')
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
        cls.origin.shutdown()
        cls.origin.server_close()
        cls.temp.cleanup()

    def fixture(self, **extra):
        path = '/mastodon/test/' + uuid.uuid4().hex
        Origin.objects[path] = {'body': b'original media', 'etag': '"version-one"', 'cache_control': 'public,max-age=3600', **extra}
        return path

    def get(self, port, path, headers=None, method='GET'):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        try:
            connection.request(method, path, headers={'Host': 's3.andreybondarenko.com', **(headers or {})})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def warm(self, path):
        for port in self.ports:
            first = self.get(port, path)
            second = self.get(port, path)
            self.assertEqual(200, first[0])
            self.assertEqual('HIT', second[1].get('X-Media-Cache'))
            self.assertEqual(first[2], second[2])
            self.assertEqual('private, no-cache', second[1].get('Cache-Control'))

    def test_deleted_object_unavailable_on_both_replicas_without_purge(self):
        path = self.fixture()
        self.warm(path)
        del Origin.objects[path]
        for port in self.ports:
            self.assertEqual(404, self.get(port, path)[0])

    def test_acl_change_denies_warm_caches_without_purge(self):
        path = self.fixture()
        self.warm(path)
        Origin.objects[path]['status'] = 403
        for port in self.ports:
            self.assertEqual(403, self.get(port, path)[0])

    def test_replacement_selects_new_body_on_both_replicas(self):
        path = self.fixture()
        self.warm(path)
        Origin.objects[path].update(body=b'new media', etag='"version-two"')
        for port in self.ports:
            response = self.get(port, path)
            self.assertEqual(b'new media', response[2])
            self.assertEqual('MISS', response[1].get('X-Media-Cache'))
            self.assertEqual('HIT', self.get(port, path)[1].get('X-Media-Cache'))

    def test_origin_failure_never_serves_cached_content(self):
        path = self.fixture()
        self.warm(path)
        Origin.objects[path]['status'] = 503
        for port in self.ports:
            self.assertEqual(503, self.get(port, path)[0])

    def test_signed_cookie_query_range_head_and_conditional_bypass(self):
        path = self.fixture()
        self.warm(path)
        for port in self.ports:
            for suffix, headers, method in [('', {'Authorization': 'AWS4-HMAC-SHA256 test'}, 'GET'),
                    ('', {'Cookie': 'session=value'}, 'GET'), ('?X-Amz-Signature=test', {}, 'GET'),
                    ('?other=value', {}, 'GET'), ('', {'Range': 'bytes=0-0'}, 'GET'),
                    ('', {'If-None-Match': '"version-one"'}, 'GET'), ('', {}, 'HEAD')]:
                before = Origin.heads
                response = self.get(port, path + suffix, headers, method)
                self.assertEqual('BYPASS', response[1].get('X-Media-Cache'))
                self.assertEqual(before + (method == 'HEAD'), Origin.heads)
        Origin.objects[path]['status'] = 403
        self.assertEqual(200, self.get(self.ports[0], path, {'Authorization': 'AWS4-HMAC-SHA256 test'})[0])
        self.assertEqual(200, self.get(self.ports[0], path + '?X-Amz-Signature=test')[0])

    def test_unsafe_responses_are_not_stored(self):
        for extra in [{'etag': None}, {'omit_head_length': True}, {'head_length': 10_000_000},
                {'cache_control': 'private,max-age=3600'}, {'cache_control': 'no-store'},
                {'set_cookie': True}, {'head_etag': '"concurrent-old-version"'},
                {'cache_control': 'public,max-age=60', 'head_control': 'public,max-age=3600'}]:
            path = self.fixture(**extra)
            for port in self.ports:
                self.get(port, path)
                second = self.get(port, path)
                self.assertEqual(200, second[0], extra)
                self.assertNotEqual('HIT', second[1].get('X-Media-Cache'), extra)

    def test_no_public_admin_api_or_other_bucket(self):
        for port in self.ports:
            for path in ['/souin-api/__mastodon_cache_pilot/flush', '/__origin_head', '/other-bucket/object']:
                self.assertIn(self.get(port, path)[0], (403, 404))

    def test_cache_policy_and_content_type_changes_with_same_etag(self):
        path = self.fixture()
        self.warm(path)
        Origin.objects[path]['content_type'] = 'image/png'
        for port in self.ports:
            response = self.get(port, path)
            self.assertEqual('image/png', response[1].get('Content-Type'))
            self.assertEqual('MISS', response[1].get('X-Media-Cache'))
        Origin.objects[path]['cache_control'] = 'no-store'
        for port in self.ports:
            response = self.get(port, path)
            self.assertEqual('BYPASS', response[1].get('X-Media-Cache'))
            self.assertEqual('private, no-store', response[1].get('Cache-Control'))
