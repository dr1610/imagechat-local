"""Explicit, release-only updates. Never installs dependencies or modifies user data."""
import hashlib
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = 'dr1610/imagechat-local'
VERSION = '0.1.3-beta'
LIMIT = 20 * 1024 * 1024

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def version(value):
    m = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:-beta(?:\.(\d+))?)?', value)
    if not m:
        raise ValueError('未対応のバージョン表記です。')
    return (*map(int, m.group(1, 2, 3)), 0 if '-beta' in value else 1, int(m.group(4) or 0))

def fetch(url):
    if not (url.startswith(f'https://api.github.com/repos/{REPO}/releases') or
            url.startswith(f'https://github.com/{REPO}/releases/download/')):
        raise ValueError('更新元が正しくありません。')
    req = urllib.request.Request(url, headers={'User-Agent': 'ImageChat-Local-Updater', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError('更新ファイルが大きすぎます。')
    return data

def safe_name(name):
    p = Path(name)
    if '\\' in name or ':' in name or p.is_absolute() or any(x in ('..', '.', '') for x in name.split('/')):
        raise ValueError('更新パスが正しくありません。')
    if p.parts[0].lower() in ('data', 'models', '.venv', 'backups', '.git'):
        raise ValueError('保護されたフォルダは更新できません。')
    if not (p.suffix in ('.py', '.js', '.css', '.html', '.md', '.json', '.txt', '.ps1', '.bat') or name in ('LICENSE', 'NOTICE')):
        raise ValueError('未対応の更新ファイルです。')
    return name

def prepare(root, archive, stage, tag):
    """Validate the whole package BEFORE writing any installed file."""
    root, stage = Path(root).resolve(), Path(stage)
    baseline = json.loads((root / 'update-baseline.json').read_text('utf-8'))
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len({n.lower() for n in names}) or sum(i.file_size for i in z.infolist()) > LIMIT:
            raise ValueError('不正な更新パッケージです。')
        manifest = json.loads(z.read('update-manifest.json'))
        if manifest['protocol'] != 1 or manifest['version'] != tag.lstrip('v'):
            raise ValueError('更新形式が対応していません。')
        files = manifest['files']
        if set(names) != set(files) | {'update-manifest.json'}:
            raise ValueError('更新ファイル一覧が一致しません。')
        changes = []
        for name, expected in files.items():
            safe_name(name)
            target = root / name
            if not target.resolve().is_relative_to(root):
                raise ValueError('リンク先への更新はできません。')
            content = z.read(name)
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError('更新ファイルの検証に失敗しました。')
            current = digest(target) if target.exists() else None
            if current == expected:
                continue
            if expected == baseline.get(name):
                # Upstream did not change this file. Keep local customizations.
                continue
            if current != baseline.get(name):
                raise ValueError('ローカル変更を保護するため更新を停止しました: ' + name)
            if name == 'requirements.txt' and current != expected:
                raise ValueError('依存環境の変更が必要なため、別フォルダへの手動更新が必要です。')
            changes.append(name)
        stage.mkdir(parents=True, exist_ok=False)
        for name in changes:
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(name))
    (stage / 'update-baseline.json').write_text(json.dumps(files), encoding='utf-8')
    return changes + ['update-baseline.json']

class Updater:
    def __init__(self, app, root, port, shutdown):
        self.app, self.root, self.port, self.shutdown = app, Path(root), port, shutdown
        self.lock = threading.RLock()
        self.busy = False
        self.frozen = False
        self.release = None
        self.state = {'status': 'idle', 'current': VERSION, 'message': '更新を確認できます。'}
        self.settings = app.store.root / 'update-settings.json'
        try: self.automatic = json.loads(self.settings.read_text('utf-8'))['automatic']
        except (OSError, ValueError, KeyError): self.automatic = True

    def status(self):
        with self.lock:
            result = {**self.state, 'automatic': self.automatic}
        outcome = self.app.store.root / 'update-result.json'
        if outcome.exists():
            try: result['last_result'] = json.loads(outcome.read_text('utf-8'))
            except (OSError, ValueError): pass
        return result

    def active(self):
        with self.app.rewriter.lock:
            rewrite = any(j['status'] in ('Waiting', 'Generating') for j in self.app.rewriter.jobs.values())
        return bool(self.app.store.active()) or rewrite

    def action(self, body):
        action = body.get('action', 'check')
        with self.lock:
            if action == 'settings':
                self.automatic = bool(body.get('automatic'))
                self.settings.write_text(json.dumps({'automatic': self.automatic}), encoding='utf-8')
            elif not self.busy:
                self.busy = True
                threading.Thread(target=self.run, args=(action,), daemon=True).start()
        return self.status()

    def run(self, action):
        try:
            if action == 'check':
                self.state.update(status='checking', message='GitHubの公開リリースを確認しています…')
                releases = json.loads(fetch(f'https://api.github.com/repos/{REPO}/releases?per_page=30'))
                candidates = []
                for r in releases:
                    try:
                        if not r['draft'] and version(r['tag_name']) > version(VERSION): candidates.append(r)
                    except ValueError: continue
                if not candidates:
                    self.release = None
                    self.state.update(status='current', message='新しい公開リリースはありません。')
                    return
                self.release = max(candidates, key=lambda r: version(r['tag_name']))
                r = self.release
                supported = any(a['name'] == 'ImageChat-update.zip' and a.get('digest', '').startswith('sha256:') for a in r['assets'])
                self.state.update(status='available', latest=r['tag_name'], notes=r.get('body') or '', supported=supported,
                                  message='新しいバージョンがあります。' if supported else '新しい版があります。自動更新用パッケージは未公開です。')
            elif action == 'install':
                if not self.release or self.state.get('status') != 'available': raise ValueError('先に更新を確認してください。')
                asset = next((a for a in self.release['assets'] if a['name'] == 'ImageChat-update.zip'), None)
                if not asset or not re.fullmatch(r'sha256:[a-f0-9]{64}', asset.get('digest') or ''):
                    raise ValueError('検証可能な更新パッケージがありません。')
                self.state.update(status='downloading', message='更新ファイルを取得・検証しています…')
                content = fetch(asset['browser_download_url'])
                if hashlib.sha256(content).hexdigest() != asset['digest'][7:]: raise ValueError('ダウンロードのハッシュが一致しません。')
                folder = self.app.store.root / 'updates' / str(time.time_ns())
                folder.mkdir(parents=True)
                archive = folder / 'release.zip'; archive.write_bytes(content)
                changes = prepare(self.root, archive, folder / 'stage', self.release['tag_name'])
                self.state.update(status='waiting', message='生成とEnhancerの完了を待っています。更新後に自動再起動します。')
                while self.active():
                    if self.app.stopping.wait(1): return
                with self.lock:
                    self.frozen = True
                    # Handler uses this same lock around mutations, closing the submit/update race.
                    if self.active():
                        self.frozen = False
                        raise ValueError('新しい生成が始まりました。完了後に更新を再実行してください。')
                self.state.update(status='restarting', message='バックアップして再起動しています…')
                job = dict(root=str(self.root.resolve()), data=str(self.app.store.root.resolve()), port=self.port,
                           changes=changes, version=self.release['tag_name'].lstrip('v'))
                (folder / 'job.json').write_text(json.dumps(job), encoding='utf-8')
                shutil.copy2(self.root / 'update_worker.py', folder / 'worker.py')
                subprocess.Popen([sys.executable, '-B', str(folder / 'worker.py'), str(folder)],
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), close_fds=True)
                self.shutdown()
            else: raise ValueError('未対応の操作です。')
        except Exception as e:
            self.frozen = False
            self.state.update(status='error', message=str(e))
            self.app.logger.exception('Update failed')
        finally:
            with self.lock: self.busy = False
