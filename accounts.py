"""Provision a student or manager for the local, non-demo database."""
import argparse
from getpass import getpass
import secrets
from server import ROOT, connect, setup, password_hash


def main():
    parser=argparse.ArgumentParser(description='新建本地照见账号')
    parser.add_argument('username');parser.add_argument('name');parser.add_argument('cohort');parser.add_argument('--role',choices=['student','manager','operator'],default='student')
    args=parser.parse_args()
    if not all(x.strip() and len(x)<=60 for x in (args.username,args.name,args.cohort)):parser.error('账号、姓名、班级应为 1—60 个字符')
    password=getpass('请输入密码（至少 10 个字符）：')
    if not 10<=len(password)<=256 or password!=getpass('再次输入密码：'):parser.error('密码长度不符或两次密码不同')
    file=ROOT/'.local'/'app.sqlite3';setup(file,False);db=connect(file)
    try:
        with db:
            if db.execute('SELECT 1 FROM users WHERE username=?',(args.username.strip(),)).fetchone():parser.error('账号已存在')
            salt=secrets.token_hex(16);db.execute('INSERT INTO users(username,name,role,cohort,salt,password_hash) VALUES(?,?,?,?,?,?)',(args.username.strip(),args.name.strip(),args.role,args.cohort.strip(),salt,password_hash(password,salt)))
    finally:db.close()
    print('账号已建立，请使用 python server.py 启动个人数据库。')

if __name__=='__main__':main()
