"""Run from the repository root: python -m unittest discover -s tests -v."""
import json
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPCookieProcessor, Request

import server


class Quiet(server.Handler):
    def log_message(self,*args):pass


class Pilot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory();cls.db=Path(cls.tmp.name)/'test.db';server.setup(cls.db,True)
        cls.host=ThreadingHTTPServer(('127.0.0.1',0),Quiet);cls.host.dbfile=cls.db;cls.host.demo=True
        cls.base=f'http://127.0.0.1:{cls.host.server_port}';cls.thread=Thread(target=cls.host.serve_forever,daemon=True);cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.host.shutdown();cls.host.server_close();cls.thread.join();cls.tmp.cleanup()

    def call(self,browser,path,data=None,status=200):
        body=None if data is None else json.dumps(data).encode();req=Request(self.base+path,body,headers={'Content-Type':'application/json'})
        try:response=browser.open(req)
        except HTTPError as exc:response=exc
        with response:
            result=json.load(response);self.assertEqual(response.status,status,(path,result));return result

    def login(self,username):
        browser=build_opener(HTTPCookieProcessor(CookieJar()));self.call(browser,'/api/login',{'username':username,'password':'ZhaojianDemo1'});return browser

    def test_student_journey_and_scope(self):
        a=self.login('lin');other=self.login('zhou');mgr=self.login('chen');snap={'energy':3,'mood':3,'recovery':4,'tension':3,'note':'测试专属记录'}
        self.call(a,'/api/student/snapshot',snap);sid=self.call(a,'/api/student/overview')['snapshots'][0]['id'];self.call(other,'/api/student/card',{'source':'snapshot','source_id':sid},400)
        active=self.call(a,'/api/student/start',{'kind':'rest'});self.assertEqual(self.call(self.login('lin'),'/api/student/overview')['actions'][0]['id'],active['id']);self.call(a,'/api/student/finish',{'id':active['id'],'feedback':'没变化'})
        card={'source':'action','source_id':active['id'],'note':'回看这一步'}
        self.call(a,'/api/student/card',card);self.call(a,'/api/student/card',card);cards=self.call(a,'/api/student/overview')['cards'];self.assertEqual(sum(c['source_id']==active['id'] and c['source']=='action' for c in cards),1)
        self.call(mgr,'/api/student/overview',status=403);self.assertTrue(self.call(a,'/api/student/chat',{'mode':'倾听','text':'想复习但有点烦'})['reply']);self.call(a,'/api/logout',{});self.call(a,'/api/student/overview',status=401)

    def test_calendar_and_optional_cycle(self):
        a=self.login('lin'); mgr=self.login('chen');other=self.login('zhou'); data={'content':'标题,开始,结束,次数,间隔周\n软件工程,2027-03-01T08:00,2027-03-01T09:00,2,2'}
        self.assertEqual(len(self.call(a,'/api/campus/import/preview',data)['rows']),2);self.assertEqual(self.call(a,'/api/campus/import/confirm',data)['added'],2);self.assertEqual(self.call(a,'/api/campus/import/confirm',data)['added'],0)
        self.assertFalse(self.call(other,'/api/campus')['events']);self.call(a,'/api/privacy/consent',{'enabled':True});self.call(a,'/api/privacy/save',{'start_day':'2025-06-01','end_day':'2025-06-04','feeling':'测试'});self.assertTrue(self.call(a,'/api/privacy')['entries']);self.call(mgr,'/api/privacy',status=403);self.call(other,'/api/privacy',status=403);self.call(a,'/api/privacy/consent',{'enabled':False});self.assertFalse(self.call(a,'/api/privacy')['entries'])

    def test_scoped_support(self):
        a=self.login('lin'); mgr=self.login('chen'); other=self.login('wu');recipient=self.call(a,'/api/sharing')['recipients'][0]['id'];item=self.call(a,'/api/sharing/create',{'recipient':recipient,'topic':'学业安排','summary':'仅共享周三想约时间','days':1});self.assertEqual(self.call(mgr,'/api/manage/detail',item)['summary'],'仅共享周三想约时间');self.call(other,'/api/manage/detail',item,403);self.call(mgr,'/api/manage/status',{**item,'status':'following'});self.call(a,'/api/sharing/revoke',item);self.call(mgr,'/api/manage/detail',item,403)

    def test_wearable_and_portability(self):
        a=self.login('zhou');self.call(a,'/api/data/bind',{'device':'测试表'});file={'content':'time,metric,value\n2025-06-01T10:00:00+08:00,steps,500'};self.assertEqual(self.call(a,'/api/data/preview',file)['count'],1);upload={**file,'device':'测试表'};self.assertEqual(self.call(a,'/api/data/import',upload)['saved'],1);self.assertEqual(self.call(a,'/api/data/import',upload)['saved'],0);result=self.call(a,'/api/data/export');self.assertEqual(result['student_observations'][0]['value'],500);self.call(a,'/api/data/clear',{'confirm':'清空我的数据'});self.call(a,'/api/session');self.call(a,'/api/data/export',status=401);self.assertFalse(self.call(self.login('zhou'),'/api/data/export')['student_observations'])

    def test_published_campus_and_action_version(self):
        mgr=self.login('chen');operator=self.login('ops');a=self.login('lin');other=self.login('zhou')
        event={'title':'期末演示','kind':'考试','starts':'2027-05-21T09:00','ends':'2027-05-21T11:30','place':'A101'}
        self.call(mgr,'/api/campus/board/event/save',event);board=self.call(a,'/api/campus/board');key={'id':board['events'][0]['id']};self.assertFalse(self.call(other,'/api/campus/board')['events']);self.assertEqual(self.call(a,'/api/campus/board/add',key)['added'],1);self.assertEqual(self.call(a,'/api/campus/board/add',key)['added'],0)
        self.call(mgr,'/api/ops',status=403);self.call(operator,'/api/manage',status=403);text='写下今晚第一道题的题号';draft=self.call(operator,'/api/ops/draft',{'kind':'start','description':text});old=self.call(a,'/api/student/overview')['catalog']['start']['description'];self.assertNotEqual(old,text);self.call(operator,'/api/ops/publish',{**draft,'reviewed':text});self.assertEqual(self.call(a,'/api/student/overview')['catalog']['start']['description'],text);self.assertEqual(self.call(other,'/api/student/overview')['catalog']['start']['description'],old);self.call(operator,'/api/ops/rollback',{'kind':'start','target':0,'current':draft['id']});self.assertEqual(self.call(a,'/api/student/overview')['catalog']['start']['description'],old)
