"""Independent Windows pet window. Its student session is received from the local launcher."""
import argparse
import ctypes
from ctypes import wintypes
import json
import math
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk

from PIL import Image, ImageTk

from desktop_chat import ChatPanel
from desktop_client import Client, DesktopAPIError


ROOT = Path(__file__).resolve().parent
ATLAS = ROOT / 'desktop_assets' / 'pet.png'
KEY_COLOR = '#ff00ff'
MOODS = ('calm', 'happy', 'curious', 'relaxed', 'sleepy', 'listening')
ACTIONS = {'摸摸头': 'pat', '招招手': 'wave', '伸懒腰': 'stretch', '打个盹': 'rest'}


class MonitorInfo(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('screen', wintypes.RECT),
                ('work', wintypes.RECT), ('flags', wintypes.DWORD)]


class Display:
    def __init__(self):
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        try:
            # Use physical pixels for both Tk pointer positions and monitor work areas.
            self.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except AttributeError:
            self.user32.SetProcessDPIAware()
        self.monitor = self.user32.MonitorFromPoint
        self.monitor.argtypes = (wintypes.POINT, wintypes.DWORD)
        self.monitor.restype = wintypes.HANDLE
        self.info = self.user32.GetMonitorInfoW
        self.info.argtypes = (wintypes.HANDLE, ctypes.POINTER(MonitorInfo))
        self.info.restype = wintypes.BOOL

    def work_area(self, x, y):
        handle = self.monitor(wintypes.POINT(x, y), 2)  # MONITOR_DEFAULTTONEAREST
        info = MonitorInfo()
        info.size = ctypes.sizeof(info)
        if not self.info(handle, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        return info.work

    @staticmethod
    def clamp(x, y, width, height, area):
        return (max(area.left, min(x, area.right - width)),
                max(area.top, min(y, area.bottom - height)))


class DesktopPet:
    def __init__(self, root, display, client, user, initial):
        self.root, self.display, self.client, self.user = root, display, client, user
        self.position_file = Path(os.environ.get('ZHAOJIAN_DESKTOP_POSITION',
                                                 ROOT / '.local' / 'desktop-pet-position.json'))
        self.drag = None
        self.in_action = False
        self.results = queue.Queue()
        self.sprite_size = min(195, max(120, round(root.winfo_fpixels('1i') * 1.42)))
        self.size = self.sprite_size + 10
        self.mood = initial.get('mood', 'calm')
        self.motion_at = 0.0
        root.title('照见 · 桌面小照')
        root.overrideredirect(True)
        root.configure(bg=KEY_COLOR)
        root.attributes('-transparentcolor', KEY_COLOR, '-toolwindow', True, '-topmost', True)
        self.canvas = tk.Canvas(root, name='mascot', width=self.size, height=self.size,
                                bg=KEY_COLOR, borderwidth=0, highlightthickness=0, cursor='hand2')
        self.canvas.pack()
        self.images = {}
        with Image.open(ATLAS) as atlas:
            side = atlas.height
            if atlas.width != side * len(MOODS):
                raise ValueError('桌宠图集不完整')
            for idx, mood in enumerate(MOODS):
                sprite = atlas.crop((idx*side, 0, (idx+1)*side, side)).convert('RGBA')
                sprite = sprite.resize((self.sprite_size, self.sprite_size), Image.Resampling.LANCZOS)
                # Windows color-key transparency is binary. Remove diffuse shadow pixels
                # before compositing so they do not form a magenta halo on the desktop.
                alpha = sprite.getchannel('A').point(lambda a: 255 if a >= 105 else 0)
                sprite.putalpha(alpha)
                self.images[mood] = ImageTk.PhotoImage(sprite, master=root)
        self.picture = self.canvas.create_image(5, 5, image=self.images.get(self.mood,self.images['calm']), anchor='nw')
        self.chat = ChatPanel(root, client, user, on_mood=self.set_mood, place=self.place_chat)
        self.menu = tk.Menu(root, tearoff=False, font=('Microsoft YaHei UI', 10))
        self.menu.add_command(label='与小照聊天', command=self.open_chat)
        self.menu.add_separator()
        for label, action in ACTIONS.items():
            self.menu.add_command(label=label, command=lambda action=action: self.perform(action))
        self.menu.add_separator()
        self.menu.add_command(label='退出桌面小照', command=root.destroy)
        self.canvas.bind('<ButtonPress-1>', self.press)
        self.canvas.bind('<B1-Motion>', self.move)
        self.canvas.bind('<ButtonRelease-1>', self.release)
        self.canvas.bind('<Button-3>', self.context_menu)
        self.canvas.bind('<Return>', lambda _: self.open_chat())
        root.protocol('WM_DELETE_WINDOW', root.destroy)
        root.bind('<Alt-F4>', lambda _: root.destroy())
        x, y = self.saved_position()
        self.place(x, y, self.display.work_area(x + self.size//2, y + self.size//2))
        root.deiconify()
        root.update_idletasks()
        self.animate()
        root.after(100, self.poll_results)
        root.after(4000, self.verify_owner)

    def saved_position(self):
        try:
            point = json.loads(self.position_file.read_text(encoding='utf-8'))
            x, y = point['x'], point['y']
            if all(type(v) is int and abs(v) < 1_000_000 for v in (x,y)):
                return x,y
        except (OSError, KeyError, ValueError, TypeError):
            pass
        area = self.display.work_area(0, 0)
        return area.right - self.size - 26, area.bottom - self.size - 26

    def place(self, x, y, area):
        self.x, self.y = self.display.clamp(x, y, self.size, self.size, area)
        # "+-nn" is an absolute negative origin in Tk. "-nn" means right/bottom-relative.
        self.root.geometry(f'{self.size}x{self.size}+{self.x}+{self.y}')

    def save_position(self):
        target = self.position_file
        temp = target.with_name(f'{target.name}.{os.getpid()}.tmp')
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temp.write_text(json.dumps({'x':self.x, 'y':self.y}), encoding='utf-8')
            temp.replace(target)
        except OSError:
            pass

    def press(self, event):
        self.canvas.focus_set()
        self.drag = (event.x_root, event.y_root, self.x, self.y, False)
        self.canvas.grab_set()

    def move(self, event):
        if self.drag is None:
            return
        x0, y0, origin_x, origin_y, moved = self.drag
        dx, dy = event.x_root-x0, event.y_root-y0
        if not moved and math.hypot(dx, dy) < 7:
            return
        self.drag = x0, y0, origin_x, origin_y, True
        self.place(origin_x+dx, origin_y+dy, self.display.work_area(event.x_root, event.y_root))

    def release(self, event):
        if self.drag is None:
            return
        self.move(event)
        moved = self.drag[-1]
        self.drag = None
        self.canvas.grab_release()
        if moved:
            self.save_position()
        else:
            self.open_chat()

    def place_chat(self, window, x, y, width, height):
        area = self.display.work_area(self.x+self.size//2, self.y+self.size//2)
        if x+width+12 > area.right:
            x = self.x-width-12
        width = min(width, area.right-area.left-20)
        height = min(height, area.bottom-area.top-50)
        x,y = self.display.clamp(x, y, width+14, height+42, area)
        window.geometry(f'{width}x{height}+{x}+{y}')

    def open_chat(self):
        self.chat.show(self.x+self.size+8, self.y+self.size-450)

    def context_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def set_mood(self, mood):
        if mood in self.images:
            self.mood = mood
            self.motion_at = time.monotonic()
            self.canvas.itemconfigure(self.picture, image=self.images[mood])

    def animate(self):
        now = time.monotonic()
        bob = 1.5 * math.sin(now * (1.6 if self.mood == 'sleepy' else 2.0))
        t = now-self.motion_at
        sway = 3*math.sin(t*12)*(1-t) if t < 1 else 0
        self.canvas.coords(self.picture, 5+round(sway), 5+round(bob))
        self.root.after(75, self.animate)

    def background(self, kind, fetch):
        def run():
            try:
                self.results.put((kind, fetch(), None))
            except DesktopAPIError as exc:
                self.results.put((kind, None, exc))
        threading.Thread(target=run, daemon=True).start()

    def perform(self, action):
        if not self.in_action:
            self.in_action = True
            self.background('action', lambda:self.client.post('/api/pet/interact', {'action':action}))

    def verify_owner(self):
        self.background('session', lambda:self.client.get('/api/session'))

    def poll_results(self):
        while not self.results.empty():
            kind, result, error = self.results.get_nowait()
            if error and error.status in (401,403):
                self.root.destroy()
                return
            if kind == 'session':
                owner = (result or {}).get('user')
                if not error and (not owner or owner.get('id') != self.user['id'] or owner.get('role') != 'student'):
                    self.root.destroy()
                    return
                if error:
                    self.chat.close()
                else:
                    # A disconnected display must not strand the mascot on a vanished monitor.
                    area = self.display.work_area(self.x+self.size//2, self.y+self.size//2)
                    if not self.drag and self.display.clamp(self.x, self.y, self.size, self.size, area) != (self.x,self.y):
                        self.place(self.x, self.y, area)
                self.root.after(4000, self.verify_owner)
            elif kind == 'action':
                self.in_action = False
                if not error:
                    self.set_mood(result['mood'])
        self.root.after(100, self.poll_results)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    root = None
    try:
        if os.name != 'nt':
            raise ValueError('桌面小照需要 Windows')
        handshake = json.loads(sys.stdin.buffer.readline(2048))
        client = Client(args.port, handshake['token'])
        user = client.get('/api/session')['user']
        if not user or user['role'] != 'student':
            raise ValueError('请先登录学生账号')
        initial = client.get('/api/pet')
        display = Display()
        root = tk.Tk()
        root.withdraw()
        pet = DesktopPet(root, display, client, user, initial)
        root.update()
    except (OSError, ValueError, KeyError, TypeError, DesktopAPIError, tk.TclError):
        if root is not None:
            root.destroy()
        print(json.dumps({'ready':False,'error':'无法打开桌面小照，请核对学生会话与本机窗口环境'}),flush=True)
        return 1
    print(json.dumps({'ready':True}),flush=True)
    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
