"""Runs outside the server. Backup, apply, health-check, rollback. No pip/git."""
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

def transact(root, stage, backup, changes, start, healthy):
    backup.mkdir(parents=True, exist_ok=False)
    existed = []
    for name in changes:
        target = root / name
        if target.exists():
            dest = backup / name; dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, dest); existed.append(name)
    (backup / 'rollback.json').write_text(json.dumps({'changes': changes, 'existed': existed}), encoding='utf-8')
    child = None
    try:
        for name in changes:
            dest = root / name; dest.parent.mkdir(parents=True, exist_ok=True)
            temporary = dest.with_name(dest.name + '.update-tmp')
            shutil.copy2(stage / name, temporary); os.replace(temporary, dest)
        child = start()
        if not healthy(child): raise RuntimeError('更新版の起動確認に失敗しました。')
        return True
    except Exception:
        if child is not None and child.poll() is None:
            child.terminate(); child.wait(timeout=15)
        for name in changes:
            if name in existed: shutil.copy2(backup / name, root / name)
            else: (root / name).unlink(missing_ok=True)
        raise

def main(folder):
    folder = Path(folder); job = json.loads((folder / 'job.json').read_text('utf-8'))
    root, data, port = Path(job['root']), Path(job['data']), job['port']
    result = data / 'update-result.json'
    def record(status, message):
        result.write_text(json.dumps(dict(status=status, message=message, backup=str(folder / 'backup')), ensure_ascii=False), encoding='utf-8')
    def start():
        log = open(folder / 'startup.log', 'ab')
        try:
            return subprocess.Popen([sys.executable, '-B', str(root / 'server.py'), '--port', str(port), '--data-dir', str(data)],
                                    cwd=root, stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        finally: log.close()
    def healthy(child):
        for _ in range(60):
            if child.poll() is not None: return False
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=1) as r: h = json.load(r)
                if h.get('version') == job['version'] and h.get('installation_id') == hashlib.sha256(str(root.resolve()).lower().encode()).hexdigest(): return True
            except Exception: pass
            time.sleep(1)
        return False
    try:
        # Acquire the application's data lock after shutdown, then release before new server starts.
        sys.path.insert(0, str(root))
        from runtime_lock import DataLock
        lock = None
        for _ in range(60):
            try: lock = DataLock(data); break
            except Exception: time.sleep(1)
        if lock is None: raise RuntimeError('アプリが終了しなかったため更新しませんでした。')
        try:
            with socket.socket() as probe:
                if probe.connect_ex(('127.0.0.1', port)) == 0: raise RuntimeError('ポートが使用中です。更新しませんでした。')
            # Snapshot metadata for manual recovery; protocol 1 packages must not migrate schemas.
            with sqlite3.connect(data / 'sessions.sqlite3') as source, sqlite3.connect(folder / 'sessions.sqlite3') as dest: source.backup(dest)
        finally: lock.close()
        try:
            transact(root, folder / 'stage', folder / 'backup', job['changes'], start, healthy)
            record('completed', '更新と再起動が完了しました。')
        except Exception as e:
            record('rolled_back', str(e) + ' 元のアプリを復元しました。')
            start()
    except Exception as e: record('failed', str(e))

if __name__ == '__main__': main(sys.argv[1])
