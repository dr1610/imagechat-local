"""Prompt enhancement boundary. No network implementation is enabled in v1."""
from dataclasses import dataclass
from comfy import AppError


@dataclass(frozen=True)
class PromptResult:
    original: str
    enhanced: str | None

    @property
    def effective(self):
        return self.original if self.enhanced is None else self.enhanced


def enhance(original: str, mode: str = 'off') -> PromptResult:
    if mode != 'off':
        raise AppError('Unsupported', 'Prompt Enhancerは現在OFFのみ対応しています。外部送信は行いません。')
    return PromptResult(original=original, enhanced=None)
