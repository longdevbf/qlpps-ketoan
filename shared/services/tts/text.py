"""Tách câu tiếng Việt cho TTS — chia text dài thành các câu nhỏ để
tổng hợp/stream từng câu một (giảm độ trễ tới câu đầu).

Quy tắc tách:
    - Ngắt theo dấu kết câu: . ? ! …  và theo xuống dòng.
    - Giữ lại dấu kết câu ở cuối mỗi mảnh (đọc tự nhiên hơn).
    - Gộp mảnh quá ngắn (< MIN_LEN ký tự) vào câu liền kề để tránh
      sinh ra những "câu" lẻ kiểu "Dạ." hay "Ạ." rời rạc.
"""
from __future__ import annotations

import re

# Mảnh ngắn hơn ngưỡng này sẽ được gộp vào câu trước (hoặc sau nếu là mảnh đầu).
MIN_LEN = 8

# Tách giữ lại dấu kết câu: . ? ! … và mọi ký tự xuống dòng.
# Dùng lookbehind cho dấu câu + split theo khoảng trắng/newline sau đó.
_SENT_SPLIT = re.compile(r"(?<=[\.\?\!…])\s+|\n+")


def split_sentences(text: str) -> list[str]:
    """Tách `text` thành danh sách câu tiếng Việt.

    Ví dụ:
        >>> split_sentences("Dạ chào sếp. Hôm nay doanh thu 1 tỷ! Sếp cần gì nữa ạ?")
        ['Dạ chào sếp.', 'Hôm nay doanh thu 1 tỷ!', 'Sếp cần gì nữa ạ?']
    """
    if not text or not text.strip():
        return []

    # Tách thô theo dấu câu + xuống dòng.
    raw = [p.strip() for p in _SENT_SPLIT.split(text) if p and p.strip()]
    if not raw:
        return []

    # Gộp mảnh quá ngắn vào câu liền kề.
    merged: list[str] = []
    for part in raw:
        if merged and len(part) < MIN_LEN:
            # Mảnh ngắn → dính vào câu trước.
            merged[-1] = f"{merged[-1]} {part}".strip()
        elif merged and len(merged[-1]) < MIN_LEN:
            # Câu trước (đầu chuỗi) còn quá ngắn → kéo mảnh này vào nó.
            merged[-1] = f"{merged[-1]} {part}".strip()
        else:
            merged.append(part)

    return merged
