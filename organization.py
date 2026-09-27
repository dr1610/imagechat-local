"""Additive organization metadata; never modifies generation or image records."""
import uuid
from comfy import AppError


class Organization:
    def init_organization(self):
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS collections(
          id TEXT PRIMARY KEY, name TEXT NOT NULL,
          parent_id TEXT REFERENCES collections(id), position INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS placements(
          session_id TEXT PRIMARY KEY REFERENCES sessions(id),
          collection_id TEXT REFERENCES collections(id), position INTEGER NOT NULL);
        ''')

    def organization(self):
        with self.lock:
            return dict(collections=[dict(r) for r in self.db.execute('SELECT * FROM collections ORDER BY position,id')],
                        placements=[dict(r) for r in self.db.execute('SELECT * FROM placements ORDER BY position,session_id')])

    def organize(self, data):
        with self.lock, self.db:
            action = data.get('action')
            cid = data.get('id')
            def collection(value):
                row = self.db.execute('SELECT * FROM collections WHERE id=?', (value,)).fetchone()
                if not row: raise AppError('Input', 'プロジェクト／フォルダが見つかりません。')
                return row
            def name():
                value = str(data.get('name', '')).strip()
                if not value or len(value)>100: raise AppError('Input', '名前は1〜100文字で入力してください。')
                return value
            if action == 'create':
                parent = data.get('parent_id') or None
                if parent and collection(parent)['parent_id'] is not None:
                    raise AppError('Input', 'フォルダはプロジェクト内の1階層までです。')
                cid = str(uuid.uuid4())
                pos = self.db.execute('SELECT COALESCE(MAX(position),-1)+1 FROM collections WHERE parent_id IS ?', (parent,)).fetchone()[0]
                self.db.execute('INSERT INTO collections VALUES (?,?,?,?)', (cid,name(),parent,pos))
            elif action == 'rename':
                collection(cid)
                self.db.execute('UPDATE collections SET name=? WHERE id=?', (name(),cid))
            elif action == 'delete':
                collection(cid)
                ids = [cid]+[r[0] for r in self.db.execute('SELECT id FROM collections WHERE parent_id=?',(cid,))]
                for value in ids:
                    self.db.execute('UPDATE placements SET collection_id=NULL WHERE collection_id=?',(value,))
                self.db.execute('DELETE FROM collections WHERE parent_id=?',(cid,))
                self.db.execute('DELETE FROM collections WHERE id=?',(cid,))
            elif action == 'move':
                sid=data.get('session_id'); self.session(sid)
                target=data.get('collection_id') or None
                if target: collection(target)
                old=self.db.execute('SELECT collection_id FROM placements WHERE session_id=?',(sid,)).fetchone()
                if (old[0] if old else None)==target: return dict(ok=True,id=cid)
                pos=self.db.execute('SELECT COALESCE(MAX(position),-1)+1 FROM placements WHERE collection_id IS ?',(target,)).fetchone()[0]
                self.db.execute('INSERT INTO placements VALUES (?,?,?) ON CONFLICT(session_id) DO UPDATE SET collection_id=excluded.collection_id,position=excluded.position',(sid,target,pos))
            elif action == 'reorder':
                direction=data.get('direction')
                if direction not in (-1,1): raise AppError('Input','並べ替え方向が不正です。')
                if data.get('kind')=='session':
                    self.session(cid)
                    row=self.db.execute('SELECT collection_id FROM placements WHERE session_id=?',(cid,)).fetchone()
                    parent=row[0] if row else None
                    ids=[r[0] for r in self.db.execute('SELECT s.id FROM sessions s LEFT JOIN placements p ON p.session_id=s.id WHERE p.collection_id IS ? ORDER BY COALESCE(p.position,2147483647),s.created,s.id',(parent,))]
                    table='placements'
                else:
                    parent=collection(cid)['parent_id']
                    ids=[r[0] for r in self.db.execute('SELECT id FROM collections WHERE parent_id IS ? ORDER BY position,id',(parent,))]
                    table='collections'
                index=ids.index(cid); other=index+direction
                if 0<=other<len(ids): ids[index],ids[other]=ids[other],ids[index]
                for pos,value in enumerate(ids):
                    if table=='placements':
                        self.db.execute('INSERT INTO placements VALUES (?,?,?) ON CONFLICT(session_id) DO UPDATE SET position=excluded.position',(value,parent,pos))
                    else: self.db.execute('UPDATE collections SET position=? WHERE id=?',(pos,value))
            else: raise AppError('Input','整理操作が不正です。')
            return dict(ok=True,id=cid)
