"""Personal action suggestions using explicit journal choices and personal calendar gaps."""
from collections import Counter
from datetime import datetime, timedelta
import json

from campus import CAMPUS_TZ

# A standalone minute and a later, longer version of each activity.
ACTIVITIES = {
    'pause': ('给眼睛放个假', '放下手中的屏幕，找一个舒服的位置，看一眼远处的颜色。', '留一段安静的课间', '离开座位，找一处安静的窗边。想回来时就回来。', 5),
    'sort': ('把脑中的一件事写下来', '在便签上只写下最占心思的一件事，然后圈出今天能动手的一小步。', '把眼前的事排个序', '列三件挂心的事，只选一件今天能动手的小事。', 5),
    'start': ('为待办写一行开头', '打开作业或笔记，只写标题和第一行。铃响时可以停下。', '做一轮小任务', '挑出一份具体作业，完成其中的一个步骤。', 10),
    'connect': ('写一句想说的话', '在自己的草稿里写一句想对谁说的话。是否发出去，由你决定。', '给联络留一点时间', '选一个愿意亲近的人，留一句近况，或者先存成草稿。', 5),
    'notice': ('记住眼前的一个细节', '看看身边的光线、颜色或声音，为一个细节起个名字。', '收集一件有趣的小事', '走到身边一个熟悉的地方，记下今天看到的新细节。', 5),
    'wrap': ('记下一件完成的小事', '给今天刚做过的一件小事写下一行注脚。', '给今天留一句收尾', '记下今天做过的一件事，给明天留一个可以直接开始的开头。', 3),
}
WANTS = {'有人听我说':'connect','理清思绪':'sort','歇一会儿':'pause','迈出第一步':'start'}
FEELINGS = {'疲惫':'pause','有点乱':'sort','焦虑':'sort','委屈':'connect','想念':'connect','好奇':'notice','期待':'start','开心':'notice','平静':'notice','被理解':'connect','松了一口气':'pause'}
OPEN, CLOSE = 7*60+30, 22*60+30


