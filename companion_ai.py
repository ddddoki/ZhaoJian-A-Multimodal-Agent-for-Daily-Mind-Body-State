"""Local text generation and neutral image-scene inference. No remote recipients."""
import atexit
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import threading
import time
from urllib import request
import scene_model

AI = Path(__file__).parent / '.local' / 'ai'
TEXT_NAME = 'Qwen2.5-1.5B-Instruct'
VISION_NAME = 'CLIP ViT-B/32'
SYSTEM = ('你是照见里的校园陪伴伙伴小照。用自然简洁的简体中文和大学生说话，认真回应用户所说的具体细节。'
          '尊重个人意愿，避免说教、诊断、虚构的资源、打分和对他人内心的推测。有紧急危险时鼓励找身边可信任的人和当地紧急服务。')
_lock = threading.Lock()
_process = None
_endpoint = ''
_secret = ''
_opener = request.build_opener(request.ProxyHandler({}))


def init(db):
    pass


def bundled():
    return (AI/'runtime'/'llama-server.exe').is_file() and (AI/'model.gguf').is_file()


def stop():
    global _process
    if _process is not None and _process.poll() is None:
        _process.terminate()
        try:_process.wait(timeout=3)
        except subprocess.TimeoutExpired:_process.kill()


atexit.register(stop)


def _call(url,payload=None,timeout=8,key=None):
    headers={'Content-Type':'application/json'}
    if key:headers['Authorization']='Bearer '+key
    query=request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None,headers=headers)
    with _opener.open(query,timeout=timeout) as resp:
        return json.loads(resp.read(524288))


def _worker():
    global _process,_secret,_endpoint
    with _lock:
        if _process is not None and _process.poll() is None:return _endpoint,_secret
        if not bundled():return None,None
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        _endpoint=f'http://127.0.0.1:{port}'
        _secret=secrets.token_urlsafe(24)
        env=dict(os.environ,LLAMA_API_KEY=_secret)
        cmd=[str(AI/'runtime'/'llama-server.exe'),'-m',str(AI/'model.gguf'),'--host','127.0.0.1','--port',str(port),
             '--alias',TEXT_NAME,'-c','4096','-t','6','-ngl','0','--parallel','1','--no-webui','--log-disable']
        _process=subprocess.Popen(cmd,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                  creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        for _ in range(120):
            if _process.poll() is not None:break
            try:
                if _call(_endpoint+'/health',timeout=.8,key=_secret).get('status')=='ok':return _endpoint,_secret
            except (OSError,ValueError):pass
            time.sleep(.25)
        stop();return None,None


def _generate(messages):
    model=os.environ.get('ZHAOJIAN_LOCAL_MODEL','').strip()
    try:
        if model:
            response=_call('http://127.0.0.1:11434/api/chat',{'model':model,'messages':messages,'stream':False,
                           'options':{'num_predict':150,'temperature':.55}},timeout=50)
            content=response['message']['content']
        else:
            host,key=_worker()
            if not host:return None
            model=TEXT_NAME
            response=_call(host+'/v1/chat/completions',{'model':model,'messages':messages,'temperature':.55,'max_tokens':150},timeout=65,key=key)
            content=response['choices'][0]['message']['content']
        if not isinstance(content,str) or not content.strip():return None
        return {'text':content.strip()[:1000],'source':'本机生成 · '+model}
    except (OSError,ValueError,KeyError,IndexError,TypeError):return None


def converse(text,mode,history,memory):
    messages=[{'role':'system','content':SYSTEM+' 当前陪伴方式：'+str(mode)+'。回应不超过三句话，最多问一个具体问题。'}]
    for item in history[-6:]:
        if item.get('role') in ('user','assistant'):
            messages.append({'role':item['role'],'content':str(item['content'])[:450]})
    prompt=('这次我允许你参考的个人偏好：'+memory+'\n' if memory else '')+text
    return _generate(messages+[{'role':'user','content':prompt}])


def reflect(text,feelings,need):
    if any(w in text for w in ('自杀','不想活','自残','想死','轻生','活不下去')):
        return {'text':'谢谢你记下这份感受。如果你现在可能伤害自己，请先联系身边可信任的人陪伴你，并联系当地急救或就近急诊。','source':'固定安全回应'}
    prompt=json.dumps({'手记':text[:1800],'我选的感受':feelings,'我需要':need},ensure_ascii=False)
    return _generate([{'role':'system','content':'你是大学生的日记回声。只回应这一篇里的具体小事。第一句话要提到原文中的一个动作或物品。第二句用一个问题邀请作者说出更多。不要套用安慰话，不要续写，不要评价或诊断。用自然中文。'},
                      {'role':'user','content':'手记：交完报告，就在操场旁买了个热红薯。感受：松了一口气。'},
                      {'role':'assistant','content':'交完报告，手里正好捧着热红薯。那一刻你最想慢慢享受的，是哪一点？'},
                      {'role':'user','content':prompt}])


def look(image_bytes,caption):
    if not scene_model.ready():return None
    try:return {'text':scene_model.describe(image_bytes),'source':'本机场景匹配 · '+VISION_NAME}
    except (OSError,ValueError,RuntimeError):return None


def handle(db,user,method,path,data):
    if method!='GET' or path!='/api/ai/status':return NotImplemented
    model=os.environ.get('ZHAOJIAN_LOCAL_MODEL','').strip()
    available=bundled()
    if model:
        try:available=model in [m.get('name') for m in _call('http://127.0.0.1:11434/api/tags',timeout=2).get('models',[])]
        except (OSError,ValueError):available=False
    return {'text':{'available':available,'model':model or TEXT_NAME,'provider':'本机 Ollama' if model else '本机 llama.cpp'},
            'vision':{'available':bool(scene_model.ready()),'model':VISION_NAME,'provider':'本机 ONNX Runtime'}}
