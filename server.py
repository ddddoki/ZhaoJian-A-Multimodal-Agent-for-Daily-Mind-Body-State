"""Local first edition of Zhaojian. Run python server.py --demo."""
import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import secrets
import sqlite3
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, unquote

import student
import campus
import manager
import personal
import ops
import journal
import pet
import companion_ai
import registration
from desktop_launch import DesktopPetLauncher, LaunchError
import care
import planner
from registration import password_hash

ROOT = Path(__file__).resolve().parent
WEB = ROOT / 'web'
MODULES = (student, campus, manager, personal, ops, journal, pet, companion_ai, care, planner)
PUBLIC_FIELDS = ('id', 'username', 'name', 'role', 'cohort')
DEMO_USERS = [('lin', '林同学', 'student', '软件一班'), ('zhou', '周同学', 'student', '软件二班'), ('chen', '陈老师', 'manager', '软件一班'), ('wu', '吴老师', 'manager', '软件二班'), ('ops', '运营体验员', 'operator', '软件一班')]


def connect(file):
    db = sqlite3.connect(file, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def setup(file, demo):
    Path(file).parent.mkdir(parents=True, exist_ok=True)
    db = connect(file)
    try:
        with db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, name TEXT NOT NULL, role TEXT NOT NULL, cohort TEXT NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, expires INTEGER NOT NULL);''')
            migrated = registration.init(db)
            for module in MODULES:
                module.init(db)
            if demo:
                for username, name, role, cohort in DEMO_USERS:
                    gender = {'lin': 'female', 'zhou': 'male'}.get(username)
                    existing = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
                    if existing is None:
                        salt=secrets.token_hex(16)
                        db.execute('INSERT INTO users(username,name,role,cohort,salt,password_hash,gender) VALUES(?,?,?,?,?,?,?)',
                                   (username,name,role,cohort,salt,password_hash('ZhaojianDemo1',salt),gender))
                    elif migrated and gender and (existing['role'],existing['name']) == ('student',name):
                        # Only update known fictional accounts in an existing demo database.
                        if existing['password_hash'] == password_hash('ZhaojianDemo1',existing['salt']):
                            db.execute('UPDATE users SET gender=? WHERE id=?', (gender,existing['id']))
    finally:
        db.close()


def public_user(row):
    result = {key:row[key] for key in PUBLIC_FIELDS}
    if row['role'] == 'student':
        result['gender'] = row['gender']
    return result


def codespace_origin(port):
    name = os.environ.get('CODESPACE_NAME')
    domain = os.environ.get('GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN')
    if os.environ.get('CODESPACES') == 'true' and name and domain:
        return f'https://{name}-{port}.{domain}'


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, content, mime='application/json; charset=utf-8', cookie=None):
        if not isinstance(content, bytes):
            content=json.dumps(content,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(content)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        if cookie:
            self.send_header('Set-Cookie',cookie)
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        path=unquote(urlsplit(self.path).path)
        if path.startswith('/api/'):
            return self.api('GET',path,{})
        file=(WEB / (path.lstrip('/') or 'index.html')).resolve()
        if not file.is_relative_to(WEB) or not file.is_file():
            return self.reply(404,{'error':'页面不存在'})
        mime=mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
        self.reply(200,file.read_bytes(), mime+'; charset=utf-8' if mime.startswith(('text/','application/javascript')) else mime)

    def accepts_origin(self, origin):
        host = self.headers.get('Host')
        if urlsplit(origin).netloc == host:
            return True
        # Port forwarding may rewrite Host or Origin to the internal loopback address.
        public_origin = getattr(self.server, 'codespace_origin', None)
        if not public_origin:
            return False
        port = self.server.server_port
        local_hosts = (f'127.0.0.1:{port}', f'localhost:{port}')
        if origin == public_origin:
            return host in local_hosts
        return host == urlsplit(public_origin).netloc and origin in {f'http://{h}' for h in local_hosts}

    def do_POST(self):
        origin=self.headers.get('Origin')
        if origin and not self.accepts_origin(origin):
            return self.reply(403,{'error':'请求来源无效'})
        path = urlsplit(self.path).path
        max_mb = 8 if path == '/api/journal/save' else 1
        try:
            size=int(self.headers.get('Content-Length',0))
            if size<0 or size>max_mb*1024*1024 or self.headers.get_content_type()!='application/json':
                raise ValueError
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict): raise ValueError
        except (UnicodeError,ValueError):
            return self.reply(400,{'error':f'请提交有效的 JSON 数据，大小不超过 {max_mb} MB'})
        self.api('POST',path,data)

    def api(self, method, path, data):
        db=connect(self.server.dbfile)
        try:
            with db:
                result,status,cookie=self.dispatch(db,method,path,data)
            self.reply(status,result,cookie=cookie)
        except PermissionError as exc:
            self.reply(403,{'error':str(exc) or '没有访问权限'})
        except (ValueError,KeyError,TypeError,sqlite3.IntegrityError) as exc:
            self.reply(400,{'error':str(exc) if isinstance(exc,ValueError) else '数据格式不正确或记录重复'})
        except Exception:
            import traceback
            traceback.print_exc()
            self.reply(500,{'error':'保存或读取失败，请重新尝试'})
        finally:
            db.close()

    def dispatch(self,db,method,path,data):
        cookies=SimpleCookie();cookies.load(self.headers.get('Cookie',''))
        token=cookies['zj_session'].value if 'zj_session' in cookies else ''
        digest=hashlib.sha256(token.encode()).hexdigest()
        user=db.execute('SELECT u.* FROM users u JOIN sessions s ON u.id=s.user_id WHERE s.token=? AND s.expires>?',(digest,time.time())).fetchone()
        if path=='/api/session' and method=='GET':
            return {'user':public_user(user) if user else None,'demo':self.server.demo,
                    'desktop_pet':os.name=='nt' and hasattr(self.server,'desktop_pet')},200,None
        if path == '/api/demo/invite' and method == 'POST':
            if not self.server.demo:
                raise PermissionError('仅演示库开放体验邀请')
            return registration.issue_invite(db, data.get('role'), '软件一班', hours=1, demo=True),200,None
        if path == '/api/register' and method == 'POST':
            row = registration.register(db, data, self.server.demo)
            return {'user':public_user(row)},201,registration.session_cookie(db, row['id'], digest)
        if path == '/api/login' and method == 'POST':
            row = registration.authenticate(db, data)
            if row is None:
                return {'error':'身份、账号或密码不正确'},401,None
            return {'user':public_user(row)},200,registration.session_cookie(db, row['id'], digest)
        if path=='/api/logout' and method=='POST':
            if hasattr(self.server,'desktop_pet'):
                self.server.desktop_pet.close(digest)
            db.execute('DELETE FROM sessions WHERE token=?',(digest,))
            return {'ok':True},200,'zj_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'
        if user is None:return {'error':'请先登录'},401,None
        if path == '/api/desktop/start' and method == 'POST':
            if user['role'] != 'student':
                raise PermissionError('请使用学生身份打开桌面小照')
            if not hasattr(self.server,'desktop_pet'):
                return {'error':'此服务尚未启用本机桌宠'},503,None
            try:
                return self.server.desktop_pet.start(token),200,None
            except LaunchError as exc:
                return {'error':str(exc)},503,None
        if (method == 'GET' and path == '/api/profile') or (method == 'POST' and path in ('/api/profile/gender','/api/profile/clear-cycle')):
            return registration.profile(db, user, path, data),200,None
        for module in MODULES:
            result=module.handle(db,public_user(user),method,path,data)
            if result is not NotImplemented:return result,200,None
        return {'error':'接口不存在'},404,None


def main():
    cli=argparse.ArgumentParser(description='照见本地服务')
    cli.add_argument('--demo',action='store_true',help='创建虚构体验账号，启用一键体验')
    cli.add_argument('--open',action='store_true',help='服务就绪后打开浏览器')
    cli.add_argument('--port',type=int,default=8767)
    cli.add_argument('--db',type=Path)
    args=cli.parse_args();file=args.db or ROOT/'.local'/('demo.sqlite3' if args.demo else 'app.sqlite3')
    setup(file,args.demo)
    with ThreadingHTTPServer(('127.0.0.1',args.port),Handler) as server:
        server.dbfile=file;server.demo=args.demo
        server.codespace_origin = codespace_origin(server.server_port)
        server.desktop_pet = DesktopPetLauncher(server.server_port)
        print(f'照见已启动 http://127.0.0.1:{server.server_port}',flush=True)
        if args.open:
            import webbrowser
            webbrowser.open(f'http://127.0.0.1:{server.server_port}')
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.desktop_pet.close()

if __name__=='__main__':main()
