"""Pi-local persistent timers and bounded LED effects; no shell or generic GPIO RPC."""

import asyncio
import base64
import math
import re
import sqlite3
import struct
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from reminders import Reminders, ReminderSpec

COLORS = {
    "red": (64, 0, 0),
    "green": (0, 64, 0),
    "blue": (0, 0, 64),
    "yellow": (64, 32, 0),
    "white": (32, 32, 32),
    "off": (0, 0, 0),
}


class TimerStore:
    """Persist deadlines on the appliance; backend or network loss does not cancel them."""

    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS timers (id TEXT PRIMARY KEY, due REAL, label TEXT, state"
            " TEXT)"
        )
        self.db.commit()

    def create(self, timer_id, seconds, label, now=None):
        """Create a new timer if it does not exist and limits allow, returning its state."""
        if (
            isinstance(seconds, bool)
            or not isinstance(seconds, (int, float))
            or not 1 <= seconds <= 604800
        ):
            raise ValueError("Timer duration must be between 1 second and 7 days")
        if not isinstance(label, str) or len(label) > 100:
            raise ValueError("Timer label is too long")
        existing = next((item for item in self.list_all() if item["id"] == timer_id), None)
        if existing:
            return existing
        if len(self.active()) >= 16:
            raise ValueError("At most 16 active timers are supported")
        due = (time.time() if now is None else now) + seconds
        self.db.execute(
            "INSERT OR IGNORE INTO timers VALUES (?, ?, ?, ?)", (timer_id, due, label, "pending")
        )
        self.db.commit()
        return next(item for item in self.list_all() if item["id"] == timer_id)

    def list_all(self):
        """Return all stored timers ordered by their due time."""
        return [
            {"id": row[0], "due": row[1], "label": row[2], "state": row[3]}
            for row in self.db.execute("SELECT * FROM timers ORDER BY due")
        ]

    def active(self):
        """Return pending or ringing timers with their remaining seconds calculated."""
        now = time.time()
        return [
            dict(item, remaining_seconds=max(0, round(item["due"] - now, 1)))
            for item in self.list_all()
            if item["state"] in ("pending", "ringing")
        ]

    def set_state(self, timer_id, state):
        """Update the state of a specific timer to ringing, done, or cancelled."""
        if state not in ("ringing", "done", "cancelled"):
            raise ValueError("Invalid timer state")
        self.db.execute("UPDATE timers SET state=? WHERE id=?", (state, timer_id))
        self.db.commit()


def alarm_pcm():
    """Generate a conservative-volume triple beep locally, without a paid API call."""
    output = bytearray()
    for _ in range(3):
        for sample in range(7200):
            envelope = min(1, sample / 240, (7200 - sample) / 240)
            output.extend(
                struct.pack(
                    "<h", int(5000 * envelope * math.sin(2 * math.pi * 880 * sample / 24000))
                )
            )
        output.extend(b"\0\0" * 4800)
    return bytes(output)


@dataclass
class IndicatorState:
    """Keep the LED callback, base color and temporary effect together."""

    set_led: Callable[[tuple[int, int, int]], None]
    base: tuple = (0, 16, 0)
    effect: asyncio.Task | None = None


