"""Optional on-device Ollama integration. Input stays on the loopback interface."""
import json
import os
from urllib import error, request


def compose(text, mode):
    model=os.environ.get('ZHAOJIAN_LOCAL_MODEL', '').strip()
    if not model:
        return None
    instruction=('你是照见校园桌宠。用中文和大学生交流，尊重自主选择。'
                 '根据所选方式倾听、梳理问题或给一个可执行的微小行动。用三句以内回答。'
                 '遇到紧急危险鼓励联系身边可信任的人和当地急救。不得诊断、开药或承诺疗效。'
                 '你无法查看健康数据、课表或发起联系；不要编造服务或号码。')
    payload={'model':model,'stream':False,'messages':[{'role':'system','content':instruction},{'role':'user','content':f'陪伴方式：{mode}\n{text}'}], 'options':{'num_predict':220}}
    req=request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    try:
        opener=request.build_opener(request.ProxyHandler({}), NoRedirect())
        with opener.open(req,timeout=24) as response:
            obj=json.loads(response.read(100000)); reply=obj['message']['content']
            return reply.strip()[:650] if isinstance(reply,str) and reply.strip() else None
    except (OSError,error.URLError,ValueError,KeyError,TypeError):
        return None


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self,*args):
        return None
