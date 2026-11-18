"""Student-owned state, actions, cards and local companion for the first pilot."""
import time
from datetime import date, datetime, timedelta
from statistics import median

DIMS = ('energy', 'tension', 'recovery', 'mood')
ACTIONS = {
    'start': ('写下第一步', '拿出一张纸，只写下这件事的第一步。', 120),
    'settle': ('给自己一分钟', '放下手里的事，看看身边三样熟悉的东西。', 60),
    'rest': ('窗边歇一会', '找一个舒服的位置，把视线从屏幕移向远处。', 120),
    'move': ('课间走一走', '选一段方便的路，按自己的节奏走一小段。', 300),
}
EXPERIMENTS = (
    ('听一段喜欢的音乐','选一首熟悉的歌，听完写下最想留下的那一句。'),
    ('画出今天的校园','用两分钟随手画出今天经过的一处角落。'),
    ('读一段课外文字','找一段感兴趣的文字，读完记下一个新问题。'),
)
FEEDBACK = ('有帮助', '没变化', '不适合我')


def init(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, at INTEGER NOT NULL, energy INTEGER, tension INTEGER, recovery INTEGER, mood INTEGER, note TEXT);
    CREATE INDEX IF NOT EXISTS snapshot_owner ON snapshots(user_id,at);
    CREATE TABLE IF NOT EXISTS student_actions(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, kind TEXT NOT NULL, at INTEGER NOT NULL, status TEXT NOT NULL, feedback TEXT DEFAULT '', ended INTEGER);
    CREATE UNIQUE INDEX IF NOT EXISTS one_active_action ON student_actions(user_id) WHERE status='active';
    CREATE TABLE IF NOT EXISTS student_cards(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, source TEXT NOT NULL, source_id INTEGER NOT NULL, title TEXT NOT NULL, kind TEXT NOT NULL, note TEXT NOT NULL, at INTEGER NOT NULL, UNIQUE(user_id,source,source_id));
    CREATE TABLE IF NOT EXISTS student_memories(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL, note TEXT NOT NULL, at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS student_experiments(user_id INTEGER NOT NULL, week TEXT NOT NULL, choice INTEGER NOT NULL, status TEXT NOT NULL, reflection TEXT NOT NULL, PRIMARY KEY(user_id,week));
    CREATE TABLE IF NOT EXISTS student_observations(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL, kind TEXT NOT NULL,value REAL NOT NULL,at INTEGER NOT NULL,source TEXT NOT NULL);
    ''')


def rows(db, sql, args=()):
    c=db.execute(sql,args)
    return [dict(zip((d[0] for d in c.description),r)) for r in c.fetchall()]


def clean(value, limit):
    if not isinstance(value,str) or len(value)>limit:
        raise ValueError('文字内容过长或格式错误')
    return value.strip()


def item_id(data, key='id'):
    n=data.get(key)
    if type(n) is not int or n<1: raise ValueError('记录编号无效')
    return n


def recommend(s):
    if not s: return 'start'
    if s['tension']>=4: return 'settle'
    if s['energy']<=2 or s['recovery']<=2: return 'rest'
    if s['mood']<=2: return 'move'
    return 'start'


# Maximum useful age for each kind of contextual evidence in this pilot.
# A baseline uses at most one reading per previous day from the same source.
SIGNALS = {
    '睡眠（小时）': ('睡眠', '小时', 36, '能量与恢复'),
    '步数（步）': ('步数', '步', 8, '当天活动'),
    '心率（次/分）': ('心率', '次/分', 2, '当时的身体活动'),
    'HRV（毫秒）': ('HRV', '毫秒', 12, '当时的身体活动'),
}


def signal_context(db, uid, now):
    readings = rows(db, """SELECT kind,value,at,source FROM student_observations
                       WHERE user_id=? AND at BETWEEN ? AND ?
                       ORDER BY at DESC,id DESC""", (uid, now-16*86400, now))
    result = []
    for kind, (label, unit, hours, context) in SIGNALS.items():
        samples = [r for r in readings if r['kind'] == kind]
        if not samples or now-samples[0]['at'] > hours*3600:
            continue
        latest = samples[0]
        moment = datetime.fromtimestamp(latest['at'])
        if label == '步数' and moment.date() != date.fromtimestamp(now):
            continue
        daily = {}
        # Comparing a morning step count with a full day's count is misleading.
        # For non-sleep readings, use each day's closest time within two hours.
        for previous in samples[1:]:
            point = datetime.fromtimestamp(previous['at'])
            age = (moment.date()-point.date()).days
            if not 1 <= age <= 14 or previous['source'] != latest['source']:
                continue
            gap = abs((point.hour-moment.hour)*60+point.minute-moment.minute)
            if label != '睡眠' and gap > 120:
                continue
            if point.date() not in daily or gap < daily[point.date()][0]:
                daily[point.date()] = (gap,previous['value'])
        values = [v for _,v in daily.values()]
        result.append({'label':label, 'unit':unit, 'context':context, **latest,
                       'days':len(values), 'baseline':round(median(values),1) if len(values)>=3 else None})
    return result


def overview(db, uid, now, cohort=None):
    def recent(table, count):
        return rows(db,f'SELECT * FROM {table} WHERE user_id=? ORDER BY id DESC LIMIT ?', (uid,count))
    snapshots=recent('snapshots',15)
    monday=date.today()-timedelta(days=date.today().weekday())
    lower=int(datetime.combine(monday,datetime.min.time()).timestamp())
    weekly=rows(db,'SELECT * FROM snapshots WHERE user_id=? AND at>=? ORDER BY at,id',(uid,lower))
    completed=db.execute("SELECT COUNT(*) FROM student_actions WHERE user_id=? AND ended>=? AND status='done'",(uid,lower)).fetchone()[0]
    exp=rows(db,'SELECT choice,status,reflection FROM student_experiments WHERE user_id=? AND week=?',(uid,str(monday)))
    experiment=exp[0] if exp else {'choice':0,'status':'offered','reflection':''}
    experiment['title'],experiment['description']=EXPERIMENTS[experiment['choice']]
    catalog = {k:{'title':v[0],'description':v[1],'seconds':v[2]} for k,v in ACTIONS.items()}
    if cohort is not None:
        from ops import catalog_for
        catalog = catalog_for(db,cohort,catalog)
    return {'evidence':signal_context(db,uid,now), 'experiment':experiment,'snapshots':snapshots,'actions':recent('student_actions',20),'cards':recent('student_cards',100),'memories':recent('student_memories',50),'observations':recent('student_observations',30), 'catalog':catalog,'recommended':recommend(snapshots[0] if snapshots else None),'weekly':{'days':len({date.fromtimestamp(r['at']) for r in weekly}),'count':len(weekly),'actions':completed,'since':str(monday),'daily':[{'day':str(day),'mood':round(sum(r['mood'] for r in weekly if date.fromtimestamp(r['at'])==day)/sum(1 for r in weekly if date.fromtimestamp(r['at'])==day),1)} for day in sorted({date.fromtimestamp(r['at']) for r in weekly})]},'now':now}


def handle(db,user,method,path,data):
    if not path.startswith('/api/student/'): return NotImplemented
    if user is None or user['role']!='student': raise PermissionError('仅学生本人可访问')
    uid=user['id']; now=int(time.time()); op=path.removeprefix('/api/student/')
    if method=='GET' and op=='overview': return overview(db,uid,now,user['cohort'] if 'cohort' in user.keys() else None)
    if method!='POST': return NotImplemented
    if op=='snapshot':
        dims=[data.get(k) for k in DIMS]
        if any(type(v) is not int or not 1<=v<=5 for v in dims): raise ValueError('请逐项选择 1 至 5 分')
        note=clean(data.get('note',''),240)
        if 'id' in data:
            changed=db.execute('UPDATE snapshots SET energy=?,tension=?,recovery=?,mood=?,note=? WHERE id=? AND user_id=?',(*dims,note,item_id(data),uid)).rowcount
            if not changed: raise ValueError('找不到这次记录')
        else: db.execute('INSERT INTO snapshots(user_id,at,energy,tension,recovery,mood,note) VALUES(?,?,?,?,?,?,?)',(uid,now,*dims,note))
    elif op=='start':
        kind=data.get('kind');
        if kind not in ACTIONS: raise ValueError('请选择列表中的行动')
        db.execute("INSERT OR IGNORE INTO student_actions(user_id,kind,at,status) VALUES(?,?,?,'active')",(uid,kind,now))
        session=rows(db,"SELECT id,kind FROM student_actions WHERE user_id=? AND status='active'",(uid,))[0]
        if session['kind']!=kind: raise ValueError('请先完成或结束当前行动')
        return session
    elif op in ('finish','cancel'):
        rid=item_id(data); feedback=data.get('feedback',''); status='done' if op=='finish' else 'cancelled'
        if op=='finish' and feedback not in FEEDBACK: raise ValueError('请选择行动反馈')
        changed=db.execute("UPDATE student_actions SET status=?,feedback=?,ended=? WHERE id=? AND user_id=? AND status='active'",(status,feedback,now,rid,uid)).rowcount
        if not changed and not rows(db,'SELECT id FROM student_actions WHERE id=? AND user_id=? AND status=?',(rid,uid,status)): raise ValueError('这次行动已经结束或不存在')
    elif op=='card':
        source=data.get('source'); rid=item_id(data,'source_id'); note=clean(data.get('note',''),160)
        if source=='snapshot':
            match=rows(db,'SELECT * FROM snapshots WHERE id=? AND user_id=?',(rid,uid)); kind=recommend(match[0]) if match else 'start';title='照见此刻'
        elif source=='action':
            match=rows(db,"SELECT kind FROM student_actions WHERE id=? AND user_id=? AND status='done'",(rid,uid));kind=match[0]['kind'] if match else 'start'; title=ACTIONS[kind][0]
        else: raise ValueError('未知打卡来源')
        if not match: raise ValueError('请先完成自己的记录')
        db.execute('INSERT OR IGNORE INTO student_cards(user_id,source,source_id,title,kind,note,at) VALUES(?,?,?,?,?,?,?)',(uid,source,rid,title,kind,note,now))
    elif op in ('card-edit','card-delete','memory-delete','observation-delete'):
        rid=item_id(data)
        if op=='card-edit': count=db.execute('UPDATE student_cards SET note=? WHERE user_id=? AND id=?',(clean(data.get('note'),160),uid,rid)).rowcount
        else:
            table={'card-delete':'student_cards','memory-delete':'student_memories','observation-delete':'student_observations'}[op]
            count=db.execute(f'DELETE FROM {table} WHERE user_id=? AND id=?',(uid,rid)).rowcount
        if not count: raise ValueError('找不到这条记录')
    elif op in ('memory','memory-edit'):
        note=clean(data.get('note'),180)
        if not note: raise ValueError('请先写下一项希望记住的偏好')
        if op=='memory-edit':
            changed=db.execute('UPDATE student_memories SET note=? WHERE user_id=? AND id=?',(note,uid,item_id(data))).rowcount
            if not changed: raise ValueError('找不到这项偏好')
        else:
            db.execute('INSERT INTO student_memories(user_id,note,at) VALUES(?,?,?)',(uid,note,now))
    elif op=='experiment':
        change=data.get('change'); week=str(date.today()-timedelta(days=date.today().weekday()))
        if data.get('week')!=week: raise ValueError('周次已变化，请刷新重试')
        if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
        saved=rows(db,'SELECT choice,status,reflection FROM student_experiments WHERE user_id=? AND week=?',(uid,week))
        record=saved[0] if saved else {'choice':0,'status':'offered','reflection':''}
        if change=='swap' and record['status']=='offered': record['choice']=(record['choice']+1)%len(EXPERIMENTS)
        elif change=='accept' and record['status']=='offered': record['status']='accepted'
        elif change=='skip' and record['status'] in ('offered','accepted'): record['status']='skipped'
        elif change=='complete' and record['status']=='accepted':
            record['reflection']=clean(data.get('reflection',''),160);record['status']='done'
        else: raise ValueError('本周尝试的状态已变化，请刷新查看')
        db.execute('INSERT INTO student_experiments VALUES(?,?,?,?,?) ON CONFLICT(user_id,week) DO UPDATE SET choice=excluded.choice,status=excluded.status,reflection=excluded.reflection',(uid,week,record['choice'],record['status'],record['reflection']))
    elif op=='observation':
        kind=data.get('kind'); value=data.get('value'); limits={'睡眠（小时）':(0,24),'步数（步）':(0,100000),'心率（次/分）':(20,300),'HRV（毫秒）':(0,1000)}
        if kind not in limits or type(value) not in (float,int) or not limits[kind][0]<=value<=limits[kind][1]: raise ValueError('请核对指标和数值范围')
        db.execute('INSERT INTO student_observations(user_id,kind,value,at,source) VALUES(?,?,?,?,?)',(uid,kind,value,now,'本人手动录入'))
    elif op=='chat':
        text=clean(data.get('text'),400); mode=data.get('mode','梳理');
        if not text or mode not in ('倾听','梳理','起步'): raise ValueError('请写下一句话并选择陪伴方式')
        if any(word in text for word in ('自杀','不想活','自残','结束生命','想死','伤害自己','轻生','活不下去')):
            return {'reply':'谢谢你告诉我。先让一个信任的人知道你现在的处境，请对方陪着你。如果你可能马上伤害自己，请立即联系当地急救或直接前往最近的急诊。你也可以打开校园资源，寻找可以当面陪你的人。','resource':True}
        kind='start' if any(w in text for w in ('作业','论文','复习','考试','早八','学习')) else 'rest' if any(w in text for w in ('累','困','熬夜')) else 'settle'
        subject={'start':'眼前的学习任务','rest':'今天的疲惫','settle':'刚才提到的事情'}[kind]
        reply={'倾听':f'我们可以先聊聊{subject}。此刻你最希望别人理解哪一点？','梳理':f'关于{subject}，试着把「已经发生的」和「还在担心的」各说一句。你想从哪一句开始？','起步':f'我们先从「{ACTIONS[kind][0]}」开始。{ACTIONS[kind][1]} 想试试就点下面的行动，也可以先留在这里聊。'}[mode]
        if data.get('use_model') is True:
            from local_model import compose
            model_reply=compose(text,mode)
            if model_reply: reply=model_reply
            else: reply+='（本机模型未启用或暂时不可用，已使用内置陪伴回应。）'
        if data.get('use_memory') is True:
            memory=rows(db,'SELECT note FROM student_memories WHERE user_id=? ORDER BY id DESC LIMIT 1',(uid,))
            if memory: reply+=f' 你曾希望我记住「{memory[0]["note"]}」。这次也可以按这个偏好调整。'
        return {'reply':reply,'kind':kind if mode=='起步' else None}
    else: return NotImplemented
    return {'ok':True}
