"""Enum constants cho dropdown UI ketoan.

Anh chốt 2026-04-29:
- Loại Doanh Thu (5): Đồ Gỗ Lẻ / Dự Án / Đồ Mây / Vận Chuyển / Khác
- Loại Thanh Toán (4): Đặt Cọc / Thanh Toán / Thu Ship / Khác
"""
from __future__ import annotations


LOAI_DOANH_THU: list[str] = [
    "Doanh thu đồ gỗ lẻ",
    "Doanh thu dự án",
    "Doanh thu đồ mây",
    "Doanh thu vận chuyển",
    "Doanh thu khác",
]


LOAI_THANH_TOAN: list[str] = [
    "Đặt cọc",
    "Thanh toán",
    "Thu ship",
    "Khác",
]
