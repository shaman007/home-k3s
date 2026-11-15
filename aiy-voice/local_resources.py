"""Pi-local persistent timers and bounded LED effects; no shell or generic GPIO RPC."""
import asyncio
import math
from pathlib import Path
import sqlite3
import struct
import time

COLORS = {'red': (64, 0, 0), 'green': (0, 64, 0), 'blue': (0, 0, 64),
          'yellow': (64, 32, 0), 'white': (32, 32, 32), 'off': (0, 0, 0)}


class TimerStore:
    """Persist deadlines on the appliance; backend or network loss does not cancel them."""
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS timers (id TEXT PRIMARY KEY, due REAL, label TEXT, state TEXT)')
        self.db.commit()

    def create(self, timer_id, seconds, label, now=None):
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 1 <= seconds <= 604800:
            raise ValueError('Timer duration must be between 1 second and 7 days')
        if not isinstance(label, str) or len(label) > 100:
            raise ValueError('Timer label is too long')
        existing = next((item for item in self.list_all() if item['id'] == timer_id), None)
        if existing:
            return existing
        if len(self.active()) >= 16:
            raise ValueError('At most 16 active timers are supported')
        due = (time.time() if now is None else now) + seconds
        self.db.execute('INSERT OR IGNORE INTO timers VALUES (?, ?, ?, ?)', (timer_id, due, label, 'pending'))
        self.db.commit()
        return next(item for item in self.list_all() if item['id'] == timer_id)

    def list_all(self):
        return [{'id': row[0], 'due': row[1], 'label': row[2], 'state': row[3]}
                for row in self.db.execute('SELECT * FROM timers ORDER BY due')]

    def active(self):
        return [item for item in self.list_all() if item['state'] in ('pending', 'ringing')]

    def set_state(self, timer_id, state):
        if state not in ('ringing', 'done', 'cancelled'):
            raise ValueError('Invalid timer state')
        self.db.execute('UPDATE timers SET state=? WHERE id=?', (state, timer_id))
        self.db.commit()


def alarm_pcm():
    """Generate a conservative-volume triple beep locally, without a paid API call."""
    output = bytearray()
    for _ in range(3):
        for sample in range(7200):
            envelope = min(1, sample / 240, (7200 - sample) / 240)
            output.extend(struct.pack('<h', int(5000 * envelope * math.sin(2 * math.pi * 880 * sample / 24000))))
        output.extend(b'\0\0' * 4800)
    return bytes(output)


class LocalResources:
    """Allowlisted appliance operations and a scheduler independent of the network."""
    def __init__(self, state_path, set_led, play_alarm):
        self.timers = TimerStore(state_path)
        self.set_led = set_led
        self.play_alarm = play_alarm
        self.base = (0, 16, 0)
        self.effect = None
        self.ringing = None

    def status(self, color):
        self.base = color
        if self.effect is None or self.effect.done():
            self.set_led(color)

    async def blink(self, color, seconds):
        try:
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                self.set_led(color)
                await asyncio.sleep(0.25)
                self.set_led((0, 0, 0))
                await asyncio.sleep(0.25)
        finally:
            self.set_led(self.base)

    def start_effect(self, color, seconds):
        if self.effect and not self.effect.done():
            self.effect.cancel()
        self.effect = asyncio.create_task(self.blink(color, seconds))

    async def command(self, event):
        action = event.get('action')
        if action == 'blink':
            color, seconds = event.get('color'), event.get('seconds')
            if color not in COLORS or isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 1 <= seconds <= 30:
                raise ValueError('Unsupported color/duration')
            self.start_effect(COLORS[color], seconds)
            return {'ok': True}
        if action == 'set_timer':
            return self.timers.create(event['id'], event.get('seconds'), event.get('label', ''))
        if action == 'list_timers':
            return {'timers': self.timers.active()}
        if action == 'cancel_timer':
            self.timers.set_state(event.get('timer_id'), 'cancelled')
            return {'ok': True, 'timers': self.timers.active()}
        if action == 'status':
            temp = Path('/sys/class/thermal/thermal_zone0/temp')
            return {'uptime_seconds': float(Path('/proc/uptime').read_text().split()[0]),
                    'temperature_c': int(temp.read_text()) / 1000 if temp.exists() else None,
                    'timers': self.timers.active()}
        raise ValueError('Unsupported device operation')

    async def scheduler(self):
        while True:
            for timer in self.timers.active():
                if timer['due'] <= time.time() and timer['state'] in ('pending', 'ringing'):
                    self.timers.set_state(timer['id'], 'ringing')
                    self.ringing = timer['id']
                    self.start_effect(COLORS['yellow'], 6)
                    await self.play_alarm(alarm_pcm())
                    self.timers.set_state(timer['id'], 'done')
                    self.ringing = None
            await asyncio.sleep(0.25)

    async def close(self):
        if self.effect:
            self.effect.cancel()
            await asyncio.gather(self.effect, return_exceptions=True)
        self.timers.db.close()


class AudioOutput:
    """Serialize local alarms and streamed speech through the same ALSA device."""
    def __init__(self, device):
        self.device = device
        self.process = None
        self.lock = asyncio.Lock()

    async def play(self, pcm):
        async with self.lock:
            if self.process is None or self.process.returncode is not None:
                self.process = await asyncio.create_subprocess_exec(
                    '/usr/bin/aplay', '-q', '-D', self.device, '-t', 'raw', '-f', 'S16_LE',
                    '-r', '24000', '-c', '1', '-B', '100000', '-F', '20000',
                    stdin=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            self.process.stdin.write(pcm)
            await self.process.stdin.drain()

    async def finish(self):
        async with self.lock:
            if self.process:
                self.process.stdin.close()
                await self.process.wait()
                code = self.process.returncode
                self.process = None
                if code:
                    raise RuntimeError('ALSA playback failed')
