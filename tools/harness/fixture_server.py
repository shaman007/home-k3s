#!/usr/bin/env python3
"""Minimal stdio MCP fixture. Tools manipulate a JSON dictionary, never real paths."""

import json
from pathlib import Path
import sys


def tools():
    """Expose a deliberately small fake operational surface."""
    definitions = [
        ('read_file', 'Read one virtual fixture file; paths are dictionary keys, not host paths.', {'path': {'type': 'string'}}),
        ('write_file', 'Write one virtual fixture file; does not write a host file.', {'path': {'type': 'string'}, 'content': {'type': 'string'}}),
        ('deployment_evidence', 'Read synthetic Git/Argo/application evidence.', {}),
        ('request_approval', 'Record a simulated approval question; no human request is sent.', {'reason': {'type': 'string'}}),
        ('checkpoint', 'Save a simulated non-secret memory checkpoint, not a real MemPalace write.', {'content': {'type': 'string'}}),
        ('deploy', 'Simulate a deployment in fixture state; never changes a live system.', {}),
    ]
    return [{'name': name, 'description': description,
             'inputSchema': {'type': 'object', 'properties': properties,
                             'required': list(properties), 'additionalProperties': False}}
            for name, description, properties in definitions]


def call(state, name, arguments):
    """Allow only named operations on already-existing virtual file keys."""
    state['calls'].append({'name': name, 'arguments': arguments})
    if name in {'read_file', 'write_file'}:
        path = arguments.get('path')
        if not isinstance(path, str) or path not in state['files']:
            raise ValueError('Unknown virtual file; no host path access')
        if name == 'write_file':
            content = arguments.get('content')
            if not isinstance(content, str) or len(content) > 10000:
                raise ValueError('Invalid fixture content')
            state['files'][path] = content
            return 'updated'
        return state['files'][path]
    if name == 'deployment_evidence':
        return state['evidence']
    if name in {'request_approval', 'checkpoint'}:
        content = arguments.get('reason' if name == 'request_approval' else 'content')
        if not isinstance(content, str) or not content.strip() or len(content) > 10000:
            raise ValueError('Invalid fixture message')
        state['approvals' if name == 'request_approval' else 'memory'].append(content)
        return 'recorded'
    if name == 'deploy':
        state['deployed'] = True
        return 'simulated deployment recorded'
    raise ValueError('Unknown fixture tool')


def respond(message, state_path):
    """Handle the MCP lifecycle and persist synthetic tool observations only."""
    method, params = message.get('method'), message.get('params') or {}
    if 'id' not in message:
        return None
    if method == 'initialize':
        result = {'protocolVersion': params.get('protocolVersion', '2025-06-18'),
                  'capabilities': {'tools': {}}, 'serverInfo': {'name': 'harness-fixture', 'version': '1'}}
    elif method == 'tools/list':
        result = {'tools': tools()}
    elif method == 'tools/call':
        state = json.loads(state_path.read_text())
        try:
            value = call(state, params.get('name'), params.get('arguments') or {})
            result = {'content': [{'type': 'text', 'text': json.dumps(value)}], 'isError': False}
        except (ValueError, TypeError, KeyError):
            result = {'content': [{'type': 'text', 'text': 'Invalid fixture call; no host access'}], 'isError': True}
        state_path.write_text(json.dumps(state))
    elif method == 'resources/list':
        result = {'resources': []}
    elif method == 'prompts/list':
        result = {'prompts': []}
    elif method == 'ping':
        result = {}
    else:
        return {'jsonrpc': '2.0', 'id': message['id'], 'error': {'code': -32601, 'message': 'Method not found'}}
    return {'jsonrpc': '2.0', 'id': message['id'], 'result': result}


def main():
    state_path = Path(sys.argv[1])
    for line in sys.stdin:
        try:
            response = respond(json.loads(line), state_path)
            if response is not None:
                print(json.dumps(response), flush=True)
        except (ValueError, TypeError, KeyError, OSError):
            # No raw tool arguments or state ever go to server logs.
            print(json.dumps({'jsonrpc': '2.0', 'id': None,
                              'error': {'code': -32700, 'message': 'Invalid fixture request'}}), flush=True)


if __name__ == '__main__':
    main()
