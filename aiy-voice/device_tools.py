"""Bounded voice tools for local resources; the model never sees shell/GPIO paths."""
import asyncio
import time
import resource
import uuid

STARTED = time.monotonic()

TOOLS = [
    {'type': 'function', 'name': 'blink_light', 'description': 'Blink the built-in RGB button light on the speaker. Supported colors only, 1–30 seconds.',
     'parameters': {'type': 'object', 'properties': {'color': {'type': 'string', 'enum': ['red', 'green', 'blue', 'yellow', 'white', 'off']}, 'seconds': {'type': 'number'}}, 'required': ['color', 'seconds'], 'additionalProperties': False}},
    {'type': 'function', 'name': 'set_timer', 'description': 'Set a timer on the speaker. It rings locally even if network or backend is temporarily unavailable. Duration 1 second to 7 days.',
     'parameters': {'type': 'object', 'properties': {'seconds': {'type': 'number'}, 'label': {'type': 'string'}}, 'required': ['seconds', 'label'], 'additionalProperties': False}},
    {'type': 'function', 'name': 'list_timers', 'description': 'List active timers on the speaker.', 'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'type': 'function', 'name': 'cancel_timer', 'description': 'Cancel an active timer by the ID returned by list_timers or set_timer.',
     'parameters': {'type': 'object', 'properties': {'timer_id': {'type': 'string'}}, 'required': ['timer_id'], 'additionalProperties': False}},
    {'type': 'function', 'name': 'device_status', 'description': 'Read speaker temperature, uptime, active timers and backend process clock/memory/uptime; no general filesystem or shell access.',
     'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
]
ACTIONS = {'blink_light': 'blink', 'set_timer': 'set_timer', 'list_timers': 'list_timers',
           'cancel_timer': 'cancel_timer', 'device_status': 'status'}


class DeviceTools:
    def __init__(self, websocket, db):
        self.websocket = websocket
        self.pending = {}
        self.db = db
        db.execute('CREATE TABLE IF NOT EXISTS device_commands (id TEXT PRIMARY KEY, created REAL, action TEXT, result TEXT)')
        db.commit()

    async def call(self, name, arguments):
        import json
        if name not in ACTIONS or not isinstance(arguments, dict):
            return {'error': 'Unsupported device operation'}
        command_id = uuid.uuid4().hex
        event = dict(arguments, type='device_command', id=command_id, action=ACTIONS[name])
        future = asyncio.get_running_loop().create_future()
        self.pending[command_id] = future
        try:
            await self.websocket.send_json(event)
            result = await asyncio.wait_for(future, 8)
            if name == 'device_status':
                result['backend'] = {'process_uptime_seconds': int(time.monotonic() - STARTED),
                                     'clock_unix': time.time(),
                                     'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
            # Persist acknowledged operations in PVC; appliance maintains executable timer state.
            self.db.execute('INSERT INTO device_commands VALUES (?, ?, ?, ?)',
                            (command_id, time.time(), ACTIONS[name], json.dumps(result)))
            self.db.commit()
            return result
        except TimeoutError:
            return {'error': 'Device did not acknowledge; do not claim successful execution'}
        finally:
            self.pending.pop(command_id, None)

    def acknowledge(self, event):
        future = self.pending.get(event.get('id'))
        if future and not future.done():
            future.set_result(event.get('result', {'error': 'Missing result'}))
