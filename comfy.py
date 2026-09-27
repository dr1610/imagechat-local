"""Local ComfyUI transport. No model loading and no changes to ComfyUI."""
import base64
import ipaddress
import json
import os
import socket
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


class AppError(Exception):
    def __init__(self, category, message, detail=None):
        super().__init__(message)
        self.category, self.detail = category, detail

    def as_dict(self):
        return dict(category=self.category, message=str(self), detail=self.detail)


def local_url(url):
    p = urllib.parse.urlsplit(url.rstrip('/'))
    if p.scheme != 'http' or p.username or p.password or p.path not in ('', '/') or p.query or p.fragment:
        raise AppError('Connection', '接続先はローカルComfyUIの http://ホスト:ポート を指定してください。')
    host = p.hostname or ''
    try:
        ip = ipaddress.ip_address(host)
        allowed = ip.is_loopback or ip.is_private and not ip.is_unspecified and not ip.is_link_local
    except ValueError:
        allowed = host == 'localhost'
    if not allowed:
        raise AppError('Privacy', 'ローカルモードではlocalhostまたはプライベートIPだけに接続できます。')
    try:
        port = p.port
    except ValueError:
        raise AppError('Connection', 'ポート番号が正しくありません。')
    return url.rstrip('/')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AppError('Privacy', 'ComfyUIから別URLへの転送は許可されていません。')


class Comfy:
    def __init__(self, url):
        self.url = local_url(url)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, path, data=None, raw=False, timeout=15, content_type='application/json'):
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode() if data is not None else None
        req = urllib.request.Request(self.url + path, body, {'Content-Type': content_type})
        try:
            with self.opener.open(req, timeout=timeout) as response:
                out = response.read()
                return out if raw else json.loads(out) if out else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode('utf-8', 'replace')[:16000]
            raise AppError('Workflow' if path == '/prompt' else 'ComfyAPI', f'ComfyUIがエラーを返しました（HTTP {e.code}）。', detail)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise AppError('Connection', 'ComfyUIへ接続できません。起動と接続先を確認してください。', str(e))

    def upload(self, path):
        boundary = 'QIC' + os.urandom(12).hex()
        name = 'qic_' + os.urandom(12).hex() + '.png'
        data = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\nContent-Type: image/png\r\n\r\n'.encode()
                + path.read_bytes() + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\nfalse\r\n--{boundary}--\r\n'.encode())
        r = self.request('/upload/image', data, content_type='multipart/form-data; boundary=' + boundary, timeout=60)
        return '/'.join(x for x in (r.get('subfolder'), r['name']) if x)

    def events(self, client_id, callback, stop):
        """Small RFC6455 receive client; progress is optional, history remains authoritative."""
        p = urllib.parse.urlsplit(self.url)
        while not stop.is_set():
            try:
                with socket.create_connection((p.hostname, p.port or 80), timeout=5) as sock:
                    key = base64.b64encode(os.urandom(16)).decode()
                    sock.sendall((f'GET /ws?clientId={client_id} HTTP/1.1\r\nHost: {p.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
                    def receive(n):
                        out = b''
                        while len(out) < n:
                            part = sock.recv(n - len(out))
                            if not part:
                                raise OSError('WebSocket closed')
                            out += part
                        return out
                    header = b''
                    while not header.endswith(b'\r\n\r\n') and len(header) < 8192:
                        header += receive(1)
                    if b' 101 ' not in header.split(b'\r\n')[0]:
                        raise OSError('WebSocket upgrade refused')
                    sock.settimeout(20)
                    while not stop.is_set():
                        a, b = receive(2)
                        size = b & 127
                        if size == 126:
                            size = struct.unpack('!H', receive(2))[0]
                        elif size == 127:
                            size = struct.unpack('!Q', receive(8))[0]
                        if size > 32 * 1024 * 1024:
                            raise OSError('Frame too large')
                        mask = receive(4) if b & 128 else None
                        payload = receive(size)
                        if mask:
                            payload = bytes(v ^ mask[i % 4] for i, v in enumerate(payload))
                        opcode = a & 15
                        if opcode == 1:
                            callback(json.loads(payload))
                        elif opcode == 8:
                            break
                        elif opcode == 9:
                            m = os.urandom(4)
                            sock.sendall(bytes([0x8A, 0x80 | len(payload)]) + m + bytes(v ^ m[i % 4] for i, v in enumerate(payload)))
            except (OSError, ValueError, KeyError):
                stop.wait(3)
