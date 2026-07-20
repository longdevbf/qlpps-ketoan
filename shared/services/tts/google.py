"""Google Cloud Text-to-Speech provider (REST v1, xác thực bằng API key).

Đơn giản hơn FPT: POST 1 lần -> nhận base64 mp3 NGAY (không phải poll link async).
Giọng Việt Neural2/Wavenet rất trong, tự nhiên. Free 1 triệu ký tự/tháng.

Env:
  GOOGLE_TTS_API_KEY   (bắt buộc)  API key có bật Cloud Text-to-Speech API.
  GOOGLE_TTS_VOICE     (mặc định vi-VN-Neural2-A)
  GOOGLE_TTS_RATE      (mặc định 1.0)  tốc độ đọc 0.25..4.0.

Bảo mật: KHÔNG bao giờ log API key.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from collections import OrderedDict
from typing import Optional

import httpx

from .base import TTSError, TTSProvider, register_provider

logger = logging.getLogger(__name__)

GOOGLE_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
_HTTP_TIMEOUT = 30.0
_MAX_RETRIES = 3          # retry lỗi MẠNG (ConnectError tới Google chập chờn từ VPS)

# Giọng Việt của Google (Neural2 nét nhất; Wavenet cũng rất tốt).
_VOICES: list[dict] = [
    {"id": "vi-VN-Neural2-A", "label": "Neural2 A (nữ)", "gender": "female", "accent": "bac"},
    {"id": "vi-VN-Neural2-D", "label": "Neural2 D (nam)", "gender": "male", "accent": "bac"},
    {"id": "vi-VN-Wavenet-A", "label": "Wavenet A (nữ)", "gender": "female", "accent": "bac"},
    {"id": "vi-VN-Wavenet-C", "label": "Wavenet C (nữ)", "gender": "female", "accent": "bac"},
    {"id": "vi-VN-Wavenet-B", "label": "Wavenet B (nam)", "gender": "male", "accent": "bac"},
    {"id": "vi-VN-Wavenet-D", "label": "Wavenet D (nam)", "gender": "male", "accent": "bac"},
    {"id": "vi-VN-Standard-A", "label": "Standard A (nữ)", "gender": "female", "accent": "bac"},
]
_VOICE_IDS = {v["id"] for v in _VOICES}

# Cache LRU trong RAM: (provider, text, voice, rate) -> mp3 bytes.
_CACHE_MAX = 256
_cache: "OrderedDict[tuple, bytes]" = OrderedDict()


def _cache_get(key: tuple) -> Optional[bytes]:
    val = _cache.get(key)
    if val is not None:
        _cache.move_to_end(key)
    return val


def _cache_put(key: tuple, value: bytes) -> None:
    _cache[key] = value
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


class GoogleTTSProvider(TTSProvider):
    """Provider gọi Google Cloud Text-to-Speech (REST v1)."""

    name = "google"

    def _api_key(self) -> str:
        key = (os.getenv("GOOGLE_TTS_API_KEY") or "").strip()
        if not key:
            raise TTSError("GOOGLE_TTS_API_KEY chưa cấu hình")
        return key

    def default_voice(self) -> str:
        return (os.getenv("GOOGLE_TTS_VOICE") or "vi-VN-Neural2-A").strip() or "vi-VN-Neural2-A"

    def _rate(self, speed: Optional[int]) -> float:
        """speakingRate 0.25..4.0. App truyền speed int (-3..3) -> map nhẹ; nếu None
        thì lấy env GOOGLE_TTS_RATE (mặc định 1.0)."""
        if speed is not None:
            try:
                # Base 1.12 (nhanh hơn ~12% mặc định) + ±0.13/nấc slider (-3..3).
                # Anh Quang 2026-07-08: giảm 1.25 → 1.12 cho Mai đọc chậm lại 1 chút.
                return max(0.25, min(4.0, 1.12 + int(speed) * 0.13))
            except (TypeError, ValueError):
                pass
        try:
            return max(0.25, min(4.0, float(os.getenv("GOOGLE_TTS_RATE") or 1.0)))
        except (TypeError, ValueError):
            return 1.0

    def list_voices(self) -> list[dict]:
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

        rate = self._rate(speed)

        cache_key = (self.name, text, sel_voice, round(rate, 3))
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        audio = await self._call_google(api_key, text, sel_voice, rate)
        _cache_put(cache_key, audio)
        return audio

    async def _call_google(self, api_key: str, text: str, voice: str, rate: float) -> bytes:
        payload = {
            "input": {"text": text},
            "voice": {"languageCode": "vi-VN", "name": voice},
            "audioConfig": {"audioEncoding": "MP3", "speakingRate": rate},
        }
        timeout = httpx.Timeout(connect=8.0, read=_HTTP_TIMEOUT, write=10.0, pool=8.0)
        # Retry lỗi MẠNG (ConnectError từ VPS tới Google chập chờn) để Mai KHÔNG rơi
        # về giọng trình duyệt. Lỗi API (key/quota/HTTP != 200) thì KHÔNG retry.
        last_err: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=timeout) as cli:
                    resp = await cli.post(GOOGLE_TTS_URL, params={"key": api_key}, json=payload)
                if resp.status_code != 200:
                    # KHÔNG lộ key; lấy message lỗi của Google nếu có.
                    msg = ""
                    try:
                        msg = ((resp.json() or {}).get("error", {}) or {}).get("message", "")
                    except Exception:
                        pass
                    raise TTSError(f"Google TTS HTTP {resp.status_code}: {msg[:140]}")
                try:
                    data = resp.json()
                except Exception:
                    raise TTSError("Google TTS trả response không phải JSON")
                b64 = data.get("audioContent")
                if not b64:
                    raise TTSError("Google TTS không trả audioContent")
                try:
                    return base64.b64decode(b64)
                except Exception as e:
                    raise TTSError("Google TTS audioContent giải mã lỗi") from e
            except TTSError:
                raise  # lỗi API/logic — không retry
            except httpx.HTTPError as e:
                last_err = e
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(0.4 * (attempt + 1))  # backoff nhẹ rồi thử lại
                    continue
        raise TTSError(
            f"Lỗi mạng khi gọi Google TTS sau {_MAX_RETRIES} lần: "
            f"{type(last_err).__name__ if last_err else 'unknown'}"
        )


# Đăng ký provider vào registry (import module này là tự đăng ký).
register_provider("google", GoogleTTSProvider)
