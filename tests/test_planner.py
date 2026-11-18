import sqlite3
import unittest
from datetime import datetime,timedelta
from unittest.mock import patch

import campus
import journal
import planner
import student


class PersonalPlanTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('CREATE TABLE users(id INTEGER PRIMARY KEY)')
        self.db.execute('INSERT INTO users VALUES (1),(2)')
        for mod in (student,journal,campus,planner):mod.init(self.db)
        self.now=datetime(2026,11,19,8,30,tzinfo=campus.CAMPUS_TZ)
        self.setting=patch('planner.clock',side_effect=lambda:self.now)
        self.setting.start()

    def tearDown(self):
        self.setting.stop();self.db.close()

    def call(self,endpoint='',data=None,uid=1,role='student'):
        with self.db:
            return planner.handle(self.db,{'id':uid,'role':role},'GET' if data is None else 'POST','/api/plan'+endpoint,data or {})

    def entry(self,need='歇一会儿',uid=1,state='published',ago=0):
        stamp=(self.now-timedelta(days=ago)).isoformat()
        with patch('journal.when',return_value=stamp),self.db:
            return journal.handle(self.db,{'role':'student','id':uid},'POST','/api/journal/save',
                                  {'story':'一段自述，无需评分','need':need,'state':state})['id']

    def event(self,start,end):
        self.db.execute("INSERT OR IGNORE INTO campus_events(owner,title,kind,starts,ends,place,origin) VALUES(1,'课','课程',?,?,'','手动')",
                        ('2026-11-19T'+start,'2026-11-19T'+end))
        self.db.commit()

    def test_minute_timer_and_private_ownership(self):
        key=self.entry();self.assertIn('歇一会儿',self.call('/minute',{'entry':key})['reason'])
        with self.assertRaises(ValueError):self.call('/minute',{'entry':key},2)
        with self.assertRaises(PermissionError):self.call('/minute',{'entry':key},role='manager')
        start=self.call('/minute/start',{'entry':key})['started']
        self.assertEqual(start,self.call('/minute/start',{'entry':key})['started'])
        with self.assertRaises(ValueError):self.call('/minute/done',{'entry':key})
        self.now+=timedelta(seconds=60)
        self.assertTrue(self.call('/minute/done',{'entry':key})['done'])
        self.assertTrue(self.call('/minute',{'entry':key})['done'])
        with self.db:self.db.execute('DELETE FROM journal_entries WHERE id=?',(key,))
        self.assertFalse(self.db.execute('SELECT * FROM minute_sessions').fetchall())

    def test_history_calendar_and_editing(self):
        for n in (0,1,2):self.entry(ago=n)
        self.entry(state='draft');self.entry(ago=20);self.entry(uid=2)
        self.event('08:40','10:15')
        result=self.call('/generate',{})
        self.assertEqual(result['samples'],3)
        first=result['items'][0];self.assertEqual((first['kind'],first['time']),('pause','10:15'));self.assertIn('3 篇选择了「歇一会儿」',first['reason'])
        with self.assertRaises(ValueError):self.call('/move',{'id':first['id'],'time':'09:45'})
        with self.assertRaises(ValueError):self.call('/move',{'id':first['id'],'time':'11:05'},uid=2)
        moved=self.call('/move',{'id':first['id'],'time':'11:05'})
        self.assertTrue(moved['items'][0]['adjusted'])
        self.assertEqual(self.call('/generate',{})['items'][0]['time'],'11:05')
        self.event('11:00','12:00');self.assertTrue(self.call()['items'][0]['conflict'])
        self.call('/status',{'id':first['id'],'status':'skipped'});self.assertEqual(self.call()['items'][0]['status'],'skipped')

    def test_no_data_full_day_and_midnight(self):
        self.assertEqual(self.call()['samples'],0)
        self.event('07:00','23:00');self.assertEqual(self.call('/generate',{})['items'],[])
        self.now=self.now.replace(day=20,hour=23);self.assertFalse(self.call()['suggested'])
        self.assertFalse(self.call()['items'])
