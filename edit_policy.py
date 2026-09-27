"""Conservative, inspectable routing based on the illustration benchmark."""
import re
from comfy import AppError

def plan(prompt, references, params, editor=None):
    mode=params.get('enhancer','auto')
    if mode not in ('auto','off','local'):
        raise AppError('Input','Enhancerは自動・OFF・ONから選択してください。')
    p=str(prompt); refs=len(references or [])
    angle=bool(re.search(r'俯瞰|煽り|あおり|見下ろ|見上げ|上から|下から|high.angle|low.angle',p,re.I))
    pose=refs>1 and bool(re.search(r'ポーズ|姿勢|pose',p,re.I))
    swap=refs>1 and bool(re.search(r'入れ替|入替|置き換|置換|差し替|replace|swap',p,re.I))
    # Mask/pose workflows are not covered by the enhancer comparison.
    canvas_control=bool(editor and (editor.get('poses') or any(s.get('layer')=='mask' for s in editor.get('strokes',[]))))
    reason='参照ポーズ' if pose else 'キャラ置換' if swap else '上下アングル' if angle and refs else ''
    automatic=bool(reason and not canvas_control and params.get('art_style')=='illustration' and params.get('quality_profile','standard')=='standard' and params.get('outpaint_mode','standard')=='standard')
    required=mode=='local' or (mode=='auto' and automatic)
    return dict(version=1,mode=mode,use_enhancer=required,reason=reason if required and mode=='auto' else 'ON指定' if required else '原文で生成')

def mask_color(prompt, editor):
    if not editor or editor.get('poses'):return False
    strokes=editor.get('strokes',[])
    if any(s.get('layer')!='mask' and not s.get('erase') for s in strokes):return False
    if not any(s.get('layer')=='mask' and not s.get('erase') for s in strokes):return False
    return bool(re.search(r'(?:青|赤|緑|黄|白|黒|紫|ピンク|オレンジ|水色)(?:色)?(?:に|く)|色を.{0,12}(?:変|変更)|recolou?r',str(prompt),re.I))
