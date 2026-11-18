import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import time
import unittest
from unittest.mock import patch

from desktop_client import Client, DesktopAPIError

try:
    import tkinter as tk
except ImportError:
    tk = None
else:
    from desktop_chat import ChatPanel


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.requests.append((self.path, self.headers['Cookie']))
        if self.path == '/api/pet':
            self.send_response(302)
            self.send_header('Location', '/redirect-target')
            self.end_headers()
            return
        self.send_response(401)
        self.end_headers()
        self.wfile.write(json.dumps({'error':'请登录'}).encode())

    def log_message(self, *args):
        pass


class ClientTest(unittest.TestCase):
    def test_loopback_cookie_and_no_redirect(self):
        with ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
            server.requests=[]
            thread=Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                token='x'*43
                client=Client(server.server_port,token)
                with patch.dict(os.environ, {'HTTP_PROXY':'http://127.0.0.1:1'}):
                    for path,status in [('/api/pet',302),('/api/pet/unused',401)]:
                        with self.assertRaises(DesktopAPIError) as error: client.get(path)
                        self.assertEqual(error.exception.status,status)
                with self.assertRaises(ValueError): client.get('https://example.net/api/pet')
                self.assertEqual(server.requests,[('/api/pet','zj_session='+token),
                                                  ('/api/pet/unused','zj_session='+token)])
            finally:
                server.shutdown()
                thread.join(3)


class FakeClient:
    def __init__(self):
        self.user={'id':1,'username':'chen','name':'演示同学','role':'student'}
        self.payloads=[]
        self.keep=False
        self.rev=0

    def get(self,path):
        if path=='/api/session':return {'user':self.user}
        if path=='/api/ai/status':return {'text':{'model':'测试模型','available':True}}
        if path=='/api/pet':return {'revision':self.rev,'keep':self.keep,'turns':[]}
        raise AssertionError(path)

    def post(self,path,payload):
        if path=='/api/pet/retention':
            self.keep=payload['keep'];self.rev+=1
            return {'keep':self.keep,'revision':self.rev}
        if path!='/api/pet/chat':raise AssertionError(path)
        self.payloads.append(payload)
        return {'text':'收到你的近况','source':'测试模型' if payload['use_ai'] else '离线陪伴',
                'mood':'listening','urgent':False}


@unittest.skipIf(tk is None, 'Tk is unavailable')
class PanelTest(unittest.TestCase):
    def setUp(self):
        try:
            self.root=tk.Tk()
        except tk.TclError:
            self.skipTest('Tk display unavailable')
        self.root.withdraw()
        self.client=FakeClient()
        self.panel=ChatPanel(self.root,self.client,dict(self.client.user))
        # Exercise real Tk controls without showing a test window to the user.
        self.panel._build()
        self.panel.window.deiconify=lambda:None

    def tearDown(self):
        self.root.destroy()

    def wait(self,check):
        end=time.monotonic()+4
        while not check() and time.monotonic()<end:
            self.root.update()
            time.sleep(.005)
        self.assertTrue(check())

    def test_native_chat_context_retention_and_expiry(self):
        panel=self.panel
        panel.show()
        self.wait(lambda:panel.ready)
        panel.field.insert('1.0','今天画了一棵树')
        panel.offline.invoke()
        self.wait(lambda:len(panel.turns)==1)
        self.assertFalse(self.client.payloads[-1]['use_ai'])
        panel.field.insert('1.0','我还想画点什么')
        panel.ai.invoke()
        self.wait(lambda:len(panel.turns)==2)
        payload=self.client.payloads[-1]
        self.assertTrue(payload['use_ai'])
        self.assertEqual([r['role'] for r in payload['history']],['user','assistant'])
        self.assertIn('测试模型',panel.log.get('1.0','end'))
        panel.retain_control.invoke()
        self.wait(lambda:not panel.busy)
        self.assertTrue(self.client.keep)
        panel.retain_control.invoke()
        self.wait(lambda:not panel.busy)
        self.assertFalse(panel.turns)
        self.client.user=None
        panel.show()
        self.wait(lambda:panel.expired)
        self.assertEqual(panel.offline['state'],'disabled')
        self.assertNotIn('画了一棵树',panel.log.get('1.0','end'))
        self.assertFalse(panel.owner_label['text'])
