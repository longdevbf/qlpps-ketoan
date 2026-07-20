"""Interface trừu tượng + registry cho TTS provider (plug-in).

Thiết kế plug-in: app chỉ gọi `shared.services.tts.synthesize(...)`; muốn đổi
nhà cung cấp (FPT → Piper → viXTTS...) chỉ cần:
    1. Viết class kế thừa `TTSProvider`.
    2. Gọi `register_provider("ten", LopProvider)`.
    3. Set env `TTS_PROVIDER=ten`.
KHÔNG sửa code app.

Provider được chọn qua env `TTS_PROVIDER` (default "fpt"). Instance được
cache lại (1 provider / process) để tái dùng connection/cache nội bộ.
"""
from __future__ import annotations

import abc
import logging
import os
from typing import Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER = "fpt"


class TTSError(Exception):
    """Lỗi khi tổng hợp giọng nói (cấu hình sai, mạng lỗi, provider trả lỗi)."""


class TTSProvider(abc.ABC):
    """Hợp đồng mọi provider TTS phải tuân theo.

    Mỗi provider tự lo: đọc env riêng, gọi API, cache, chuẩn hoá lỗi -> TTSError.
    """

    #: Tên đăng ký (khớp giá trị env TTS_PROVIDER).
    name: str = "base"

    @abc.abstractmethod
    async def synthesize(
        self,
        text: str,
        *,
        voice: Optional[str] = None,
        speed: Optional[int] = None,
    ) -> bytes:
        """Tổng hợp `text` -> mp3 bytes. Lỗi phải raise TTSError."""
        raise NotImplementedError

    @abc.abstractmethod
    def list_voices(self) -> list[dict]:
        """Danh sách giọng: [{"id","label","gender","accent"}, ...]."""
        raise NotImplementedError

    @abc.abstractmethod
    def default_voice(self) -> str:
        """Giọng mặc định của provider."""
        raise NotImplementedError


# --- Registry ----------------------------------------------------------------

_REGISTRY: dict[str, Callable[[], TTSProvider]] = {}
_INSTANCES: dict[str, TTSProvider] = {}


def register_provider(name: str, factory: Callable[[], TTSProvider]) -> None:
    """Đăng ký 1 provider. `factory` là callable không tham số trả TTSProvider
    (thường là chính class provider).
    """
    _REGISTRY[name.lower().strip()] = factory


def _active_name() -> str:
    """Tên provider đang bật (env TTS_PROVIDER, default 'fpt')."""
    return (os.getenv("TTS_PROVIDER") or DEFAULT_PROVIDER).lower().strip()


def get_provider() -> TTSProvider:
    """Lấy instance provider đang active (cache 1 instance / process).

    raise TTSError nếu tên provider không tồn tại trong registry.
    """
    name = _active_name()
    cached = _INSTANCES.get(name)
    if cached is not None:
        return cached

    factory = _REGISTRY.get(name)
    if factory is None:
        raise TTSError(
            f"TTS_PROVIDER='{name}' chưa được đăng ký "
            f"(có: {', '.join(sorted(_REGISTRY)) or 'không có'})"
        )
    inst = factory()
    _INSTANCES[name] = inst
    return inst
