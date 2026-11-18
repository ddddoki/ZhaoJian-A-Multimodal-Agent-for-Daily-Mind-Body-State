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
        return dict(username=username,name='测试用户',cohort='学生自填班级',password='test-password-1234',role=role)

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
