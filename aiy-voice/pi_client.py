"""AIY button-held PCM streaming client; idle microphone samples are discarded."""
import asyncio
import json
import logging
import os
from pathlib import Path
import time
from urllib.parse import urlsplit

import aiohttp

RATE = 24000
DEVICE = "plughw:CARD=aiyvoicebonnet,DEV=0"
LOG = logging.getLogger("aiy-client")


def led(rgb):
    """Set RGB through the reviewed narrow Voice Bonnet sysfs interface."""
    command = "".join(f"led{i}={value};ch{i}_enable={int(value > 0)};"
                      for i, value in enumerate(rgb, 1))
    Path("/sys/class/leds/ktd202x:led1/device/registers").write_text(command, encoding="ascii")


def voice_url(origin):
    """Validate the configured origin before sending any device credentials."""
    parsed = urlsplit(origin)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("Backend must be an HTTPS origin")
    return "wss://" + parsed.netloc + "/v1/voice"


class Client:
    """Keep capture warm, stream button-held samples, play replies as they arrive."""
    def __init__(self, websocket):
        self.ws = websocket
        self.recording = False
        self.busy = False
        self.count = 0
        self.player = None
        self.released = None
        self.first_audio = None
        self.deadline = None

    async def start(self):
        """Start a turn only when the preceding reply has finished playing."""
        if self.recording or self.busy:
            return
        await self.ws.send_json({"type": "start"})
        self.recording, self.count = True, 0
        led((64, 0, 0))
        self.deadline = asyncio.get_running_loop().call_later(
            30, lambda: asyncio.create_task(self.stop()))

    async def stop(self):
        """Commit the turn at release (or at the 30-second capture limit)."""
        if not self.recording:
            return
        self.recording, self.busy = False, True
        self.deadline.cancel()
        self.released, self.first_audio = time.monotonic(), None
        await self.ws.send_json({"type": "stop"})
        led((32, 16, 0))

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
        """Start ALSA at the first chunk instead of waiting for a complete reply."""
        async for message in self.ws:
            if message.type == aiohttp.WSMsgType.BINARY:
                if self.player is None:
                    self.player = await asyncio.create_subprocess_exec(
                        "/usr/bin/aplay", "-q", "-D", DEVICE, "-t", "raw", "-f", "S16_LE",
                        "-r", str(RATE), "-c", "1", "-B", "100000", "-F", "20000",
                        stdin=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
                    self.first_audio = time.monotonic()
                    led((0, 0, 64))
                    LOG.info("first_audio_ms=%d", (self.first_audio - self.released) * 1000)
                self.player.stdin.write(message.data)
                await self.player.stdin.drain()
            elif message.type == aiohttp.WSMsgType.TEXT:
                event = json.loads(message.data)
                if event["type"] == "done":
                    if self.player:
                        self.player.stdin.close()
                        await self.player.wait()
                        if self.player.returncode:
                            raise RuntimeError("Speaker playback failed")
                        self.player = None
                    self.busy = False
                    led((0, 16, 0))
                elif event["type"] == "error":
                    raise RuntimeError("Voice backend failed")
            else:
                break
        raise RuntimeError("Voice connection closed")


async def connection(http):
    """Connect before enabling the button, with automatic cleanup on any failure."""
    url = voice_url(os.environ["AIY_BACKEND_URL"])
    token = os.environ["AIY_BEARER_TOKEN"]
    if len(token) < 32:
        raise ValueError("Device token is too short")
    processes, tasks = [], []
    async with http.ws_connect(url, headers={"Authorization": "Bearer " + token},
                               heartbeat=30, max_msg_size=1024 * 1024) as ws:
        async with asyncio.timeout(45):
            message = await ws.receive_json()
        if message.get("type") != "ready" or message.get("rate") != RATE:
            raise RuntimeError("Backend not ready")
        client = Client(ws)
        try:
            capture = await asyncio.create_subprocess_exec(
                "/usr/bin/arecord", "-q", "-D", DEVICE, "-f", "S16_LE", "-r", str(RATE),
                "-c", "1", "-t", "raw", "-B", "100000", "-F", "20000",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            processes.append(capture)
            # First discard warm-up data before announcing readiness.
            await asyncio.wait_for(capture.stdout.readexactly(960), 15)
            button = await asyncio.create_subprocess_exec(
                "/usr/bin/stdbuf", "-oL", "/usr/bin/gpiomon", "--chip", "gpiochip0",
                "--bias", "pull-up", "--edges", "both", "--debounce-period", "30ms", "23",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            processes.append(button)
            led((0, 16, 0))
            LOG.info("ready model=%s", message.get("model"))
            tasks = [asyncio.create_task(client.capture(capture.stdout)),
                     asyncio.create_task(client.buttons(button.stdout)),
                     asyncio.create_task(client.receive())]
            done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            if client.deadline:
                client.deadline.cancel()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if client.player and client.player.returncode is None:
                client.player.kill()
                await client.player.wait()
            for process in processes:
                if process.returncode is None:
                    process.terminate()
                await process.wait()


async def main():
    """Reconnect after network loss; the service also starts automatically at boot."""
    logging.basicConfig(level=logging.INFO)
    async with aiohttp.ClientSession(trust_env=False) as http:
        while True:
            try:
                await connection(http)
            except (OSError, RuntimeError, ValueError, TimeoutError, aiohttp.ClientError) as exc:
                LOG.warning("connection_failed kind=%s", type(exc).__name__)
                led((64, 0, 0))
                await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
