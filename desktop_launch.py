"""Start one local desktop companion for a particular web session."""
import hashlib
import json
import os
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
from threading import Lock, Thread

ROOT = Path(__file__).resolve().parent


class LaunchError(Exception):
    pass


class DesktopPetLauncher:
    def __init__(self, port):
        self.port = port
        self._lock = Lock()
        self._process = None
        self._session = None

    def _stop(self):
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        self._process = self._session = None

    def close(self, session=None):
        with self._lock:
            if session is None or session == self._session:
                self._stop()

    def start(self, token):
        if os.name != 'nt':
            raise LaunchError('桌面小照目前支持 Windows。')
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self._lock:
            if self._process is not None and self._process.poll() is None and self._session == digest:
                return {'running': True, 'already_running': True}
            self._stop()
            try:
                proc = subprocess.Popen(
                    [sys.executable, str(ROOT / 'desktop_pet.py'), '--port', str(self.port)],
                    cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                self._process = proc
                self._session = digest
                # The credential is passed only to the fixed local helper, never to argv, disk or the browser.
                with proc.stdin as pipe:
                    pipe.write((json.dumps({'token': token}) + '\n').encode('utf-8'))
                received = Queue(maxsize=1)

                def read_ready():
                    with proc.stdout as pipe:
                        received.put(pipe.readline(2048))

                Thread(target=read_ready, daemon=True).start()
                answer = json.loads(received.get(timeout=16))
                if not isinstance(answer, dict) or answer.get('ready') is not True or proc.poll() is not None:
                    raise LaunchError('桌面窗口启动失败，请检查当前登录和本机图形环境。')
            except (Empty, ValueError, OSError, LaunchError) as exc:
                self._stop()
                raise LaunchError('未能打开桌面小照。请确认已登录学生账号，并已安装 Tk 和 Pillow 后再试。') from exc
            return {'running': True, 'already_running': False}
