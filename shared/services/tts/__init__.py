"""TTS plug-in cho app V2 — tổng hợp giọng nói tiếng Việt.

API công khai (các module khác CHỈ nên import từ đây):

    from shared.services.tts import (
        synthesize, list_voices, default_voice, split_sentences, TTSError,
    )

Provider mặc định = FPT.AI; đổi nhà cung cấp qua env `TTS_PROVIDER` mà
KHÔNG sửa code app (xem base.register_provider).
"""
from __future__ import annotations

from typing import Optional

from .base import TTSError, get_provider, register_provider
from .text import split_sentences

# Import provider để nó tự đăng ký vào registry. Thêm provider mới ở đây.
from . import fpt as _fpt  # noqa: F401  (side-effect: register_provider)
from . import google as _google  # noqa: F401  (side-effect: register_provider)

__all__ = [
    "TTSError",
    "synthesize",
    "list_voices",
    "default_voice",
    "split_sentences",
    "register_provider",
]


async def synthesize(
    text: str,
    *,
    voice: Optional[str] = None,
    speed: Optional[int] = None,
) -> bytes:
    """Tổng hợp `text` thành mp3 bytes qua provider đang active.

    Lỗi (thiếu key / mạng / provider trả lỗi) -> raise TTSError.
    """
    return await get_provider().synthesize(text, voice=voice, speed=speed)


def list_voices() -> list[dict]:
    """Danh sách giọng của provider active: [{"id","label","gender","accent"}, ...]."""
    return get_provider().list_voices()


def default_voice() -> str:
    """Giọng mặc định của provider active."""
    return get_provider().default_voice()
