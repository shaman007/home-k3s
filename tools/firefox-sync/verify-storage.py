#!/usr/bin/env python3
"""Run an isolated authenticated Sync storage round trip through a local tunnel or the public HTTPS endpoint.

This checks Hawk authentication and persistence, not Mozilla sign-in or Firefox clients.
Creates and deletes only a fresh synthetic user's data. Never prints credentials.
"""
import argparse
import base64
import hashlib
import hmac
import json
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:18000')
    args = parser.parse_args()
    origin = urllib.parse.urlsplit(args.url)
    local = origin.scheme == 'http' and origin.hostname in ('127.0.0.1', 'localhost')
    public = origin.scheme == 'https' and origin.hostname == 'sync.andreybondarenko.com' and origin.port in (None, 443)
    if not (local or public) or origin.username or origin.password or origin.path or origin.query or origin.fragment:
        parser.error('Use a local HTTP tunnel or https://sync.andreybondarenko.com')
    data = json.loads(subprocess.check_output(
        ['kubectl', 'get', 'secret', 'firefox-sync-env', '-n', 'firefox-sync', '-o', 'json']))
    master = base64.b64decode(data['data']['SYNC_MASTER_SECRET'])

    def hkdf(info, salt=None):
        prk = hmac.new(salt or bytes(32), master, hashlib.sha256).digest()
        return hmac.new(prk, info + b'\x01', hashlib.sha256).digest()

    # Reserved high range, independent from the tokenserver's sequential enrollment IDs.
    uid = 4_000_000_000 + secrets.randbelow(1_000_000)
    salt = secrets.token_hex(6)
    payload = json.dumps({'uid': uid, 'node': args.url, 'expires': time.time() + 120,
                          'salt': salt, 'fxa_uid': secrets.token_hex(16),
                          'fxa_kid': secrets.token_hex(16)}, separators=(',', ':')).encode()
    signing_key = hkdf(b'services.mozilla.com/tokenlib/v1/signing')
    token = base64.urlsafe_b64encode(payload + hmac.new(signing_key, payload, hashlib.sha256).digest()).decode()
    key = base64.urlsafe_b64encode(hkdf(
        ('services.mozilla.com/tokenlib/v1/derive/' + token).encode(), salt.encode()))
    base = f'/1.5/{uid}'

    def request(method, path, body=None):
        body_bytes = None if body is None else json.dumps(body).encode()
        ts = str(int(time.time()))
        nonce = secrets.token_hex(6)
        content_type = 'application/json'
        digest = ''
        if body_bytes is not None:
            digest = base64.b64encode(hashlib.sha256(
                b'hawk.1.payload\n' + content_type.encode() + b'\n' + body_bytes + b'\n').digest()).decode()
        normalized = '\n'.join(['hawk.1.header', ts, nonce, method, path,
                                 origin.hostname, str(origin.port or (443 if origin.scheme == 'https' else 80)), digest, '', ''])
        mac = base64.b64encode(hmac.new(key, normalized.encode(), hashlib.sha256).digest()).decode()
        authorization = f'Hawk id="{token}", ts="{ts}", nonce="{nonce}", mac="{mac}"'
        if digest:
            authorization += f', hash="{digest}"'
        req = urllib.request.Request(args.url + path, data=body_bytes, method=method,
            headers={'Authorization': authorization, 'Content-Type': content_type,
                     'X-Confirm-Delete': '1'})
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'{method} {path}: HTTP {error.code}') from None
        except Exception:
            raise RuntimeError(f'{method} {path}: transport failure (details suppressed)') from None

    status, body = request('GET', base + '/info/collections')
    if status != 200 or json.loads(body) != {}:
        raise RuntimeError('Synthetic user already contains data; refusing to write or delete')
    written = False
    try:
        record = {'id': 'bootstrap-smoke', 'payload': secrets.token_hex(24)}
        # Mark before the write, so an ambiguous response still triggers cleanup.
        written = True
        status, _ = request('PUT', base + '/storage/bookmarks/bootstrap-smoke', record)
        if status != 200:
            raise RuntimeError('Storage write did not return HTTP 200')
        status, body = request('GET', base + '/storage/bookmarks/bootstrap-smoke')
        actual = json.loads(body)
        if status != 200 or actual.get('payload') != record['payload']:
            raise RuntimeError('Storage read did not match the written payload')
        print('Authenticated Hawk storage write/read matched.')
    finally:
        if written:
            request('DELETE', base + '/storage')
            status, body = request('GET', base + '/info/collections')
            if status != 200 or json.loads(body) != {}:
                raise RuntimeError('Synthetic-user cleanup could not be verified')
            print('Synthetic-user storage cleanup verified.')


if __name__ == '__main__':
    main()
