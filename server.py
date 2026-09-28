"""Loopback-only desktop web application; no CDN, telemetry, or external AI calls."""
import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import secrets
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core import Application, AppError, ROOT, PARAMS
from comfy import Comfy
from edit_policy import plan as edit_plan
from model_routing import resolve as resolve_model
from image_library import ImageLibrary
from updater import Updater, VERSION

# Windows registry associations can label modules as text/plain. Browsers reject
# those responses as ES modules, preventing the entire UI from initializing.
mimetypes.add_type('text/javascript', '.mjs')
mimetypes.add_type('text/javascript', '.js')


def serve(port=8791, data_root=None):
    token=secrets.token_urlsafe(32)
    installation_id=hashlib.sha256(str(ROOT.resolve()).lower().encode()).hexdigest()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,format,*args): pass

        def send(self,status,data,content_type='application/json; charset=utf-8',download=None):
            if not isinstance(data,bytes): data=json.dumps(data,ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            if download:self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+urllib.parse.quote(download))
            self.end_headers()
            try:self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):pass

        def do_GET(self): self.handle_request(False)
        def do_POST(self):
            with updater.lock:
                if updater.frozen:
                    self.send(409,dict(error=dict(message='更新中です。再起動後に操作してください。')));return
                self.handle_request(True)

        def handle_request(self,mutation):
            try:
                host=self.headers.get('Host','').split(':')[0]
                if host not in ('127.0.0.1','localhost'):raise AppError('Privacy','ローカルホストのみアクセスできます。')
                p=urllib.parse.urlsplit(self.path);path=p.path;query=urllib.parse.parse_qs(p.query)
                if mutation:
                    if self.headers.get('X-QIC-Token')!=token: self.send(403,dict(error=dict(category='Privacy',message='ページを再読み込みしてください。')));return
                    origin=self.headers.get('Origin')
                    if origin and origin not in (f'http://127.0.0.1:{port}',f'http://localhost:{port}'):
                        raise AppError('Privacy','別サイトからの操作は受け付けません。')
                    length=int(self.headers.get('Content-Length',0))
                    if not 0<length<=45*1024*1024:raise AppError('Input','送信サイズが正しくありません。')
                    raw=self.rfile.read(length)
                    if path=='/api/assets':
                        self.send(200,app.store.add_image(raw,urllib.parse.unquote(self.headers.get('X-Filename','image.png'))));return
                    body=json.loads(raw)
                    if path=='/api/updates': result=updater.action(body)
                    elif path=='/api/sessions': result=app.store.create_session(body.get('title','新しいチャット'))
                    elif path.startswith('/api/sessions/'):
                        sid=path.rsplit('/',1)[1];app.store.update_session(sid,body);result={'ok':True}
                    elif path=='/api/library/favorite':result=library.favorite(body)
                    elif path=='/api/organization':result=app.store.organize(body)
                    elif path=='/api/generate':result=app.generate(body)
                    elif path=='/api/generation-plan':
                        preview={**PARAMS,**body.get('params',{})}
                        result=edit_plan(body.get('prompt',''),body.get('references',[]),preview,body.get('editor'))
                        result['model']=resolve_model(preview,body.get('editor'),app.config,editing=bool(body.get('references')),prompt=body.get('prompt',''))
                    elif path=='/api/rewrites':result=app.rewriter.start(body)
                    elif path.startswith('/api/rewrites/') and path.endswith('/cancel'):result=app.rewriter.cancel(path.split('/')[3])
                    elif path.startswith('/api/generations/'):
                        _,_,_,gid,action=path.split('/')
                        if action=='cancel': result=app.cancel(gid)
                        elif action=='regenerate': result=app.regenerate(gid,body.get('params'))
                        elif action=='recover':result=app.retry_output(gid)
                        else:raise AppError('Input','操作が見つかりません。')
                    elif path=='/api/settings':result=app.save_config(body)
                    elif path=='/api/connection':result=app.connection(body.get('url'))
                    elif path=='/api/shutdown':
                        result={'ok':True};app.stopping.set();threading.Thread(target=server.shutdown,daemon=True).start()
                    else:self.send(404,{'error':{'message':'Not found'}});return
                    self.send(200,result);return
                if path=='/api/updates':self.send(200,updater.status());return
                if path=='/api/bootstrap':
                    self.send(200,dict(token=token,settings=app.config,defaults=PARAMS,workflows=app.workflows.list(),sessions=app.store.sessions(),version=VERSION));return
                if path=='/api/library':self.send(200,library.list());return
                if path=='/api/organization':self.send(200,app.store.organization());return
                if path=='/api/sessions':self.send(200,app.store.sessions());return
                if path.startswith('/api/rewrites/'):self.send(200,app.rewriter.get(path.rsplit('/',1)[1]));return
                if path.startswith('/api/sessions/'):
                    self.send(200,app.store.session(path.rsplit('/',1)[1]));return
                if path.startswith('/api/generations/'):
                    g=app.store.generation(path.rsplit('/',1)[1]);self.send(200,g,download='generation-'+g['id']+'.json' if 'download' in query else None);return
                if path.startswith('/api/assets/'):
                    aid=path.rsplit('/',1)[1];a=app.store.asset(aid)
                    self.send(200,app.store.asset_path(aid).read_bytes(),'image/png',a['name'] if 'download' in query else None);return
                if path=='/api/health':self.send(200,{'ok':True,'application':'ImageChat Local','installation_id':installation_id,'version':VERSION});return
                if path=='/api/comfy-status':
                    try:
                        Comfy(app.config['comfy_url']).request('/system_stats',timeout=3)
                        self.send(200,{'connected':True})
                    except AppError as e:self.send(200,{'connected':False,'error':e.as_dict()})
                    return
                target=(ROOT/'public'/('index.html' if path=='/' else path.lstrip('/'))).resolve()
                if not target.is_relative_to((ROOT/'public').resolve()) or not target.is_file():self.send(404,{'error':{'message':'Not found'}});return
                self.send(200,target.read_bytes(),mimetypes.guess_type(str(target))[0] or 'application/octet-stream')
            except AppError as e:self.send(400,dict(error=e.as_dict()))
            except (ValueError,TypeError,KeyError) as e:self.send(400,dict(error=dict(category='Input',message='入力形式を確認してください。',detail=str(e))))
            except Exception as e:
                app.logger.exception('HTTP request failed')
                self.send(500,dict(error=dict(category='Save' if isinstance(e,OSError) else 'Application',message='処理できませんでした。保存領域とログを確認してください。',detail=str(e))))

    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    from runtime_lock import DataLock
    try:lock=DataLock(data_root or os.environ.get('QIC_DATA_DIR') or ROOT/'data')
    except BaseException:server.server_close();raise
    try:app=Application(data_root)
    except BaseException:
        lock.close();server.server_close();raise
    library=ImageLibrary(app.store)
    def update_shutdown():
        app.stopping.set();threading.Thread(target=server.shutdown,daemon=True).start()
    updater=Updater(app,ROOT,port,update_shutdown)
    app.recover()
    if updater.automatic:updater.action({'action':'check'})
    print(f'ImageChat Local: http://127.0.0.1:{port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:app.stopping.set();server.server_close();lock.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8791);parser.add_argument('--data-dir')
    args=parser.parse_args();serve(args.port,args.data_dir)
