"""Independent daily reminder cycles, persisted on the appliance in local time."""

import hashlib
import re
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from datetime import time as wall_time
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Europe/Prague")
MAX_AUDIO = 24000 * 2 * 15


def normalized(text):
    """Normalize text for comparison by lowercasing, removing punctuation, and collapsing
    whitespace.
    """
    return " ".join(re.sub(r"[^\w\s]", " ", text.casefold().replace("ё", "е")).split())


def confirms(statement, phrase):
    """Accept an explicit positive statement; questions/negation/examples cannot dismiss."""
    if not isinstance(statement, str) or "?" in statement or "？" in statement:
        return False
    statement, phrase = normalized(statement), normalized(phrase)
    return statement in {
        prefix + phrase for prefix in ("", "я ", "уже ", "я уже ", "да ", "да я ", "да я уже ")
    }


def completed_statement(statement):
    """Conservative guard on full verbatim evidence when the voice model identifies a task."""
    if not isinstance(statement, str) or "?" in statement or "？" in statement:
        return False
    text = normalized(statement)
    tokens = set(text.split())
    blocked = {
        "не",
        "нет",
        "потом",
        "позже",
        "завтра",
        "вчера",
        "позавчера",
        "если",
        "ли",
        "приму",
        "выпью",
        "покормлю",
        "сделаю",
        "собираюсь",
        "надо",
        "нужно",
        "хочу",
        "планирую",
        "возможно",
        "наверное",
        "может",
        "скажу",
        "например",
        "кажется",
        "забыл",
        "забыла",
        "забыли",
        "пропустил",
        "отложил",
        "думал",
        "думала",
    }
    blocked |= {"бы", "хотел", "хотела", "скажи", "напомни", "напомнил", "напомнила"}
    if tokens & blocked:
        return False
    return bool(
        re.search(
            r"\b(?:\w+(?:ал|ала|али|ил|ила|или|ел|ела|ели|ыл|ыла|ыли|ял|яла|яли|нул|нула|нули)|"
            r"готов[аоы]?|сделан[аоы]?|выполнен[аоы]?|завершен[аоы]?|"
            r"накормлен[аоы]?|покормлен[аоы]?|"
            r"принят[аоы]?|выпит[аоы]?|обслужен[аоы]?|сыт[аоы]?)\b",
            text,
        )
    )


