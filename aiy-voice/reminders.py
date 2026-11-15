"""Independent daily reminder cycles, persisted on the appliance in local time."""
from datetime import datetime, time as wall_time, timedelta, date
import re
import sqlite3
import time
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Europe/Prague')
MAX_AUDIO = 24000 * 2 * 15


def normalized(text):
    return ' '.join(re.sub(r'[^\w\s]', ' ', text.casefold().replace('ё', 'е')).split())


def confirms(statement, phrase):
    """Accept an explicit positive statement; questions/negation/examples cannot dismiss."""
    if not isinstance(statement, str) or '?' in statement or '？' in statement:
        return False
    statement, phrase = normalized(statement), normalized(phrase)
    return statement in {prefix + phrase for prefix in ('', 'я ', 'уже ', 'я уже ', 'да ', 'да я ', 'да я уже ')}


def completed_statement(statement):
    """Conservative guard on full verbatim evidence when the voice model identifies a task."""
    if not isinstance(statement, str) or '?' in statement or '？' in statement:
        return False
    text = normalized(statement); tokens = set(text.split())
    blocked = {'не', 'нет', 'потом', 'позже', 'завтра', 'вчера', 'позавчера', 'если', 'ли',
               'приму', 'выпью', 'покормлю', 'сделаю', 'собираюсь', 'надо', 'нужно', 'хочу',
               'планирую', 'возможно', 'наверное', 'может', 'скажу', 'например', 'кажется',
               'забыл', 'забыла', 'забыли', 'пропустил', 'отложил', 'думал', 'думала'}
    blocked |= {'бы', 'хотел', 'хотела', 'скажи', 'напомни', 'напомнил', 'напомнила'}
    if tokens & blocked:
        return False
    return bool(re.search(r'\b(?:\w+(?:ал|ала|али|ил|ила|или|ел|ела|ели|ыл|ыла|ыли|ял|яла|яли|нул|нула|нули)|готов[аоы]?|сделан[аоы]?|выполнен[аоы]?|завершен[аоы]?|накормлены|покормлены|приняты|выпиты)\b', text))


