"""AIY button-held PCM streaming client; idle microphone samples are discarded."""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import aiohttp
from local_resources import AudioOutput, LocalResources

RATE = 24000
DEVICE = "plughw:CARD=aiyvoicebonnet,DEV=0"
LOG = logging.getLogger("aiy-client")


def scheduled_color(rgb, now=None):
    """Apply the Prague night schedule to every button indicator state."""
    now = now or datetime.now(ZoneInfo("Europe/Prague"))
    minute = now.hour * 60 + now.minute
    if minute < 360:
        return (0, 0, 0)
    if minute >= 1410:
        peak = max(rgb)
        return tuple(round(value / peak) for value in rgb) if peak else (0, 0, 0)
    return tuple(round(value * 0.1875) for value in rgb)


class ScheduledIndicator:
    """Remember the requested color and refresh it across quiet-hour boundaries."""

    def __init__(self):
        self.rgb = (0, 0, 0)
        self.applied = None

    def __call__(self, rgb):
        self.rgb = rgb
        self.refresh()

    def refresh(self):
        """Write only when the effective color changes."""
        color = scheduled_color(self.rgb)
        if color != self.applied:
            led(color)
            self.applied = color

    async def run(self):
        """Update idle lighting within one second of a schedule boundary."""
        while True:
            self.refresh()
            await asyncio.sleep(1)


def led(rgb):
    """Set RGB through the reviewed narrow Voice Bonnet sysfs interface."""
    command = "".join(
        f"led{i}={value};ch{i}_enable={int(value > 0)};" for i, value in enumerate(rgb, 1)
    )
    Path("/sys/class/leds/ktd202x:led1/device/registers").write_text(command, encoding="ascii")


def voice_url(origin):
    """Validate the configured origin before sending any device credentials."""
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Backend must be an HTTPS origin")
    if (
        parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Backend must be an HTTPS origin")
    return "wss://" + parsed.netloc + "/v1/voice"


@dataclass
class TurnTiming:
    """Hold capture deadline and playback latency timestamps for one turn."""

    released: float | None = None
    first_audio: float | None = None
    last_audio_received: float | None = None
    deadline: asyncio.TimerHandle | None = None


@dataclass
class ReplyAudio:
    """One bounded turn shared by independent receiving and playback tasks."""

    pcm: bytearray = field(default_factory=bytearray)
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    done: bool = False
    failed: bool = False
    queued: bool = False
    total: int = 0


@dataclass
class PlaybackState:
    """Keep audio output, reserve and per-turn queues together."""

    audio: AudioOutput
    reply: ReplyAudio = field(default_factory=ReplyAudio)
    buffer_seconds: float = 3.0
    replies: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=1))