def minute(value):
    """Parse an HH:MM string into total minutes since midnight."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}", value):
        raise ValueError("Time must be HH:MM")
    hour, minutes = map(int, value.split(":"))
    if hour > 23 or minutes > 59:
        raise ValueError("Invalid local time")
    return hour * 60 + minutes


@dataclass(frozen=True)
class ReminderSpec:
    """Validated-on-create content and recurrence options for one reminder."""

    text: str
    start_time: str
    end_time: str
    repeat_minutes: int
    confirmation_phrase: str
    weekdays: list[int] | None = None
    jitter_minutes: int = 0


def _validate_content(spec, audio):
    """Reject invalid speech content and malformed cached PCM before storing it."""
    if not isinstance(spec.text, str) or not 1 <= len(spec.text.strip()) <= 120:
        raise ValueError("Reminder text must be 1–120 characters")
    if (
        not isinstance(spec.confirmation_phrase, str)
        or not 1 <= len(spec.confirmation_phrase.strip()) <= 100
    ):
        raise ValueError("Explicit confirmation phrase required")
    if (
        "?" in spec.confirmation_phrase
        or not normalized(spec.confirmation_phrase)
        or set(normalized(spec.confirmation_phrase).split()) & {"не", "нет", "вчера", "завтра"}
    ):
        raise ValueError("Confirmation must be an affirmative statement")
    if not isinstance(audio, bytes) or not audio or len(audio) > MAX_AUDIO or len(audio) % 2:
        raise ValueError("Invalid cached reminder audio")


def _recurrence(spec):
    """Validate the local window and return its bounds and weekday mask."""
    start, end = minute(spec.start_time), minute(spec.end_time)
    if end <= start:
        raise ValueError("Daily window must end after it starts; no overnight reminders")
    if (
        isinstance(spec.repeat_minutes, bool)
        or not isinstance(spec.repeat_minutes, int)
        or not 1 <= spec.repeat_minutes <= 720
    ):
        raise ValueError("Repeat interval must be 1–720 whole minutes")
    days = list(range(7)) if spec.weekdays is None else spec.weekdays
    if (
        not isinstance(days, list)
        or not days
        or any((not isinstance(x, int) or isinstance(x, bool)) or not 0 <= x <= 6 for x in days)
    ):
        raise ValueError("Weekdays must be a non-empty list, Monday=0 through Sunday=6")
    mask = sum(1 << x for x in set(days))
    if (
        (not isinstance(spec.jitter_minutes, int) or isinstance(spec.jitter_minutes, bool))
        or not 0 <= spec.jitter_minutes <= 10
        or spec.jitter_minutes * 2 >= spec.repeat_minutes
    ):
        raise ValueError("Jitter must be 0–10 minutes and less than half the repeat interval")
    return start, end, mask


class Reminders:
    """A confirmation closes one reminder for one Prague calendar date, never forever."""

    def __init__(self, db):
        self.db = db
        self.slot_cache = {}
        db.execute(
            "CREATE TABLE IF NOT EXISTS daily_reminders (id TEXT PRIMARY KEY, text TEXT, start"
            " INTEGER, end INTEGER, repeat INTEGER, phrase TEXT, first_date TEXT, enabled INTEGER,"
            " audio BLOB, last_date TEXT, last_slot INTEGER)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS reminder_acknowledgements (id TEXT, day TEXT, at REAL,"
            " PRIMARY KEY(id, day))"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS reminder_recurrence (id TEXT PRIMARY KEY, weekdays INTEGER"
            " NOT NULL, jitter INTEGER NOT NULL, seed TEXT NOT NULL)"
        )
        db.commit()

        db.execute("CREATE TABLE IF NOT EXISTS reminder_suspensions "
                   "(id TEXT PRIMARY KEY, until_date TEXT NOT NULL)")
        db.commit()

    def now(self, stamp=None):
        """Convert the supplied timestamp, or the current clock, to Prague local time."""
        return datetime.fromtimestamp(time.time() if stamp is None else stamp, ZONE)

    def create(self, identity, spec, audio, *, first_date=None, stamp=None):
        """Validate and persist a reminder, returning existing identities unchanged."""
        existing = self.db.execute(
            "SELECT id FROM daily_reminders WHERE id=?", (identity,)
        ).fetchone()
        if existing:
            return self.describe(identity, stamp)
        _validate_content(spec, audio)
        start, end, mask = _recurrence(spec)
        if (
            self.db.execute("SELECT count(*) FROM daily_reminders WHERE enabled=1").fetchone()[0]
            >= 16
        ):
            raise ValueError("At most 16 daily reminders are supported")
        duplicates = self.db.execute(
            "SELECT id FROM daily_reminders WHERE enabled=1 AND text=? AND start=? AND end=? AND"
            " repeat=? AND phrase=?",
            (spec.text.strip(), start, end, spec.repeat_minutes, spec.confirmation_phrase.strip()),
        ).fetchall()
        for duplicate in duplicates:
            old = self.row(duplicate[0])
            if old["weekdays"] == mask and old["jitter"] == spec.jitter_minutes:
                return self.describe(duplicate[0], stamp)
        now = self.now(stamp)
        if first_date is None:
            first = now.date() + timedelta(days=int(now.hour * 60 + now.minute >= start))
        else:
            first = date.fromisoformat(first_date)
            if first < now.date():
                raise ValueError("First date cannot be in the past")
        with self.db:
            self.db.execute(
                "INSERT INTO daily_reminders VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, NULL, -1)",
                (
                    identity,
                    spec.text.strip(),
                    start,
                    end,
                    spec.repeat_minutes,
                    spec.confirmation_phrase.strip(),
                    first.isoformat(),
                    audio,
                ),
            )
            self.db.execute(
                "INSERT INTO reminder_recurrence VALUES (?, ?, ?, ?)",
                (identity, mask, spec.jitter_minutes, uuid.uuid4().hex),
            )
        return self.describe(identity, stamp)

    def row(self, identity):
        """Fetch and reconstruct the full reminder record including recurrence data."""
        row = self.db.execute("SELECT * FROM daily_reminders WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise ValueError("Unknown reminder")
        result = dict(
            zip(
                (
                    "id",
                    "text",
                    "start",
                    "end",
                    "repeat",
                    "phrase",
                    "first_date",
                    "enabled",
                    "audio",
                    "last_date",
                    "last_slot",
                ),
                row,
            )
        )
        recurrence = self.db.execute(
            "SELECT weekdays,jitter,seed FROM reminder_recurrence WHERE id=?", (identity,)
        ).fetchone()
        result.update(zip(("weekdays", "jitter", "seed"), recurrence or (127, 0, identity)))
        return result

    def active_day(self, row, day):
        """Check if a reminder is scheduled for a specific date based on first date and weekdays."""
        paused = self.pause_until(row["id"])
        return (day.isoformat() >= max(row["first_date"], paused or row["first_date"])
                and bool(row["weekdays"] & (1 << day.weekday())))

    def pause_until(self, identity):
        """Return the exclusive end of a persistent pause, including expired history."""
        row = self.db.execute("SELECT until_date FROM reminder_suspensions WHERE id=?",
                              (identity,)).fetchone()
        return row[0] if row else None

    def suspend(self, identity, until_date, stamp=None):
        """Pause until midnight on a local date without completing or disabling the task."""
        self.row(identity)
        if not isinstance(until_date, str):
            raise ValueError("Resume date must be YYYY-MM-DD")
        target = date.fromisoformat(until_date)
        if not 1 <= (target - self.now(stamp).date()).days <= 366:
            raise ValueError("Resume date must be within the next 366 days")
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO reminder_suspensions VALUES (?, ?)",
                            (identity, target.isoformat()))
        return {"ok": True, "reminder": self.describe(identity, stamp)}

    def resume(self, identity, stamp=None):
        """Resume early, preserving acknowledgements and skipping elapsed slots."""
        row = self.row(identity)
        now = self.now(stamp)
        with self.db:
            self.db.execute("DELETE FROM reminder_suspensions WHERE id=?", (identity,))
            self.db.execute("UPDATE daily_reminders SET last_date=?,last_slot=? WHERE id=?",
                            (now.date().isoformat(), self.elapsed_slot(row, now), identity))
        return {"ok": True, "reminder": self.describe(identity, stamp)}

    def elapsed_slot(self, row, now):
        """Identify the most recent elapsed slot on the current schedule."""
        return max((slot for slot, at in self.slots(row, now.date()) if at <= now), default=-1)

    def update(self, identity, changes, audio=None, stamp=None):
        """Validate an additive edit before replacing schedule/content; retain task history."""
        row = self.row(identity)
        fields = {"text", "start_time", "end_time", "repeat_minutes", "confirmation_phrase",
                  "weekdays", "jitter_minutes", "first_date"}
        if not isinstance(changes, dict) or not changes or set(changes) - fields:
            raise ValueError("Invalid reminder changes")
        values = {**self.describe(identity, stamp), **changes}
        spec = ReminderSpec(*(values[k] for k in
                              ("text", "start_time", "end_time", "repeat_minutes",
                               "confirmation_phrase", "weekdays", "jitter_minutes")))
        if values["text"] != row["text"] and audio is None:
            raise ValueError("Updated reminder text requires updated speech")
        audio = row["audio"] if audio is None else audio
        _validate_content(spec, audio)
        start, end, mask = _recurrence(spec)
        first = date.fromisoformat(values["first_date"])
        now = self.now(stamp)
        if "first_date" in changes and first < now.date():
            raise ValueError("First date cannot be in the past")
        row.update(start=start, end=end, repeat=spec.repeat_minutes, jitter=spec.jitter_minutes)
        with self.db:
            self.db.execute("UPDATE daily_reminders SET text=?, start=?, end=?, repeat=?, phrase=?,"
                            "first_date=?, audio=?, last_date=?, last_slot=? WHERE id=?",
                            (spec.text.strip(), start, end, spec.repeat_minutes,
                             spec.confirmation_phrase.strip(), first.isoformat(), audio,
                             now.date().isoformat(), self.elapsed_slot(row, now), identity))
            self.db.execute("INSERT OR REPLACE INTO reminder_recurrence VALUES (?, ?, ?, ?)",
                            (identity, mask, spec.jitter_minutes, row["seed"]))
        return {"ok": True, "reminder": self.describe(identity, stamp)}

    def slots(self, row, day):
        """Stable random offsets per task/date/nominal slot; never redraw while polling."""
        key = (row["seed"], day, row["start"], row["end"], row["repeat"], row["jitter"])
        if key in self.slot_cache:
            return self.slot_cache[key]
        result = []
        midnight = datetime.combine(day, wall_time(), ZONE)
        for slot, minute_of_day in enumerate(range(row["start"], row["end"], row["repeat"])):
            radius = row["jitter"] * 60
            digest = hashlib.sha256(f"{row['seed']}:{day.isoformat()}:{slot}".encode()).digest()
            offset = int.from_bytes(digest[:8], "big") % (2 * radius + 1) - radius
            second = max(0, min(minute_of_day * 60 + offset, row["end"] * 60 - 1))
            result.append((slot, midnight + timedelta(seconds=second)))
        if len(self.slot_cache) >= 64:
            self.slot_cache.clear()
        self.slot_cache[key] = result
        return result

    def acknowledged(self, identity, day):
        """Return the saved acknowledgement timestamp for one reminder and local day."""
        return self.db.execute(
            "SELECT at FROM reminder_acknowledgements WHERE id=? AND day=?", (identity, day)
        ).fetchone()

    def due(self, stamp=None):
        """Return reminders that are currently due for delivery, excluding acknowledged ones."""
        now = self.now(stamp)
        day = now.date().isoformat()
        minutes = now.hour * 60 + now.minute
        result = []
        for (identity,) in self.db.execute("SELECT id FROM daily_reminders WHERE enabled=1"):
            row = self.row(identity)
            if (
                not self.active_day(row, now.date())
                or minutes >= row["end"]
                or self.acknowledged(identity, day)
            ):
                continue
            eligible = [
                (slot, at)
                for slot, at in self.slots(row, now.date())
                if at.timestamp() <= now.timestamp()
            ]
            if not eligible:
                continue
            slot, scheduled = eligible[-1]
            if row["last_date"] != day or slot > row["last_slot"]:
                result.append(
                    {
                        "id": identity,
                        "day": day,
                        "slot": slot,
                        "audio": row["audio"],
                        "scheduled_for": scheduled.isoformat(),
                    }
                )
        return result

    def update_interval(self, identity, minutes, stamp=None):
        """Persist a new interval without replaying old slots or losing completion facts."""
        row = self.row(identity)
        if (isinstance(minutes, bool) or not isinstance(minutes, int)
                or not 1 <= minutes <= 720 or minutes <= 2 * row["jitter"]):
            raise ValueError("Invalid repeat interval for configured jitter")
        if minutes == row["repeat"]:
            return {"ok": True, "reminder": self.describe(identity, stamp)}
        now = self.now(stamp)
        row["repeat"] = minutes
        elapsed = [slot for slot, at in self.slots(row, now.date())
                   if at.timestamp() <= now.timestamp()]
        with self.db:
            self.db.execute(
                "UPDATE daily_reminders SET repeat=?, last_date=?, last_slot=? WHERE id=?",
                (minutes, now.date().isoformat(), max(elapsed, default=-1), identity),
            )
        return {"ok": True, "reminder": self.describe(identity, stamp)}

    def delivered(self, event):
        """Mark a reminder slot as delivered for the current day."""
        # An interval may change while the old cached speech is still playing.
        slots = dict(self.slots(self.row(event["id"]), date.fromisoformat(event["day"])))
        current = slots.get(event["slot"])
        if current is None or current.isoformat() != event["scheduled_for"]:
            return
        self.db.execute(
            "UPDATE daily_reminders SET last_date=?, last_slot=? WHERE id=?",
            (event["day"], event["slot"], event["id"]),
        )
        self.db.commit()

    def describe(self, identity, stamp=None):
        """Generate a detailed status object for a reminder, including next notification time."""
        row = self.row(identity)
        now = self.now(stamp)
        day = now.date()
        ack = self.acknowledged(identity, day.isoformat())
        paused_until = self.pause_until(identity)
        target_day = max(day, date.fromisoformat(row["first_date"]),
                         date.fromisoformat(paused_until) if paused_until else day)
        due_at = None
        for _ in range(8):
            if self.active_day(row, target_day) and not (
                target_day == day and (ack or now.hour * 60 + now.minute >= row["end"])
            ):
                slots = self.slots(row, target_day)
                if target_day == day:
                    delivered = row["last_slot"] if row["last_date"] == day.isoformat() else -1
                    pending = [(slot, at) for slot, at in slots if slot > delivered]
                    overdue = [
                        (slot, at) for slot, at in pending if at.timestamp() <= now.timestamp()
                    ]
                    if overdue:
                        due_at = overdue[-1][1]
                    elif pending:
                        due_at = pending[0][1]
                else:
                    due_at = slots[0][1]
                if due_at is not None:
                    break
            target_day += timedelta(days=1)
        return {
            "id": identity,
            "text": row["text"],
            "start_time": f"{row['start']//60:02}:{row['start']%60:02}",
            "end_time": f"{row['end']//60:02}:{row['end']%60:02}",
            "repeat_minutes": row["repeat"],
            "confirmation_phrase": row["phrase"],
            "enabled": bool(row["enabled"]),
            "paused_until": paused_until,
            "paused": bool(paused_until and day.isoformat() < paused_until),
            "first_date": row["first_date"],
            "acknowledged_today": bool(ack),
            "acknowledged_at": ack[0] if ack else None,
            "weekdays": [x for x in range(7) if row["weekdays"] & (1 << x)],
            "scheduled_today": self.active_day(row, day),
            "jitter_minutes": row["jitter"],
            "next_notification": due_at.isoformat() if row["enabled"] and due_at else None,
            "timezone": str(ZONE),
        }

    def list(self, stamp=None):
        """Return a list of descriptions for all enabled daily reminders."""
        return [
            self.describe(row[0], stamp)
            for row in self.db.execute(
                "SELECT id FROM daily_reminders WHERE enabled=1 ORDER BY start,id"
            )
        ]

    def acknowledge(self, statement, reminder_id=None, stamp=None):
        """Mark a reminder as completed for today if the statement matches uniquely."""
        now = self.now(stamp)
        day = now.date().isoformat()
        matches = [
            item
            for item in self.list(stamp)
            if now.weekday() in item["weekdays"]
            if (reminder_id is None or item["id"] == reminder_id)
            and (
                confirms(statement, item["confirmation_phrase"])
                or reminder_id is not None
                and completed_statement(statement)
            )
        ]
        if len(matches) != 1:
            return {
                "error": (
                    "No unique affirmative completion for today; clarify the task or date, do not"
                    " demand a fixed phrase"
                ),
                "matching_reminders": [{"id": x["id"], "text": x["text"]} for x in matches],
            }
        identity = matches[0]["id"]
        self.db.execute(
            "INSERT OR IGNORE INTO reminder_acknowledgements VALUES (?, ?, ?)",
            (identity, day, now.timestamp()),
        )
        self.db.commit()
        return {
            "ok": True,
            "acknowledged_for_date": day,
            "reminder": self.describe(identity, stamp),
        }

    def disable(self, identity, stamp=None):
        """Permanently disable a reminder by setting its enabled flag to false."""
        self.row(identity)
        self.db.execute("UPDATE daily_reminders SET enabled=0 WHERE id=?", (identity,))
        self.db.commit()
        return {"ok": True, "reminder": self.describe(identity, stamp)}
