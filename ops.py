"""Version campus-specific action copy. Published content is plain text."""
from datetime import datetime, timezone


def init(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS ops_versions(
            id INTEGER PRIMARY KEY, cohort TEXT NOT NULL, kind TEXT NOT NULL,
            description TEXT NOT NULL, base_id INTEGER NOT NULL, creator INTEGER NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('draft','published')),
            created TEXT NOT NULL, published TEXT);
        CREATE INDEX IF NOT EXISTS ix_ops_active ON ops_versions(cohort,kind,state,id);
        CREATE TABLE IF NOT EXISTS ops_audit(
            id INTEGER PRIMARY KEY, cohort TEXT NOT NULL, actor INTEGER NOT NULL,
            version_id INTEGER NOT NULL, event TEXT NOT NULL, at TEXT NOT NULL);
    """)


def _live(db, cohort, kind):
    row = db.execute("""SELECT id FROM ops_versions WHERE cohort=? AND kind=?
        AND state='published' ORDER BY published DESC,id DESC LIMIT 1""", (cohort,kind)).fetchone()
    return row[0] if row else 0


def catalog_for(db, cohort, default_catalog):
    catalog = {key:dict(value) for key,value in default_catalog.items()}
    for key, desc in db.execute("""SELECT kind, description FROM ops_versions
        WHERE cohort=? AND state='published' ORDER BY published,id""",(cohort,)):
        if key in catalog:
            catalog[key]['description'] = desc
    return catalog


def _snapshot(cursor):
    names = [field[0] for field in cursor.description]
    return [dict(zip(names, row)) for row in cursor]


def handle(db,user,method,path,data):
    routes={'/api/ops':'GET','/api/ops/draft':'POST','/api/ops/publish':'POST','/api/ops/rollback':'POST'}
    if path not in routes:
        return NotImplemented
    if user['role'] != 'operator':
        raise PermissionError('此操作需要行动库运营权限。')
    if routes[path] != method:
        raise ValueError('请求方式有误。')
    from student import ACTIONS
    cohort=user['cohort']; actor=user['id']
    if path=='/api/ops':
        versions=_snapshot(db.execute("""SELECT id,kind,description,state,base_id,creator,created,published
            FROM ops_versions WHERE cohort=? ORDER BY id DESC""",(cohort,)))
        audit=_snapshot(db.execute("""SELECT a.id,a.version_id,a.event,a.at,u.name AS actor_name FROM ops_audit a
            LEFT JOIN users u ON u.id=a.actor WHERE a.cohort=? ORDER BY a.id DESC LIMIT 50""",(cohort,)))
        defaults={k:{'title':v[0],'description':v[1],'seconds':v[2]} for k,v in ACTIONS.items()}
        return {'cohort':cohort,'defaults':defaults,'active':{k:_live(db,cohort,k) for k in ACTIONS},'versions':versions,'audit':audit}
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')
    now=datetime.now(timezone.utc).isoformat(timespec='microseconds')
    if path=='/api/ops/draft':
        kind=data.get('kind');desc=data.get('description')
        if not isinstance(kind,str) or kind not in ACTIONS or not isinstance(desc,str) or not 1<=len(desc.strip())<=200:
            raise ValueError('请选择已有行动，并填写 1 至 200 字的行动说明。')
        desc=desc.strip()
        if 'id' in data:
            key=data['id']
            if type(key) is not int or db.execute("""UPDATE ops_versions SET description=? WHERE
                id=? AND cohort=? AND kind=? AND state='draft' AND creator=?""",(desc,key,cohort,kind,actor)).rowcount != 1:
                raise ValueError('草稿已变更，或不属于当前编辑人。')
            event='edit'
        else:
            key=db.execute("""INSERT INTO ops_versions(cohort,kind,description,base_id,creator,state,created)
                VALUES(?,?,?,?,?,'draft',?)""",(cohort,kind,desc,_live(db,cohort,kind),actor,now)).lastrowid
            event='draft'
    elif path=='/api/ops/publish':
        key=data.get('id')
        if type(key) is not int: raise ValueError('请选择草稿。')
        row=db.execute("SELECT kind,base_id,description FROM ops_versions WHERE id=? AND cohort=? AND state='draft'",(key,cohort)).fetchone()
        if not row or _live(db,cohort,row[0])!=row[1] or row[2]!=data.get('reviewed'):
            raise ValueError('草稿或当前版本已变化，请重新预览并以当前版本新建草稿。')
        db.execute("UPDATE ops_versions SET state='published', published=? WHERE id=?",(now,key));event='publish'
    else:
        kind=data.get('kind');target=data.get('target');expected=data.get('current')
        if not isinstance(kind,str) or kind not in ACTIONS or type(target) is not int or type(expected) is not int or not expected or target==expected or _live(db,cohort,kind)!=expected:
            raise ValueError('请从当前版本选择一个历史版本重新发布。')
        if target:
            row=db.execute("SELECT description FROM ops_versions WHERE id=? AND cohort=? AND kind=? AND state='published'",(target,cohort,kind)).fetchone()
            if not row: raise ValueError('历史版本不可用。')
            desc=row[0]
        else:desc=ACTIONS[kind][1]
        key=db.execute("""INSERT INTO ops_versions(cohort,kind,description,base_id,creator,state,created,published)
            VALUES(?,?,?,?,?,'published',?,?)""",(cohort,kind,desc,expected,actor,now,now)).lastrowid
        event='rollback:'+str(target)
    db.execute('INSERT INTO ops_audit(cohort,actor,version_id,event,at) VALUES(?,?,?,?,?)',(cohort,actor,key,event,now))
    return {'id':key}
