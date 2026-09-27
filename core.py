"""Persistent sessions, immutable generation inputs, canvas rendering and workflow routing."""
import copy
import hashlib
import io
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
import urllib.parse
import uuid

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, UnidentifiedImageError
from comfy import AppError, Comfy, local_url
from enhancer import enhance
from style_prompt import apply_style
from reference_input import validate_reference_mentions
from organization import Organization
from community import validate as validate_community, profile_for, augment
from model_routing import resolve as resolve_model
from edit_policy import plan as edit_plan

ROOT = Path(__file__).resolve().parent
DEFAULTS = dict(comfy_url='http://127.0.0.1:8188', theme='dark', model='', text_encoder='', vae='', control_model='')
PARAMS = dict(aspect='1:1', resolution=768, seed_mode='random', seed=1, steps=25, cfg=1.0,
              sampler='euler', scheduler='simple', denoise=1.0, mask_blur=4, mask_grow=0,
              control_strength=1.0, workflow='auto', enhancer='auto', loras=[], art_style='none', quality_profile='standard', outpaint_mode='standard', model_preset='auto', sampling_policy='recommended', negative_prompt='')
TERMINAL = ('Completed', 'Failed', 'Cancelled')
POSE_EDGES = [(1,2),(1,5),(2,3),(3,4),(5,6),(6,7),(1,8),(8,9),(9,10),(1,11),(11,12),(12,13),(1,0),(0,14),(14,16),(0,15),(15,17)]
POSE_COLORS = ['#ff0000','#ff5500','#ffaa00','#ffff00','#aaff00','#55ff00','#00ff00','#00ff55','#00ffaa','#00ffff','#00aaff','#0055ff','#0000ff','#5500ff','#aa00ff','#ff00ff','#ff00aa','#ff0055']


def uid():
    return str(uuid.uuid4())


