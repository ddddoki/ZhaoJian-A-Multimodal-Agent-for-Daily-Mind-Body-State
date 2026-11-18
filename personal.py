"""Private data portability and user-authorized offline wearable imports."""
import csv
import io
import math
from datetime import datetime, timezone

PERSONAL={'minute_sessions':'owner','plan_items':'owner','care_invitations':'student','care_grants':'student','care_events':'student','journal_entries':'owner','pet_turns':'user_id','pet_states':'user_id','student_experiments':'user_id','snapshots':'user_id','student_actions':'user_id','student_cards':'user_id','student_memories':'user_id','student_observations':'user_id','campus_events':'owner','campus_preferences':'owner','cycle_entries':'owner','cycle_consent':'owner','support_shares':'student','wearable_connections':'owner'}
METRICS={'heart_rate':('心率（次/分）',20,300),'steps':('步数（步）',0,100000),'sleep_hours':('睡眠（小时）',0,24),'hrv_ms':('HRV（毫秒）',0,1000)}


def init(db):
    db.execute('CREATE TABLE IF NOT EXISTS wearable_connections(owner INTEGER PRIMARY KEY, device TEXT NOT NULL)')
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS wearable_sample ON student_observations(user_id,kind,at,source) WHERE source LIKE '设备文件：%'")


def parse_samples(content):
    if not isinstance(content,str) or len(content)>180000:raise ValueError('文件过大或编码不正确')
    reader=csv.DictReader(io.StringIO(content.lstrip('\ufeff')))
    if reader.fieldnames!=['time','metric','value']:raise ValueError('表头应为 time,metric,value')
    samples=[]
    for n,row in enumerate(reader,2):
        try:
            ts=datetime.fromisoformat(row['time'].replace('Z','+00:00')); label,low,high=METRICS[row['metric']];value=float(row['value'])
            if ts.utcoffset() is None or not math.isfinite(value) or not low<=value<=high or ts>datetime.now(timezone.utc):raise ValueError
            samples.append((int(ts.timestamp()),label,value))
        except (ValueError,KeyError,TypeError,AttributeError,OverflowError) as exc:raise ValueError(f'第 {n} 行无效，请核对时区、日期、指标与数值') from exc
        if len(samples)>1000:raise ValueError('每次最多导入 1000 条')
    if not samples:raise ValueError('没有可导入的观测')
    return samples


def handle(db,user,method,path,data):
    if not path.startswith('/api/data/'):return NotImplemented
    if user['role']!='student':raise PermissionError('仅学生本人可用')
    uid=user['id'];op=path.removeprefix('/api/data/')
    if method=='GET' and op=='export':
        # Read authorization and export from one snapshot, including legacy accounts.
        if not db.in_transaction:
            db.execute('BEGIN')
        cycle_allowed = db.execute(
            "SELECT 1 FROM users u JOIN cycle_consent c ON c.owner=u.id WHERE u.id=? AND u.gender='female'",
            (uid,),
        ).fetchone() is not None
        return {
            table: [dict(row) for row in db.execute(f'SELECT * FROM {table} WHERE {owner}=?', (uid,))]
            for table, owner in PERSONAL.items()
            if cycle_allowed or table not in ('cycle_entries', 'cycle_consent')
        }
    if method=='POST' and op=='clear':
        if data.get('confirm')!='清空我的数据':raise ValueError('请输入确认用语')
        for table,owner in PERSONAL.items():db.execute(f'DELETE FROM {table} WHERE {owner}=?',(uid,))
        db.execute('DELETE FROM sessions WHERE user_id=?',(uid,));return {'ok':True}
    if method=='GET' and op=='device':
        row=db.execute('SELECT device FROM wearable_connections WHERE owner=?',(uid,)).fetchone();return {'device':row[0] if row else None}
    if method!='POST':return NotImplemented
    if op=='bind':
        device=data.get('device');
        if not isinstance(device,str) or not 1<=len(device.strip())<=40:raise ValueError('设备名称为 1—40 个字')
        db.execute('INSERT INTO wearable_connections VALUES(?,?) ON CONFLICT(owner) DO UPDATE SET device=excluded.device',(uid,device.strip()));return {'ok':True}
    if op=='unbind':db.execute('DELETE FROM wearable_connections WHERE owner=?',(uid,));return {'ok':True}
    if op in ('preview','import'):
        if op=='import':db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT device FROM wearable_connections WHERE owner=?',(uid,)).fetchone()
        if not row:raise ValueError('请先登记数据来源设备')
        items=parse_samples(data.get('content')); source='设备文件：'+row[0]
        if op=='preview':return {'count':len(items),'sample':[{'kind':k,'value':v} for _,k,v in items[:3]],'device':row[0]}
        if data.get('device')!=row[0]:raise ValueError('设备来源已更改，请重新预览')
        saved=0
        for ts,kind,value in items:
            saved+=db.execute('INSERT OR IGNORE INTO student_observations(user_id,kind,value,at,source) VALUES(?,?,?,?,?)',(uid,kind,value,ts,source)).rowcount
        return {'saved':saved,'duplicates':len(items)-saved}
    return NotImplemented
