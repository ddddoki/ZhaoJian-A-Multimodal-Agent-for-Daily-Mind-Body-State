"""Registration with scoped, expiring invitations for privileged roles."""
import hashlib
import hmac
import re
import secrets
import time

ROLES = ('student', 'manager', 'operator')
STAFF = ('manager', 'operator')


def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS invitations (
        digest TEXT PRIMARY KEY, role TEXT NOT NULL, cohort TEXT NOT NULL,
        expires INTEGER NOT NULL, used_by INTEGER REFERENCES users(id),
        demo INTEGER NOT NULL DEFAULT 0)""")


def field(value, label, limit=60):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit or not value.strip().isprintable():
        raise ValueError(f'请填写有效的{label}（最多 {limit} 个字符）')
    return value.strip()


def signature(token):
    return hashlib.sha256(token.encode()).hexdigest()


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 300000).hex()


def issue_invite(db, role, cohort, *, hours=24, demo=False):
    if role not in STAFF or not 1 <= hours <= 168:
        raise ValueError('请选择管理或运营角色，邀请有效期为 1 至 168 小时')
    cohort = field(cohort, '班级')
    token = secrets.token_urlsafe(20)
    expires = int(time.time()) + hours * 3600
    db.execute('DELETE FROM invitations WHERE expires <= ? AND used_by IS NULL', (int(time.time()),))
    db.execute('INSERT INTO invitations(digest,role,cohort,expires,demo) VALUES(?,?,?,?,?)',
               (signature(token), role, cohort, expires, int(demo)))
    return {'invite': token, 'cohort': cohort, 'role': role, 'expires': expires}


def register(db, data, demo):
    role = data.get('role')
    if role not in ROLES:
        raise ValueError('请选择注册身份')
    username = field(data.get('username'), '账号', 40)
    if not re.fullmatch(r'[a-zA-Z0-9_.-]{3,40}', username):
        raise ValueError('账号需为 3 至 40 个英文字母、数字、短横线、下划线或点')
    name = field(data.get('name'), '显示名称')
    password = data.get('password')
    if not isinstance(password, str) or not 10 <= len(password) <= 256:
        raise ValueError('密码长度应为 10 至 256 个字符')
    cohort = field(data.get('cohort'), '班级') if role == 'student' else None
    invitation = signature(field(data.get('invite'), '邀请码', 128)) if role in STAFF else None
    salt = secrets.token_hex(16)
    derived = password_hash(password, salt)
    db.execute('BEGIN IMMEDIATE')
    if invitation:
        row = db.execute('SELECT cohort FROM invitations WHERE digest=? AND role=? AND (demo=0 OR demo=?) AND used_by IS NULL AND expires>?',
                         (invitation, role, int(demo), int(time.time()))).fetchone()
        if row is None:
            raise ValueError('邀请码无效、已使用、已过期或与当前身份不符')
        cohort = row['cohort']
    if db.execute('SELECT 1 FROM users WHERE username=?', (username,)).fetchone():
        raise ValueError('该账号已被使用，请换一个账号')
    user_id = db.execute('INSERT INTO users(username,name,role,cohort,salt,password_hash) VALUES(?,?,?,?,?,?)',
                         (username, name, role, cohort, salt, derived)).lastrowid
    if invitation:
        db.execute('UPDATE invitations SET used_by=? WHERE digest=?', (user_id, invitation))
    return db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()


def authenticate(db, data):
    username, password = data.get('username'), data.get('password')
    if not isinstance(username, str) or not isinstance(password, str) or len(password)>256:
        raise ValueError('请填写账号和密码')
    user = db.execute('SELECT * FROM users WHERE username=?', (username.strip(),)).fetchone()
    if not user or not hmac.compare_digest(password_hash(password,user['salt']), user['password_hash']):
        return None
    if 'role' in data and data['role'] != user['role']:
        return None
    return user


def session_cookie(db, user_id, previous):
    now = int(time.time())
    token = secrets.token_urlsafe(32)
    db.execute('DELETE FROM sessions WHERE expires<=? OR token=?', (now, previous))
    db.execute('INSERT INTO sessions VALUES(?,?,?)', (signature(token), user_id, now+43200))
    return f'zj_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200'
