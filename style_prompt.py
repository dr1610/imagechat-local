"""Explicit local style instruction, independent of optional prompt enhancement."""
from comfy import AppError

STYLE_INSTRUCTIONS = {
    'none': '',
    'illustration': '画風指定：イラストとして描いてください。描画された線と色で表現し、写真や実写の質感にしないでください。編集の場合も、指定された変更範囲にこの画風を適用してください。',
    'photoreal': '画風指定：フォトリアルな写真として表現してください。自然な光、現実的な素材感と細部を使い、イラストやアニメ調にしないでください。編集の場合も、指定された変更範囲にこの画風を適用してください。',
}


def apply_style(prompt, style='none', editing=False):
    if not isinstance(style, str) or style not in STYLE_INSTRUCTIONS:
        raise AppError('Input', '画風は「指定なし」「イラスト」「フォトリアル」から選択してください。')
    instruction = '' if editing else STYLE_INSTRUCTIONS[style]
    return (prompt if not instruction else prompt+'\n\n'+instruction), instruction
