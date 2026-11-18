"""Per-student companion state. Dialogue retention and model use are independent choices."""
import time


ACTIONS = {
    'pat': ('happy', '把额头轻轻靠过来'),
    'wave': ('curious', '举起小爪向你招手'),
    'stretch': ('relaxed', '和你一起慢慢伸了个懒腰'),
    'rest': ('sleepy', '合上眼睛，在旁边安静待一会儿'),
}
MOODS = {'calm':'自在','happy':'开心','curious':'好奇','relaxed':'松弛','sleepy':'困困','listening':'专注'}
MODES = ('倾听', '梳理', '起步')
KEEP = 3


def init(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS pet_states (
            user_id INTEGER PRIMARY KEY, mood TEXT NOT NULL DEFAULT 'calm',
            last_action TEXT NOT NULL DEFAULT '', touched INTEGER NOT NULL DEFAULT 0,
            keep_dialogue INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS pet_turns (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, at INTEGER NOT NULL,
            question TEXT NOT NULL, answer TEXT NOT NULL, source TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS pet_turn_owner ON pet_turns(user_id,id);
    ''')


def _state(db, uid):
    row = db.execute('SELECT mood,last_action,touched,keep_dialogue,revision FROM pet_states WHERE user_id=?',(uid,)).fetchone()
    mood, action, at, keep, rev = tuple(row) if row else ('calm','',0,0,0)
    return {'mood': mood,'mood_label': MOODS[mood], 'action': action, 'at': at, 'keep': bool(keep),'revision':rev}


def _turns(db, uid):
    records = db.execute('SELECT question,answer,source FROM pet_turns WHERE user_id=? ORDER BY id DESC LIMIT ?', (uid,KEEP)).fetchall()
    return [{'question':q,'answer':a,'source':s} for q,a,s in reversed(records)]


def _update_mood(db, uid, mood, action):
    db.execute('''INSERT INTO pet_states(user_id,mood,last_action,touched) VALUES(?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET mood=excluded.mood,last_action=excluded.last_action,touched=excluded.touched''',
        (uid,mood,action,int(time.time())))


def _context(value):
    if not isinstance(value,list) or len(value)>KEEP*2:raise ValueError('对话上下文过长，请重新打开小照')
    result=[]
    for item in value:
        if not isinstance(item,dict) or item.get('role') not in ('user','assistant'):raise ValueError('无效的对话记录')
        line=item.get('content')
        if not isinstance(line,str) or not 1<=len(line)<=2400:raise ValueError('无效的对话内容')
        result.append({'role':item['role'],'content':line})
    return result


def _fallback(text, mode, history):
    themes=(('考试 复习 作业 答辩 论文'.split(), '学业', '先写下离你最近的截止事项，把其中一小步圈起来。'),
            ('累 疲惫 睡不着 熬夜 困'.split(), '休息', '先找个舒服的位置，放下手里的东西一分钟，再决定下一件事。'),
            ('同学 室友 朋友 争吵 孤独 分手'.split(), '关系', '先在草稿里写下你想让对方听见的一句话，由你决定要不要发。'))
    previous=next((x['content'] for x in reversed(history) if x['role']=='user'),'')
    text_to_match=text if len(text.strip())>5 else text+' '+previous
    topic, step=next(((name,action) for words,name,action in themes if any(w in text_to_match for w in words)),('这件事','试着写下现在最想改变的一件小事，再选一个两分钟内能做的开头。'))
    if mode=='起步':return step+' 做到这一步就可以停下。'
    if mode=='梳理':return f'我们可以把关于{topic}的事情分成两部分：已经发生的，以及你担心接下来会发生的。你想先说哪一部分？'
    quote=text[:38].rstrip('。！？ ，,')
    if previous and text.strip() in ('嗯','是的','是啊','对','对啊','然后呢'):
        return '我还在。刚才你说到「'+previous[:32]+'」，你最希望别人理解哪一点？'
    return f'我听见你说「{quote}」。当时有什么细节，最让你想把这件事讲出来？'


def handle(db,user,method,path,data):
    if path not in ('/api/pet','/api/pet/interact','/api/pet/chat','/api/pet/retention'):return NotImplemented
    if user['role']!='student':raise PermissionError('小照只在学生本人的空间中活动')
    uid=user['id']
    if path=='/api/pet' and method=='GET':
        state=_state(db,uid);state['turns']=_turns(db,uid) if state['keep'] else []
        state['memories']=[{'id':i,'note':n} for i,n in db.execute('SELECT id,note FROM student_memories WHERE user_id=? ORDER BY id DESC LIMIT 50',(uid,))]
        return state
    if method!='POST':return NotImplemented
    if path=='/api/pet/interact':
        action=data.get('action');
        if not isinstance(action,str) or action not in ACTIONS:raise ValueError('请选择小照的一个动作')
        mood,caption=ACTIONS[action];_update_mood(db,uid,mood,action)
        return {**_state(db,uid),'caption':'小照'+caption+'。'}
    if path=='/api/pet/retention':
        keep=data.get('keep');
        if type(keep) is not bool:raise ValueError('请选择是否留存对话')
        db.execute('''INSERT INTO pet_states(user_id,keep_dialogue,revision) VALUES(?,?,1) ON CONFLICT(user_id)
            DO UPDATE SET keep_dialogue=excluded.keep_dialogue, revision=pet_states.revision+1''',(uid,int(keep)))
        if not keep: db.execute('DELETE FROM pet_turns WHERE user_id=?',(uid,))
        return _state(db,uid)
    if path!='/api/pet/chat':return NotImplemented
    text=data.get('text'); mode=data.get('mode','倾听')
    if not isinstance(text,str) or not text.strip() or len(text)>1000 or mode not in MODES:raise ValueError('请选择陪伴方式，并输入 1—1000 字的问题')
    text=text.strip(); history=_context(data.get('history',[])); memory_id=data.get('memory_id'); memory=''
    if memory_id is not None:
        if type(memory_id) is not int:raise ValueError('请选择本人的偏好')
        row=db.execute('SELECT note FROM student_memories WHERE user_id=? AND id=?',(uid,memory_id)).fetchone()
        if not row:raise ValueError('该偏好已移除或不属于当前账号')
        memory=row[0]
    previous=_state(db,uid); use_ai=data.get('use_ai',False)
    if type(use_ai) is not bool:raise ValueError('请选择本次是否使用模型')
    urgent=any(w in text for w in ('自杀','不想活','自残','结束生命','想死','伤害自己','轻生','活不下去','跳楼','想割腕'))
    if urgent:
        reply='谢谢你愿意告诉我。你现在身边有可以来陪你的人吗？如果可能马上伤害自己，请立即联系当地急救或就近前往急诊。可以先请信任的人留在你身边，陪你一起联系支持。';source='安心支持'
    else:
        result=None
        if use_ai:
            from companion_ai import converse
            result=converse(text,mode,history,memory)
        if result and isinstance(result.get('text'),str) and result['text'].strip():
            reply=result['text'].strip()[:2000];source=str(result.get('source') or '模型回应')[:100]
        else:
            reply=_fallback(text,mode,history);source='离线陪伴 · 模型暂不可用' if use_ai else '离线陪伴'
            if memory:reply+=f' 你这次选了「{memory}」，可以按这个偏好来。'
    _update_mood(db,uid,'listening','chat'); state=_state(db,uid)
    if state['keep'] and state['revision']==previous['revision']:
        db.execute('INSERT INTO pet_turns(user_id,at,question,answer,source) VALUES(?,?,?,?,?)',(uid,int(time.time()),text,reply,source))
        db.execute('DELETE FROM pet_turns WHERE user_id=? AND id NOT IN (SELECT id FROM pet_turns WHERE user_id=? ORDER BY id DESC LIMIT ?)',(uid,uid,KEEP))
    return {**state,'text':reply,'source':source,'urgent':urgent}