def now():
    return time.time()


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + secrets.token_hex(4) + '.tmp')
    try:
        with temp.open('wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def write_json(path, data):
    atomic(path, json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8'))


def dimensions(aspect, resolution, original=None):
    if aspect == 'original' and original:
        ratio = original[0] / original[1]
        return (max(32,round(int(resolution)*math.sqrt(ratio)/32)*32),max(32,round(int(resolution)/math.sqrt(ratio)/32)*32))
    try:
        a, b = [int(x) for x in aspect.split(':')]
        if a <= 0 or b <= 0 or not 0.2 <= a/b <= 5:
            raise ValueError()
        # Exact selected ratio, both dimensions multiples of 32.
        divisor = math.gcd(a, b)
        a, b = a // divisor, b // divisor
        scale = max(1, round(int(resolution) / math.sqrt(a * b) / 32))
        return a * 32 * scale, b * 32 * scale
    except (ValueError, TypeError):
        raise AppError('Input', '画像の比率が正しくありません。')


def expansion(base, ratio, alignment='center'):
    a, b = map(int, ratio.split(':'))
    d = math.gcd(a, b)
    a, b = a//d, b//d
    scale = math.ceil(max(base[0]/a, base[1]/b)/32)
    w, h = a*scale*32, b*scale*32
    x, y = (w-base[0])//2, (h-base[1])//2
    if alignment == 'left': x = 0
    if alignment == 'right': x = w-base[0]
    if alignment == 'top': y = 0
    if alignment == 'bottom': y = h-base[1]
    return dict(width=w, height=h, x=x, y=y)


def parse_expand(prompt, base):
    match = re.search(r'(16\s*[:：]\s*9|9\s*[:：]\s*16|4\s*[:：]\s*3|3\s*[:：]\s*4|1\s*[:：]\s*1)', prompt)
    trigger = re.search(r'広げ|拡張|続きを|余白|横長|縦長', prompt)
    if not (match or trigger): return None
    align = 'center'
    if re.search(r'下(方向)?(だけ|に|へ)', prompt): align = 'top'
    elif re.search(r'上(方向)?(だけ|に|へ)', prompt): align = 'bottom'
    elif re.search(r'右(方向)?(だけ|に|へ)', prompt): align = 'left'
    elif re.search(r'左(方向)?(だけ|に|へ)', prompt): align = 'right'
    if match:
        return expansion(base, re.sub(r'\s', '', match[0]).replace('：', ':'), align)
    w, h = base
    amount = max(32, round(min(w,h)*0.25/32)*32)
    dx, dy = (amount*2, 0) if re.search(r'左右|横|右|左', prompt) else (0, amount*2)
    x, y = dx//2, dy//2
    if align == 'left': x=0
    if align == 'right': x=dx
    if align == 'top': y=0
    if align == 'bottom': y=dy
    return dict(width=w+dx, height=h+dy, x=x, y=y)


class Store(Organization):
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root/'sessions.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, title TEXT NOT NULL, created REAL, updated REAL, draft TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS generations(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), created REAL, updated REAL, payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS generation_session ON generations(session_id,created);
        CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        PRAGMA user_version=1;
        ''')
        self.init_organization()
        self.db.commit()

    def sessions(self):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT id,title,created,updated FROM sessions ORDER BY updated DESC')]

    def create_session(self, title='新しいチャット'):
        s = dict(id=uid(), title=title[:100] or '新しいチャット', created=now(), updated=now(), draft={})
        with self.lock, self.db:
            self.db.execute('INSERT INTO sessions VALUES (?,?,?,?,?)', (s['id'],s['title'],s['created'],s['updated'],'{}'))
        return s

    def session(self, sid):
        with self.lock:
            r = self.db.execute('SELECT * FROM sessions WHERE id=?', (sid,)).fetchone()
            if not r: raise AppError('Session', 'チャットが見つかりません。')
            s = dict(r)
            s['draft'] = json.loads(s['draft'])
            s['generations'] = [json.loads(r[0]) for r in self.db.execute('SELECT payload FROM generations WHERE session_id=? ORDER BY created,rowid', (sid,))]
            return s

    def update_session(self, sid, data):
        self.session(sid)
        with self.lock, self.db:
            if 'title' in data:
                self.db.execute('UPDATE sessions SET title=?,updated=? WHERE id=?', (str(data['title'])[:100] or '新しいチャット',now(),sid))
            if 'draft' in data:
                draft = json.dumps(data['draft'],ensure_ascii=False)
                if len(draft) > 8_000_000: raise AppError('Input','編集下書きが大きすぎます。')
                self.db.execute('UPDATE sessions SET draft=?,updated=? WHERE id=?',(draft,now(),sid))

    def generation(self, gid):
        with self.lock:
            r=self.db.execute('SELECT payload FROM generations WHERE id=?',(gid,)).fetchone()
            if not r: raise AppError('Generation','生成履歴が見つかりません。')
            return json.loads(r[0])

    def save_generation(self, g):
        g['updated']=now()
        with self.lock, self.db:
            self.db.execute('INSERT INTO generations VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated=excluded.updated,payload=excluded.payload',
                            (g['id'],g['session_id'],g['created'],g['updated'],json.dumps(g,ensure_ascii=False)))
            self.db.execute('UPDATE sessions SET updated=? WHERE id=?',(g['updated'],g['session_id']))

    def update_generation(self, gid, **updates):
        with self.lock:
            g=self.generation(gid)
            g.update(updates)
            self.save_generation(g)
            return g

    def active(self):
        with self.lock:
            return [g for r in self.db.execute('SELECT payload FROM generations') if (g:=json.loads(r[0]))['status'] not in TERMINAL]

    def asset(self, aid):
        with self.lock:
            r=self.db.execute('SELECT payload FROM assets WHERE id=?',(aid,)).fetchone()
            if not r: raise AppError('ImageMissing','画像が見つかりません。再添付してください。')
            return json.loads(r[0])

    def asset_path(self, aid):
        p=self.root/self.asset(aid)['file']
        if not p.is_file(): raise AppError('ImageMissing','保存画像が欠損しています。再添付してください。')
        return p

    def add_image(self, data, name='image.png', asset_id=None):
        if len(data)>40*1024*1024: raise AppError('Image','画像は40MB以下にしてください。')
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ('PNG','JPEG','WEBP','BMP'): raise AppError('Image','PNG/JPEG/WebP/BMPに対応しています。')
                if image.width*image.height>40_000_000: raise AppError('Image','画像は4000万画素以下にしてください。')
                image=ImageOps.exif_transpose(image)
                image=image.convert('RGBA' if 'A' in image.getbands() or 'transparency' in image.info else 'RGB')
                out=io.BytesIO(); image.save(out,format='PNG')
                aid=asset_id or uid()
                a=dict(id=aid,name=Path(name).name,file=f'assets/{aid}.png',width=image.width,height=image.height,alpha='A' in image.getbands(),sha256=hashlib.sha256(out.getvalue()).hexdigest())
        except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError) as e:
            raise AppError('Image','画像を読み込めません。破損または非対応の画像です。',str(e))
        atomic(self.root/a['file'],out.getvalue())
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO assets VALUES (?,?)',(aid,json.dumps(a,ensure_ascii=False)))
        return a


def render_editor(base, editor):
    """Render vectors at image coordinates, never viewport coordinates."""
    w,h=int(editor.get('width',base.width)),int(editor.get('height',base.height))
    if min(w,h)<32 or max(w,h)>4096 or w*h>8_388_608:
        raise AppError('Canvas','Canvasは32〜4096px、合計約800万画素以下にしてください。')
    x,y=int(editor.get('x',0)),int(editor.get('y',0))
    if x<0 or y<0 or x+base.width>w or y+base.height>h:
        raise AppError('Canvas','元画像を切り取らずに配置できるCanvasサイズにしてください。')
    canvas=Image.new('RGBA',(w,h),(255,255,255,255)); canvas.paste(base.convert('RGBA'),(x,y))
    sketch=Image.new('RGBA',(w,h)); mask=Image.new('L',(w,h))
    for stroke in editor.get('strokes',[]):
        points=[(float(p[0]),float(p[1])) for p in stroke.get('points',[])]
        if not points: continue
        if len(points)>100000: raise AppError('Canvas','ストロークが長すぎます。')
        size=max(1,min(256,int(stroke.get('size',8))))
        target=mask if stroke.get('layer')=='mask' else sketch
        color=(0 if target is mask else (0,0,0,0)) if stroke.get('erase') else (255 if target is mask else stroke.get('color','#18caca'))
        d=ImageDraw.Draw(target); d.line(points,fill=color,width=size,joint='curve')
        r=size/2
        for px,py in (points[0],points[-1]): d.ellipse((px-r,py-r,px+r,py+r),fill=color)
    pose=Image.new('RGB',(w,h),'black'); draw=ImageDraw.Draw(pose)
    for person in editor.get('poses',[]):
        pts=person.get('points',[])
        if len(pts)!=18: raise AppError('Pose','ポーズは18関節の形式で保存してください。')
        hidden=set(person.get('hidden',[]))
        if any(not isinstance(j,int) or j<0 or j>=18 for j in hidden): raise AppError('Pose','非表示関節の番号が不正です。')
        for i,(a,b) in enumerate(POSE_EDGES):
            if a in hidden or b in hidden: continue
            draw.line([tuple(pts[a]),tuple(pts[b])],fill=POSE_COLORS[i],width=max(3,round(min(w,h)/160)))
        for i,(px,py) in enumerate(pts):
            if i in hidden: continue
            r=max(3,round(min(w,h)/140));draw.ellipse((px-r,py-r,px+r,py+r),fill=POSE_COLORS[i])
    return canvas, sketch, mask, pose


class Workflows:
    def __init__(self, root=ROOT/'workflows'): self.root=Path(root)

    def load(self, name, seen=None):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+',name): raise AppError('Workflow','Workflow名が正しくありません。')
        seen=set(seen or ())
        if name in seen: raise AppError('Workflow','Workflowの継承が循環しています。')
        seen.add(name)
        try: raw=json.loads((self.root/(name+'.json')).read_text(encoding='utf-8'))
        except (OSError,ValueError) as e: raise AppError('Workflow','Workflowファイルを読み込めません。',str(e))
        result=self.load(raw['extends'],seen) if raw.get('extends') else {}
        graph=copy.deepcopy(result.get('graph',{})); graph.update(raw.get('graph',{}))
        result.update(raw); result['graph']=graph
        for node,inputs in raw.get('overrides',{}).items(): graph[node]['inputs'].update(inputs)
        return result

    def list(self):
        out=[]
        for p in sorted(self.root.glob('*.json')):
            try:
                w=self.load(p.stem)
                out.append({k:w.get(k) for k in ('id','label','version','intents','capabilities','max_references')})
            except AppError as e: out.append(dict(id=p.stem,label=p.stem,error=e.as_dict()))
        return out

    def select(self,intent,name='auto'):
        if name!='auto': return self.load(name)
        for w in self.list():
            if intent in (w.get('intents') or []): return self.load(w['id'])
        raise AppError('Unsupported','この操作に対応するWorkflowがありません。')

    def build(self,w,params,uploads,features):
        needed=set(features)-{'control'}
        if uploads: needed.add('references')
        if not needed.issubset(set(w.get('capabilities',[]))):
            raise AppError('Unsupported','選択したWorkflowは、この画像・Sketch・Mask・Poseの組み合わせに対応していません。')
        if len(uploads)>w.get('max_references',0): raise AppError('Unsupported','このWorkflowの参照画像枚数の上限を超えています。')
        graph=copy.deepcopy(w['graph'])
        for f in features:
            definition=w.get('features',{}).get(f)
            if not definition: continue
            graph.update(copy.deepcopy(definition.get('graph',{})))
            for node,inputs in definition.get('overrides',{}).items(): graph[node]['inputs'].update(inputs)
        if uploads:
            binding=w['reference_binding']
            for i,upload in enumerate(uploads,1):
                node='ref_'+str(i)
                graph[node]={'class_type':binding['loader_type'],'inputs':{binding['loader_input']:upload}}
                graph[binding['node']]['inputs'][binding['prefix']+str(i)]=[node,0]
        def replace(v):
            if isinstance(v,str) and v.startswith('$'):
                if v[1:] not in params: raise AppError('Workflow',f'Workflowの入力 {v} が未定義です。')
                return params[v[1:]]
            if isinstance(v,dict): return {k:replace(x) for k,x in v.items()}
            if isinstance(v,list): return [replace(x) for x in v]
            return v
        return replace(graph)


class Application:
    def __init__(self, data_root=None):
        self.store=Store(data_root or os.environ.get('QIC_DATA_DIR') or ROOT/'data')
        self.workflows=Workflows()
        self.lock=threading.RLock()
        self.stopping=threading.Event()
        self.config_path=self.store.root/'settings.json'
        self.config={**DEFAULTS,**(json.loads(self.config_path.read_text(encoding='utf-8')) if self.config_path.exists() else {})}
        self.client_id=self.config.setdefault('client_id',uid())
        write_json(self.config_path,self.config)
        self.logger=logging.getLogger('qic.'+self.client_id); self.logger.setLevel(logging.INFO)
        h=RotatingFileHandler(self.store.root/'application.log',maxBytes=2_000_000,backupCount=3,encoding='utf-8')
        h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'));self.logger.addHandler(h)
        self.threads={}
        from rewriter import Rewriter
        self.rewriter=Rewriter(self)

    def save_config(self,data):
        with self.lock:
            if 'comfy_url' in data: local_url(data['comfy_url'])
            for k in DEFAULTS:
                if k in data: self.config[k]=data[k]
            write_json(self.config_path,self.config)
        return self.config

    def connection(self,url=None):
        c=Comfy(url or self.config['comfy_url']); stats=c.request('/system_stats'); info=c.request('/object_info',timeout=30)
        fields={'model':('UNETLoader','unet_name',r'qwen_image_2[._]1'), 'text_encoder':('CLIPLoader','clip_name',r'qwen3vl'),
                'vae':('VAELoader','vae_name',r'qwen_image_2[._]1'), 'control_model':('ModelPatchLoader','name',r'Qwen-Image-2[._]1')}
        choices={}; detected={}
        for key,(node,field,pattern) in fields.items():
            choices[key]=info.get(node,{}).get('input',{}).get('required',{}).get(field,[[]])[0]
            matches=[n for n in choices[key] if re.search(pattern,n,re.I)]
            detected[key]=next((n for n in matches if 'int8' in n.lower()),matches[0] if matches else '')
        samplers=info.get('KSampler',{}).get('input',{}).get('required',{})
        required=['TextEncodeQwenImage21','UNETLoader','CLIPLoader','VAELoader','KSampler','VAEDecode','SaveImage']
        return dict(connected=True,system=stats,models=choices,detected=detected,missing_nodes=[n for n in required if n not in info],
                    control_available='QwenImage21FunControlNetApply' in info and bool(detected['control_model']),
                    samplers=samplers.get('sampler_name',[[]])[0],schedulers=samplers.get('scheduler',[[]])[0])

    def generate(self,body):
        with self.lock:
            return self._generate(body)

    def _generate(self,body):
        sid=body.get('session_id'); self.store.session(sid)
        if body.get('request_id'):
            with self.store.lock:
                for r in self.store.db.execute('SELECT payload FROM generations WHERE session_id=?',(sid,)):
                    g=json.loads(r[0])
                    if g.get('request_id')==body['request_id']: return g
        original=str(body.get('prompt',''))
        if not original.strip(): raise AppError('Input','日本語などで作りたい画像を入力してください。')
        if len(original)>16000: raise AppError('Input','指示は16000文字以下にしてください。')
        refs=list(body.get('references') or [])
        if len(refs)>10: raise AppError('Input','参照画像は10枚までです。')
        for aid in refs: self.store.asset_path(aid)
        validate_reference_mentions(original,refs)
        params={**PARAMS,**body.get('params',{})}
        validate_community(params)
        policy=edit_plan(original,refs,params,body.get('editor'))
        if body.get('regenerated_from_generation_id'):
            source=self.store.generation(body['regenerated_from_generation_id'])
            if source['session_id']!=sid:raise AppError('Session','別チャットの再生成元は指定できません。')
            if source.get('edit_policy') and params['enhancer']==source['params']['enhancer']:
                policy=copy.deepcopy(source['edit_policy'])
        rewrite_metadata=None
        if policy['use_enhancer']:
            from enhancer import PromptResult
            translated,rewrite_metadata=self.rewriter.approved(body)
            prompt_result=PromptResult(original,translated)
            effective_prompt=translated
            style_instruction={'illustration':'Render as a drawn illustration, preserving the reference illustration style.','photoreal':'Render in photorealistic photographic style.','none':''}.get(params['art_style'],'')
            if refs:style_instruction=''
            if style_instruction:effective_prompt+='\n\n'+style_instruction
        else:
            prompt_result=enhance(original,'off')
            effective_prompt,style_instruction=apply_style(prompt_result.effective,params['art_style'],editing=bool(refs))
        validate_reference_mentions(effective_prompt,refs)
        if params.get('loras'): raise AppError('Unsupported','LoRA管理は今後の拡張です。未使用にしてください。')
        params['seed']=int(params['seed']) if params['seed_mode']=='fixed' else secrets.randbelow(2**53)
        limits={'seed':(0,2**53-1),'steps':(1,100),'cfg':(0,30),'denoise':(0.01,1),'mask_blur':(0,64),'mask_grow':(0,64),'control_strength':(0,2)}
        for k,(low,high) in limits.items():
            try: val=float(params[k])
            except (ValueError,TypeError): raise AppError('Input',f'{k}の値が正しくありません。')
            if not math.isfinite(val) or not low<=val<=high: raise AppError('Input',f'{k}は{low}〜{high}で指定してください。')
        params['steps']=int(params['steps'])
        params['resolution']=int(params['resolution'])
        if params['resolution'] not in (384,512,768,1024,1536,2048): raise AppError('Input','解像度の選択が正しくありません。')
        parent=body.get('parent_generation_id') or None
        if parent:
            pg=self.store.generation(parent)
            if pg['session_id']!=sid: raise AppError('Session','別チャットの画像は参照画像として添付してください。')
        refs=list(body.get('references') or [])
        if len(refs)>10: raise AppError('Input','参照画像は10枚までです。')
        for aid in refs: self.store.asset_path(aid)
        editor=copy.deepcopy(body.get('editor'))
        if editor and not refs: raise AppError('Canvas','編集する元画像を指定してください。')
        natural_expand=None
        if refs:
            base=self.store.asset(refs[0]); natural_expand=parse_expand(original,(base['width'],base['height']))
            if natural_expand and (not editor or (editor.get('width'),editor.get('height'))==(base['width'],base['height'])):
                previous=editor or {'strokes':[],'poses':[]}
                dx=natural_expand['x']-previous.get('x',0);dy=natural_expand['y']-previous.get('y',0)
                for stroke in previous.get('strokes',[]):stroke['points']=[[x+dx,y+dy] for x,y in stroke['points']]
                for pose in previous.get('poses',[]):pose['points']=[[x+dx,y+dy] for x,y in pose['points']]
                editor={**previous,**natural_expand}
        prior=None
        if body.get('regenerated_from_generation_id'):
            prior=self.store.generation(body['regenerated_from_generation_id'])
            if prior['session_id']!=sid:raise AppError('Session','別チャットの再生成元は指定できません。')
        model_selection=resolve_model(params,editor,self.config,prior=prior,editing=bool(refs),prompt=original)
        for k,(low,high) in limits.items():
            try: val=float(params[k])
            except (ValueError,TypeError): raise AppError('Input',f'{k}の値が正しくありません。')
            if not math.isfinite(val) or not low<=val<=high: raise AppError('Input',f'{k}は{low}〜{high}で指定してください。')
        params['steps']=int(params['steps'])
        negative_prompt=params['negative_prompt'] if params['sampling_policy']=='manual' else model_selection.get('negative','')
        if not isinstance(negative_prompt,str) or len(negative_prompt)>16000:raise AppError('Input','Negative Promptは16000文字以内で指定してください。')
        params['negative_prompt']=negative_prompt
        if not refs:effective_prompt=model_selection.get('prefix','')+effective_prompt
        model_config={k:self.config[k] for k in ('model','text_encoder','vae','control_model')}
        if model_selection['file']:model_config['model']=model_selection['file']
        gid=uid()
        g=dict(id=gid,request_id=body.get('request_id'),session_id=sid,created=now(),status='Waiting',stage='生成準備',progress=None,
               original_prompt=prompt_result.original,enhanced_prompt=prompt_result.enhanced,prompt=effective_prompt,style_instruction=style_instruction,params=params,references=refs,editor=editor,
               parent_generation_id=parent,regenerated_from_generation_id=body.get('regenerated_from_generation_id'),
               rewrite=rewrite_metadata,edit_policy=policy,outputs=[],error=None,cancel_requested=False,comfy_url=self.config['comfy_url'],model_config=model_config,model_selection=model_selection,
               natural_expand=natural_expand,prompt_id=None)
        self.store.save_generation(g)
        self.start(gid)
        return g

    def regenerate(self,gid,override=None):
        g=self.store.generation(gid)
        params={**g['params'],**(override or {})}
        if 'model_preset' not in g['params'] and 'model_preset' not in (override or {}):
            params.update(model_preset='settings',sampling_policy='manual')
        if set(override or {})&{'steps','cfg','sampler','scheduler','denoise','negative_prompt'} and 'sampling_policy' not in (override or {}):params['sampling_policy']='manual'
        return self.generate(dict(session_id=g['session_id'],prompt=g['original_prompt'],references=g['references'],editor=g.get('editor'),
                                  parent_generation_id=g['parent_generation_id'],regenerated_from_generation_id=gid,params=params,rewrite_id=(g.get('rewrite') or {}).get('id'),enhanced_prompt=g.get('enhanced_prompt')))

    def start(self,gid,recover=False):
        with self.lock:
            if gid in self.threads and self.threads[gid].is_alive(): return
            t=threading.Thread(target=self.run,args=(gid,recover),daemon=True);self.threads[gid]=t;t.start()

    def recover(self):
        for g in self.store.active(): self.start(g['id'],bool(g.get('prompt_id')))

    def cancel(self,gid):
        with self.lock:
            g=self.store.generation(gid)
            if g['status'] in TERMINAL: return g
            self.store.update_generation(gid,cancel_requested=True,stage='停止要求中')
            if g.get('prompt_id'):
                # Atomic job-specific cancel endpoint; never send a global interrupt.
                Comfy(g['comfy_url']).request('/api/jobs/'+g['prompt_id']+'/cancel',{})
            return self.store.generation(gid)

    def retry_output(self,gid):
        g=self.store.generation(gid)
        if g['status']=='Completed':return g
        if g['status']=='Cancelled':raise AppError('Generation','停止した生成は「再生成」で新しいGenerationとして実行してください。')
        if not g.get('prompt_id'): raise AppError('Generation','再取得できる生成IDがありません。再生成してください。')
        self.store.update_generation(gid,status='Waiting',error=None,cancel_requested=False,stage='結果を再取得')
        self.start(gid,True)
        return self.store.generation(gid)

    def prepare(self,g,c):
        folder=self.store.root/'generations'/g['id'];folder.mkdir(parents=True,exist_ok=True)
        params={**g['params'],**g['model_config'], 'prompt':g['prompt'],'negative_prompt':g['params'].get('negative_prompt',''),'output_prefix':'QwenImageChat/'+g['id']}
        info=c.request('/object_info',timeout=30)
        fields={'model':('UNETLoader','unet_name',r'qwen_image_2[._]1'), 'text_encoder':('CLIPLoader','clip_name',r'qwen3vl'), 'vae':('VAELoader','vae_name',r'qwen_image_2[._]1'), 'control_model':('ModelPatchLoader','name',r'Qwen-Image-2[._]1')}
        for key,(node,field,pattern) in fields.items():
            choices=info.get(node,{}).get('input',{}).get('required',{}).get(field,[[]])[0]
            if not params.get(key):
                matches=[n for n in choices if re.search(pattern,n,re.I)]
                params[key]=next((n for n in matches if 'int8' in n.lower()),matches[0] if matches else '')
            if key!='control_model' and params[key] not in choices: raise AppError('Model',f'{key}のモデルが見つかりません。接続設定で選び直してください。')
        features=[]; files={}; images=[]
        if g['references']:
            for aid in g['references']:
                with Image.open(self.store.asset_path(aid)) as im: images.append(im.copy())
            base=images[0]
            if g.get('editor'):
                editor=g['editor'];canvas,sketch,mask,pose=render_editor(base,editor)
                images[0]=Image.alpha_composite(canvas,sketch)
                if sketch.getbbox(): features.append('sketch')
                if canvas.size!=base.size: features.append('expand')
                if mask.getbbox():
                    features.extend(['control','mask'])
                    grow=int(params['mask_grow']);blur=float(params['mask_blur'])
                    rawmask=mask.copy()
                    if canvas.size!=base.size:
                        margin=Image.new('L',canvas.size,255)
                        ImageDraw.Draw(margin).rectangle((int(editor.get('x',0)),int(editor.get('y',0)),int(editor.get('x',0))+base.width-1,int(editor.get('y',0))+base.height-1),fill=0)
                        mask=ImageChops.lighter(mask,margin)
                    if grow: mask=mask.filter(ImageFilter.MaxFilter(grow*2+1))
                    if blur: mask=mask.filter(ImageFilter.GaussianBlur(blur))
                    for name,im in [('mask_raw',rawmask),('mask',mask),('base',canvas)]:
                        path=folder/(name+'.png'); im.save(path);files[name]=str(path.relative_to(self.store.root))
                    params['base_upload']=c.upload(folder/'base.png');params['mask_upload']=c.upload(folder/'mask.png')
                if pose.getbbox():
                    if 'control' not in features:features.append('control')
                    features.append('pose');pose.save(folder/'pose.png');files['pose']=str((folder/'pose.png').relative_to(self.store.root))
                    params['pose_upload']=c.upload(folder/'pose.png')
                sketch.save(folder/'sketch.png');files['sketch']=str((folder/'sketch.png').relative_to(self.store.root))
                target=tuple(max(32,math.ceil(n/32)*32) for n in images[0].size)
            else:
                target=dimensions(params['aspect'],params['resolution'],base.size) if params['aspect']=='original' else dimensions(params['aspect'],params['resolution'])
            # Letterbox, never stretch. Encoder's resolution=0 preserves the prepared size.
            if profile_for(params,features)=='outpaint':
                # Keep the source at its exact pixel size; only new area is gray.
                editor=g['editor'];x,y=int(editor.get('x',0)),int(editor.get('y',0))
                canvas=Image.new('RGBA',target,(128,128,128,255));canvas.paste(base.convert('RGBA'),(x,y))
                margin=Image.new('L',target,255)
                ImageDraw.Draw(margin).rectangle((x,y,x+base.width-1,y+base.height-1),fill=0)
                for name,im in [('preserve_base',canvas),('preserve_mask',margin)]:
                    path=folder/(name+'.png');im.save(path);files[name]=str(path.relative_to(self.store.root))
                images[0]=canvas
                profile=json.loads((ROOT/'profiles'/'outpaint.json').read_text(encoding='utf-8'))
                params['prompt']=profile['prompt_prefix']+'\n\n'+params['prompt']
            elif images[0].size!=target:
                fit=ImageOps.contain(images[0],target,Image.Resampling.LANCZOS)
                padded=Image.new('RGBA',target,'white');padded.paste(fit.convert('RGBA'),((target[0]-fit.width)//2,(target[1]-fit.height)//2));images[0]=padded
            params['width'],params['height']=images[0].size
        else:params['width'],params['height']=dimensions(params['aspect'],params['resolution'])
        if max(params['width'],params['height'])>4096 or params['width']*params['height']>8_388_608:raise AppError('Canvas','生成サイズが大きすぎます。Canvasを調整してください。')
        if 'mask' in features: intent='inpaint'
        elif 'pose' in features:intent='pose'
        elif 'expand' in features:intent='outpaint'
        elif len(images)>1:intent='multi_reference'
        elif 'sketch' in features:intent='sketch'
        else:intent='edit' if images else 't2i'
        w=self.workflows.select(intent,params['workflow'])
        w,community_profile=augment(w,params,features,info)
        uploads=[]
        for i,im in enumerate(images):
            path=folder/f'reference_{i+1}.png';im.save(path);uploads.append(c.upload(path));files[f'reference_{i+1}']=str(path.relative_to(self.store.root))
        graph=self.workflows.build(w,params,uploads,features)
        for node in graph.values():
            if node['class_type'] not in info:raise AppError('Node','必要なNodeがありません：'+node['class_type'])
            description=info[node['class_type']]
            if description.get('api_node') or description.get('python_module','').startswith('comfy_api_nodes'):
                raise AppError('Privacy','外部AI用Nodeを含むWorkflowはローカルモードで実行できません：'+node['class_type'])
        if 'control' in features:
            choices=info.get('ModelPatchLoader',{}).get('input',{}).get('required',{}).get('name',[[]])[0]
            if params['control_model'] not in choices:raise AppError('Model','Qwen 2.1 ControlNetモデルがありません。')
        write_json(folder/'workflow.json',graph)
        write_json(folder/'request.json',{**g,'effective_parameters':params,'intent':intent,'features':features,'files':files,'workflow_profile':w})
        self.logger.info('request generation=%s intent=%s workflow=%s refs=%d features=%s',g['id'],intent,w['id'],len(uploads),features)
        return dict(workflow=graph,workflow_id=w['id'],workflow_version=w.get('version'),workflow_hash=hashlib.sha256(json.dumps(w,sort_keys=True).encode()).hexdigest(),
                    output_nodes=w['outputs'],effective_parameters=params,intent=intent,features=features,files=files,
                    community_profile=community_profile,applied_loras=params.get('loras',[]))

    def run(self,gid,recover=False):
        stop=threading.Event()
        try:
            g=self.store.generation(gid);c=Comfy(g['comfy_url'])
            def event(e):
                d=e.get('data',{})
                current=self.store.generation(gid)
                if current['status'] in TERMINAL or d.get('prompt_id')!=current.get('prompt_id'):return
                if e['type']=='progress': self.store.update_generation(gid,progress=dict(value=d.get('value'),max=d.get('max')),stage='画像を生成中',status='Generating')
                elif e['type']=='executing' and d.get('node'):self.store.update_generation(gid,stage='画像を処理中',status='Generating')
            threading.Thread(target=c.events,args=(self.client_id+'-'+gid,event,stop),daemon=True).start()
            if not recover:
                prepared=self.prepare(g,c)
                with self.lock:
                    g=self.store.generation(gid)
                    if g['cancel_requested']:
                        self.store.update_generation(gid,status='Cancelled',stage='停止済み');return
                    pid=uid()
                    self.store.update_generation(gid,**prepared,prompt_id=pid,stage='ComfyUIへ送信中')
                    # Persist the client-generated UUID before POST. A lost response is recoverable without resubmission.
                    try:c.request('/prompt',dict(prompt=prepared['workflow'],prompt_id=pid,client_id=self.client_id+'-'+gid,extra_data={'qic_generation_id':gid}),timeout=90)
                    except AppError as e:
                        if e.category!='Connection':raise
                g=self.store.generation(gid)
            pid=g['prompt_id'];last_seen=now();missing_since=None
            while not self.stopping.is_set():
                try:
                    history=c.request('/history/'+pid)
                    current=self.store.generation(gid)
                    if pid in history:
                        h=history[pid];status=h.get('status',{})
                        if status.get('status_str')=='error':
                            messages=status.get('messages',[])
                            if any(m[0]=='execution_interrupted' for m in messages):
                                self.store.update_generation(gid,status='Cancelled',stage='停止済み');return
                            detail=json.dumps(messages,ensure_ascii=False)
                            category='Memory' if 'out of memory' in detail.lower() else 'Workflow'
                            raise AppError(category,'ComfyUIの生成処理でエラーが発生しました。設定を見直して再試行できます。',detail)
                        if status.get('completed') or h.get('outputs'):
                            self.save_outputs(current,h,c);return
                    queue=c.request('/queue');running={x[1] for x in queue.get('queue_running',[])};pending={x[1] for x in queue.get('queue_pending',[])}
                    if current['cancel_requested']:
                        if pid in running or pid in pending:c.request('/api/jobs/'+pid+'/cancel',{})
                        else:
                            self.store.update_generation(gid,status='Cancelled',stage='停止済み');return
                    if pid in running|pending:
                        missing_since=None
                        self.store.update_generation(gid,status='Generating' if pid in running else 'Waiting',stage='生成中' if pid in running else ('英語変換の完了待ち' if any(n.get('class_type')=='TextGenerate' for item in queue.get('queue_running',[]) for n in item[2].values()) else '順番待ち'))
                    else:
                        missing_since=missing_since or now()
                        if now()-missing_since>20:raise AppError('JobMissing','ComfyUIに生成が見つかりません。履歴が消去されたか送信が完了していません。自動再送は行っていません。')
                    last_seen=now()
                except AppError as e:
                    if e.category!='Connection' or now()-last_seen>120:raise
                    self.store.update_generation(gid,stage='接続確認中・生成IDを保持しています')
                self.stopping.wait(1.5)
        except Exception as e:
            err=e if isinstance(e,AppError) else AppError('Save' if isinstance(e,(OSError,sqlite3.Error)) else 'Application','処理を完了できませんでした。入力と履歴は保持されています。',str(e))
            self.logger.error('generation=%s category=%s detail=%s',gid,err.category,str(err.detail)[:4000])
            try:self.store.update_generation(gid,status='Failed',stage='エラー',error=err.as_dict())
            except Exception:self.logger.exception('Failed to persist failure state')
        finally:stop.set()

    def save_outputs(self,g,history,c):
        folder=self.store.root/'generations'/g['id']
        self.store.update_generation(g['id'],stage='結果を保存中')
        outputs=[]
        for node in g['output_nodes']:
            for index,item in enumerate(history.get('outputs',{}).get(node,{}).get('images',[])):
                try:data=c.request('/view?'+urllib.parse.urlencode(item),raw=True,timeout=60)
                except AppError as e:raise AppError('Output','生成は完了しましたが、画像を取得できません。結果を再取得できます。',e.detail)
                rawname=f'raw_{node}_{index}.png';atomic(folder/rawname,data)
                if 'mask' in g.get('features',[]) or 'preserve_mask' in g.get('files',{}):
                    # Preserve unmasked pixels, also keep the original model output separately.
                    basefile=g['files'].get('preserve_base',g['files'].get('base'));maskfile=g['files'].get('preserve_mask',g['files'].get('mask'))
                    with Image.open(io.BytesIO(data)) as result, Image.open(self.store.root/basefile) as base, Image.open(self.store.root/maskfile) as mask:
                        size=result.size
                        if base.size!=size or mask.size!=size:raise AppError('Output','Maskと出力サイズが一致しません。合成せず元出力を保存しました。')
                        merged=Image.composite(result.convert('RGBA'),base.convert('RGBA'),mask.convert('L'))
                        buf=io.BytesIO();merged.save(buf,format='PNG');data=buf.getvalue()
                aid=str(uuid.uuid5(uuid.UUID(g['id']),f'{node}:{index}'))
                a=self.store.add_image(data,f'Qwen-{g["id"][:8]}-{len(outputs)+1}.png',aid)
                outputs.append(a)
        if not outputs:raise AppError('Output','Workflowが出力画像を返していません。出力Nodeの設定を確認してください。')
        self.store.update_generation(g['id'],outputs=outputs,status='Completed',stage='完了',progress=None,error=None,completed=now())
        write_json(folder/'metadata.json',self.store.generation(g['id']))
        self.logger.info('completed generation=%s outputs=%d',g['id'],len(outputs))
