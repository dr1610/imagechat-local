"""Opt-in community additions; graph/settings remain in external profiles."""
import copy,json,hashlib
from pathlib import Path
from comfy import AppError

ROOT=Path(__file__).resolve().parent

def validate(params):
    if params.get('quality_profile','standard') not in ('standard','turbo4') or params.get('outpaint_mode','standard') not in ('standard','lora_restore'):
        raise AppError('Input','生成方式または画像拡張の設定が不正です。')

def profile_for(params,features):
    if params.get('quality_profile','standard')!='standard' or params.get('outpaint_mode','standard')!='standard':
        raise AppError('Unsupported','この配布版は標準生成・標準拡張に対応します。追加LoRA方式は含みません。')
    turbo=params.get('quality_profile','standard')=='turbo4'
    outpaint=params.get('outpaint_mode','standard')=='lora_restore' and 'expand' in features
    if turbo and outpaint:raise AppError('Unsupported','高速4stepと拡張補助LoRAの併用は未検証です。生成方式を標準に戻してください。')
    if turbo and ('control' in features or 'mask' in features or 'pose' in features):raise AppError('Unsupported','高速4stepのMask／ControlNet併用は未検証です。標準方式を使用してください。')
    if outpaint and (set(features)&{'mask','pose','sketch'}):raise AppError('Unsupported','元画像固定の拡張補助はSketch／Mask／Poseとの併用に未対応です。標準の画像拡張を使用してください。')
    return 'turbo4' if turbo else 'outpaint' if outpaint else None

def augment(workflow,params,features,info):
    name=profile_for(params,features)
    if not name:return workflow,None
    if params.get('workflow','auto')!='auto':raise AppError('Unsupported','追加機能の使用時はWorkflowを「入力から自動選択」にしてください。')
    raw=(ROOT/'profiles'/(name+'.json')).read_bytes();p=json.loads(raw)
    for node in p['required_nodes']:
        if node not in info:raise AppError('Node','追加機能に必要なNodeがありません：'+node)
    required=info[p['loader_type']]['input']['required']['lora_name']
    choices=required[0] if isinstance(required[0],list) else required[1].get('options',[])
    if p['lora'] not in choices:raise AppError('Model','追加LoRAが見つかりません：'+p['lora'])
    w=copy.deepcopy(workflow)
    if name=='turbo4':
        if params['steps']!=4 or params['cfg']!=1 or params['sampler']!='euler' or params['denoise']!=1:
            raise AppError('Input','高速4stepではSteps=4、CFG=1、Sampler=euler、Denoise=1を指定してください。')
        params['latent']=copy.deepcopy(w['graph']['6']['inputs']['latent_image'])
        params['scheduler']='viggle_dynamic_4step'
    w['graph'].update(copy.deepcopy(p.get('graph',{})))
    for node,inputs in p.get('overrides',{}).items():w['graph'][node]['inputs'].update(inputs)
    params['loras']=[dict(name=p['lora'],weight=1.0,loader=p['loader_type'])]
    meta=dict(id=name,label=p['label'],sha256=hashlib.sha256(raw).hexdigest(),definition=p)
    w['community_profile']=meta
    return w,meta