class LocalResources:
    """Allowlisted appliance operations and a scheduler independent of the network."""

    def __init__(self, state_path, set_led, play_alarm):
        self.timers = TimerStore(state_path)
        self.volume = Volume(self.timers.db)
        self.reminders = Reminders(self.timers.db)
        self.timers.db.execute(
            "CREATE TABLE IF NOT EXISTS voice_notes (id TEXT PRIMARY KEY, text TEXT, created REAL)"
        )
        self.timers.db.commit()
        self.light = IndicatorState(set_led)
        self.play_alarm = play_alarm
        self.ringing = None
        self.engaged = False

    def status(self, color):
        """Set the base LED color and apply it if no temporary effect is running."""
        self.light.base = color
        if self.light.effect is None or self.light.effect.done():
            self.light.set_led(color)

    async def blink(self, color, seconds):
        """Blink the LED with the specified color for the given duration."""
        try:
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                self.light.set_led(color)
                await asyncio.sleep(0.25)
                self.light.set_led((0, 0, 0))
                await asyncio.sleep(0.25)
        finally:
            self.light.set_led(self.light.base)

    def start_effect(self, color, seconds):
        """Cancel any running LED effect and start a new blink task."""
        if self.light.effect and not self.light.effect.done():
            self.light.effect.cancel()
        self.light.effect = asyncio.create_task(self.blink(color, seconds))

    async def command(self, event):
        """Validate and dispatch only the allowlisted appliance operations."""
        action = event.get("action")
        if action in {"save_note", "list_notes"}:
            return self._note_command(event)
        if action in {
            "update_reminder_interval",
            "update_daily_reminder",
            "suspend_daily_reminder",
            "resume_daily_reminder",
            "create_daily_reminder",
            "list_daily_reminders",
            "acknowledge_reminder",
            "disable_daily_reminder",
        }:
            return self._reminder_command(event)
        if action == "blink":
            color, seconds = event.get("color"), event.get("seconds")
            if (
                color not in COLORS
                or isinstance(seconds, bool)
                or not isinstance(seconds, (int, float))
                or not 1 <= seconds <= 30
            ):
                raise ValueError("Unsupported color/duration")
            self.start_effect(COLORS[color], seconds)
            return {"ok": True}
        if action in {"set_timer", "list_timers", "cancel_timer"}:
            return self._timer_command(event)
        if action in {"set_volume", "adjust_volume"}:
            operation, field = (
                (self.volume.set, "level")
                if action == "set_volume" else (self.volume.adjust, "delta")
            )
            return await operation(event.get(field))
        if action == "status":
            temp = Path("/sys/class/thermal/thermal_zone0/temp")
            return {
                "volume_percent": await self.volume.get(),
                "uptime_seconds": float(
                    Path("/proc/uptime").read_text(encoding="utf-8").split()[0]
                ),
                "temperature_c": (
                    int(temp.read_text(encoding="utf-8")) / 1000 if temp.exists() else None
                ),
                "timers": self.timers.active(),
                "reminders": self.reminders.list(),
            }
        raise ValueError("Unsupported device operation")

    def _note_command(self, event):
        """Save or retrieve explicit notes in the persistent appliance database."""
        action = event["action"]
        if action == "save_note":
            text = event.get("text")
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000:
                raise ValueError("Invalid note")
            if self.timers.db.execute("SELECT count(*) FROM voice_notes").fetchone()[0] >= 100:
                raise ValueError("Note storage full")
            self.timers.db.execute(
                "INSERT OR IGNORE INTO voice_notes VALUES (?, ?, ?)",
                (event["id"], text.strip(), time.time()),
            )
            self.timers.db.commit()
            return {"ok": True, "note_id": event["id"]}
        if action == "list_notes":
            return {
                "notes": [
                    dict(zip(("id", "text", "created"), row))
                    for row in self.timers.db.execute("SELECT * FROM voice_notes ORDER BY created")
                ]
            }
        raise ValueError("Unsupported note operation")

    def _timer_command(self, event):
        """Apply an allowlisted timer operation and return its current state."""
        action = event["action"]
        if action == "set_timer":
            return self.timers.create(event["id"], event.get("seconds"), event.get("label", ""))
        if action == "list_timers":
            return {"timers": self.timers.active()}
        if action == "cancel_timer":
            self.timers.set_state(event.get("timer_id"), "cancelled")
            return {"ok": True, "timers": self.timers.active()}
        raise ValueError("Unsupported timer operation")

    def _reminder_command(self, event):
        """Apply the reminder operations accepted by command()."""
        action = event["action"]
        if action in {"update_daily_reminder", "update_reminder_interval"}:
            return self._edit_reminder(event)
        if action in {"suspend_daily_reminder", "resume_daily_reminder"}:
            return (self.reminders.suspend(event.get("reminder_id"), event.get("until_date"))
                    if action == "suspend_daily_reminder"
                    else self.reminders.resume(event.get("reminder_id")))
        if action == "create_daily_reminder":
            audio = base64.b64decode(event.get("audio", ""), validate=True)
            return self.reminders.create(
                event["id"],
                ReminderSpec(
                    event.get("text"),
                    event.get("start_time"),
                    event.get("end_time"),
                    event.get("repeat_minutes"),
                    event.get("confirmation_phrase"),
                    weekdays=event.get("weekdays"),
                    jitter_minutes=event.get("jitter_minutes", 0),
                ),
                audio,
                first_date=event.get("first_date"),
            )
        if action == "list_daily_reminders":
            return {"reminders": self.reminders.list()}
        if action == "acknowledge_reminder":
            return self.reminders.acknowledge(event.get("confirmation"), event.get("reminder_id"))
        if action == "disable_daily_reminder":
            return self.reminders.disable(event.get("reminder_id"))
        raise ValueError("Unsupported reminder operation")

    def _edit_reminder(self, event):
        """Regenerate speech only for text edits; keep the legacy interval operation."""
        if event["action"] == "update_reminder_interval":
            return self.reminders.update_interval(
                event.get("reminder_id"), event.get("repeat_minutes"))
        audio = (base64.b64decode(event["audio"], validate=True) if "audio" in event else None)
        return self.reminders.update(event.get("reminder_id"), event.get("changes"), audio)

    async def scheduler(self):
        """Continuously check for due timers and reminders to trigger alarms and effects."""
        while True:
            for timer in self.timers.active():
                if self.engaged:
                    break
                if timer["due"] <= time.time() and timer["state"] in ("pending", "ringing"):
                    self.timers.set_state(timer["id"], "ringing")
                    self.ringing = timer["id"]
                    self.start_effect(COLORS["yellow"], 6)
                    await self.play_alarm(alarm_pcm())
                    self.timers.set_state(timer["id"], "done")
                    self.ringing = None
            for reminder in self.reminders.due():
                if self.engaged:
                    break
                # A confirmation can arrive while an earlier reminder is playing.
                if reminder["id"] not in {item["id"] for item in self.reminders.due()}:
                    continue
                self.start_effect(COLORS["yellow"], 6)
                await self.play_alarm(reminder["audio"])
                self.reminders.delivered(reminder)
            await asyncio.sleep(0.25)

    async def close(self):
        """Cancel active effects and close the timer database connection."""
        if self.light.effect:
            self.light.effect.cancel()
            await asyncio.gather(self.light.effect, return_exceptions=True)
        self.timers.db.close()


