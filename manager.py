"""Scoped campus support. Only student-authored summaries leave the personal area."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4


def init(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS support_shares (
            id TEXT PRIMARY KEY,
            student INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            recipient INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            topic TEXT NOT NULL, summary TEXT NOT NULL,
            created TEXT NOT NULL, expires TEXT NOT NULL, revoked TEXT,
            status TEXT NOT NULL DEFAULT 'new');
        CREATE INDEX IF NOT EXISTS ix_support_recipient ON support_shares(recipient, expires);
        CREATE TABLE IF NOT EXISTS support_access (
            id INTEGER PRIMARY KEY, share TEXT NOT NULL REFERENCES support_shares(id) ON DELETE CASCADE,
            actor INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            event TEXT NOT NULL, at TEXT NOT NULL);
    ''')


TOPICS = ('学业安排', '校园适应', '生活困扰', '想找人聊聊', '其他事项')
STATES = ('new', 'following', 'done')
WINDOWS = (1, 3, 7)
MIN_GROUP = 5


def moment():
    return datetime.now(timezone.utc).replace(microsecond=0)


def rows(cursor):
    fields = [d[0] for d in cursor.description]
    return [dict(zip(fields, row)) for row in cursor]


def log(db, share, actor, event, at):
    db.execute('INSERT INTO support_access(share,actor,event,at) VALUES(?,?,?,?)', (share,actor,event,at))


def manager_share(db, user, key, now):
    result = rows(db.execute('''SELECT s.id, s.summary, s.topic, s.status, s.created, s.expires, u.name AS student_name
        FROM support_shares s JOIN users u ON u.id=s.student WHERE s.id=? AND s.recipient=?
        AND s.revoked IS NULL AND s.expires>? AND u.cohort=? AND u.role='student' ''',
        (key, user['id'], now, user['cohort'])))
    if not result:
        raise PermissionError('这条事项当前未授权访问。')
    return result[0]


def handle(db, user, method, path, data):
    actions = {'/api/sharing': 'GET','/api/sharing/create':'POST','/api/sharing/revoke':'POST',
               '/api/manage':'GET','/api/manage/detail':'POST','/api/manage/status':'POST'}
    if path not in actions:
        return NotImplemented
    role = 'manager' if path.startswith('/api/manage') else 'student'
    if user['role'] != role:
        raise PermissionError('当前身份无法访问此页面。')
    if method != actions[path]:
        raise ValueError('请求方式有误。')
    user_id, cohort = user['id'],user['cohort']
    current = moment()
    now = current.isoformat()
    if path == '/api/sharing':
        recipients = rows(db.execute("SELECT id,name FROM users WHERE cohort=? AND role='manager' ORDER BY name,id",(cohort,)))
        shares = rows(db.execute('''SELECT s.id,s.topic,s.summary,s.status,s.created,s.expires,s.revoked,u.name AS recipient_name,
            (SELECT MAX(at) FROM support_access a WHERE a.share=s.id AND a.event='view') AS last_view
            FROM support_shares s JOIN users u ON u.id=s.recipient WHERE student=? ORDER BY s.created DESC,s.rowid DESC''',(user_id,)))
        for share in shares:
            share['active'] = not share['revoked'] and share['expires'] > now
        return {'recipients':recipients,'shares':shares,'topics':TOPICS}
    if path == '/api/sharing/create':
        topic, summary = data.get('topic'),data.get('summary')
        days, recipient = data.get('days'),data.get('recipient')
        if topic not in TOPICS or not isinstance(summary,str) or not 1<=len(summary.strip())<=400:
            raise ValueError('请选择事项类型，并填写 1 至 400 字的共享摘要。')
        if type(days) is not int or days not in WINDOWS or type(recipient) is not int:
            raise ValueError('请选择有效的接收人和共享期限。')
        if not db.execute("SELECT 1 FROM users WHERE id=? AND role='manager' AND cohort=?",(recipient,cohort)).fetchone():
            raise PermissionError('接收人超出可选范围。')
        key = uuid4().hex
        db.execute('INSERT INTO support_shares(id,student,recipient,topic,summary,created,expires) VALUES(?,?,?,?,?,?,?)',
                   (key,user_id,recipient,topic,summary.strip(),now,(current+timedelta(days=days)).isoformat()))
        log(db,key,user_id,'grant',now)
        return {'id':key}
    key = data.get('id') if isinstance(data.get('id'),str) else ''
    if path == '/api/sharing/revoke':
        existing = db.execute('SELECT revoked FROM support_shares WHERE id=? AND student=?',(key,user_id)).fetchone()
        if not existing:
            raise PermissionError('这条事项不属于当前账号。')
        if not existing[0]:
            db.execute('UPDATE support_shares SET revoked=? WHERE id=? AND student=?',(now,key,user_id))
            log(db,key,user_id,'revoke',now)
        return {'ok':True}
    if path == '/api/manage':
        inbox = rows(db.execute('''SELECT s.id,s.status,s.created,s.expires FROM support_shares s JOIN users u ON u.id=s.student
            WHERE s.recipient=? AND s.revoked IS NULL AND s.expires>? AND u.cohort=? AND u.role='student'
            ORDER BY s.created DESC,s.rowid DESC''',(user_id,now,cohort)))
        total = db.execute("SELECT COUNT(*) FROM users WHERE role='student' AND cohort=?",(cohort,)).fetchone()[0]
        group = {'suppressed':total<MIN_GROUP,'minimum':MIN_GROUP}
        if total>=MIN_GROUP:
            group['members'] = total
            group['activity'] = []
            for weeks, label in ((0,'近 7 天'), (1,'前一个 7 天')):
                end = int(current.timestamp()) + 1 - weeks * 7 * 86400
                start = end - 7 * 86400
                for table, metric in (('snapshots','自评人数'), ('student_cards','打卡人数')):
                    count = db.execute(f'''SELECT COUNT(DISTINCT e.user_id) FROM {table} e
                        JOIN users u ON u.id=e.user_id WHERE u.role='student' AND u.cohort=?
                        AND e.at>=? AND e.at<?''',(cohort,start,end)).fetchone()[0]
                    enough = min(count,total-count) >= MIN_GROUP
                    group['activity'].append({'label':label+metric,'count':count if enough else None})
        return {'cohort':cohort,'inbox':inbox,'group':group}
    # Acquire the write transaction before reading a grant. Revocation and a
    # logged view/status change are then ordered consistently by SQLite.
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')
    now = moment().isoformat()
    info = manager_share(db,user,key,now)
    if path == '/api/manage/detail':
        log(db,key,user_id,'view',now)
        return info
    status = data.get('status')
    if status not in STATES:
        raise ValueError('处理状态无效。')
    db.execute('UPDATE support_shares SET status=? WHERE id=?',(status,key))
    log(db,key,user_id,'status:'+status,now)
    return {'ok':True}
