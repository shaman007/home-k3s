"""Bounded voice tools for local resources; the model never sees shell/GPIO paths."""

import asyncio
import json
import resource
import time
import uuid

STARTED = time.monotonic()

TOOLS = [
    {
        "type": "function",
        "name": "create_daily_reminder",
        "description": "",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "start_time": {"type": "string", "description": ""},
                "end_time": {"type": "string", "description": ""},
                "repeat_minutes": {"type": "integer"},
                "confirmation_phrase": {
                    "type": "string",
                    "description": "",
                },
                "weekdays": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 7,
                    "uniqueItems": True,
                    "items": {"type": "integer", "minimum": 0, "maximum": 6},
                    "description": "",
                },
                "jitter_minutes": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10,
                    "description": "",
                },
                "first_date": {
                    "type": ["string", "null"],
                    "description": "",
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
        "description": "",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "acknowledge_reminder",
        "description": "",
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
        "description": "",
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
        "description": "",
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
        "description": "",
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
        "description": "",
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
        "description": "",
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
        "description": "",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "cancel_timer",
        "description": "",
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
        "description": "",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]
def appliance_tool(name, description, properties, required):
    """Describe a bounded persistent appliance operation."""
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object", "properties": properties,
            "required": required, "additionalProperties": False,
        },
    }


TOOLS.extend([
    appliance_tool(
        "update_daily_reminder", "",
        {"reminder_id": {"type": "string"}, "changes": {
            "type": "object", "minProperties": 1, "additionalProperties": False,
            "properties": {
                "text": {"type": "string", "minLength": 1, "maxLength": 120},
                "start_time": {"type": "string"}, "end_time": {"type": "string"},
                "repeat_minutes": {"type": "integer", "minimum": 1, "maximum": 720},
                "confirmation_phrase": {"type": "string", "minLength": 1, "maxLength": 100},
                "weekdays": {"type": "array", "minItems": 1, "maxItems": 7,
                             "uniqueItems": True, "items": {"type": "integer",
                                                            "minimum": 0, "maximum": 6}},
                "jitter_minutes": {"type": "integer", "minimum": 0, "maximum": 10},
                "first_date": {"type": "string"},
            }}}, ["reminder_id", "changes"],
    ),
    appliance_tool(
        "suspend_daily_reminder", "",
        {"reminder_id": {"type": "string"},
         "until_date": {"type": "string", "description": ""}},
        ["reminder_id", "until_date"],
    ),
    appliance_tool(
        "resume_daily_reminder", "",
        {"reminder_id": {"type": "string"}}, ["reminder_id"],
    ),
    appliance_tool(
        "update_reminder_interval",
        "",
        {
            "reminder_id": {"type": "string"},
            "repeat_minutes": {"type": "integer", "minimum": 1, "maximum": 720},
        },
        ["reminder_id", "repeat_minutes"],
    ),
    appliance_tool(
        "save_note",
        "",
        {"text": {"type": "string", "minLength": 1, "maxLength": 4000}},
        ["text"],
    ),
    appliance_tool(
        "list_notes",
        "",
        {}, [],
    ),
])

ACTIONS = {
    "update_daily_reminder": "update_daily_reminder",
    "suspend_daily_reminder": "suspend_daily_reminder",
    "resume_daily_reminder": "resume_daily_reminder",
    "update_reminder_interval": "update_reminder_interval",
    "save_note": "save_note",
    "list_notes": "list_notes",
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
        elif name == "update_daily_reminder" and "text" in arguments.get("changes", {}):
            if self.speech is None:
                return {"error": "Reminder speech is unavailable"}
            event["audio"] = await self.speech(arguments["changes"]["text"])
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
