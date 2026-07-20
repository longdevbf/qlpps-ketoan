"""FPT.AI TTS provider (HMI TTS v5).

Luồng gọi FPT (đặc thù): FPT KHÔNG trả mp3 trực tiếp. POST text -> nhận về
1 LINK ASYNC; phải GET link đó và POLL tới khi file sẵn sàng (HTTP 200 +
size > ngưỡng) rồi mới có bytes mp3.

Bảo mật: KHÔNG bao giờ log api-key (chỉ log có/không cấu hình).
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections import OrderedDict
from typing import Optional

import httpx

from .base import TTSError, TTSProvider, register_provider

logger = logging.getLogger(__name__)

FPT_TTS_URL = "https://api.fpt.ai/hmi/tts/v5"

# Poll link async: tối đa ~16 lần, mỗi lần chờ ~0.3s (bắt audio sớm -> giảm độ trễ).
_POLL_MAX_TRIES = 16
_POLL_INTERVAL_S = 0.3
_MIN_AUDIO_BYTES = 2048  # > 2KB mới coi là file mp3 hợp lệ (tránh body lỗi/HTML).

_HTTP_TIMEOUT = 30.0

# Danh sách giọng FPT — kèm label tiếng Việt + gender + accent.
_VOICES: list[dict] = [
    {"id": "banmai", "label": "Bạn Mai (nữ Bắc)", "gender": "female", "accent": "bac"},
    {"id": "lannhi", "label": "Lan Nhi (nữ Nam)", "gender": "female", "accent": "nam"},
    {"id": "myan", "label": "Mỹ An (nữ Trung)", "gender": "female", "accent": "trung"},
    {"id": "thuminh", "label": "Thu Minh (nữ Bắc)", "gender": "female", "accent": "bac"},
    {"id": "ngoclam", "label": "Ngọc Lam (nữ Trung)", "gender": "female", "accent": "trung"},
    {"id": "leminh", "label": "Lê Minh (nam Bắc)", "gender": "male", "accent": "bac"},
    {"id": "giahuy", "label": "Gia Huy (nam Trung)", "gender": "male", "accent": "trung"},
]
_VOICE_IDS = {v["id"] for v in _VOICES}

# Cache LRU trong RAM: (provider, text, voice, speed) -> mp3 bytes.
# Giới hạn 256 mục để khỏi tổng hợp lại các câu lặp (lời chào, câu mẫu...).
_CACHE_MAX = 256
_cache: "OrderedDict[tuple, bytes]" = OrderedDict()


def _cache_get(key: tuple) -> Optional[bytes]:
    val = _cache.get(key)
    if val is not None:
        _cache.move_to_end(key)  # đánh dấu vừa dùng (LRU).
    return val


def _cache_put(key: tuple, value: bytes) -> None:
    _cache[key] = value
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)  # bỏ mục cũ nhất.


class FPTProvider(TTSProvider):
    """Provider gọi FPT.AI HMI TTS v5."""

    name = "fpt"

    def _api_key(self) -> str:
        key = (os.getenv("FPT_API_KEY") or "").strip()
        if not key:
            raise TTSError("FPT_API_KEY chưa cấu hình")
        return key

    def default_voice(self) -> str:
        return (os.getenv("FPT_VOICE") or "thuminh").strip() or "thuminh"

    def _default_speed(self) -> int:
        try:
            spd = int(os.getenv("FPT_SPEED") or 0)
        except (TypeError, ValueError):
            spd = 0
        # FPT cho phép -3..3.
        return max(-3, min(3, spd))

    def list_voices(self) -> list[dict]:
        # Trả copy để caller không sửa nhầm bảng gốc.
        return [dict(v) for v in _VOICES]

    async def synthesize(
        self,
        text: str,
        *,
        voice: Optional[str] = None,
        speed: Optional[int] = None,
    ) -> bytes:
        if not text or not text.strip():
            raise TTSError("Nội dung text rỗng")

        api_key = self._api_key()  # raise sớm nếu thiếu key.

        sel_voice = (voice or self.default_voice()).strip()
        if sel_voice not in _VOICE_IDS:
            sel_voice = self.default_voice()

        sel_speed = self._default_speed() if speed is None else max(-3, min(3, int(speed)))

        cache_key = (self.name, text, sel_voice, sel_speed)
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        audio = await self._call_fpt(api_key, text, sel_voice, sel_speed)
        _cache_put(cache_key, audio)
        return audio

    async def _call_fpt(
        self, api_key: str, text: str, voice: str, speed: int
    ) -> bytes:
        """Gọi FPT: POST lấy link async -> poll link -> bytes mp3."""
        headers = {
            "api-key": api_key,
            "voice": voice,
            "speed": str(speed),
            "format": "mp3",
        }
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as cli:
                resp = await cli.post(
                    FPT_TTS_URL,
                    headers=headers,
                    content=text.encode("utf-8"),  # body = text thô UTF-8.
                )
                if resp.status_code != 200:
                    raise TTSError(
                        f"FPT trả HTTP {resp.status_code} khi tạo TTS"
                    )
                try:
                    data = resp.json()
                except Exception:
                    raise TTSError("FPT trả response không phải JSON")

                if data.get("error"):
                    raise TTSError(
                        f"FPT báo lỗi (error={data.get('error')}): "
                        f"{data.get('message') or 'không rõ'}"
                    )

                async_url = data.get("async")
                if not async_url:
                    raise TTSError("FPT không trả link async")

                return await self._poll_audio(cli, async_url)
        except TTSError:
            raise
        except httpx.HTTPError as e:
            # Không lộ key: chỉ nêu loại lỗi mạng.
            raise TTSError(f"Lỗi mạng khi gọi FPT: {type(e).__name__}") from e

    async def _poll_audio(self, cli: httpx.AsyncClient, url: str) -> bytes:
        """GET link async tới khi HTTP 200 + size > ngưỡng (tối đa _POLL_MAX_TRIES)."""
        last_status: Optional[int] = None
        last_size = 0
        for _ in range(_POLL_MAX_TRIES):
            await asyncio.sleep(_POLL_INTERVAL_S)
            try:
                r = await cli.get(url)
            except httpx.HTTPError:
                continue  # mạng chập chờn -> thử lại.
            last_status = r.status_code
            if r.status_code == 200:
                content = r.content
                last_size = len(content)
                if last_size > _MIN_AUDIO_BYTES:
                    return content
                # 200 nhưng file còn nhỏ -> file chưa render xong, poll tiếp.
        raise TTSError(
            f"FPT chưa tạo xong audio sau {_POLL_MAX_TRIES} lần thử "
            f"(HTTP cuối={last_status}, size={last_size}B)"
        )


# Đăng ký provider vào registry (import module này là tự đăng ký).
register_provider("fpt", FPTProvider)
