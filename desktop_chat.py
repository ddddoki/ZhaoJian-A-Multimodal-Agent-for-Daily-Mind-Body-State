"""Tk conversation window for Xiao Zhao. All network work runs outside Tk's thread."""
import queue
import threading
import tkinter as tk

from desktop_client import DesktopAPIError


PAPER = '#f3f7f2'
INK = '#24443e'
MUTED = '#526c63'
ACCENT = '#265f52'
LINE = '#c9dbd1'
FONT = 'Microsoft YaHei UI'


def button(parent, label, callback, primary=False):
    return tk.Button(parent, text=label, command=callback, relief='flat', borderwidth=0,
                     bg=ACCENT if primary else '#e0ece4', fg='white' if primary else INK,
                     activebackground='#346e61' if primary else '#c7e0d1',
                     activeforeground='white' if primary else INK, disabledforeground='#8c9c94',
                     padx=10, pady=4, cursor='hand2', font=(FONT, 9))


def context(turns):
    return [message for turn in turns[-3:] for message in (
        {'role': 'user', 'content': turn['question']},
        {'role': 'assistant', 'content': turn['answer']},
    )]


class ChatPanel:
    def __init__(self, root, client, user, on_mood=None, place=None):
        self.root, self.client, self.user = root, client, user
        self.on_mood, self.place = on_mood, place
        self.window = None
        self.turns = []
        self.revision = None
        self.busy = False
        self.expired = False
        self.ready = False
        self.model_name = ''
        self._results = queue.Queue()
        self._generation = 0

    def _build(self):
        w = self.window = tk.Toplevel(self.root)
        w.withdraw()
        w.title('小照 · 桌面对话')
        w.configure(bg=PAPER)
        w.attributes('-topmost', True)
        w.minsize(280, 290)
        w.protocol('WM_DELETE_WINDOW', self.close)
        w.bind('<Escape>', lambda _: self.close())
        w.columnconfigure(0, weight=1)
        w.rowconfigure(1, weight=1)

        header = tk.Frame(w, bg='#dcebe0', padx=13, pady=8)
        header.grid(row=0, column=0, sticky='ew')
        tk.Label(header, text='小照', bg='#dcebe0', fg=INK,
                 font=(FONT, 15, 'bold')).pack(side='left')
        self.owner_label = tk.Label(header, bg='#dcebe0', fg=MUTED, font=(FONT, 9))
        self.owner_label.pack(side='right')

        body = tk.Frame(w, bg=PAPER, padx=13, pady=6)
        body.grid(row=1, column=0, sticky='nsew')
        self.log = tk.Text(body, bg=PAPER, fg=INK, wrap='char', relief='flat', height=6,
                           padx=1, highlightthickness=0, cursor='arrow', font=(FONT, 10))
        scroll = tk.Scrollbar(body, command=self.log.yview, width=10)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.log.pack(side='left', fill='both', expand=True)
        self.log.tag_configure('speaker', foreground=ACCENT, font=(FONT, 9, 'bold'), spacing1=5)
        self.log.tag_configure('copy', spacing3=5, lmargin1=2, lmargin2=2)
        self.log.tag_configure('quiet', foreground=MUTED, spacing1=6)
        self.log.configure(state='disabled')

        compose = tk.Frame(w, bg=PAPER, padx=12, pady=7)
        compose.grid(row=2, column=0, sticky='ew')
        modes = tk.Frame(compose, bg=PAPER)
        modes.pack(fill='x')
        self.mode = tk.StringVar(w, '倾听')
        self.mode_controls = []
        for option in ('倾听','梳理','起步'):
            control = tk.Radiobutton(modes, text=option, value=option, variable=self.mode,
                                     indicatoron=False, relief='flat', bd=0, bg=PAPER, fg=INK,
                                     activebackground='#d5e8db', selectcolor='#cce2d5',
                                     padx=7, pady=3, font=(FONT, 9))
            control.pack(side='left')
            self.mode_controls.append(control)
        self.retain = tk.BooleanVar(w, False)
        self.retain_control = tk.Checkbutton(modes, text='保留三轮', variable=self.retain,
                                             command=self._retention, bg=PAPER, activebackground=PAPER,
                                             fg=MUTED, font=(FONT, 9), bd=0, highlightthickness=0)
        self.retain_control.pack(side='right')
        self.field = tk.Text(compose, height=2, bg='#fdfefb', fg=INK, font=(FONT, 10),
                             wrap='char', relief='flat', highlightbackground=LINE,
                             highlightthickness=1, highlightcolor=ACCENT, padx=7, pady=6)
        self.field.pack(fill='x', pady=(5,3))
        self.field.bind('<Control-Return>', self._keyboard_send)
        self.status = tk.StringVar(w, '')
        hint = tk.Label(compose, textvariable=self.status, anchor='w', justify='left', bg=PAPER,
                        fg=MUTED, wraplength=318, font=(FONT, 9))
        hint.pack(fill='x', pady=(0,4))
        hint.bind('<Configure>', lambda e: hint.configure(wraplength=max(100,e.width-3)))
        self.scope = tk.Label(compose, bg=PAPER, fg=MUTED, anchor='w',
                              justify='left', font=(FONT, 8))
        self.scope.pack(fill='x', pady=(0,3))
        actions = tk.Frame(compose, bg=PAPER)
        actions.pack(fill='x')
        self.offline = button(actions, '离线发送', lambda: self.send(False))
        self.ai = button(actions, '本机 AI 回应', lambda: self.send(True), True)
        self.offline.pack(side='left', fill='x', expand=True, padx=(0,3))
        self.ai.pack(side='left', fill='x', expand=True, padx=(3,0))

    def _keyboard_send(self, event):
        self.send(False)
        return 'break'

    def _controls(self):
        allowed = self.ready and not self.busy and not self.expired
        state = 'normal' if allowed else 'disabled'
        for control in [self.field,self.offline,self.retain_control,*self.mode_controls]:
            control.configure(state=state)
        self.ai.configure(state='normal' if allowed and self.model_name else 'disabled')

    def _paint(self, message=''):
        self.log.configure(state='normal')
        self.log.delete('1.0','end')
        if message or not self.turns:
            self.log.insert('end', message or '我在。今天有什么想和我说的？', 'quiet')
        else:
            for turn in self.turns:
                self.log.insert('end','我\n','speaker')
                self.log.insert('end', turn['question']+'\n','copy')
                self.log.insert('end','小照 · '+turn['source']+'\n','speaker')
                self.log.insert('end', turn['answer']+'\n','copy')
        self.log.configure(state='disabled')
        self.log.see('end')

    def _run(self, work, success, error=None):
        self.busy = True
        self._controls()
        self._generation += 1
        generation = self._generation

        def worker():
            try:
                result = (True, work())
            except Exception as exc:
                result = (False, exc)
            self._results.put((generation, result))

        def poll():
            if generation != self._generation:
                return
            while True:
                try:
                    task, (ok, result) = self._results.get_nowait()
                except queue.Empty:
                    self.root.after(65, poll)
                    return
                if task == generation:
                    break
            self.busy = False
            if ok:
                success(result)
            elif isinstance(result, DesktopAPIError) and result.status in (401,403):
                self.expire()
            else:
                if error:
                    error()
                self.status.set(str(result) if isinstance(result,DesktopAPIError) else '本次请求失败，请稍后再试。')
            self._controls()

        threading.Thread(target=worker, name='XiaozhaoRequest', daemon=True).start()
        self.root.after(65, poll)

    def _check_owner(self):
        current = self.client.get('/api/session').get('user')
        if not current or current.get('id') != self.user['id'] or current.get('role') != 'student':
            raise DesktopAPIError('学生会话已结束', 401)

    def show(self, x=None, y=None):
        if self.window is None:
            self._build()
        w = self.window
        if x is None: x = self.root.winfo_rootx()
        if y is None: y = self.root.winfo_rooty()
        if self.place:
            self.place(w, x, y, 370, 450)
        else:
            x=max(0,min(x,w.winfo_screenwidth()-370))
            y=max(0,min(y,w.winfo_screenheight()-450))
            w.geometry(f'370x450+{x}+{y}')
        w.deiconify()
        w.lift()
        if self.expired:
            self.expire()
            return
        if self.busy:
            return
        self.ready = False
        self.owner_label.configure(text=self.user['name']+' · '+self.user['username'])
        self._paint('正在连接本人的照见空间…')
        self.status.set('正在读取会话')

        def load():
            self._check_owner()
            pet = self.client.get('/api/pet')
            status = self.client.get('/api/ai/status')
            return pet,status.get('text',{})

        def loaded(result):
            pet, model = result
            if pet['keep']:
                self.turns = list(pet['turns'])
            elif self.revision is not None and self.revision != pet['revision']:
                self.turns.clear()
            self.revision = pet['revision']
            self.retain.set(pet['keep'])
            self.model_name = model.get('model','') if model.get('available') else ''
            self.ready = True
            self.scope.configure(text='本机 AI 使用本次问题和近三轮对话。' if self.model_name else '当前可使用离线陪伴。')
            self.status.set('')
            self._paint()
            self.field.focus_set()
        self._run(load, loaded)

    open = show

    def close(self):
        if self.window is not None:
            self.window.withdraw()

    hide = close

    def expire(self):
        self.expired = True
        self.busy = self.ready = False
        self._generation += 1
        self.turns.clear()
        if self.window is not None:
            self.field.configure(state='normal')
            self.field.delete('1.0','end')
            self.retain.set(False)
            self.owner_label.configure(text='')
            self.scope.configure(text='')
            self._paint('登录已到期或已退出。请在学生端重新登录，再点「放到桌面」。')
            self.status.set('')
            self._controls()

    def _retention(self):
        if self.busy or not self.ready:
            return
        desired = self.retain.get()

        def updated(state):
            self.retain.set(state['keep'])
            self.revision = state['revision']
            if not state['keep']:
                self.turns.clear()
                self._paint()
            self.status.set('接下来的三轮对话会留存。' if state['keep'] else '已清除留存对话。')
        self._run(lambda:self.client.post('/api/pet/retention', {'keep':desired}),
                  updated, lambda:self.retain.set(not desired))

    def send(self, use_ai):
        if self.busy or not self.ready or self.expired:
            return
        question = self.field.get('1.0','end-1c').strip()
        if not 1 <= len(question) <= 1000:
            self.status.set('请输入 1 至 1000 个字。')
            return
        payload = {'text':question, 'mode':self.mode.get(), 'history':context(self.turns),
                   'use_ai':bool(use_ai)}
        self.status.set('小照正在想…' if use_ai else '小照在听…')

        def work():
            answer = self.client.post('/api/pet/chat', payload)
            self._check_owner()
            return answer

        def answered(result):
            self.turns.append({'question':question,'answer':result['text'],'source':result['source']})
            self.turns = self.turns[-12:]
            self.field.configure(state='normal')
            self.field.delete('1.0','end')
            self.status.set('可回到学生端「求助与共享」联系支持。' if result.get('urgent') else '')
            self._paint()
            if self.on_mood:
                self.on_mood(result['mood'])
        self._run(work, answered)