class AudioOutput:
    """Serialize local alarms and streamed speech through the same ALSA device."""

    def __init__(self, device):
        self.device = device
        self.process = None
        self.lock = asyncio.Lock()
        self.interrupted = None
        self.pending = bytearray()

    async def play(self, pcm, *, flush=False):
        """Write PCM data to the ALSA playback process, starting it if necessary."""
        async with self.lock:
            if self.process is None or self.process.returncode is not None:
                self.pending.extend(pcm)
                # PCM16 mono at 24 kHz: prefill 500 ms before starting playback.
                if not self.pending or (len(self.pending) < 24000 and not flush):
                    return
                pcm = bytes(self.pending)
                self.pending.clear()
                self.process = await asyncio.create_subprocess_exec(
                    "/usr/bin/aplay",
                    "-q",
                    "-D",
                    self.device,
                    "-t",
                    "raw",
                    "-f",
                    "S16_LE",
                    "-r",
                    "24000",
                    "-c",
                    "1",
                    # Absorb short network stalls before ALSA runs out of samples.
                    "-B",
                    "500000",
                    "-F",
                    "20000",
                    stdin=asyncio.subprocess.PIPE,
                    # Keep ALSA underruns visible in the service journal.
                    stderr=None,
                )
            process = self.process
            try:
                process.stdin.write(pcm)
                await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                if process is not self.interrupted:
                    raise

    async def finish(self):
        """Close the ALSA input stream and wait for the playback process to complete."""
        await self.play(b"", flush=True)
        async with self.lock:
            if self.process:
                process = self.process
                process.stdin.close()
                await process.wait()
                code = process.returncode
                self.process = None
                if code and process is not self.interrupted:
                    raise RuntimeError("ALSA playback failed")

    async def interrupt(self):
        """Stop an idle reminder/beep before capturing the user's confirmation."""
        self.pending.clear()
        process = self.process
        if process and process.returncode is None:
            self.interrupted = process
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 2)
            except TimeoutError:
                process.kill()
                await process.wait()


class Volume:
    """Control only the Voice Bonnet speaker mixer; persist the requested level."""

    def __init__(self, db):
        self.db = db
        db.execute("CREATE TABLE IF NOT EXISTS preferences (name TEXT PRIMARY KEY, value INTEGER)")
        db.commit()

    async def mixer(self, *arguments):
        """Execute an amixer command and return its stdout output."""
        process = await asyncio.create_subprocess_exec(
            "/usr/bin/amixer",
            "-c",
            "aiyvoicebonnet",
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        try:
            output, _error = await asyncio.wait_for(process.communicate(), 5)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise
        if process.returncode:
            raise OSError("Speaker mixer command failed")
        return output.decode("ascii")

    async def get(self):
        """Read the current speaker volume percentage from the mixer."""
        matches = re.findall(r"\[(\d+)%\]", await self.mixer("sget", "Speaker"))
        if not matches:
            raise ValueError("Speaker mixer returned no level")
        return int(matches[0])

    async def set(self, level):
        """Set the speaker volume to a specific percentage and persist it."""
        if isinstance(level, bool) or not isinstance(level, (int, float)) or not 0 <= level <= 100:
            raise ValueError("Volume must be between 0 and 100 percent")
        level = round(level)
        await self.mixer("sset", "Speaker", str(level) + "%")
        self.db.execute("INSERT OR REPLACE INTO preferences VALUES (?, ?)", ("volume", level))
        self.db.commit()
        return {"ok": True, "volume_percent": await self.get()}

    async def adjust(self, delta):
        """Adjust the current speaker volume by a delta, clamping to 0-100."""
        if (
            isinstance(delta, bool)
            or not isinstance(delta, (int, float))
            or not -100 <= delta <= 100
        ):
            raise ValueError("Invalid volume adjustment")
        return await self.set(max(0, min(100, await self.get() + delta)))

    async def restore(self):
        """Apply the persisted volume setting from the database to the mixer."""
        row = self.db.execute("SELECT value FROM preferences WHERE name=?", ("volume",)).fetchone()
        if row:
            await self.set(row[0])
