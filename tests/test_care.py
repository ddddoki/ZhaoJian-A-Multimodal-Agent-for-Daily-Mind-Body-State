from datetime import datetime, timedelta, timezone
import sqlite3
import unittest
from unittest.mock import patch

import care
import journal
import manager
import student


class ClassCare(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT,username TEXT,cohort TEXT,role TEXT)')
        self.db.executemany('INSERT INTO users VALUES(?,?,?,?,?)',[
            (1,'林同学','lin','B','student'),(2,'陈老师','chen','A','manager'),(3,'吴老师','wu','B','manager'),
            (4,'林同学','lin2','B','student'),(5,'郑老师','zheng','A','manager'),(6,'运营','ops','A','operator')])
        self.db.commit()
        for mod in (manager,journal,student,care):mod.init(self.db)
        self.now=datetime(2026,11,19,8,tzinfo=timezone.utc)
        stamp=patch('care.clock',side_effect=lambda:self.now);stamp.start();self.addCleanup(stamp.stop)
        self.addCleanup(self.db.close)

    def api(self,uid,op,payload=None):
        user=dict(self.db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone())
        with self.db:return care.handle(self.db,user,'GET' if payload is None else 'POST','/api/care/'+op,payload or {})

    def invite(self,manager_id=2):
        self.api(manager_id,'invite',{'field':'username','query':'lin'})
        return self.api(1,'student')['invitations'][0]['id']

    def join(self,manager_id=2):
        self.api(1,'decision',{'id':self.invite(manager_id),'decision':'accept'})

    def allow(self,teacher=2):
        self.api(1,'allow',{'teacher':teacher,'days':3,'confirmed':True})

    def entry(self,ago,words,state='published'):
        with self.db:
            result=journal.handle(self.db,{'id':1,'role':'student'},'POST','/api/journal/save',
                {'state':state,'story':'机密原文','words':words})
            self.db.execute('UPDATE journal_entries SET created=? WHERE id=?',
                            ((self.now-timedelta(days=ago)).isoformat(timespec='seconds'),result['id']))

    def test_enrol_and_transfer(self):
        with self.assertRaises(ValueError):self.api(2,'invite',{'field':'name','query':'林同学'})
        with self.assertRaises(ValueError):self.api(2,'invite',{'field':'name','query':'林'})
        key=self.invite()
        self.assertEqual(self.invite(),key)
        with self.assertRaises(ValueError):self.api(4,'decision',{'id':key,'decision':'accept'})
        self.api(1,'decision',{'id':key,'decision':'decline'})
        self.assertEqual(self.api(1,'student')['cohort'],'B')
        self.allow(3)
        with self.db:self.db.execute("""INSERT INTO support_shares(id,student,recipient,topic,summary,created,expires)
            VALUES('old',1,3,'学业安排','私密内容','2026-11-18','2026-12-18')""")
        self.join()
        self.assertEqual(self.api(1,'student')['cohort'],'A')
        self.assertTrue(self.db.execute("SELECT revoked FROM support_shares WHERE id='old'").fetchone()[0])
        with self.assertRaises(PermissionError):self.api(2,'curve',{'student':1})
        self.join(3)
        with self.assertRaises(PermissionError):self.api(3,'curve',{'student':1})

    def test_permission_and_alert(self):
        self.join();self.entry(1,['焦虑','委屈']);self.entry(0,['委屈'])
        self.entry(3,['松了一口气','开心']);self.entry(2,['自定义心情','说不清']);self.entry(2,['好奇'],'draft')
        self.entry(6,['平静','自定义心情'])
        self.assertNotIn('flag_day',self.api(2,'manager')['roster'][0])
        self.allow()
        preview=self.api(1,'student')['preview'];curve=self.api(2,'curve',{'student':1})
        self.assertEqual(curve['points'],preview['points'])
        self.assertEqual([p['value'] for p in curve['points']],[0,None,None,1,None,-1,-1])
        self.assertEqual(curve['flag_day'],'2026-11-19')
        for private in ('机密原文','焦虑','story','gender','words','照片'):self.assertNotIn(private,str(curve))
        self.api(2,'follow',{'student':1,'day':curve['flag_day']})
        self.assertTrue(self.api(2,'manager')['roster'][0]['followed'])
        self.assertTrue(self.api(1,'student')['visits'])
        with self.assertRaises(PermissionError):self.api(5,'curve',{'student':1})
        with self.assertRaises(PermissionError):self.api(3,'curve',{'student':1})
        self.api(1,'revoke',{'teacher':2})
        self.assertNotIn('flag_day',self.api(2,'manager')['roster'][0])
        with self.assertRaises(PermissionError):self.api(2,'curve',{'student':1})

    def test_fresh_view_and_explicit_report(self):
        self.join();self.allow();self.entry(0,['焦虑']);self.entry(1,['委屈'])
        opened=self.api(2,'curve',{'student':1});key={'student':1,'view':opened['view']}
        self.assertTrue(opened['flag_day'])
        for seconds,mood in ((0,4),(-10,2),(-86400,1),(0,8)):
            with self.db:self.db.execute("INSERT INTO snapshots(user_id,at,mood) VALUES(?,?,?)",
                                        (1,int(self.now.timestamp())+seconds,mood))
        updated=self.api(2,'update',key)
        self.assertEqual([p['value'] for p in updated['points'][-2:]],[-1,.5]);self.assertFalse(updated['flag_day'])
        self.assertEqual(self.api(1,'student')['preview']['points'],updated['points'])
        self.assertEqual(len(self.api(1,'student')['visits']),1)
        self.api(1,'revoke',{'teacher':2});self.allow()
        with self.assertRaises(PermissionError):self.api(2,'update',key)
        reopened=self.api(2,'curve',{'student':1});self.assertNotEqual(reopened['view'],opened['view'])

    def test_missing_expired_and_role(self):
        self.join()
        self.entry(0,['焦虑']);self.entry(2,['委屈'])
        self.allow()
        self.assertIsNone(self.api(2,'curve',{'student':1})['flag_day'])
        self.now+=timedelta(days=3)
        with self.assertRaises(PermissionError):self.api(2,'curve',{'student':1})
        with self.assertRaises(PermissionError):self.api(6,'manager')
        with self.assertRaises(PermissionError):self.api(1,'invite',{'field':'username','query':'lin2'})
        with self.assertRaises(ValueError):self.api(1,'allow',{'teacher':2,'days':7,'confirmed':False})
        with self.assertRaises(PermissionError):self.api(1,'allow',{'teacher':3,'days':7,'confirmed':True})
