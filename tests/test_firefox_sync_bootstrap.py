"""Exercise Firefox Sync secret bootstrap and scoped authentication prerequisites."""

import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

SPEC = importlib.util.spec_from_file_location(
    'firefox_sync_bootstrap', Path(__file__).parents[1] / 'tools/firefox-sync/bootstrap-secrets.py')
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class Response:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.data).encode()


class BootstrapTests(unittest.TestCase):
    def run_bootstrap(self, handler, token='hvs.fake-test-token\nnot-a-token\n'):
        with tempfile.TemporaryDirectory() as directory:
            token_path = Path(directory) / 'token'
            token_path.write_text(token)
            with patch.object(bootstrap, 'TOKEN_FILE', token_path), \
                    patch('sys.argv', ['bootstrap', '--execute']), \
                    patch.object(bootstrap.urllib.request, 'urlopen', side_effect=handler), \
                    redirect_stdout(io.StringIO()) as output:
                bootstrap.main()
                return output.getvalue()

    def test_plan_has_no_network_access(self):
        with patch('sys.argv', ['bootstrap']), \
                patch.object(bootstrap.urllib.request, 'urlopen') as request, \
                redirect_stdout(io.StringIO()):
            bootstrap.main()
            request.assert_not_called()

    def test_preserves_existing_credentials_and_selects_only_token_line(self):
        seen = []
        existing = {key: 'preserve-test-secret' for key in bootstrap.KEYS}

        def handler(request, **kwargs):
            self.assertEqual(request.get_header('X-vault-token'), 'hvs.fake-test-token')
            seen.append((request.method, request.full_url))
            return Response({'data': {'data': existing}} if request.method == 'GET' else {})

        output = self.run_bootstrap(handler)
        self.assertNotIn('preserve-test-secret', output)
        self.assertNotIn('hvs.fake-test-token', output)
        self.assertEqual([method for method, url in seen if '/kv/data/' in url], ['GET'])
        self.assertEqual(len(seen), 3)

    def test_refuses_partial_existing_secret_without_writing(self):
        calls = []

        def handler(request, **kwargs):
            calls.append(request.method)
            return Response({'data': {'data': {'MYSQL_PASSWORD': 'existing'}}})

        with self.assertRaisesRegex(RuntimeError, 'refusing to overwrite'):
            self.run_bootstrap(handler)
        self.assertEqual(calls, ['GET'])

    def test_transport_failure_cannot_expose_token_in_exception(self):
        def handler(request, **kwargs):
            raise ValueError('invalid header hvs.fake-test-token')

        with self.assertRaises(RuntimeError) as error:
            self.run_bootstrap(handler)
        self.assertNotIn('hvs.fake-test-token', str(error.exception))
        self.assertIsNone(error.exception.__cause__)
        self.assertTrue(error.exception.__suppress_context__)


if __name__ == '__main__':
    unittest.main()
