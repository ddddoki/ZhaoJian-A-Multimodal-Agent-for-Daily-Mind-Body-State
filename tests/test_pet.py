import sqlite3
import unittest
from unittest.mock import patch

import pet
import student


class PetTest(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
        student.init(self.db);pet.init(self.db)
        self.lin={'id':1,'role':'student'};self.zhou={'id':2,'role':'student'}

    def tearDown(self):self.db.close()

    def call(self,action='',data=None,user=None):
        with self.db:
            return pet.handle(self.db,user or self.lin,'POST' if data is not None else 'GET','/api/pet'+('/'+action if action else ''),data or {})

    def test_state_and_owner(self):
        self.assertEqual(self.call()['mood'],'calm')
        for action,(mood,_) in pet.ACTIONS.items():
            self.assertEqual(self.call('interact',{'action':action})['mood'],mood);self.assertEqual(self.call()['action'],action)
        self.assertEqual(self.call(user=self.zhou)['mood'],'calm')
        with self.assertRaises(PermissionError):self.call(user={'id':3,'role':'manager'})

    def test_opt_in_and_context(self):
        self.db.execute("INSERT INTO student_memories(user_id,note,at) VALUES(1,'从一个问题开始',1)")
        history=[{'role':'user','content':'我的考试快到了'},{'role':'assistant','content':'我们可以一起梳理。'}]
        msg={'text':'我想从数学开始','mode':'起步','history':history,'memory_id':1}
        with patch('companion_ai.converse',return_value={'text':'先选一道题写下已知条件。','source':'测试模型'}) as model:
            self.assertEqual(self.call('chat',msg)['source'],'离线陪伴');model.assert_not_called()
            self.assertEqual(self.call('chat',{**msg,'use_ai':True})['text'],'先选一道题写下已知条件。');model.assert_called_once_with(msg['text'],'起步',history,'从一个问题开始')
        with self.assertRaises(ValueError):self.call('chat',msg,self.zhou)
        self.assertEqual(self.call()['turns'],[])
        with patch('companion_ai.converse',return_value=None):self.assertIn('暂不可用',self.call('chat',{**msg,'use_ai':True})['source'])

    def test_retention_and_safety(self):
        self.call('retention',{'keep':True})
        for n in range(5):self.call('chat',{'text':f'今天的小事{n}'})
        self.assertEqual([t['question'] for t in self.call()['turns']],['今天的小事2','今天的小事3','今天的小事4'])
        self.assertFalse(self.call(user=self.zhou)['turns'])
        with patch('companion_ai.converse') as model:
            result=self.call('chat',{'text':'我有点想伤害自己','use_ai':True});self.assertTrue(result['urgent']);model.assert_not_called()
        self.call('retention',{'keep':False});self.assertFalse(self.call()['turns']);self.assertEqual(self.db.execute('SELECT COUNT(*) FROM pet_turns').fetchone()[0],0)
