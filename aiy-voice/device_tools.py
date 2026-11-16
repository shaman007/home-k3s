"""Bounded voice tools for local resources; the model never sees shell/GPIO paths."""

import json

import asyncio
import time
import resource
import uuid

STARTED = time.monotonic()

TOOLS = [
    {
        "type": "function",
        "name": "create_daily_reminder",
        "description": (
            "Create an independent recurring spoken reminder on the Pi, repeating until explicitly"
            " confirmed for today. Default quiet hours start22:00; default repeat30min and"
            " independent per-slot jitter plus/minus10min, including first alert. Use weekdays for"
            " weekly schedules (Monday=0). Repeat interval must exceed twice jitter. Use a short"
            " representative affirmative completion phrase; semantic equivalents are accepted for"
            " the identified task. Each reminder has independent acknowledgement. Do not create"
            " schedules merely mentioned as examples. First_date null means today if before start,"
            " otherwise tomorrow. Reminder speech is synthesized once and cached locally."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "start_time": {"type": "string", "description": "HH:MM Europe/Prague"},
                "end_time": {"type": "string", "description": "Exclusive HH:MM, normally22:00"},
                "repeat_minutes": {"type": "integer"},
                "confirmation_phrase": {
                    "type": "string",
                    "description": (
                        "Representative completion statement; user may confirm in free form by"
                        " naming the task"
                    ),
                },
                "weekdays": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 7,
                    "uniqueItems": True,
                    "items": {"type": "integer", "minimum": 0, "maximum": 6},
                    "description": "Active weekdays, Monday=0; all seven for daily",
                },
                "jitter_minutes": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10,
                    "description": (
                        "Independent plus/minus displacement of each nominal slot, including first;"
                        " default10"
                    ),
                },
                "first_date": {
                    "type": ["string", "null"],
                    "description": "YYYY-MM-DD or null for next scheduled start",
                },
            },
            "required": [
                "text",
                "start_time",
                "end_time",
                "repeat_minutes",
                "confirmation_phrase",
                "first_date",
                "weekdays",
                "jitter_minutes",
            ],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "list_daily_reminders",
        "description": (
            "List independent daily reminders, next alert, confirmation phrase and today"
            " acknowledgement."
        ),
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "acknowledge_reminder",
        "description": (
            "Mark one reminder completed for TODAY ONLY; tomorrow resumes. Pass the user entire"
            " latest affirmative completion statement verbatim, never paraphrase/shorten it. Do not"
            " call for negation, questions, future plans, quoted examples or mere button presses."
            " Use list_daily_reminders to identify the task for a semantic equivalent such as a"
            " different affirmative past-tense completion statement, then pass its reminder_id. Pi"
            " rejects negation, future plans, questions and non-today claims. Before the first"
            " alert still counts as done today. reminder_id null uses exact configured phrase"
            " matching; ambiguity requires clarification, never dismiss all."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "confirmation": {"type": "string"},
                "reminder_id": {"type": ["string", "null"]},
            },
            "required": ["confirmation", "reminder_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "disable_daily_reminder",
        "description": (
            "Stop a recurring reminder permanently only on explicit request to cancel/delete it."
            " Never use to acknowledge completion today."
        ),
        "parameters": {
            "type": "object",
            "properties": {"reminder_id": {"type": "string"}},
            "required": ["reminder_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "set_volume",
        "description": (
            "Set speaker playback volume to an absolute percentage from 0 to 100. Persists on the"
            " appliance. This affects speech and timer sounds."
        ),
        "parameters": {
            "type": "object",
            "properties": {"level": {"type": "number"}},
            "required": ["level"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "adjust_volume",
        "description": (
            "Make the speaker quieter or louder by percentage points. For a little quieter use -10,"
            " a little louder +10. Level is clamped to 0–100."
        ),
        "parameters": {
            "type": "object",
            "properties": {"delta": {"type": "number"}},
            "required": ["delta"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "blink_light",
        "description": (
            "Blink the built-in RGB button light on the speaker. Supported colors only, 1–30"
            " seconds."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "color": {
                    "type": "string",
                    "enum": ["red", "green", "blue", "yellow", "white", "off"],
                },
                "seconds": {"type": "number"},
            },
            "required": ["color", "seconds"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "set_timer",
        "description": (
            "Set a timer on the speaker. It rings locally even if network or backend is temporarily"
            " unavailable. Duration 1 second to 7 days."
        ),
        "parameters": {
            "type": "object",
            "properties": {"seconds": {"type": "number"}, "label": {"type": "string"}},
            "required": ["seconds", "label"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "list_timers",
        "description": "List active timers on the speaker.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "cancel_timer",
        "description": "Cancel an active timer by the ID returned by list_timers or set_timer.",
        "parameters": {
            "type": "object",
            "properties": {"timer_id": {"type": "string"}},
            "required": ["timer_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "device_status",
        "description": (
            "Read speaker temperature, uptime, active timers and backend process"
            " clock/memory/uptime; no general filesystem or shell access."
        ),
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]
ACTIONS = {
    "create_daily_reminder": "create_daily_reminder",
    "list_daily_reminders": "list_daily_reminders",
    "acknowledge_reminder": "acknowledge_reminder",
    "disable_daily_reminder": "disable_daily_reminder",
    "set_volume": "set_volume",
    "adjust_volume": "adjust_volume",
    "blink_light": "blink",
    "set_timer": "set_timer",
    "list_timers": "list_timers",
    "cancel_timer": "cancel_timer",
    "device_status": "status",
}


class DeviceTools:
    """Dispatch allowlisted appliance commands and correlate their acknowledgements."""

    def __init__(self, websocket, db, speech=None):
        self.websocket = websocket
        self.speech = speech
        self.pending = {}
        self.db = db
        db.execute(
            "CREATE TABLE IF NOT EXISTS device_commands (id TEXT PRIMARY KEY, created REAL, action"
            " TEXT, result TEXT)"
        )
        db.commit()

    async def call(self, name, arguments):
        """Send an allowlisted command, await its acknowledgement and persist the result."""
        if name not in ACTIONS or not isinstance(arguments, dict):
            return {"error": "Unsupported device operation"}
        command_id = uuid.uuid4().hex
        event = dict(arguments, type="device_command", id=command_id, action=ACTIONS[name])
        if name == "create_daily_reminder":
            if self.speech is None:
                return {"error": "Reminder speech is unavailable"}
            event["audio"] = await self.speech(arguments.get("text"))
        future = asyncio.get_running_loop().create_future()
        self.pending[command_id] = future
        try:
            await self.websocket.send_json(event)
            result = await asyncio.wait_for(future, 8)
            if name == "device_status":
                result["backend"] = {
                    "process_uptime_seconds": int(time.monotonic() - STARTED),
                    "clock_unix": time.time(),
                    "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                }
            # Persist acknowledged operations in PVC; appliance maintains executable timer state.
            self.db.execute(
                "INSERT INTO device_commands VALUES (?, ?, ?, ?)",
                (command_id, time.time(), ACTIONS[name], json.dumps(result)),
            )
            self.db.commit()
            return result
        except TimeoutError:
            return {"error": "Device did not acknowledge; do not claim successful execution"}
        finally:
            self.pending.pop(command_id, None)

    def acknowledge(self, event):
        """Resolve the pending future for a device command with the provided result event."""
        future = self.pending.get(event.get("id"))
        if future and not future.done():
            future.set_result(event.get("result", {"error": "Missing result"}))
