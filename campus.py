"""Student-owned calendar (campus local time) and independently consented records."""
import csv
import io
import re
from urllib.parse import urlsplit
from datetime import date, datetime, timedelta, timezone

CAMPUS_TZ = timezone(timedelta(hours=8))
KINDS = {'课程', '考试', '作业', '活动'}
MAX_EVENTS = 300


def init(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS campus_events (
          id INTEGER PRIMARY KEY, owner INTEGER NOT NULL, title TEXT NOT NULL,
          kind TEXT NOT NULL, starts TEXT NOT NULL, ends TEXT NOT NULL, place TEXT NOT NULL,
          origin TEXT NOT NULL, UNIQUE(owner,title,starts));
        CREATE INDEX IF NOT EXISTS campus_time ON campus_events(owner,starts);
        CREATE TABLE IF NOT EXISTS campus_preferences (owner INTEGER PRIMARY KEY, reminders INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS campus_public_events (
          id INTEGER PRIMARY KEY, cohort TEXT NOT NULL, title TEXT NOT NULL, kind TEXT NOT NULL,
          starts TEXT NOT NULL, ends TEXT NOT NULL, place TEXT NOT NULL, UNIQUE(cohort,title,starts));
        CREATE TABLE IF NOT EXISTS campus_public_resources (
          id INTEGER PRIMARY KEY, cohort TEXT NOT NULL, title TEXT NOT NULL, contact TEXT NOT NULL,
          url TEXT NOT NULL, UNIQUE(cohort,title));
        CREATE TABLE IF NOT EXISTS cycle_consent (owner INTEGER PRIMARY KEY, personalize INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS cycle_entries (id INTEGER PRIMARY KEY, owner INTEGER NOT NULL,
          start_day TEXT NOT NULL, end_day TEXT NOT NULL, feeling TEXT NOT NULL,
          UNIQUE(owner,start_day));
    ''')


def text(value, length, label, required=True):
    if not isinstance(value, str) or len(value.strip()) > length or (required and not value.strip()):
        raise ValueError(f'请检查{label}（最多 {length} 字）')
    return value.strip()


def calendar_time(value):
    try:
        value = datetime.fromisoformat(value)
        if value.tzinfo:
            value = value.astimezone(CAMPUS_TZ).replace(tzinfo=None)
        return value.replace(second=0, microsecond=0)
    except (TypeError, ValueError, OverflowError):
        raise ValueError('时间格式应为 YYYY-MM-DDTHH:MM') from None


def checked_event(raw):
    title = text(raw.get('title'), 80, '事务标题')
    place = text(raw.get('place', ''), 100, '地点', False)
    kind = raw.get('kind', '课程')
    if not isinstance(kind,str) or kind not in KINDS:
        raise ValueError('类型请选择课程、考试、作业或活动')
    start, end = calendar_time(raw.get('starts')), calendar_time(raw.get('ends'))
    if not start < end or end - start > timedelta(days=31):
        raise ValueError('结束时间须晚于开始时间，单项跨度最多 31 天')
    return dict(title=title, kind=kind, starts=start.isoformat(timespec='minutes'), ends=end.isoformat(timespec='minutes'), place=place)


def repeat(event, count, interval):
    if not (1 <= count <= 40 and interval in (1, 2)):
        raise ValueError('重复次数应为 1–40 次，间隔为 1 或 2 周')
    for i in range(count):
        delta = timedelta(weeks=interval*i)
        try:
            yield {**event, **{key: (calendar_time(event[key])+delta).isoformat(timespec='minutes') for key in ('starts','ends')}}
        except OverflowError:
            raise ValueError('课表日期超出范围') from None


def ics_time(value, params=''):
    utc = value.endswith('Z')
    tz = re.search(r'TZID="?([^;":]+(?:/[^;":]+)?)',params,re.I)
    if tz and tz[1].lower() not in ('asia/shanghai','asia/chongqing','china standard time','utc','etc/utc'):
        raise ValueError('日历时区未支持，请导出北京时间或 UTC 的课表')
    for fmt in ('%Y%m%dT%H%M%S','%Y%m%dT%H%M','%Y%m%d'):
        try:
            t = datetime.strptime(value.rstrip('Z'),fmt)
            if utc or (tz and tz[1].lower() in ('utc','etc/utc')):
                t = t.replace(tzinfo=timezone.utc).astimezone(CAMPUS_TZ).replace(tzinfo=None)
            return t
        except ValueError: pass
    raise ValueError('ICS 中存在无法识别的日期')


def parse_ics(content):
    events, current = [], None
    for line in re.sub(r'\r?\n[ \t]', '',content).splitlines():
        line = line.strip()
        if line.upper()=='BEGIN:VEVENT': current = {}; continue
        if current is None: continue
        if line.upper()=='END:VEVENT':
            def field(name, fallback=''):
                return current.get(name,('',fallback))[1]
            if any(key in current for key in ('EXDATE','RDATE','RECURRENCE-ID','DURATION')):
                raise ValueError('此 ICS 含例外日期、调课或特殊时长，请导出展开的事件或使用 CSV')
            if 'DTSTART' not in current: raise ValueError('ICS 事件缺少开始日期')
            params,start_raw=current['DTSTART']; start=ics_time(start_raw,params)
            if 'DTEND' in current:
                params,end_raw=current['DTEND']; end=ics_time(end_raw,params)
            else: end=start+timedelta(days=1) if len(start_raw)==8 else start+timedelta(hours=1)
            unescape=lambda s: re.sub(r'\\([nN,;\\])',lambda m:' ' if m[1].lower()=='n' else m[1],s)
            title=unescape(field('SUMMARY'))
            event=checked_event(dict(title=title,kind='考试' if '考' in title else '课程',place=unescape(field('LOCATION')),starts=start.isoformat(),ends=end.isoformat()))
            count=interval=1
            if field('RRULE'):
                try: rule=dict(x.split('=',1) for x in field('RRULE').upper().split(';'))
                except ValueError: raise ValueError('ICS 重复规则格式无效') from None
                if rule.get('FREQ')!='WEEKLY' or set(rule)-{'FREQ','INTERVAL','COUNT','UNTIL','BYDAY','WKST'} or rule.get('BYDAY','') not in ('',('MO','TU','WE','TH','FR','SA','SU')[start.weekday()]):
                    raise ValueError('仅支持每周或隔周同一星期的重复课；复杂课表请转为逐次 CSV')
                interval=int(rule.get('INTERVAL','1'))
                if interval not in (1,2): raise ValueError('仅支持每周或隔周重复')
                if 'COUNT' in rule: count=int(rule['COUNT'])
                elif 'UNTIL' in rule: count=(ics_time(rule['UNTIL']).date()-start.date()).days//(7*interval)+1
                else: raise ValueError('重复课缺少结束日期或次数')
            events.extend(repeat(event,count,interval)); current=None
            if len(events)>MAX_EVENTS: raise ValueError('单次导入最多 300 条事务')
        elif ':' in line:
            prop,value=line.split(':',1);name=prop.split(';')[0].upper();current[name]=(prop,value)
    if current is not None: raise ValueError('ICS 文件不完整')
    return events


def parse_import(data):
    content=text(data.get('content'), 180000,'课表内容').lstrip('\ufeff')
    if content.upper().startswith('BEGIN:VCALENDAR'):
        events=parse_ics(content)
    else:
        rows=csv.DictReader(io.StringIO(content)); events=[]
        if not {'标题','开始','结束'}.issubset(rows.fieldnames or []): raise ValueError('CSV 必须包含 标题、开始、结束 三列')
        for line,row in enumerate(rows,2):
            try:
                e=checked_event(dict(title=row['标题'],starts=row['开始'],ends=row['结束'],kind=row.get('类型') or '课程',place=row.get('地点') or ''))
                events.extend(repeat(e,int(row.get('次数') or 1),int(row.get('间隔周') or 1)))
            except (ValueError,TypeError) as error: raise ValueError(f'CSV 第 {line} 行：{error}') from None
            if len(events)>MAX_EVENTS: raise ValueError('单次导入最多 300 条事务')
    if not events: raise ValueError('课表中没有可导入的事务')
    return events


def event_list(db,owner):
    return [dict(row) for row in db.execute('SELECT id,title,kind,starts,ends,place,origin FROM campus_events WHERE owner=? ORDER BY starts,id',(owner,))]


def preview(events, existing):
    result=[]; saved={(r['title'],r['starts']) for r in existing}; candidates=list(existing)
    for e in events:
        dup=(e['title'],e['starts']) in saved
        clashes=[] if dup else [r['title'] for r in candidates if r['starts'] < e['ends'] and e['starts'] < r['ends']][:3]
        result.append({**e,'duplicate':dup,'conflicts':clashes})
        if not dup: saved.add((e['title'],e['starts'])); candidates.append(e)
    return result


def ensure_id(data):
    value=data.get('id');
    if type(value) is not int or value<1: raise ValueError('请选择有效记录')
    return value


def boolean(data,key):
    if type(data.get(key)) is not bool: raise ValueError('请确认授权或提醒选项')
    return int(data[key])


def campus(db,owner,method,path,data):
    if method=='GET' and path=='/api/campus':
        events=event_list(db,owner); pref=db.execute('SELECT reminders FROM campus_preferences WHERE owner=?',(owner,)).fetchone();now=datetime.now(CAMPUS_TZ).replace(tzinfo=None)
        nowkey=now.isoformat(timespec='minutes');enabled=bool(pref[0]) if pref else True
        future=[e for e in events if e['starts']>=nowkey]; upcoming=future[:1]; hints=[]
        if enabled and not any(e['starts']<=nowkey<e['ends'] for e in events):
            early=next((e for e in future if e['kind']=='课程' and calendar_time(e['starts']).hour<=8 and calendar_time(e['starts'])-now<=timedelta(days=1)),None)
            if early: hints.append('早课前留好通勤时间：「'+early['title']+'」前可以先把课本和钥匙放进包里。')
            exam=next((e for e in future if e['kind']=='考试' and calendar_time(e['starts'])-now<=timedelta(days=7)),None)
            if exam:
                stop=calendar_time(exam['starts']); first_busy=calendar_time(upcoming[0]['starts']) if upcoming else stop
                if min(stop,first_busy)-now>=timedelta(minutes=5): hints.append('距离「'+exam['title']+'」还有准备时间。下一项事务前空出五分钟，先列出三道想复习的题。')
        return {'events':events,'reminders':enabled,'hints':hints}
    if method!='POST': return NotImplemented
    if path=='/api/campus/reminders':
        db.execute('INSERT INTO campus_preferences(owner,reminders) VALUES(?,?) ON CONFLICT(owner) DO UPDATE SET reminders=excluded.reminders',(owner,boolean(data,'enabled'))); return {'ok':True}
    if path=='/api/campus/import/clear':
        n=db.execute("DELETE FROM campus_events WHERE owner=? AND origin='导入'",(owner,)).rowcount;return {'removed':n}
    if path=='/api/campus/delete':
        if not db.execute('DELETE FROM campus_events WHERE id=? AND owner=?',(ensure_id(data),owner)).rowcount: raise ValueError('找不到该事务')
        return {'ok':True}
    if path not in ('/api/campus/save','/api/campus/import/preview','/api/campus/import/confirm'):return NotImplemented
    is_save=path.endswith('/save'); items=[checked_event(data)] if is_save else parse_import(data)
    writing=not path.endswith('/preview')
    if writing and not db.in_transaction: db.execute('BEGIN IMMEDIATE')
    existing=event_list(db,owner);editing=ensure_id(data) if is_save and 'id' in data else None
    if editing and not any(e['id']==editing for e in existing):raise ValueError('找不到该事务')
    rows=preview(items,[e for e in existing if e['id']!=editing]);
    if not writing:return {'rows':rows}
    if any(e['conflicts'] for e in rows) and data.get('allow_conflicts') is not True:raise ValueError('存在时段重叠，请预览后明确确认保留冲突事务')
    if editing:
        e=rows[0];
        if e['duplicate']: raise ValueError('同名同时间的事务已存在')
        db.execute('UPDATE campus_events SET title=?,kind=?,starts=?,ends=?,place=? WHERE owner=? AND id=?',(e['title'],e['kind'],e['starts'],e['ends'],e['place'],owner,editing)); return {'updated':1}
    added=0
    for e in rows:
        if not e['duplicate']:
            db.execute('INSERT INTO campus_events(owner,title,kind,starts,ends,place,origin) VALUES(?,?,?,?,?,?,?)',(owner,e['title'],e['kind'],e['starts'],e['ends'],e['place'],'手动' if is_save else '导入'));added+=1
    return {'added':added,'duplicates':len(rows)-added}


def checked_cycle(data):
    try:
        start=date.fromisoformat(data.get('start_day')); end=date.fromisoformat(data['end_day']) if data.get('end_day') else None
    except (KeyError,ValueError,TypeError): raise ValueError('请选择有效记录日期') from None
    today=datetime.now(CAMPUS_TZ).date()
    if start>today or (end and (end<start or end>today)):raise ValueError('仅可填写已发生的日期，结束日期不能早于开始日期')
    return start.isoformat(),end.isoformat() if end else '',text(data.get('feeling',''),100,'当日感受',False)


def store_cycle(db,owner,start,end,feeling):
    db.execute('INSERT INTO cycle_entries(owner,start_day,end_day,feeling) VALUES(?,?,?,?) ON CONFLICT(owner,start_day) DO UPDATE SET end_day=excluded.end_day,feeling=excluded.feeling',(owner,start,end,feeling))


def cycle(db,owner,method,path,data):
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE' if method == 'POST' else 'BEGIN')
    person = db.execute("SELECT gender FROM users WHERE id=? AND role='student'", (owner,)).fetchone()
    if not person or person[0] != 'female':
        raise PermissionError('经期功能仅对已选择女生的学生本人开放')
    consent=db.execute('SELECT personalize FROM cycle_consent WHERE owner=?',(owner,)).fetchone()
    if path=='/api/privacy' and method=='GET':
        entries=[dict(r) for r in db.execute('SELECT id,start_day,end_day,feeling FROM cycle_entries WHERE owner=? ORDER BY start_day DESC',(owner,))] if consent else []
        today=datetime.now(CAMPUS_TZ).date().isoformat(); active=any(r['start_day']<=today<=(r['end_day'] or today) for r in entries)
        return {'enabled':consent is not None,'personalize':bool(consent and consent[0]),'entries':entries,'suggestion':'如果今天想轻一点，可以选一个坐着完成的两分钟小行动，也可以跳过。' if consent and consent[0] and active else ''}
    if method!='POST': return NotImplemented
    if path=='/api/privacy/consent':
        if boolean(data,'enabled'): db.execute('INSERT OR IGNORE INTO cycle_consent(owner) VALUES(?)',(owner,))
        else:
            db.execute('DELETE FROM cycle_entries WHERE owner=?',(owner,));db.execute('DELETE FROM cycle_consent WHERE owner=?',(owner,))
        return {'ok':True}
    if not consent:raise PermissionError('请先开启个人经期记录授权')
    if path=='/api/privacy/personalize':
        db.execute('UPDATE cycle_consent SET personalize=? WHERE owner=?',(boolean(data,'enabled'),owner)); return {'ok':True}
    if path=='/api/privacy/delete':
        if not db.execute('DELETE FROM cycle_entries WHERE owner=? AND id=?',(owner,ensure_id(data))).rowcount:raise ValueError('找不到该记录')
        return {'ok':True}
    if path=='/api/privacy/save':
        start,end,feeling=checked_cycle(data)
        if 'id' in data:
            if not db.execute('UPDATE cycle_entries SET start_day=?,end_day=?,feeling=? WHERE owner=? AND id=?',(start,end,feeling,owner,ensure_id(data))).rowcount:raise ValueError('找不到该记录')
        else: store_cycle(db,owner,start,end,feeling)
        return {'ok':True}
    if path in ('/api/privacy/import/preview','/api/privacy/import/confirm'):
        source=text(data.get('content'),45000,'经期导出内容').lstrip('\ufeff')
        reader=csv.DictReader(io.StringIO(source));rows=[]
        if not {'开始日期','结束日期'}.issubset(reader.fieldnames or []): raise ValueError('CSV 中需有 开始日期、结束日期 两列，可另加 感受 列')
        seen=set()
        for idx,r in enumerate(reader,2):
            try: start,end,feeling=checked_cycle({'start_day':r['开始日期'],'end_day':r['结束日期'],'feeling':r.get('感受','')})
            except ValueError as exc: raise ValueError(f'第 {idx} 行：{exc}') from None
            if start in seen: raise ValueError(f'第 {idx} 行开始日期重复，请先核对')
            seen.add(start)
            rows.append({'start_day':start,'end_day':end,'feeling':feeling,'update':bool(db.execute('SELECT 1 FROM cycle_entries WHERE owner=? AND start_day=?',(owner,start)).fetchone())})
            if len(rows)>180: raise ValueError('单次最多导入 180 条经期记录')
        if not rows: raise ValueError('文件中没有经期记录')
        if path.endswith('/preview'): return {'rows':rows}
        if data.get('confirmed') is not True: raise ValueError('请逐项核对后确认授权导入')
        for r in rows: store_cycle(db,owner,r['start_day'],r['end_day'],r['feeling'])
        return {'imported':len(rows)}
    return NotImplemented


def public_board(db, user, method, path, data):
    if user is None or user['role'] not in ('student','manager'):
        raise PermissionError('请使用学生或管理账号')
    cohort = user['cohort']
    if method == 'GET' and path == '/api/campus/board':
        events = db.execute('SELECT id,title,kind,starts,ends,place FROM campus_public_events WHERE cohort=? ORDER BY starts,id', (cohort,))
        resources = db.execute('SELECT id,title,contact,url FROM campus_public_resources WHERE cohort=? ORDER BY title,id', (cohort,))
        return {'events':[dict(r) for r in events], 'resources':[dict(r) for r in resources], 'cohort':cohort}
    if method != 'POST':
        return NotImplemented
    if path == '/api/campus/board/add':
        if user['role'] != 'student':
            raise PermissionError('仅学生可添加到个人课表')
        if not db.in_transaction:
            db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT title,kind,starts,ends,place FROM campus_public_events WHERE cohort=? AND id=?',(cohort,ensure_id(data))).fetchone()
        if not row:
            raise ValueError('该公告已撤下或暂不可用')
        item = dict(row)
        owner = user['id']
        match = preview([item], event_list(db,owner))[0]
        if match['duplicate']:
            return {'added':0}
        if match['conflicts'] and data.get('allow_conflicts') is not True:
            raise ValueError('与现有事务时间重叠，请确认是否仍要加入')
        db.execute("INSERT INTO campus_events(owner,title,kind,starts,ends,place,origin) VALUES(?,?,?,?,?,?,'校园发布')",
                   (owner,item['title'],item['kind'],item['starts'],item['ends'],item['place']))
        return {'added':1}
    if user['role'] != 'manager':
        raise PermissionError('仅管理账号可维护班级校历和资源')
    routes = {
        '/api/campus/board/event/save':('campus_public_events','save'),
        '/api/campus/board/event/withdraw':('campus_public_events','withdraw'),
        '/api/campus/board/resource/save':('campus_public_resources','save'),
        '/api/campus/board/resource/withdraw':('campus_public_resources','withdraw'),
    }
    if path not in routes:
        return NotImplemented
    table,action = routes[path]
    if action == 'withdraw':
        if not db.execute(f'DELETE FROM {table} WHERE id=? AND cohort=?',(ensure_id(data),cohort)).rowcount:
            raise ValueError('找不到本班发布的条目')
        return {'ok':True}
    if table == 'campus_public_events':
        fields = checked_event(data)
    else:
        title = text(data.get('title'),80,'资源名称')
        contact = text(data.get('contact',''),180,'联系方法',False)
        url = text(data.get('url',''),500,'资源链接',False)
        if url:
            parts = urlsplit(url)
            if parts.scheme not in ('http','https') or not parts.hostname or parts.username or parts.password or any(c.isspace() or ord(c)<32 or c==chr(92) for c in url):
                raise ValueError('请输入有效的 http 或 https 官方资源链接')
        if not contact and not url:
            raise ValueError('请填写已核实的联系方法或资源链接')
        fields = dict(title=title,contact=contact,url=url)
    args = tuple(fields.values())
    if 'id' in data:
        assignments = ','.join(key+'=?' for key in fields)
        if not db.execute(f'UPDATE {table} SET {assignments} WHERE id=? AND cohort=?',args+(ensure_id(data),cohort)).rowcount:
            raise ValueError('找不到本班发布的条目')
    else:
        names = ','.join(fields)
        placeholders = ','.join('?' for _ in fields)
        db.execute(f'INSERT INTO {table}(cohort,{names}) VALUES(?,{placeholders})',(cohort,)+args)
    return {'ok':True}


def handle(db,user,method,path,data):
    if not (path in ('/api/campus','/api/privacy') or path.startswith(('/api/campus/','/api/privacy/'))):return NotImplemented
    if path == '/api/campus/board' or path.startswith('/api/campus/board/'):
        return public_board(db,user,method,path,data)
    if user is None or user['role']!='student':raise PermissionError('此页面仅对学生本人开放')
    return (cycle if path.startswith('/api/privacy') else campus)(db,user['id'],method,path,data)