def init(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS minute_sessions(
            owner INTEGER NOT NULL, entry TEXT NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
            kind TEXT NOT NULL, started INTEGER NOT NULL, done INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(owner,entry));
        CREATE TABLE IF NOT EXISTS plan_items(
            id INTEGER PRIMARY KEY, owner INTEGER NOT NULL, day TEXT NOT NULL,
            starts INTEGER NOT NULL, duration INTEGER NOT NULL, kind TEXT NOT NULL,
            reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'planned', adjusted INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS plan_day ON plan_items(owner,day,starts);
    """)


def clock():
    return datetime.now(CAMPUS_TZ)


def minute_text(value):
    return f'{value//60:02d}:{value%60:02d}'


def decide(row):
    if row['need'] in WANTS:
        return WANTS[row['need']], '你在手记中选了「'+row['need']+'」。'
    for word in json.loads(row['words']):
        if word in FEELINGS:
            return FEELINGS[word], '你在手记中选了「'+word+'」。'
    return 'notice','这篇手记没有选择标准需要或感受词，先提供一个留意身边细节的选项。'


def owned_entry(db, uid, key):
    if not isinstance(key,str):raise ValueError('请选择一篇已发布的手记')
    row=db.execute("SELECT id,words,need FROM journal_entries WHERE owner=? AND id=? AND state='published'",(uid,key)).fetchone()
    if not row:raise ValueError('没有找到自己的已发布手记')
    return row


def small_action(db,uid,key,now):
    entry=owned_entry(db,uid,key)
    kind,reason=decide(entry)
    session=db.execute('SELECT kind,started,done FROM minute_sessions WHERE owner=? AND entry=?',(uid,key)).fetchone()
    if session:
        kind=session['kind']
        reason='沿用开始计时时你选定的行动。'
    title,description,*_=ACTIVITIES[kind]
    return {'entry':key,'title':title,'description':description,'reason':reason,'now':int(now.timestamp()),
            'started':session['started'] if session else None,'done':bool(session and session['done'])}


def history(db,uid,now):
    lower=(now-timedelta(days=14)).isoformat()
    # datetime() handles both UTC journal timestamps and the local comparison bound.
    samples=db.execute("""SELECT words,need FROM journal_entries WHERE owner=? AND state='published'
                           AND datetime(created)>=datetime(?) AND datetime(created)<=datetime(?)
                           ORDER BY seq DESC LIMIT 5""",(uid,lower,now.isoformat())).fetchall()
    votes=Counter()
    signals={}
    for row in samples:
        matched={}
        if row['need'] in WANTS:
            matched[WANTS[row['need']]]=(row['need'],2)
        for word in json.loads(row['words']):
            if word in FEELINGS:
                matched.setdefault(FEELINGS[word],(word,1))
        for kind,(choice,weight) in matched.items():
            votes[kind]+=weight
            signals.setdefault(kind,[]).append(choice)
    kinds=[k for k,_ in votes.most_common()]
    grounds={kind:f'最近 {len(samples)} 篇手记中，有 {len(choices)} 篇选择了'+
             '、'.join('「'+v+'」' for v in dict.fromkeys(choices))+'。'
             for kind,choices in signals.items()}
    past=db.execute("""SELECT kind FROM student_actions WHERE user_id=? AND status='done'
          AND feedback='有帮助' AND ended BETWEEN ? AND ? ORDER BY ended DESC LIMIT 1""",
          (uid,int((now-timedelta(days=14)).timestamp()),int(now.timestamp()))).fetchone()
    if past:
        kind={'rest':'pause','settle':'sort','start':'start','move':'notice'}.get(past[0])
        if kind:
            if kind not in kinds:kinds.append(kind)
            grounds[kind]='你在近两周的行动反馈里把同类活动标为「有帮助」。'
    return kinds,grounds,len(samples)


def busy_times(db,uid,now):
    day=now.date().isoformat(); tomorrow=(now.date()+timedelta(days=1)).isoformat()
    rows=db.execute("""SELECT starts,ends FROM campus_events WHERE owner=? AND starts<? AND ends>?
                       ORDER BY starts""",(uid,tomorrow+'T00:00',day+'T00:00')).fetchall()
    return [(0 if r[0][:10]<day else int(r[0][11:13])*60+int(r[0][14:16]),
             1440 if r[1][:10]>day else int(r[1][11:13])*60+int(r[1][14:16])) for r in rows]


def overlaps(start,duration,blocks):
    return any(a<start+duration and b>start for a,b in blocks)


def next_slot(start,duration,blocks):
    candidate=start
    for left,right in sorted(blocks):
        if right<=candidate:continue
        if left>=candidate+duration:break
        candidate=right
    return candidate if candidate+duration<=CLOSE else None


def today_items(db,uid,day):
    return [dict(r) for r in db.execute("SELECT * FROM plan_items WHERE owner=? AND day=? ORDER BY starts,id",(uid,day))]


def plan_state(db,uid,now):
    day=now.date().isoformat()
    current=now.hour*60+now.minute+int(bool(now.second or now.microsecond))
    blocks=busy_times(db,uid,now)
    items=today_items(db,uid,day)
    kinds,reasons,count=history(db,uid,now)
    full_kinds=list(dict.fromkeys(kinds+['start','pause','wrap']))[:3]
    reserved=[(i['starts'],i['starts']+i['duration']) for i in items if i['status']=='done' or (i['adjusted'] and i['status']=='planned')]
    occupied_kinds={i['kind'] for i in items if i['status']!='planned' or i['adjusted']}
    floor=max(OPEN,current)
    proposals=[]
    for kind,anchor in zip(full_kinds,(9*60,14*60,19*60)):
        if kind in occupied_kinds:continue
        duration=ACTIVITIES[kind][4]
        # Prefer a margin between actions, but keep an earlier free slot when the preferred time is full.
        blockers=blocks+reserved
        slot=next_slot(max(floor,anchor),duration,blockers)
        if slot is None:slot=next_slot(floor,duration,blockers)
        if slot is None:continue
        proposals.append(dict(kind=kind,starts=slot,duration=duration,
            reason=reasons.get(kind,'补一个可以自己选择的小行动。')))
        reserved.append((slot,slot+duration))
        floor=slot+duration+30
    for item in items:
        item['conflict']=overlaps(item['starts'],item['duration'],blocks)
        item['past']=item['starts']+item['duration']<=current
    def present(item):
        item['title'],item['description']=ACTIVITIES[item['kind']][2:4]
        item['time']=minute_text(item['starts'])
        return item
    return {'day':day,'items':[present(i) for i in items],'suggested':[present(i) for i in proposals],
            'samples':count,'classes':len(blocks),'window':'07:30–22:30'}


def handle(db,user,method,path,data):
    if path!='/api/plan' and not path.startswith('/api/plan/'):return NotImplemented
    if user['role']!='student':raise PermissionError('只有学生本人可以查看规划')
    uid=user['id'];now=clock();day=now.date().isoformat()
    if path=='/api/plan' and method=='GET':return plan_state(db,uid,now)
    if method!='POST':return NotImplemented
    if path=='/api/plan/minute':return small_action(db,uid,data.get('entry'),now)
    if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
    if path in ('/api/plan/minute/start','/api/plan/minute/done','/api/plan/minute/stop'):
        key=data.get('entry');row=owned_entry(db,uid,key);ts=int(now.timestamp())
        if path.endswith('/start'):
            db.execute('INSERT OR IGNORE INTO minute_sessions(owner,entry,kind,started) VALUES(?,?,?,?)',(uid,key,decide(row)[0],ts))
        elif path.endswith('/done'):
            if not db.execute('UPDATE minute_sessions SET done=1 WHERE owner=? AND entry=? AND started<=?',(uid,key,ts-60)).rowcount:
                raise ValueError('一分钟结束后可以记录完成，也可以先暂停')
        else:
            db.execute('DELETE FROM minute_sessions WHERE owner=? AND entry=? AND done=0',(uid,key))
        return small_action(db,uid,key,now)
    if path=='/api/plan/generate':
        current=plan_state(db,uid,now)
        db.execute("DELETE FROM plan_items WHERE owner=? AND day=? AND adjusted=0 AND status='planned'",(uid,day))
        for item in current['suggested']:
            db.execute('INSERT INTO plan_items(owner,day,starts,duration,kind,reason) VALUES(?,?,?,?,?,?)',
                       (uid,day,item['starts'],item['duration'],item['kind'],item['reason']))
        return plan_state(db,uid,now)
    if path not in ('/api/plan/move','/api/plan/status'):return NotImplemented
    ident=data.get('id')
    if type(ident) is not int:raise ValueError('请选择一项安排')
    item=db.execute("SELECT * FROM plan_items WHERE owner=? AND day=? AND id=?",(uid,day,ident)).fetchone()
    if not item:raise ValueError('今日没有此安排，请刷新')
    if path.endswith('/status'):
        state=data.get('status')
        if state not in ('done','skipped'):raise ValueError('状态无效')
        if item['status']!='planned' and item['status']!=state:raise ValueError('该安排已有完成或跳过记录')
        db.execute('UPDATE plan_items SET status=? WHERE id=?',(state,ident))
    else:
        if item['status']!='planned':raise ValueError('只可调整待办安排')
        value=data.get('time','')
        try:start=datetime.strptime(value,'%H:%M');minutes=start.hour*60+start.minute
        except (ValueError,TypeError):raise ValueError('请使用 24 小时时间') from None
        threshold=now.hour*60+now.minute+int(bool(now.second or now.microsecond))
        if minutes<max(OPEN,threshold) or minutes+item['duration']>CLOSE:raise ValueError('请选择今天剩余的 07:30–22:30 时段')
        blocks=busy_times(db,uid,now)+[(r['starts'],r['starts']+r['duration']) for r in today_items(db,uid,day) if r['id']!=ident and r['status']!='skipped']
        if overlaps(minutes,item['duration'],blocks):raise ValueError('这段时间已有校园事务或行动，请换一个空档')
        db.execute('UPDATE plan_items SET starts=?,adjusted=1 WHERE id=?',(minutes,ident))
    return plan_state(db,uid,now)
