"""Client for the student session handed to the native pet by the local server."""
import http.client
import json
import re


class DesktopAPIError(Exception):
    def __init__(self, message, status=0):
        super().__init__(message)
        self.status = status


class Client:
    def __init__(self, port, token):
        if type(port) is not int or not 0 < port < 65536:
            raise ValueError('本地服务端口无效')
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,200}', token):
            raise ValueError('学生会话无效')
        self.port = port
        self._cookie = 'zj_session=' + token

    def get(self, path):
        return self.request(path)

    def post(self, path, data):
        return self.request(path, data)

    def request(self, path, data=None):
        if not isinstance(path, str) or not re.fullmatch(r'/api/[a-z0-9/-]+', path):
            raise ValueError('桌面端只能调用照见本机服务')
        # A separate direct loopback connection for each worker; never follow redirects.
        connection = http.client.HTTPConnection('127.0.0.1', self.port,
                                                timeout=115 if path == '/api/pet/chat' else 5)
        try:
            headers = {'Cookie': self._cookie, 'Accept': 'application/json'}
            body = None
            if data is not None:
                body = json.dumps(data, ensure_ascii=False).encode('utf-8')
                headers['Content-Type'] = 'application/json; charset=utf-8'
            connection.request('GET' if data is None else 'POST', path, body, headers)
            response = connection.getresponse()
            if 300 <= response.status < 400:
                raise DesktopAPIError('本机服务返回了意外的跳转', response.status)
            payload = json.loads(response.read(256_001))
            if not isinstance(payload, dict):
                raise DesktopAPIError('本机服务返回了无效数据')
            if not 200 <= response.status < 300:
                raise DesktopAPIError(str(payload.get('error', '请求失败')), response.status)
            return payload
        except (OSError, http.client.HTTPException) as exc:
            raise DesktopAPIError('连接照见失败，请确认本地服务已启动。') from exc
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise DesktopAPIError('本机服务未返回有效数据。') from exc
        finally:
            connection.close()