class Client:
    """Keep capture warm and adapt the playback reserve to network starvation."""

    def __init__(self, websocket, resources=None, audio=None):
        self.ws = websocket
        self.recording = False
        self.busy = False
        self.count = 0
        self.resources = resources
        self.timing = TurnTiming()
        self.player = PlaybackState(audio)

    def status(self, rgb):
        """Update the LED status via resources or direct LED control."""
        if self.resources:
            self.resources.status(rgb)
        else:
            led(rgb)

    async def start(self):
        """Start a turn only when the preceding reply has finished playing."""
        if self.recording or self.busy:
            return
        if self.resources:
            self.resources.engaged = True
        if self.player.audio:
            await self.player.audio.interrupt()
        event = {"type": "start"}
        if self.resources:
            event["reminders"] = self.resources.reminders.list()
        await self.ws.send_json(event)
        self.recording, self.count = True, 0
        self.status((64, 0, 0))
        self.timing.deadline = asyncio.get_running_loop().call_later(
            30, lambda: asyncio.create_task(self.stop())
        )

    async def stop(self):
        """Commit the turn at release (or at the 30-second capture limit)."""
        if not self.recording:
            return
        self.recording, self.busy = False, True
        self.timing.deadline.cancel()
        self.timing.released, self.timing.first_audio = time.monotonic(), None
        self.timing.last_audio_received = None
        self.player.reply = ReplyAudio()
        await self.ws.send_json({"type": "stop"})
        self.status((32, 16, 0))

    async def capture(self, source):
        """Discard idle audio immediately; there is no retained idle pre-roll."""
        while chunk := await source.read(960):
            if self.recording:
                remaining = RATE * 2 * 30 - self.count
                chunk = chunk[:remaining]
                if chunk:
                    self.count += len(chunk)
                    await self.ws.send_bytes(chunk)
        raise RuntimeError("Microphone stopped")

    async def buttons(self, source):
        """Read every complete GPIO event, including batched press/release edges."""
        while line := await source.readline():
            if b"falling" in line:
                await self.start()
            elif b"rising" in line:
                await self.stop()
        raise RuntimeError("Button monitor stopped")

    async def receive(self):
        """Receive independently of playback, keeping all audio in bounded RAM."""
        async for message in self.ws:
            if message.type == aiohttp.WSMsgType.BINARY:
                received = time.monotonic()
                previous = self.timing.last_audio_received
                if previous is not None and received - previous > 0.25:
                    LOG.warning(
                        "audio_receive_gap_ms=%d chunk_ms=%d",
                        (received - previous) * 1000, len(message.data) * 1000 // (RATE * 2),
                    )
                if self.timing.first_audio is None:
                    self.timing.first_audio = time.monotonic()
                    LOG.info(
                        "first_audio_ms=%d", (self.timing.first_audio - self.timing.released) * 1000
                    )
                self.timing.last_audio_received = received
                # Five minutes of PCM16 mono at 24 kHz, held only in RAM.
                if self.player.reply.total + len(message.data) > RATE * 2 * 300:
                    raise RuntimeError("Voice reply exceeds five minutes")
                self.player.reply.total += len(message.data)
                self.player.reply.pcm.extend(message.data)
                self.queue_reply()
            elif message.type == aiohttp.WSMsgType.TEXT:
                event = json.loads(message.data)
                if event["type"] == "done":
                    self.player.reply.done = True
                    self.player.reply.failed = event.get("status") != "completed"
                    self.queue_reply()
                elif event["type"] == "device_command":
                    try:
                        result = await self.resources.command(event)
                    except (ValueError, KeyError, OSError) as exc:
                        result = {"error": type(exc).__name__}
                    await self.ws.send_json(
                        {"type": "device_ack", "id": event.get("id"), "result": result}
                    )
                elif event["type"] == "error":
                    raise RuntimeError("Voice backend failed")
            else:
                break
        raise RuntimeError("Voice connection closed")

    def queue_reply(self):
        """Wake playback without blocking receipt or WebSocket heartbeats."""
        if not self.player.reply.queued:
            self.player.replies.put_nowait(self.player.reply)
            self.player.reply.queued = True
        self.player.reply.changed.set()

    async def play_reply(self, reply):
        """Drain before starvation, then refill a larger reserve instead of stuttering."""
        playing, end, stalls = False, 0.0, 0
        while True:
            reply.changed.clear()
            if reply.failed:
                reply.pcm.clear()
                await self.player.audio.interrupt()
                await self.player.audio.finish()
                return
            ready = len(reply.pcm) >= round(RATE * 2 * self.player.buffer_seconds)
            if reply.pcm and (playing or ready or reply.done):
                pcm = bytes(reply.pcm)
                reply.pcm.clear()
                if not playing:
                    self.status((0, 0, 64))
                    LOG.info("playback_start reserve_ms=%d target_ms=%d",
                             len(pcm) * 1000 // (RATE * 2), self.player.buffer_seconds * 1000)
                end = max(end, time.monotonic()) + len(pcm) / (RATE * 2)
                playing = True
                await self.player.audio.play(pcm)
                continue
            if reply.done:
                await self.player.audio.finish()
                if not stalls and reply.total >= RATE * 2 * 10:
                    self.player.buffer_seconds = max(1.5, self.player.buffer_seconds - 0.5)
                return
            if playing:
                try:
                    # Close and drain ALSA before it runs out of samples.
                    await asyncio.wait_for(
                        reply.changed.wait(), max(0, end - time.monotonic() - 0.15)
                    )
                except TimeoutError:
                    await self.player.audio.finish()
                    playing, end = False, 0.0
                    stalls += 1
                    self.player.buffer_seconds = min(8.0, self.player.buffer_seconds + 1.0)
                    self.status((32, 16, 0))
                    LOG.warning("audio_rebuffer target_ms=%d", self.player.buffer_seconds * 1000)
            else:
                await reply.changed.wait()

    async def playback(self):
        """Keep receiver active while waiting for reserves or draining ALSA."""
        while True:
            await self.play_reply(await self.player.replies.get())
            self.busy = False
            self.resources.engaged = False
            self.status((0, 16, 0))


async def connection(http, resources, audio):
    """Connect before enabling the button, with automatic cleanup on any failure."""
    token = os.environ["AIY_BEARER_TOKEN"]
    if len(token) < 32:
        raise ValueError("Device token is too short")
    processes, tasks = [], []
    async with http.ws_connect(
        voice_url(os.environ["AIY_BACKEND_URL"]),
        headers={"Authorization": "Bearer " + token},
        heartbeat=30,
        max_msg_size=1024 * 1024,
    ) as ws:
        async with asyncio.timeout(45):
            message = await ws.receive_json()
        if message.get("type") != "ready" or message.get("rate") != RATE:
            raise RuntimeError("Backend not ready")
        client = Client(ws, resources, audio)
        try:
            capture = await asyncio.create_subprocess_exec(
                "/usr/bin/arecord",
                "-q",
                "-D",
                DEVICE,
                "-f",
                "S16_LE",
                "-r",
                str(RATE),
                "-c",
                "1",
                "-t",
                "raw",
                "-B",
                "100000",
                "-F",
                "20000",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            processes.append(capture)
            # First discard warm-up data before announcing readiness.
            await asyncio.wait_for(capture.stdout.readexactly(960), 15)
            button = await asyncio.create_subprocess_exec(
                "/usr/bin/stdbuf",
                "-oL",
                "/usr/bin/gpiomon",
                "--chip",
                "gpiochip0",
                "--bias",
                "pull-up",
                "--edges",
                "both",
                "--debounce-period",
                "30ms",
                "23",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            processes.append(button)
            resources.status((0, 16, 0))
            LOG.info("ready model=%s", message.get("model"))
            tasks = [
                asyncio.create_task(client.capture(capture.stdout)),
                asyncio.create_task(client.buttons(button.stdout)),
                asyncio.create_task(client.receive()),
                asyncio.create_task(client.playback()),
            ]
            done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            resources.engaged = False
            if client.timing.deadline:
                client.timing.deadline.cancel()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await audio.finish()
            for process in processes:
                if process.returncode is None:
                    process.terminate()
                await process.wait()


async def main():
    """Reconnect after network loss; the service also starts automatically at boot."""
    logging.basicConfig(level=logging.INFO)
    audio = AudioOutput(DEVICE)

    async def alarm(pcm):
        """Play PCM audio and finish the audio output stream."""
        await audio.play(pcm)
        await audio.finish()

    indicator = ScheduledIndicator()
    resources = LocalResources(
        os.environ.get("AIY_TIMER_DB", "/var/lib/aiy-voice/timers.sqlite3"), indicator, alarm
    )
    await resources.volume.restore()
    scheduler = asyncio.create_task(resources.scheduler())
    lighting = asyncio.create_task(indicator.run())
    try:
        async with aiohttp.ClientSession(trust_env=False) as http:
            while True:
                if scheduler.done():
                    scheduler.result()
                if lighting.done():
                    lighting.result()
                try:
                    await connection(http, resources, audio)
                except (
                    OSError,
                    RuntimeError,
                    ValueError,
                    TimeoutError,
                    aiohttp.ClientError,
                ) as exc:
                    LOG.warning("connection_failed kind=%s", type(exc).__name__)
                    resources.status((64, 0, 0))
                    await asyncio.sleep(5)
    finally:
        scheduler.cancel()
        lighting.cancel()
        await asyncio.gather(scheduler, lighting, return_exceptions=True)
        await resources.close()
        await audio.finish()


if __name__ == "__main__":
    asyncio.run(main())
