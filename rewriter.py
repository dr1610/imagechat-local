"""Official Qwen PE checkpoints, executed only on configured local ComfyUI."""
import copy,hashlib,json,re,threading,time,uuid
from pathlib import Path
from PIL import Image,ImageOps
from comfy import Comfy,AppError

ROOT=Path(__file__).resolve().parent
MODELS={'edit':'qwen3.5_9b_qwen_image_2.1_pe_i2i.int8_convrot.safetensors','t2i':'qwen3.5_9b_qwen_image_2.1_pe_t2i.int8_convrot.safetensors'}
def context(body):
    return {k:body.get(k,default) for k,default in [('prompt',''),('references',[]),('editor',None),('art_style','none')]}
def fingerprint(body):
    return hashlib.sha256(json.dumps(context(body),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def parse_answer(raw,count):
    if '<think>' in raw and '</think>' not in raw:raise AppError('Rewrite','変換が思考途中で終了しました。再試行してください。')
    answer=raw.rsplit('</think>',1)[-1].strip()
    decoder=json.JSONDecoder();result=None
    for m in re.finditer(r'\{',answer):
        try:
            candidate,_=decoder.raw_decode(answer[m.start():])
            if isinstance(candidate,dict) and isinstance(candidate.get('rewritten_prompt'),str):result=candidate;break
        except ValueError:pass
    if not result or not result['rewritten_prompt'].strip():raise AppError('Rewrite','公式Rewriterが有効な英文を返しませんでした。再試行してください。')
    if len(result['rewritten_prompt'])>24000:raise AppError('Rewrite','変換結果が長すぎます。')
    if any(int(n)<1 or int(n)>count for n in re.findall(r'<image(\d+)>',result['rewritten_prompt'])):raise AppError('Rewrite','変換結果に存在しない画像番号が含まれています。')
    return result

class Rewriter:
    def __init__(self,app):
        self.app=app;self.root=app.store.root/'rewrites';self.root.mkdir(exist_ok=True)
        self.jobs={};self.lock=threading.RLock()
    def save(self,j):
        with self.lock:
            self.jobs[j['id']]=j
            p=self.root/(j['id']+'.json');tmp=p.with_suffix('.tmp')
            tmp.write_text(json.dumps(j,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(p)
    def get(self,jid):
        if not re.fullmatch(r'[a-f0-9-]{36}',jid):raise AppError('Rewrite','変換IDが不正です。')
        with self.lock:
            if jid in self.jobs:return copy.deepcopy(self.jobs[jid])
            p=self.root/(jid+'.json')
            if not p.exists():raise AppError('Rewrite','変換記録が見つかりません。')
            j=json.loads(p.read_text(encoding='utf-8'))
            if j['status'] in ('Waiting','Generating'):j.update(status='Failed',error='アプリが再起動しました。再変換してください。')
            return j
    def start(self,body):
        from reference_input import validate_reference_mentions
        self.app.store.session(body['session_id'])
        ctx=context(body)
        validate_reference_mentions(str(ctx['prompt']),ctx['references'])
        if not str(ctx['prompt']).strip() or len(ctx['prompt'])>16000:raise AppError('Input','変換する指示を16000文字以内で入力してください。')
        if len(ctx['references'])>10:raise AppError('Input','画像は10枚までです。')
        for aid in ctx['references']:self.app.store.asset_path(aid)
        j=dict(id=str(uuid.uuid4()),session_id=body['session_id'],status='Waiting',created=time.time(),context=ctx,fingerprint=fingerprint(body),comfy_url=self.app.config['comfy_url'],cancel_requested=False)
        self.save(j);threading.Thread(target=self.run,args=(j,),daemon=True).start();return copy.deepcopy(j)
    def cancel(self,jid):
        with self.lock:
            j=self.jobs.get(jid)
            if not j:return self.get(jid)
            if j['status'] in ('Completed','Failed','Cancelled'):return copy.deepcopy(j)
            j['cancel_requested']=True;self.save(j)
            if j.get('prompt_id'):Comfy(j['comfy_url']).request('/api/jobs/'+j['prompt_id']+'/cancel',{})
            return copy.deepcopy(j)
    def approved(self,body):
        j=self.get(body.get('rewrite_id',''))
        ctx={**body,'art_style':body.get('params',{}).get('art_style','none')}
        same_context=j['fingerprint']==fingerprint(ctx)
        if not same_context and body.get('regenerated_from_generation_id'):
            prior=self.app.store.generation(body['regenerated_from_generation_id'])
            same_context=(prior.get('rewrite') or {}).get('id')==j['id'] and prior['session_id']==body['session_id'] and prior['original_prompt']==body['prompt'] and prior['references']==body.get('references',[]) and prior.get('editor')==body.get('editor') and prior['params']['art_style']==body['params']['art_style']
        if j['status']!='Completed' or j['session_id']!=body['session_id'] or not same_context:raise AppError('Rewrite','原文・画像・Canvas・画風が変わっています。もう一度英語に変換してください。')
        text=body.get('enhanced_prompt',j['result']['rewritten_prompt'])
        if not isinstance(text,str) or not text.strip() or len(text)>24000:raise AppError('Rewrite','英文を確認してください。')
        if any(int(n)<1 or int(n)>len(ctx['references']) for n in re.findall(r'<image(\d+)>',text)):raise AppError('Rewrite','英文の画像番号を確認してください。')
        return text,dict(id=j['id'],model=j['model'],result=j['result'],user_edited=text!=j['result']['rewritten_prompt'])
    def run(self,j):
        stop=threading.Event()
        try:
            from core import render_editor
            c=Comfy(j['comfy_url']);ctx=j['context'];refs=ctx['references'];task='edit' if refs else 't2i';model=MODELS[task]
            info=c.request('/object_info',timeout=30)
            for n in ('CLIPLoader','TextGenerate','PreviewAny','LoadImage','BatchImagesNode'):
                if n not in info:raise AppError('Node','公式Rewriterに必要なNodeがありません：'+n)
            if model not in info['CLIPLoader']['input']['required']['clip_name'][0]:raise AppError('Model','公式Rewriterモデルが見つかりません：'+model)
            folder=self.root/j['id'];folder.mkdir(exist_ok=True)
            images=[]
            for i,aid in enumerate(refs):
                with Image.open(self.app.store.asset_path(aid)) as src:im=src.convert('RGBA')
                if i==0 and ctx['editor']:
                    base,sketch,mask,pose=render_editor(im,ctx['editor']);im=Image.alpha_composite(base,sketch)
                # Same-size letterbox for Comfy's image batch; never stretch references.
                rgb=Image.new('RGB',im.size,'white');rgb.paste(im,mask=im.getchannel('A'))
                fitted=ImageOps.contain(rgb,(768,768));canvas=Image.new('RGB',(768,768),'white');canvas.paste(fitted,((768-fitted.width)//2,(768-fitted.height)//2))
                path=folder/f'reference_{i+1}.png';canvas.save(path);images.append(c.upload(path))
            system=(ROOT/'prompts'/('system_prompt_edit.txt' if refs else 'system_prompt_t2i.txt')).read_text(encoding='utf-8')
            raw=ctx['prompt']
            styles={'illustration':'Keep the output an anime or drawn illustration, preserving the illustration medium of the subject reference.','photoreal':'Render the output in a photorealistic photographic style.','none':''}
            raw+='\n'+styles.get(ctx['art_style'],'')
            if ctx['editor']:
                raw+='\nCanvas edits are intentional. Preserve the selected canvas composition; use visible sketch as a placement guide where present.'
            vision=''.join('<|vision_start|><|image_pad|><|vision_end|>' for _ in images)
            formatted=f'<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{vision}{raw}<|im_end|>\n<|im_start|>assistant\n<think>\n'
            inputs={'clip':['1',0],'prompt':formatted,'max_length':24000 if refs else 16256,'thinking':True,'use_default_template':False,'mtp':'auto','sampling_mode':'on','sampling_mode.temperature':1.0,'sampling_mode.top_k':20,'sampling_mode.top_p':0.95,'sampling_mode.min_p':0.0,'sampling_mode.repetition_penalty':1.0,'sampling_mode.presence_penalty':0.0 if refs else 1.5,'sampling_mode.seed':42}
            graph={'1':{'class_type':'CLIPLoader','inputs':{'clip_name':model,'type':'qwen_image','device':'default'}},'2':{'class_type':'TextGenerate','inputs':inputs},'3':{'class_type':'PreviewAny','inputs':{'source':['2',0]}}}
            if images:
                for i,name in enumerate(images):graph[str(10+i)]={'class_type':'LoadImage','inputs':{'image':name}}
                graph['4']={'class_type':'BatchImagesNode','inputs':{f'images.image{i}':[str(10+i),0] for i in range(len(images))}};inputs['image']=['4',0]
            (folder/'workflow.json').write_text(json.dumps(graph,ensure_ascii=False,indent=2),encoding='utf-8')
            client_id='qic-rewriter-'+j['id']
            last_progress=[0.0]
            def event(e):
                d=e.get('data',{})
                with self.lock:
                    if j['status'] not in ('Waiting','Generating') or d.get('prompt_id')!=j.get('prompt_id'):return
                    if e.get('type')=='progress' and time.monotonic()-last_progress[0]>=0.4:
                        last_progress[0]=time.monotonic()
                        j.update(progress={'value':d.get('value'),'max':d.get('max')},stage='思考・英文生成中')
                        self.save(j)
                    elif e.get('type')=='executing' and d.get('node'):
                        j['stage']='画像解析・英文生成の準備中';self.save(j)
            threading.Thread(target=c.events,args=(client_id,event,stop),daemon=True).start()
            with self.lock:
                if j['cancel_requested']:j['status']='Cancelled';self.save(j);return
                j.update(model=model,task=task,status='Generating',stage='準備・順番待ち',progress=None,prompt_id=c.request('/prompt',{'prompt':graph,'client_id':client_id})['prompt_id']);self.save(j)
            deadline=time.monotonic()+1800
            while time.monotonic()<deadline:
                if j['cancel_requested']:j['status']='Cancelled';self.save(j);return
                h=c.request('/history/'+j['prompt_id']).get(j['prompt_id'])
                if h:
                    if h['status']['status_str']!='success':raise AppError('Rewrite','公式Rewriterの実行に失敗しました。',h['status'])
                    raw='\n'.join(h['outputs']['3']['text']);(folder/'raw-output.txt').write_text(raw,encoding='utf-8')
                    if '</think>' not in raw:raise AppError('Rewrite','変換が思考途中で終了しました。再試行してください。')
                    j.update(result=parse_answer(raw,len(refs)),status='Completed',completed=time.time());self.save(j);return
                if not j.get('progress'):
                    queue=c.request('/queue')
                    j['stage']='画像解析・モデル読込中' if any(x[1]==j['prompt_id'] for x in queue.get('queue_running',[])) else '順番待ち'
                    self.save(j)
                time.sleep(1)
            c.request('/api/jobs/'+j['prompt_id']+'/cancel',{})
            raise AppError('Rewrite','変換が時間内に完了しませんでした。再試行してください。')
        except Exception as e:
            j.update(status='Cancelled' if j['cancel_requested'] else 'Failed',error=str(e));self.save(j);self.app.logger.exception('Rewrite failed')
        finally:
            stop.set()
