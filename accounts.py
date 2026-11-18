"""Provision a local account or issue a one-use scoped staff invitation."""
import argparse
from getpass import getpass
from pathlib import Path
import secrets
import sys
from registration import STAFF, field, issue_invite
from server import ROOT, connect, setup, password_hash


def main():
    legacy = sys.argv[1:2] != ['invite'] or (len(sys.argv) >= 4 and not sys.argv[3].startswith('-'))
    parser = argparse.ArgumentParser(description='建立照见账号' if legacy else '签发照见工作人员注册邀请')
    if legacy:
        parser.add_argument('username')
        parser.add_argument('name')
    parser.add_argument('cohort')
    parser.add_argument('--db', type=Path, default=ROOT/'.local'/'app.sqlite3')
    parser.add_argument('--role', choices=['student',*STAFF] if legacy else STAFF, default='student' if legacy else None, required=not legacy)
    if not legacy:
        parser.add_argument('--hours', type=int, default=24)
    args = parser.parse_args(sys.argv[1:] if legacy else sys.argv[2:])
    setup(args.db,False)
    db = connect(args.db)
    try:
        with db:
            if not legacy:
                invite = issue_invite(db, args.role, args.cohort, hours=args.hours)
                print(f"所属班级：{invite['cohort']}；身份：{invite['role']}；有效期：{args.hours} 小时。")
                print(f"一次性邀请码：{invite['invite']}")
                return
            username, name, cohort = (field(v,k) for v,k in [(args.username,'账号'),(args.name,'姓名'),(args.cohort,'班级')])
            password = getpass('请输入密码（至少 10 个字符）：')
            if not 10 <= len(password) <= 256 or password != getpass('再次输入密码：'):
                parser.error('密码长度不符或两次密码不同')
            if db.execute('SELECT 1 FROM users WHERE username=?',(username,)).fetchone():
                parser.error('账号已存在')
            salt = secrets.token_hex(16)
            db.execute('INSERT INTO users(username,name,role,cohort,salt,password_hash) VALUES(?,?,?,?,?,?)',
                       (username, name, args.role, cohort, salt, password_hash(password,salt)))
    except ValueError as exc:
        parser.error(str(exc))
    finally:
        db.close()
    print('账号已建立。')


if __name__=='__main__':
    main()
