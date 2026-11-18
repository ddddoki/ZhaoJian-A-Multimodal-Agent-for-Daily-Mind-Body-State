import base64
from io import BytesIO
import sqlite3
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from PIL import Image, PngImagePlugin
import journal
import student


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.execute('CREATE TABLE users(id INTEGER PRIMARY KEY)')
        self.db.execute('INSERT INTO users VALUES (1),(2),(3)')
        student.init(self.db)
        journal.init(self.db)
        pic=Image.new('RGB',(16,9),'skyblue')
        private=PngImagePlugin.PngInfo();private.add_text('GPS','example private original metadata')
        buf=BytesIO();pic.save(buf,'PNG',pnginfo=private)
        self.photo=base64.b64encode(buf.getvalue()).decode()
    def tearDown(self):self.db.close()
    def call(self,route='',payload=None,uid=1,role='student'):
        method='GET' if payload is None else 'POST'
        with self.db:
            return journal.handle(self.db,{'id':uid,'role':role},method,'/api/journal'+route,payload or {})
    def test_journey_without_score(self):
        draft=self.call('/save',{'words':['委屈','期待'],'story':'答辩之后，还想和队友好好聊聊。','state':'draft'})
        saved=self.call('/save',{**draft,'state':'published','image':self.photo,'caption':'活动后'})
        key=saved['id']; self.assertEqual(saved['revision'],2)
        result=self.call('/image/'+key)
        binary=base64.b64decode(result['image'])
        with Image.open(BytesIO(binary)) as output:
            self.assertEqual(output.size,(16,9));self.assertEqual(output.format,'JPEG');self.assertFalse(output.getexif())
        self.assertNotIn(b'example private original metadata',binary)
        for role in ['manager','operator']:
            with self.assertRaises(PermissionError): self.call('/image/'+key,role=role)
        with self.assertRaises(ValueError):self.call('/image/'+key,uid=2)
        self.assertFalse(self.call(uid=2)['entries'])
        with self.assertRaises(ValueError): self.call('/save',draft)
        with self.assertRaises(ValueError):self.call('/delete',{'id':key,'revision':1})
        saved=self.call('/save',{**saved,'image':None});self.assertEqual(saved['width'],0)
        with self.assertRaises(ValueError):self.call('/image/'+key)
        self.call('/delete',{'id':key,'revision':saved['revision']})
        self.assertFalse(self.call()['entries'])
    def test_model_opt_in_and_invalid_image(self):
        with self.assertRaises(ValueError):
            self.call('/save',{'image':base64.b64encode(b'broken file').decode()})
        saved=self.call('/save',{'story':'窗外的雨让我想起家。','image':self.photo})
        key={'id':saved['id'],'revision':saved['revision']}
        with self.assertRaises(ValueError): self.call('/look',key)
        captured=[]
        def look(photo,caption):
            captured.append(photo);return {'source':'test vision','text':'蓝色背景。'}
        mock=SimpleNamespace(look=look,reflect=lambda *args:None)
        with patch.dict(sys.modules,{'companion_ai':mock}):
            self.assertFalse(self.call('/reflect',{**key,'consent':True})['available'])
            result=self.call('/look',{**key,'consent':True})
            self.assertEqual(result['entry']['scene'],'蓝色背景。');self.assertTrue(captured[0].startswith(b'\xff\xd8'))
            self.assertEqual(self.call('/save',{**result['entry'],'image':None})['scene'],'')
    def test_one_card_after_publication(self):
        draft=self.call('/save',{'story':'今天在教室听雨。','state':'draft'})
        with self.assertRaises(ValueError):
            self.call('/card',{'id':draft['id']})
        saved=self.call('/save',{**draft,'state':'published'})
        for i in range(2):
            self.call('/card',{'id':saved['id'],'note':'不慌不忙'})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM student_cards WHERE user_id=1 AND source='journal'").fetchone()[0],1)
        with self.assertRaises(ValueError):self.call('/card',{'id':saved['id']},uid=2)
    def test_private_pagination(self):
        for i in range(19):self.call('/save',{'story':str(i)})
        page=self.call();self.assertEqual(len(page['entries']),16)
        second=self.call('/page',{'before':page['next']});self.assertEqual(len(second['entries']),3)
        self.assertFalse(set(x['id'] for x in page['entries'])&set(x['id'] for x in second['entries']))
if __name__=='__main__':unittest.main()
