"""Read existing assets and provenance; favorites never alter generations."""
import json
from comfy import AppError

class ImageLibrary:
    def __init__(self, store):
        self.store=store
        with store.lock,store.db:
            store.db.execute('CREATE TABLE IF NOT EXISTS library_favorites(asset_id TEXT PRIMARY KEY REFERENCES assets(id))')

    def favorite(self, body):
        aid=body.get('asset_id');self.store.asset(aid)
        if not isinstance(body.get('favorite'),bool):raise AppError('Input','お気に入りの指定が不正です。')
        with self.store.lock,self.store.db:
            if body['favorite']:self.store.db.execute('INSERT OR IGNORE INTO library_favorites VALUES (?)',(aid,))
            else:self.store.db.execute('DELETE FROM library_favorites WHERE asset_id=?',(aid,))
        return {'ok':True}

    def list(self):
        s=self.store
        with s.lock:
            assets={r['id']:json.loads(r['payload']) for r in s.db.execute('SELECT * FROM assets')}
            sessions={r['id']:dict(r) for r in s.db.execute('SELECT id,title,draft FROM sessions')}
            gens=[json.loads(r[0]) for r in s.db.execute('SELECT payload FROM generations ORDER BY created DESC,rowid DESC')]
            stars={r[0] for r in s.db.execute('SELECT asset_id FROM library_favorites')}
            organization=s.organization()
        entries={}
        def entry(aid):
            if aid not in assets:return None
            if aid not in entries:
                a=assets[aid]
                entries[aid]=dict(id=aid,name=a.get('name','画像'),width=a.get('width'),height=a.get('height'),favorite=aid in stars,missing=not (s.root/a['file']).is_file(),kind='attached',created=0,contexts=[])
            return entries[aid]
        def context(g,role):
            return dict(generation_id=g['id'],session_id=g['session_id'],title=sessions.get(g['session_id'],{}).get('title','チャット'),prompt=g.get('original_prompt',''),created=g.get('created',0),role=role)
        # First record actual output provenance; input usage is supplementary.
        for g in gens:
            for a in g.get('outputs',[]):
                e=entry(a['id'])
                if e is not None:
                    e['kind']='generated';e['contexts'].append(context(g,'output'));e['created']=max(e['created'],g.get('created',0))
        for g in gens:
            for aid in dict.fromkeys(g.get('references',[])):
                e=entry(aid)
                if e is not None:
                    e['contexts'].append(context(g,'input'));e['created']=max(e['created'],g.get('created',0))
        for sid,session in sessions.items():
            for aid in dict.fromkeys(json.loads(session['draft']).get('references',[])):
                e=entry(aid)
                if e is not None and not any(c['session_id']==sid for c in e['contexts']):
                    e['contexts'].append(dict(session_id=sid,title=session['title'],generation_id=None,prompt='',role='draft',created=0))
        for aid in assets:entry(aid)
        return dict(items=sorted(entries.values(),key=lambda e:(e['created'],e['id']),reverse=True),sessions=[dict(id=v['id'],title=v['title']) for v in sessions.values()],organization=organization)
