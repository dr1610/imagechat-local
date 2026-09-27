"""Reject missing numbered references before any model work."""
import re
import unicodedata
from comfy import AppError

def validate_reference_mentions(prompt, references):
    text = unicodedata.normalize('NFKC', prompt)
    numbers = [int(n) for n in re.findall(r'<\s*image\s*(\d+)\s*>', text, re.I)]
    numbers += [int(n) for n in re.findall(r'(\d+)\s*枚目', text)]
    missing = sorted(set(n for n in numbers if n < 1 or n > len(references)))
    if missing:
        raise AppError('Input', '指示にある画像が添付されていません：' + '、'.join(f'{n}枚目' for n in missing) + '。参照画像を確認してください。')
