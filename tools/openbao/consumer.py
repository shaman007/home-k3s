"""Scoped recovery consumers: encrypted archives and memory-only credentials."""
import argparse
import base64
import contextlib
import json
import os
import pathlib
import re
import select
import subprocess  # nosec B404
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from recovery import RecoveryError, recover_kv, supplemental_secrets

ROOT = pathlib.Path(__file__).resolve().parents[2]
RECOVERY = pathlib.Path.home() / '.local/state/openbao-recovery'
IDENTITY = pathlib.Path.home() / '.config/talos-backup/age-key.txt'
RECIPIENT = pathlib.Path.home() / '.config/talos-backup/age-recipient.txt'
INITIAL = RECOVERY / 'openbao-new-initialization-2026-11-16.json.age'
MIRROR = RECOVERY / 'kubernetes-secrets-2026-11-16.age'
CA = RECOVERY / 'openbao-backend-ca.crt'


def command(args, *, data=None, env=None, allowed=(0,)):
    """Capture output; never forward secret-bearing CLI stdout or stderr."""
    result = subprocess.run(args, input=data, capture_output=True, env=env)
    if result.returncode not in allowed:
        raise RecoveryError(f'{args[0]} operation failed (exit {result.returncode}); output withheld')
    return result


def decrypt(path):
    """Decode an explicitly authorized encrypted archive only in memory."""
    return json.loads(command(['age', '-d', '-i', str(IDENTITY), str(path)]).stdout)


def encrypt_new(path, document):
    """Never overwrite original recovery material or create plaintext files."""
    if path.exists():
        raise RecoveryError('Refusing to overwrite the initialization archive')
    command(['age', '-R', str(RECIPIENT), '-o', str(path)], data=json.dumps(document).encode())
    path.chmod(0o600)
    if decrypt(path) != document:
        raise RecoveryError('Initialization archive verification failed')


def kube(resource, namespace, name):
    """Read one selected resource into the authorized consumer."""
    return json.loads(command(['kubectl', 'get', resource, name, '-n', namespace, '-o', 'json']).stdout)


