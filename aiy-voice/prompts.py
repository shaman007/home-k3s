"""Read model-facing instructions only from the OpenBao/ESO-mounted secret."""

import copy
import json
import os
from pathlib import Path

TEXT_KEYS = (
    "voice", "session_time_prefix", "live_reminder_prefix", "task_data_prefix",
    "web_search", "reminder_speech", "memory_notice",
)
MAX_BYTES = 131072


def load_prompts():
    """Read a complete secret projection without caching or logging its contents."""
    try:
        path = Path(os.environ.get("AIY_PROMPTS_FILE", "/run/aiy-prompts/bundle.json"))
        with path.open("rb") as source:
            raw = source.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError
        bundle = json.loads(raw)
        if not isinstance(bundle, dict) or bundle.get("version") != 1:
            raise ValueError
        if set(bundle) != {"version", "tools", *TEXT_KEYS}:
            raise ValueError
        if any(not isinstance(bundle[k], str) or not bundle[k].strip() for k in TEXT_KEYS):
            raise ValueError
        if bundle["web_search"].count("{now}") != 1:
            raise ValueError
        if not isinstance(bundle["tools"], dict):
            raise ValueError
        for name, descriptions in bundle["tools"].items():
            if not isinstance(name, str) or not isinstance(descriptions, dict):
                raise ValueError
            if any(not isinstance(k, str) or not isinstance(v, str) or not v.strip()
                   for k, v in descriptions.items()):
                raise ValueError
        return bundle
    except (OSError, ValueError, TypeError, KeyError):
        raise RuntimeError("AIY prompt secret is unavailable or invalid") from None


def _description_paths(value, prefix=""):
    """Identify only description slots; secret data cannot change tool contracts."""
    found = {}
    if isinstance(value, dict):
        for key, item in value.items():
            path = prefix + "/" + key.replace("~", "~0").replace("/", "~1")
            if key == "description":
                found[path] = (value, key)
            else:
                found.update(_description_paths(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.update(_description_paths(item, prefix + "/" + str(index)))
    return found


def describe_tools(tools, bundle):
    """Fill text slots only; reject missing/extra tools or schema description paths."""
    if set(bundle["tools"]) != {tool["name"] for tool in tools}:
        raise RuntimeError("AIY prompt tool catalog does not match runtime")
    result = copy.deepcopy(tools)
    for tool in result:
        slots = _description_paths(tool)
        values = bundle["tools"][tool["name"]]
        if set(slots) != set(values):
            raise RuntimeError("AIY prompt descriptions do not match runtime")
        for path, (parent, key) in slots.items():
            parent[key] = values[path]
    return result
