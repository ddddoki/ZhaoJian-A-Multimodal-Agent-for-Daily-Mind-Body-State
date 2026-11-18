"""Class invitations and time-limited, teacher-specific trend sharing."""
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4


TZ = timezone(timedelta(hours=8))
EASY = frozenset(('松了一口气', '期待', '开心', '被理解', '好奇'))
DIFFICULT = frozenset(('有点乱', '疲惫', '委屈', '焦虑'))
WEIGHTS = {**dict.fromkeys(EASY, 1), **dict.fromkeys(DIFFICULT, -1), '平静': 0}
ROUTES = {
    'student': ('GET','student'), 'manager': ('GET','manager'), 'invite': ('POST','manager'),
    'decision': ('POST','student'), 'allow': ('POST','student'), 'revoke': ('POST','student'),
    'curve': ('POST','manager'), 'update': ('POST','manager'), 'follow': ('POST','manager'),
}


def clock():
    return datetime.now(timezone.utc)


def init(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS care_invitations (
            id TEXT PRIMARY KEY, student INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            teacher INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            cohort TEXT NOT NULL, issued INTEGER NOT NULL, expires INTEGER NOT NULL, state TEXT NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS care_pending ON care_invitations(student,teacher) WHERE state='pending';
        CREATE TABLE IF NOT EXISTS care_grants (
            student INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            teacher INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            cohort TEXT NOT NULL, expires INTEGER NOT NULL, granted INTEGER NOT NULL, PRIMARY KEY(student,teacher));
        CREATE TABLE IF NOT EXISTS care_events (
            id INTEGER PRIMARY KEY, student INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            teacher INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL, at INTEGER NOT NULL, day TEXT NOT NULL DEFAULT '');
        CREATE INDEX IF NOT EXISTS care_activity ON care_events(student,teacher,kind,at);
    """)


def rows(cursor):
    return [dict(row) for row in cursor]


def required_id(data,key):
    value = data.get(key)
    if type(value) is not int or value <= 0:
        raise ValueError('请选择有效账号')
    return value


def record(db,student,teacher,kind,now,day=''):
    return db.execute('INSERT INTO care_events(student,teacher,kind,at,day) VALUES(?,?,?,?,?)',
                      (student,teacher,kind,now,day)).lastrowid


def curve(db,student,moment):
    today=moment.astimezone(TZ).date()
    start=today-timedelta(days=6)
    start_stamp=datetime.combine(start,datetime.min.time(),tzinfo=TZ).astimezone(timezone.utc).isoformat(timespec='seconds')
    daily={}
    for created,encoded in db.execute("""SELECT created,words FROM journal_entries
        WHERE owner=? AND state='published' AND created>=? ORDER BY created""",(student,start_stamp)):
        day=datetime.fromisoformat(created).astimezone(TZ).date()
        if not start<=day<=today:continue
        words={w for w in json.loads(encoded) if w in WEIGHTS}
        if words:
            daily.setdefault(day,[]).append(sum(WEIGHTS[w] for w in words)/len(words))
    # A student's own latest quick mood report for the day takes precedence over any word summary.
    reported={}
    first_second=int(datetime.fromisoformat(start_stamp).timestamp())
    for at,mood in db.execute("""SELECT at,mood FROM snapshots WHERE user_id=? AND at BETWEEN ? AND ?
            AND typeof(mood)='integer' AND mood BETWEEN 1 AND 5 ORDER BY at,id""",
            (student,first_second,int(moment.timestamp()))):
        reported[datetime.fromtimestamp(at,TZ).date()] = (mood-3)/2
    points=[]
    for i in range(7):
        day=start+timedelta(days=i)
        values=daily.get(day,[])
        value=reported.get(day,round(sum(values)/len(values),2) if values else None)
        points.append({'date':day.isoformat(), 'value':value})
    # Requiring consecutive calendar days prevents gaps or multiple same-day entries triggering a warning.
    latest=6 if points[6]['value'] is not None else 5
    signal=all(p['value'] is not None and p['value']<=-.5 for p in points[latest-1:latest+1])
    return {'points':points,'flag_day':points[latest]['date'] if signal else None}


def grant(db,student,teacher,cohort,now):
    return db.execute("""SELECT g.expires FROM care_grants g
        JOIN users s ON s.id=g.student AND s.role='student' AND s.cohort=g.cohort
        JOIN users m ON m.id=g.teacher AND m.role='manager' AND m.cohort=g.cohort
        WHERE g.student=? AND g.teacher=? AND g.cohort=? AND g.expires>?""",
        (student,teacher,cohort,now)).fetchone()


def followed(db,student,teacher,day):
    return bool(day and db.execute("""SELECT 1 FROM care_events WHERE student=? AND teacher=?
        AND kind='follow' AND day=? LIMIT 1""",(student,teacher,day)).fetchone())


def student_view(db,user,moment,now):
    sid,cohort=user['id'],user['cohort']
    invites=rows(db.execute("""SELECT i.id,m.name AS teacher,i.cohort,i.expires FROM care_invitations i
        JOIN users m ON m.id=i.teacher AND m.role='manager' AND m.cohort=i.cohort
        WHERE i.student=? AND i.state='pending' AND i.expires>? ORDER BY i.issued DESC""",(sid,now)))
    teachers=rows(db.execute("""SELECT m.id,m.name,CASE WHEN g.expires>? THEN g.expires END AS until
        FROM users m LEFT JOIN care_grants g ON g.teacher=m.id AND g.student=? AND g.cohort=m.cohort
        WHERE m.role='manager' AND m.cohort=? ORDER BY m.name,m.id""",(now,sid,cohort)))
    visits=rows(db.execute("""SELECT m.name,e.at FROM care_events e JOIN users m ON m.id=e.teacher
        WHERE e.student=? AND e.kind='view' ORDER BY e.id DESC LIMIT 5""",(sid,)))
    return {'cohort':cohort,'invitations':invites,'teachers':teachers,'preview':curve(db,sid,moment),'visits':visits}


def manager_view(db,user,moment,now):
    tid,cohort=user['id'],user['cohort']
    roster=rows(db.execute("SELECT id,name,username FROM users WHERE role='student' AND cohort=? ORDER BY name,id",(cohort,)))
    for member in roster:
        sid=member['id']; permission=grant(db,sid,tid,cohort,now)
        member['until']=permission['expires'] if permission else None
        if permission:
            signal=curve(db,sid,moment)['flag_day']
            member['flag_day']=signal
            member['followed']=followed(db,sid,tid,signal)
    pending=rows(db.execute("""SELECT s.name,s.username,i.expires FROM care_invitations i JOIN users s ON s.id=i.student
        WHERE i.teacher=? AND i.cohort=? AND i.state='pending' AND i.expires>? ORDER BY i.issued DESC""",(tid,cohort,now)))
    return {'cohort':cohort,'roster':roster,'pending':pending}


def send_invite(db,user,data,now):
    field=data.get('field');query=data.get('query')
    if field not in ('username','name') or not isinstance(query,str) or not 1<=len(query.strip())<=60:
        raise ValueError('请输入完整的学生账号或姓名')
    matched=db.execute(f"SELECT id,cohort FROM users WHERE role='student' AND {field}=? LIMIT 2",(query.strip(),)).fetchall()
    if not matched:raise ValueError('没有匹配的已注册学生，请核对账号或姓名')
    if len(matched)>1:raise ValueError('存在同名学生，请使用学生账号邀请')
    sid=matched[0]['id']; tid=user['id']
    if matched[0]['cohort']==user['cohort']:raise ValueError('这位学生已经在本班')
    db.execute("""UPDATE care_invitations SET state='expired' WHERE student=? AND teacher=? AND state='pending'
        AND (expires<=? OR cohort<>?)""",(sid,tid,now,user['cohort']))
    db.execute("""INSERT OR IGNORE INTO care_invitations(id,student,teacher,cohort,issued,expires,state)
        VALUES(?,?,?,?,?,?,'pending')""",(uuid4().hex,sid,tid,user['cohort'],now,now+7*86400))
    return {'ok':True}


def decide(db,user,data,now):
    key=data.get('id');decision=data.get('decision');sid=user['id']
    if not isinstance(key,str) or decision not in ('accept','decline'):raise ValueError('请选择有效的班级邀请')
    invite=db.execute("""SELECT i.teacher,i.cohort FROM care_invitations i JOIN users m
        ON m.id=i.teacher AND m.cohort=i.cohort AND m.role='manager'
        WHERE i.id=? AND i.student=? AND i.state='pending' AND i.expires>?""",(key,sid,now)).fetchone()
    if not invite:raise ValueError('邀请已处理或已失效')
    db.execute('UPDATE care_invitations SET state=? WHERE id=?',(decision,key))
    if decision=='accept':
        if user['cohort']!=invite['cohort']:
            db.execute('UPDATE users SET cohort=? WHERE id=?',(invite['cohort'],sid))
            db.execute('DELETE FROM care_grants WHERE student=?',(sid,))
            db.execute("""UPDATE support_shares SET revoked=? WHERE student=? AND revoked IS NULL""",
                       (datetime.fromtimestamp(now,timezone.utc).isoformat(),sid))
        db.execute("UPDATE care_invitations SET state='closed' WHERE student=? AND state='pending'",(sid,))
    return {'ok':True,'cohort':invite['cohort'] if decision=='accept' else user['cohort']}


def handle(db,user,method,path,data):
    if not path.startswith('/api/care/'):return NotImplemented
    op=path.removeprefix('/api/care/')
    if op not in ROUTES:return NotImplemented
    expected,role=ROUTES[op]
    if method!=expected:raise ValueError('请求方式无效')
    if user['role']!=role:raise PermissionError('当前身份无法访问')
    # Re-read membership inside the transaction so a parallel transfer/revocation cannot revive access.
    if not db.in_transaction:db.execute('BEGIN IMMEDIATE' if method=='POST' else 'BEGIN')
    fresh=db.execute('SELECT id,role,cohort FROM users WHERE id=?',(user['id'],)).fetchone()
    if not fresh or fresh['role']!=role:raise PermissionError('当前身份已发生变化')
    user=dict(fresh);uid=user['id'];cohort=user['cohort']
    moment=clock();now=int(moment.timestamp())
    if op=='student':return student_view(db,user,moment,now)
    if op=='manager':return manager_view(db,user,moment,now)
    if op=='invite':return send_invite(db,user,data,now)
    if op=='decision':return decide(db,user,data,now)
    if op in ('allow','revoke'):
        teacher=required_id(data,'teacher')
        if op=='revoke':
            db.execute('DELETE FROM care_grants WHERE student=? AND teacher=?',(uid,teacher))
            return {'ok':True}
        days=data.get('days')
        if type(days) is not int or days not in (3,7,14) or data.get('confirmed') is not True:
            raise ValueError('请先预览共享内容，然后确认授权期限')
        if not db.execute("SELECT id FROM users WHERE id=? AND role='manager' AND cohort=?",(teacher,cohort)).fetchone():
            raise PermissionError('只能向本班负责人授权')
        db.execute("""INSERT INTO care_grants(student,teacher,cohort,expires,granted) VALUES(?,?,?,?,?)
            ON CONFLICT(student,teacher) DO UPDATE SET cohort=excluded.cohort,expires=excluded.expires,granted=excluded.granted""",
                   (uid,teacher,cohort,now+days*86400,now))
        record(db,uid,teacher,'allow',now);return {'ok':True}
    student=required_id(data,'student')
    permission=grant(db,student,uid,cohort,now)
    if not permission:raise PermissionError('授权已结束，当前无法查看这位学生的趋势')
    result=curve(db,student,moment)
    if op in ('curve','update'):
        if op=='curve':
            view_id=record(db,student,uid,'view',now)
        else:
            view_id=required_id(data,'view')
            # An open curve belongs to one grant. A revoke followed by a new grant always
            # requires a fresh explicit view, even when both happened within the same second.
            if not db.execute("""SELECT 1 FROM care_events v WHERE v.id=? AND v.student=? AND v.teacher=?
                AND v.kind='view' AND NOT EXISTS (SELECT 1 FROM care_events g WHERE g.student=v.student
                AND g.teacher=v.teacher AND g.kind='allow' AND g.id>v.id)""",(view_id,student,uid)).fetchone():
                raise PermissionError('授权已更新，请重新打开曲线')
        return {**result,'view':view_id,'until':permission['expires'],'followed':followed(db,student,uid,result['flag_day'])}
    day=result['flag_day']
    if not day or data.get('day')!=day:raise ValueError('该提醒已更新，请刷新后查看')
    if not followed(db,student,uid,day):record(db,student,uid,'follow',now,day)
    return {'ok':True}