@contextlib.contextmanager
def pod_connection(pod):
    """Verify ownership of a random pod-specific forward before sending a key."""
    secret = kube('secret', 'openbao', 'openbao-server-letsencrypt-tls')
    CA.write_bytes(base64.b64decode(secret['data']['ca.crt']))
    CA.chmod(0o600)
    forward = subprocess.Popen(['kubectl', 'port-forward', '-n', 'openbao', 'pod/' + pod, ':8200', '--address', '127.0.0.1'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        if not select.select([forward.stdout], [], [], 20)[0]:
            raise RecoveryError('Owned port-forward did not start')
        line = forward.stdout.readline()
        match = re.fullmatch(r'Forwarding from 127\.0\.0\.1:(\d+) -> 8200\n', line)
        if not match or forward.poll() is not None:
            raise RecoveryError('Could not verify ownership of pod forwarding')
        # Drain routine connection messages so a long apply cannot fill the pipe.
        threading.Thread(target=lambda: list(forward.stdout), daemon=True).start()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith(('VAULT_', 'BAO_', 'TF_VAR_', 'TF_LOG')):
                env.pop(key, None)
        env.update({'VAULT_ADDR': 'https://127.0.0.1:' + match.group(1), 'VAULT_CACERT': str(CA), 'VAULT_TLS_SERVER_NAME': 'openbao-api.int.andreybondarenko.com', 'VAULT_TOKEN': ''})
        yield env
    finally:
        forward.terminate()
        try:
            forward.wait(timeout=5)
        except subprocess.TimeoutExpired:
            forward.kill()
            forward.wait()


def vault(env, verb, path, data=None):
    """Use the installed CLI with JSON stdin, never secret values in argv."""
    args = ['vault', verb, '-format=json', path]
    if data is not None:
        args.append('-')
    result = command(args, data=json.dumps(data).encode() if data is not None else None, env=env)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def keycloak_client():
    """Read the surviving OIDC client with scoped Keycloak admin credentials."""
    secret = kube('secret', 'keycloak', 'keycloak-admin')['data']
    credentials = {key: base64.b64decode(secret[key]).decode() for key in ('username', 'password')}
    base = 'https://sso.andreybondarenko.com'
    body = urllib.parse.urlencode({'client_id': 'admin-cli', 'grant_type': 'password', **credentials}).encode()
    request = urllib.request.Request(base + '/realms/master/protocol/openid-connect/token', data=body)
    with urllib.request.urlopen(request, timeout=20) as response:
        token = json.load(response)['access_token']
    def read(path):
        request = urllib.request.Request(base + '/admin/realms/master/' + path, headers={'Authorization': 'Bearer ' + token})
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    clients = read('clients?clientId=openbao')
    if len(clients) != 1 or not clients[0].get('enabled'):
        raise RecoveryError('Expected one enabled existing OpenBao OIDC client')
    client = clients[0]
    client_secret = read('clients/' + client['id'] + '/client-secret')['value']
    contract = {key: client.get(key) for key in ('clientId', 'redirectUris', 'protocolMappers', 'publicClient', 'standardFlowEnabled', 'directAccessGrantsEnabled')}
    return contract, client_secret


def await_unsealed(env):
    """Raft join/unseal can complete asynchronously after the write response."""
    for _ in range(30):
        result = command(['vault', 'status', '-format=json'], env=env, allowed=(0, 2))
        if json.loads(result.stdout).get('sealed') is False:
            return True
        time.sleep(1)
    return False


def initialize(pod):
    """Initialize only a verified new, previously uninitialized recovery server."""
    if not pod.startswith('openbao-20261116-') or INITIAL.exists():
        raise RecoveryError('Initialization requires a new recovery pod and absent archive')
    with pod_connection(pod) as env:
        result = command(['vault', 'status', '-format=json'], env=env, allowed=(0, 2))
        if json.loads(result.stdout)['initialized']:
            raise RecoveryError('Refusing to initialize an existing server')
        material = json.loads(command(['vault', 'operator', 'init', '-format=json', '-key-shares=1', '-key-threshold=1'], env=env).stdout)
        encrypt_new(INITIAL, material)
        vault(env, 'write', 'sys/unseal', {'key': material['unseal_keys_b64'][0]})
        if not await_unsealed(env):
            raise RecoveryError('New server did not unseal with its verified archived key')
        print(json.dumps({'pod': pod, 'initialized': True, 'unsealed': True, 'encrypted_archive_verified': True}))


def unseal(pods):
    """Use only the new generation's matching encrypted unseal material."""
    material = decrypt(INITIAL)
    for pod in pods:
        if not pod.startswith('openbao-20261116-'):
            raise RecoveryError('Unseal restricted to the new recovery generation')
        with pod_connection(pod) as env:
            vault(env, 'write', 'sys/unseal', {'key': material['unseal_keys_b64'][0]})
            if not await_unsealed(env):
                raise RecoveryError('New replica unseal did not complete')
            print(json.dumps({'pod': pod, 'unsealed': True}), flush=True)


def configure(pod):
    """Apply reviewed IaC with an ephemeral/write-only OIDC client secret."""
    material = decrypt(INITIAL)
    contract, oidc_secret = keycloak_client()
    (ROOT / 'terraform/openbao/keycloak-client.json').write_text(json.dumps(contract, indent=2) + '\n')
    with pod_connection(pod) as env:
        env.update({'VAULT_TOKEN': material['root_token'], 'TF_VAR_openbao_address': env['VAULT_ADDR'], 'TF_VAR_openbao_ca_cert_file': str(CA), 'TF_VAR_openbao_tls_server_name': env['VAULT_TLS_SERVER_NAME'], 'TF_VAR_oidc_client_secret': oidc_secret})
        directory = RECOVERY / 'tofu'
        directory.mkdir(mode=0o700, exist_ok=True)
        state, plan = directory / 'terraform.tfstate', directory / 'rebuild.tfplan'
        command(['tofu', '-chdir=' + str(ROOT / 'terraform/openbao'), 'init', '-input=false', '-reconfigure', '-backend-config=path=' + str(state)], env=env)
        result = command(['tofu', '-chdir=' + str(ROOT / 'terraform/openbao'), 'plan', '-input=false', '-no-color', '-state=' + str(state), '-out=' + str(plan)], env=env)
        (directory / 'plan-summary.txt').write_bytes(result.stdout)
        document = json.loads(command(['tofu', '-chdir=' + str(ROOT / 'terraform/openbao'), 'show', '-json', str(plan)], env=env).stdout)
        changes = document.get('resource_changes', [])
        if any('delete' in item['change']['actions'] for item in changes):
            raise RecoveryError('Refusing a recovery plan containing destruction')
        if oidc_secret.encode() in plan.read_bytes() or oidc_secret in json.dumps(document):
            raise RecoveryError('OIDC secret detected in plan; application refused')
        command(['tofu', '-chdir=' + str(ROOT / 'terraform/openbao'), 'apply', '-input=false', '-no-color', str(plan)], env=env)
        for path in (state, pathlib.Path(str(state) + '.backup')):
            if path.exists():
                path.chmod(0o600)
                if oidc_secret in path.read_text() or material['root_token'] in path.read_text():
                    raise RecoveryError('Credential detected in state')
        vault(env, 'write', 'kv/data/openbao/oidc', {'data': {'client_id': 'openbao', 'client_secret': oidc_secret, 'discovery_url': 'https://sso.andreybondarenko.com/realms/master'}})
        print(json.dumps({'iac_applied': True, 'resources_planned': len(changes), 'secret_free_plan_and_state': True}))


def restore_kv(pod):
    """Restore known fields, then compare exact read-back only in memory."""
    material = decrypt(INITIAL)
    values, report = recover_kv(decrypt(MIRROR))
    if values.get('harbor', {}).get('user') == 'shaman007':
        values['desktop/harbor'] = {'value': values['harbor']['password']}
    with pod_connection(pod) as env:
        env['VAULT_TOKEN'] = material['root_token']
        for path, fields in sorted(values.items()):
            quoted = urllib.parse.quote(path, safe='/')
            vault(env, 'write', 'kv/data/' + quoted, {'data': fields})
            if vault(env, 'read', 'kv/data/' + quoted)['data']['data'] != fields:
                raise RecoveryError('KV read-back mismatch; values withheld')
        print(json.dumps({'kv_paths_restored_and_verified': len(values), 'external_secrets_covered': report['external_secrets_covered'], 'canonicalized_configurations': len(report['canonicalized_thanos_sources'])}))


def restore_supplemental(pod):
    """Preserve known unmapped application material without inventing old paths."""
    material = decrypt(INITIAL)
    values = supplemental_secrets(decrypt(MIRROR))
    with pod_connection(pod) as env:
        env['VAULT_TOKEN'] = material['root_token']
        for path, fields in sorted(values.items()):
            vault(env, 'write', 'kv/data/' + path, {'data': fields})
            if vault(env, 'read', 'kv/data/' + path)['data']['data'] != fields:
                raise RecoveryError('Supplemental read-back mismatch; values withheld')
    print(json.dumps({'supplemental_secrets_preserved_and_verified': len(values)}))


def snapshot(pod):
    """Encrypt a live Raft snapshot in memory, without a plaintext temp file."""
    material = decrypt(INITIAL)
    output = RECOVERY / 'openbao-rebuilt-2026-11-16.snap.age'
    if output.exists():
        raise RecoveryError('Refusing to overwrite the rebuilt snapshot')
    with pod_connection(pod) as env:
        # Connect using the validated public service name for TLS verification.
        request = urllib.request.Request('https://openbao.int.andreybondarenko.com/v1/sys/storage/raft/snapshot', headers={'X-Vault-Token': material['root_token']})
        with urllib.request.urlopen(request, timeout=60) as response:
            content = response.read()
        command(['age', '-R', str(RECIPIENT), '-o', str(output)], data=content)
        output.chmod(0o600)
        restored = command(['age', '-d', '-i', str(IDENTITY), str(output)]).stdout
        if restored != content:
            raise RecoveryError('Encrypted rebuilt snapshot failed verification')
    print(json.dumps({'rebuilt_raft_snapshot_encrypted_and_verified': True, 'plaintext_persisted': False}))


def main():
    """Run one explicitly selected recovery phase."""
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('keycloak-contract', 'initialize', 'unseal', 'configure', 'restore-kv', 'restore-supplemental', 'snapshot'))
    parser.add_argument('--pod', default='openbao-20261116-0')
    parser.add_argument('--pods', nargs='+')
    args = parser.parse_args()
    try:
        if args.phase == 'keycloak-contract':
            contract, _ = keycloak_client()
            print(json.dumps(contract, indent=2))
        elif args.phase == 'initialize':
            initialize(args.pod)
        elif args.phase == 'unseal':
            unseal(args.pods or [args.pod])
        elif args.phase == 'configure':
            configure(args.pod)
        elif args.phase == 'restore-kv':
            restore_kv(args.pod)
        elif args.phase == 'restore-supplemental':
            restore_supplemental(args.pod)
        elif args.phase == 'snapshot':
            snapshot(args.pod)
    except (RecoveryError, urllib.error.URLError, KeyError) as error:
        print(str(error) if isinstance(error, RecoveryError) else 'Recovery consumer failed; secret-bearing details withheld', file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
