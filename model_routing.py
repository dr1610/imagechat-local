"""Resolve and snapshot the image model before enqueue; no silent missing-model fallback."""
import copy,json
from pathlib import Path
from comfy import AppError
ROOT=Path(__file__).resolve().parent

def resolve(params,editor,config,catalog=None,prior=None,editing=False,prompt=''):
    catalog=catalog or json.loads((ROOT/'public'/'model-catalog.json').read_text(encoding='utf-8'))
    choice=params.get('model_preset','auto');style=params.get('art_style','none');policy=params.get('sampling_policy','recommended')
    if choice not in ('auto','settings',*catalog['models']):raise AppError('Input','画像モデルの選択が不正です。')
    if policy not in ('recommended','manual'):raise AppError('Input','モデル設定の選択が不正です。')
    control=bool(editor and (editor.get('poses') or any(s.get('layer')=='mask' for s in editor.get('strokes',[]))))
    addon=params.get('quality_profile','standard')!='standard' or params.get('outpaint_mode','standard')!='standard' or control
    illustration_edit=editing and style=='illustration'
    selected=('official' if addon or illustration_edit else catalog['auto'].get(style,'official')) if choice=='auto' else choice
    restored=False
    # Regenerate uses the previous actual model and profile, even if the catalog was edited.
    if prior and not prior.get('model_selection') and choice=='settings':
        result=dict(id='settings',label='元の生成モデル',file=prior.get('effective_parameters',{}).get('model') or prior['model_config'].get('model',''),settings={},negative=prior['params'].get('negative_prompt',''),reason='旧履歴の再生成：モデルを復元')
    elif prior and prior.get('model_selection') and choice==prior['params'].get('model_preset','auto') and style==prior['params'].get('art_style','none'):
        result=copy.deepcopy(prior['model_selection']);selected=result['id'];result['reason']='再生成：元のモデルと設定を復元'
        restored=True
    elif selected=='settings':
        result=dict(id='settings',label='接続設定のモデル',file=config.get('model',''),settings={},negative='',reason='手動：接続設定')
    else:
        result=copy.deepcopy(catalog['models'][selected]);result.update(id=selected,reason='補助機能に対応する公式モデル' if choice=='auto' and addon else '画風から自動選択' if choice=='auto' else '手動選択')
    if not restored and illustration_edit and selected=='official' and params.get('quality_profile','standard')=='standard':
        result['settings']={**result.get('settings',{}),'cfg':3}
        result['reason']='イラスト編集向け設定'
        from edit_policy import mask_color
        if mask_color(prompt,editor):result['settings']['control_strength']=0.5
    if restored and policy=='recommended':
        for key in ('steps','cfg','sampler','scheduler','denoise','control_strength'):
            if key in prior['params']:params[key]=prior['params'][key]
    if addon and selected not in ('official','settings'):raise AppError('Unsupported','追加モデルと高速4step・拡張LoRA・Mask／Poseの併用は未検証です。モデルを自動または公式へ変更してください。')
    if addon and selected=='settings' and result.get('file') in [m['file'] for k,m in catalog['models'].items() if k!='official']:raise AppError('Unsupported','この追加モデルに補助LoRA／ControlNetは重ねられません。公式モデルを選択してください。')
    if not restored and policy=='recommended' and params.get('quality_profile','standard')=='standard':
        params.update(result.get('settings',{}))
        if illustration_edit and selected=='official':params['control_strength']=result.get('settings',{}).get('control_strength',1.0)
    if style=='photoreal' and selected=='noct_anime':result['negative']='';result['prefix']=''
    return result
