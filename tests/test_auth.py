import json
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import time
import unittest
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPCookieProcessor, Request

import registration
import server


class QuietHandler(server.Handler):
    def log_message(self, *args):
        pass


class RegistrationTest(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file=Path(self.temp.name)/'db.sqlite3'
        server.setup(self.file,False)
        self.http=ThreadingHTTPServer(('127.0.0.1',0),QuietHandler)
        self.http.dbfile=self.file
        self.http.demo=False
        thread=Thread(target=self.http.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)
        self.base=f'http://127.0.0.1:{self.http.server_port}'
        self.client=build_opener(HTTPCookieProcessor(CookieJar()))

    def call(self,path,data=None,status=200):
        request=Request(self.base+path, data=None if data is None else json.dumps(data).encode(),
                        headers={'Content-Type':'application/json'})
        try:response=self.client.open(request)
        except HTTPError as exc:response=exc
        with response:
            result=json.load(response)
            self.assertEqual(response.status,status,(path,result))
            return result

    def draft(self,role='student',username='local.student'):
        return dict(username=username,name='测试用户',cohort='学生自填班级',password='test-password-1234',role=role,**({'gender':'female'} if role=='student' else {}))

    def issue(self,role):
        db=server.connect(self.file)
        try:
            with db:return registration.issue_invite(db,role,'班级一')['invite']
        finally:db.close()

    def test_student_registration_session_login_and_duplicate(self):
        data=self.draft()
        user=self.call('/api/register',data,201)['user']
        self.assertEqual(self.call('/api/session')['user'], user)
        self.assertEqual(user['role'],'student')
        self.call('/api/register',data,400)
        self.call('/api/logout',{})
        self.call('/api/login',{**data,'role':'manager'},401)
        self.assertEqual(self.call('/api/login',data)['user'],user)
        self.call('/api/register',{**data,'role':'admin'},400)

    def test_staff_roles_scope_and_single_use(self):
        for role in registration.STAFF:
            token=self.issue(role)
            data={**self.draft(role,role+'.user'),'invite':token}
            self.call('/api/register',{**data,'role':'operator' if role=='manager' else 'manager'},400)
            person=self.call('/api/register',data,201)['user']
            self.assertEqual((person['role'],person['cohort']),(role,'班级一'))
            self.call('/api/register',{**data,'username':role+'.other'},400)

    def test_demo_invitation_cannot_be_used_in_non_demo_mode(self):
        self.call('/api/demo/invite',{'role':'operator'},403)
        self.http.demo=True
        invite=self.call('/api/demo/invite',{'role':'operator'})['invite']
        self.http.demo=False
        data={**self.draft('operator'),'invite':invite}
        self.call('/api/register',data,400)
        self.http.demo=True
        self.call('/api/register',data,201)

    def test_expired_token(self):
        token=self.issue('manager')
        db=server.connect(self.file)
        try:
            with db:db.execute('UPDATE invitations SET expires=?',(int(time.time())-1,))
        finally:db.close()
        self.call('/api/register',{**self.draft('manager'),'invite':token},400)
    def test_retry_after_name_conflict_and_concurrent_redemption(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        self.call('/api/register',self.draft(username='taken.user'),201)
        token=self.issue('manager')
        self.call('/api/register',{**self.draft('manager','taken.user'),'invite':token},400)
        barrier=Barrier(2)
        def apply(n):
            body={**self.draft('manager',f'concurrent.{n}'),'invite':token}
            request=Request(self.base+'/api/register',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
            barrier.wait(timeout=10)
            try:
                with build_opener().open(request) as response:return response.status
            except HTTPError as exc:
                with exc:return exc.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(apply,(1,2))),[201,400])

    def test_gender_is_required_personal_and_independent_from_cycle_consent(self):
        original=self.draft()
        for bad in (None, 'unknown', '', [], 1):
            self.call('/api/register',{**original, 'gender':bad},400)
        self.call('/api/register',{k:v for k,v in original.items() if k!='gender'},400)
        user=self.call('/api/register',original,201)['user']
        self.assertEqual((user['gender'],user['cohort']),('female',''))
        self.assertFalse(self.call('/api/privacy')['enabled'])
        self.call('/api/privacy/save',{'start_day':'2024-01-01'},403)
        self.call('/api/privacy/consent',{'enabled':True})
        self.call('/api/privacy/save',{'start_day':'2024-01-01','feeling':'私人测试'},200)
        self.call('/api/profile/gender',{'gender':'male'})
        self.assertEqual(self.call('/api/session')['user']['gender'],'male')
        self.call('/api/privacy',status=403)
        for path, data in (('consent',{'enabled':True}),('save',{}),('personalize',{'enabled':True}),
                           ('import/preview',{}),('import/confirm',{}),('delete',{'id':1})):
            self.call('/api/privacy/'+path,data,403)
        self.assertTrue(self.call('/api/profile')['has_cycle_history'])
        self.assertFalse(self.call('/api/data/export').get('cycle_entries'))
        self.call('/api/profile/gender',{'gender':'female'})
        self.assertFalse(self.call('/api/privacy')['enabled'])
        self.call('/api/privacy/consent',{'enabled':True})
        self.assertEqual(self.call('/api/privacy')['entries'][0]['feeling'],'私人测试')
        self.call('/api/profile/gender',{'gender':'male'})
        self.call('/api/profile/clear-cycle',{'confirm':True})
        self.assertFalse(self.call('/api/profile')['has_cycle_history'])
        token=self.issue('manager')
        staff=self.call('/api/register',{**self.draft('manager','teacher.gender'),'gender':'female','invite':token},201)['user']
        self.assertNotIn('gender',staff)
        self.call('/api/profile',status=403)
        self.call('/api/privacy',status=403)

    def test_legacy_profile_completion_preserves_original_data(self):
        import sqlite3
        legacy=Path(self.temp.name)/'legacy.db'
        db=sqlite3.connect(legacy)
        db.execute('CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, name TEXT NOT NULL, role TEXT NOT NULL, cohort TEXT NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL)')
        db.execute("INSERT INTO users VALUES(1,'old','原账号','student','软件一班','00',?)",
                   (registration.password_hash('legacy-pass','00'),))
        db.commit();db.close()
        server.setup(legacy,False)
        self.http.dbfile=legacy
        account=self.call('/api/login',{'username':'old','password':'legacy-pass'})['user']
        self.assertIsNone(account['gender'])
        self.call('/api/privacy',status=403)
        db=server.connect(legacy)
        with db:
            db.execute("INSERT INTO cycle_consent(owner,personalize) VALUES(1,1)")
            db.execute("INSERT INTO cycle_entries(owner,start_day,end_day,feeling) VALUES(1,'2024-01-01','','旧记录')")
        db.close()
        self.call('/api/profile/gender',{'gender':'female'})
        self.assertFalse(self.call('/api/privacy')['enabled'])
        self.call('/api/privacy/consent',{'enabled':True})
        self.assertEqual(self.call('/api/privacy')['entries'][0]['feeling'],'旧记录')
