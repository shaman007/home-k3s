"""Daily-cycle acceptance, early dismiss, quiet hours, catch-up and restart regressions."""
from datetime import datetime
import asyncio
import base64
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'aiy-voice'))
from reminders import Reminders, ZONE
from local_resources import LocalResources, AudioOutput
from reminder_speech import synthesize


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=ZONE).timestamp()


class RemindersTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:'); self.store = Reminders(self.db)
    def tearDown(self):
        self.db.close()
    def add(self, identity='fish', phrase='покормил рыбок'):
        return self.store.create(identity, 'Покорми рыбок' if identity=='fish' else 'Покорми кошек',
                                 '10:00','22:00',30,phrase,b'\0\0'*24000,
                                 first_date='2026-11-16',stamp=stamp('2026-11-16T08:00'))
    def test_each_slot_fires_once_and_stops_at_22(self):
        self.add()
        self.assertEqual(self.store.due(stamp('2026-11-16T09:59')),[])
        event=self.store.due(stamp('2026-11-16T10:00'))[0]; self.store.delivered(event)
        self.assertEqual(self.store.due(stamp('2026-11-16T10:29')),[])
        self.assertEqual(len(self.store.due(stamp('2026-11-16T10:30'))),1)
        self.assertEqual(self.store.due(stamp('2026-11-16T22:00')),[])
        self.assertEqual(self.store.due(stamp('2026-11-17T09:59')),[])
        self.assertEqual(len(self.store.due(stamp('2026-11-17T10:00'))),1)
    def test_early_completion_closes_only_today_and_only_that_task(self):
        self.add(); self.add('cats','покормил кошек')
        result=self.store.acknowledge('Я уже покормил рыбок',stamp=stamp('2026-11-16T08:15'))
        self.assertTrue(result['ok'])
        self.assertEqual([x['id'] for x in self.store.due(stamp('2026-11-16T10:00'))],['cats'])
        self.assertEqual({x['id'] for x in self.store.due(stamp('2026-11-17T10:00'))},{'fish','cats'})
    def test_semantic_completion_with_explicit_task_and_negative_guards(self):
        self.add()
        self.assertTrue(self.store.acknowledge('Рыбок накормил сегодня',reminder_id='fish',stamp=stamp('2026-11-16T08:00'))['ok'])
        for text in ['не покормил рыбок','покормлю рыбок позже','я покормил рыбок?', 'я вчера покормил рыбок', 'я забыл покормить рыбок', 'если я покормил рыбок', 'я скажу покормил рыбок']:
            self.db.execute('DELETE FROM reminder_acknowledgements');self.db.commit()
            self.assertIn('error',self.store.acknowledge(text,reminder_id='fish',stamp=stamp('2026-11-16T11:00')))
            self.assertFalse(self.store.describe('fish',stamp('2026-11-16T11:00'))['acknowledged_today'])
    def test_duplicate_phrases_require_clarification(self):
        self.add('fish','сделал');self.add('cats','сделал')
        self.assertIn('error',self.store.acknowledge('сделал',stamp=stamp('2026-11-16T11:00')))
        self.assertEqual(len(self.store.due(stamp('2026-11-16T11:00'))),2)
        self.store.acknowledge('сделал',reminder_id='fish',stamp=stamp('2026-11-16T11:00'))
        self.assertIn('error',self.store.acknowledge('сделал',stamp=stamp('2026-11-16T11:01')))
        self.assertFalse(self.store.describe('cats',stamp('2026-11-16T11:01'))['acknowledged_today'])
    def test_restart_preserves_ack_and_no_backlog_storm(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.sqlite';db=sqlite3.connect(path);r=Reminders(db)
            r.create('a','Проверь задачу','10:00','22:00',30,'сделал',b'\0\0',first_date='2026-11-16',stamp=stamp('2026-11-16T08:00'))
            due=r.due(stamp('2026-11-16T15:17'));self.assertEqual(len(due),1);r.delivered(due[0])
            r.acknowledge('сделал',stamp=stamp('2026-11-16T15:18'));db.close()
            db=sqlite3.connect(path);r=Reminders(db)
            self.assertEqual(r.due(stamp('2026-11-16T16:00')),[])
            self.assertEqual(len(r.due(stamp('2026-11-17T10:00'))),1);db.close()
    def test_dst_uses_local_calendar_day(self):
        self.store.create('dst','Проверь задачу','10:00','22:00',30,'сделал',b'\0\0',first_date='2026-10-24',stamp=stamp('2026-10-24T08:00'))
        result=self.store.acknowledge('сделал',stamp=stamp('2026-10-24T11:00'))
        self.assertTrue(result['reminder']['next_notification'].endswith('+01:00'))
        self.assertEqual(len(self.store.due(stamp('2026-10-25T10:00'))),1)
    def test_default_first_start_is_tomorrow_if_start_already_passed(self):
        result=self.store.create('a','Проверь задачу','10:00','22:00',30,'сделал',b'\0\0',stamp=stamp('2026-11-16T15:00'))
        self.assertEqual(result['first_date'],'2026-11-17')
        self.assertEqual(self.store.due(stamp('2026-11-16T15:00')),[])
        self.assertTrue(self.store.acknowledge('сделал',stamp=stamp('2026-11-16T15:00'))['ok'])
        self.assertEqual(len(self.store.due(stamp('2026-11-17T10:00'))),1)
    def test_disabling_differs_from_daily_ack(self):
        self.add();self.store.disable('fish',stamp=stamp('2026-11-16T12:00'))
        self.assertEqual(self.store.due(stamp('2026-11-17T10:00')),[])


class PlaybackTests(unittest.IsolatedAsyncioTestCase):
    async def test_reminders_wait_for_conversation_and_play_offline(self):
        resources = LocalResources(':memory:', Mock(), AsyncMock())
        resources.reminders.now = lambda _stamp=None: datetime(2026,11,16,10,tzinfo=ZONE)
        resources.reminders.create('test','Проверь задачу','10:00','22:00',30,'сделал',b'\0\0',first_date='2026-11-16')
        resources.engaged = True
        task = asyncio.create_task(resources.scheduler())
        try:
            await asyncio.sleep(0.01)
            resources.play_alarm.assert_not_awaited()
            resources.engaged = False
            await asyncio.sleep(0.3)
            resources.play_alarm.assert_awaited_once_with(b'\0\0')
            self.assertEqual(resources.reminders.due(), [])
        finally:
            task.cancel(); await asyncio.gather(task,return_exceptions=True)
            await resources.close()

    async def test_press_interrupts_playback_without_waiting_for_audio_lock(self):
        output = AudioOutput('unused')
        process = Mock(returncode=None)
        process.wait = AsyncMock()
        output.process = process
        async with output.lock:
            await asyncio.wait_for(output.interrupt(),0.1)
        process.terminate.assert_called_once()
        self.assertIs(output.interrupted,process)


class SpeechTests(unittest.IsolatedAsyncioTestCase):
    async def run_speech(self, transcript):
        pcm = b'\0\0'*100
        events = [dict(type='session.updated'),
                  dict(type='response.output_audio.delta',delta=base64.b64encode(pcm).decode()),
                  dict(type='response.output_audio_transcript.done',transcript=transcript),
                  dict(type='response.done',response={'id':'test','status':'completed','usage':{}})]
        class Socket:
            send_json = AsyncMock()
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
            async def __aiter__(self):
                for event in events:
                    yield SimpleNamespace(data=json.dumps(event))
        http = Mock(); http.ws_connect.return_value = Socket()
        ledger = Mock()
        try:
            return await synthesize(http,'fake','Проверь задачу',ledger)
        finally:
            ledger.record.assert_called_once()

    async def test_literal_audio_and_usage_are_retained(self):
        self.assertEqual(base64.b64decode(await self.run_speech('Проверь задачу.')),b'\0\0'*100)

    async def test_changed_spoken_text_is_not_installed(self):
        with self.assertRaisesRegex(ValueError,'did not match'):
            await self.run_speech('Конечно, проверь задачу')