def minute(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{2}:\d{2}', value):
        raise ValueError('Time must be HH:MM')
    hour, minutes = map(int, value.split(':'))
    if hour > 23 or minutes > 59:
        raise ValueError('Invalid local time')
    return hour * 60 + minutes


class Reminders:
    """A confirmation closes one reminder for one Prague calendar date, never forever."""
    def __init__(self, db):
        self.db = db
        db.execute('CREATE TABLE IF NOT EXISTS daily_reminders (id TEXT PRIMARY KEY, text TEXT, start INTEGER, end INTEGER, repeat INTEGER, phrase TEXT, first_date TEXT, enabled INTEGER, audio BLOB, last_date TEXT, last_slot INTEGER)')
        db.execute('CREATE TABLE IF NOT EXISTS reminder_acknowledgements (id TEXT, day TEXT, at REAL, PRIMARY KEY(id, day))')
        db.commit()

    def now(self, stamp=None):
        return datetime.fromtimestamp(time.time() if stamp is None else stamp, ZONE)

    def create(self, identity, text, start_time, end_time, repeat_minutes, confirmation_phrase, audio,
               first_date=None, stamp=None):
        existing = self.db.execute('SELECT id FROM daily_reminders WHERE id=?', (identity,)).fetchone()
        if existing:
            return self.describe(identity, stamp)
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 120:
            raise ValueError('Reminder text must be 1–120 characters')
        if not isinstance(confirmation_phrase, str) or not 1 <= len(confirmation_phrase.strip()) <= 100:
            raise ValueError('Explicit confirmation phrase required')
        if '?' in confirmation_phrase or not normalized(confirmation_phrase) or set(normalized(confirmation_phrase).split()) & {'не', 'нет', 'вчера', 'завтра'}:
            raise ValueError('Confirmation must be an affirmative statement')
        if not isinstance(audio, bytes) or not audio or len(audio) > MAX_AUDIO or len(audio) % 2:
            raise ValueError('Invalid cached reminder audio')
        start, end = minute(start_time), minute(end_time)
        if end <= start:
            raise ValueError('Daily window must end after it starts; no overnight reminders')
        if isinstance(repeat_minutes, bool) or not isinstance(repeat_minutes, int) or not 1 <= repeat_minutes <= 720:
            raise ValueError('Repeat interval must be 1–720 whole minutes')
        if self.db.execute('SELECT count(*) FROM daily_reminders WHERE enabled=1').fetchone()[0] >= 16:
            raise ValueError('At most 16 daily reminders are supported')
        duplicate = self.db.execute('SELECT id FROM daily_reminders WHERE enabled=1 AND text=? AND start=? AND end=? AND repeat=? AND phrase=?',
                                    (text.strip(), start, end, repeat_minutes, confirmation_phrase.strip())).fetchone()
        if duplicate:
            return self.describe(duplicate[0], stamp)
        now = self.now(stamp)
        if first_date is None:
            first = now.date() + timedelta(days=int(now.hour * 60 + now.minute >= start))
        else:
            first = date.fromisoformat(first_date)
            if first < now.date():
                raise ValueError('First date cannot be in the past')
        self.db.execute('INSERT INTO daily_reminders VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, NULL, -1)',
                        (identity, text.strip(), start, end, repeat_minutes, confirmation_phrase.strip(), first.isoformat(), audio))
        self.db.commit()
        return self.describe(identity, stamp)

    def row(self, identity):
        row = self.db.execute('SELECT * FROM daily_reminders WHERE id=?', (identity,)).fetchone()
        if row is None:
            raise ValueError('Unknown reminder')
        return dict(zip(('id', 'text', 'start', 'end', 'repeat', 'phrase', 'first_date', 'enabled',
                         'audio', 'last_date', 'last_slot'), row))

    def acknowledged(self, identity, day):
        return self.db.execute('SELECT at FROM reminder_acknowledgements WHERE id=? AND day=?',
                               (identity, day)).fetchone()

    def due(self, stamp=None):
        now = self.now(stamp); day = now.date().isoformat(); minutes = now.hour * 60 + now.minute
        result = []
        for (identity,) in self.db.execute('SELECT id FROM daily_reminders WHERE enabled=1'):
            row = self.row(identity)
            if day < row['first_date'] or not row['start'] <= minutes < row['end'] or self.acknowledged(identity, day):
                continue
            slot = (minutes - row['start']) // row['repeat']
            if row['last_date'] != day or slot > row['last_slot']:
                result.append({'id': identity, 'day': day, 'slot': slot, 'audio': row['audio']})
        return result

    def delivered(self, event):
        self.db.execute('UPDATE daily_reminders SET last_date=?, last_slot=? WHERE id=?',
                        (event['day'], event['slot'], event['id']))
        self.db.commit()

    def describe(self, identity, stamp=None):
        row = self.row(identity); now = self.now(stamp); day = now.date(); clock = now.hour * 60 + now.minute
        ack = self.acknowledged(identity, day.isoformat())
        target_day = max(day, date.fromisoformat(row['first_date']))
        target_minute = row['start']
        if target_day == day:
            if ack or clock >= row['end']:
                target_day += timedelta(days=1)
            elif clock >= row['start']:
                slot = (clock - row['start']) // row['repeat']
                if row['last_date'] == day.isoformat() and row['last_slot'] >= slot:
                    target_minute = row['start'] + (row['last_slot'] + 1) * row['repeat']
                    if target_minute >= row['end']:
                        target_day += timedelta(days=1); target_minute = row['start']
                else:
                    target_minute = clock
        due_at = datetime.combine(target_day, wall_time(target_minute // 60, target_minute % 60), ZONE)
        return {'id': identity, 'text': row['text'], 'start_time': f"{row['start']//60:02}:{row['start']%60:02}",
                'end_time': f"{row['end']//60:02}:{row['end']%60:02}", 'repeat_minutes': row['repeat'],
                'confirmation_phrase': row['phrase'], 'enabled': bool(row['enabled']), 'first_date': row['first_date'],
                'acknowledged_today': bool(ack), 'acknowledged_at': ack[0] if ack else None,
                'next_notification': due_at.isoformat() if row['enabled'] else None, 'timezone': str(ZONE)}

    def list(self, stamp=None):
        return [self.describe(row[0], stamp) for row in self.db.execute('SELECT id FROM daily_reminders WHERE enabled=1 ORDER BY start,id')]

    def acknowledge(self, statement, reminder_id=None, stamp=None):
        now = self.now(stamp); day = now.date().isoformat()
        matches = [item for item in self.list(stamp)
                   if (reminder_id is None or item['id'] == reminder_id)
                   and (confirms(statement, item['confirmation_phrase'])
                        or reminder_id is not None and completed_statement(statement))]
        if len(matches) != 1:
            return {'error': 'No unique explicit confirmation; ask which task and its confirmation phrase',
                    'matching_reminders': [{'id': x['id'], 'text': x['text']} for x in matches]}
        identity = matches[0]['id']
        self.db.execute('INSERT OR IGNORE INTO reminder_acknowledgements VALUES (?, ?, ?)',
                        (identity, day, now.timestamp()))
        self.db.commit()
        return {'ok': True, 'acknowledged_for_date': day, 'reminder': self.describe(identity, stamp)}

    def disable(self, identity, stamp=None):
        self.row(identity)
        self.db.execute('UPDATE daily_reminders SET enabled=0 WHERE id=?', (identity,)); self.db.commit()
        return {'ok': True, 'reminder': self.describe(identity, stamp)}
