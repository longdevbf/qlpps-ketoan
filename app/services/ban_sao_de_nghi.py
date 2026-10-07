"""Từ chối "kèm bản sao" cho khoản trả nhà cung cấp có HAI dòng chi nối nhau.

Một khoản trả NCC hiện ra ở Duyệt chi bằng hai dòng cùng số tiền: đề xuất bên Mua Hàng
(muahang.congno, cột dntt_id) và Đề nghị TT bản sao bên Sale Admin (saleadmin.denghitt, cột
ref_congno). Nút Chi ở một bên khoá bên kia (da_chi_ngoai / da_chi), nhưng nút Từ chối trước đây
KHÔNG — từ chối một dòng mà dòng còn lại vẫn chi được (30/09/2026, khoản 50.000.000 Chiến Phương).

Hàm ở đây từ chối luôn dòng còn lại. Ghi trong CÙNG giao dịch với dòng vừa từ chối (caller commit
sau) nên cả hai cùng đổi hoặc không cái nào đổi. Chỉ đụng dòng còn "sống" (cho_duyet / kt_duyet /
duyet) và CHƯA chi; dòng đã chi hoặc đã từ chối thì để nguyên. Dùng raw SQL có điều kiện ngay trong
UPDATE (đọc app khác theo luật cross-app) nên không cần nạp model của app anh em.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def tu_choi_dntt_kem(
    db: Session, *, dntt_id: Optional[str], ly_do: str, username: str,
) -> Optional[str]:
    """Đề xuất Mua Hàng vừa bị từ chối → từ chối luôn Đề nghị TT bản sao (nếu còn chờ chi).

    Trả id Đề nghị TT đã từ chối, hoặc None nếu không có / không còn sống / đã chi.
    Ghi cột theo đúng cách hai đường từ chối sẵn có: cấp 1 (cho_duyet → kt_tu_choi) ghi kt_*,
    còn lại (→ tu_choi) ghi nguoi_duyet / ngay_duyet / ly_do giống reject_denghitt của Sale Admin.
    """
    if not dntt_id:
        return None
    return db.execute(
        text("""
            UPDATE saleadmin.denghitt SET
                trang_thai   = CASE WHEN trang_thai = 'cho_duyet' THEN 'kt_tu_choi' ELSE 'tu_choi' END,
                kt_duyet_boi = CASE WHEN trang_thai = 'cho_duyet' THEN :u ELSE kt_duyet_boi END,
                kt_duyet_luc = CASE WHEN trang_thai = 'cho_duyet' THEN now() ELSE kt_duyet_luc END,
                kt_ghi_chu   = CASE WHEN trang_thai = 'cho_duyet' THEN :ly ELSE kt_ghi_chu END,
                nguoi_duyet  = CASE WHEN trang_thai = 'cho_duyet' THEN nguoi_duyet ELSE :u END,
                ngay_duyet   = CASE WHEN trang_thai = 'cho_duyet' THEN ngay_duyet ELSE now() END,
                ly_do        = CASE WHEN trang_thai = 'cho_duyet' THEN ly_do ELSE :ly END
            WHERE id = :id
              AND trang_thai IN ('cho_duyet', 'kt_duyet', 'duyet')
              AND NOT COALESCE(da_chi, FALSE) AND NOT COALESCE(da_chi_ngoai, FALSE)
            RETURNING id
        """),
        {"id": dntt_id, "u": username, "ly": f"{ly_do} (từ chối kèm đề xuất Mua Hàng)"},
    ).scalar_one_or_none()


def tu_choi_de_xuat_kem(
    db: Session, *, congno_id: Optional[str], ly_do: str, username: str,
) -> Optional[str]:
    """Đề nghị TT vừa bị từ chối → từ chối luôn đề xuất trả NCC bên Mua Hàng (nếu còn chờ chi).

    Trả id đề xuất đã từ chối, hoặc None. Ghi đúng cột Mua Hàng đọc lại khi "Sửa & gửi lại"
    (ghi_chu_duyet khi tu_choi, kt_ghi_chu khi kt_tu_choi) và thêm một mốc vào lich_su bằng đúng
    action có sẵn trong danh sách đóng của Mua Hàng (kt_tu_choi | ceo_tu_choi).
    """
    if not congno_id:
        return None
    return db.execute(
        text("""
            UPDATE muahang.congno SET
                lich_su = COALESCE(lich_su, '[]'::jsonb) || jsonb_build_array(jsonb_build_object(
                    'action', CASE WHEN trang_thai = 'cho_duyet' THEN 'kt_tu_choi' ELSE 'ceo_tu_choi' END,
                    'by', CAST(:u AS text),
                    'time', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"'),
                    'note', CAST(:ly AS text))),
                trang_thai    = CASE WHEN trang_thai = 'cho_duyet' THEN 'kt_tu_choi' ELSE 'tu_choi' END,
                kt_duyet_boi  = CASE WHEN trang_thai = 'cho_duyet' THEN :u ELSE kt_duyet_boi END,
                kt_duyet_luc  = CASE WHEN trang_thai = 'cho_duyet' THEN now() ELSE kt_duyet_luc END,
                kt_ghi_chu    = CASE WHEN trang_thai = 'cho_duyet' THEN :ly ELSE kt_ghi_chu END,
                nguoi_duyet   = CASE WHEN trang_thai = 'cho_duyet' THEN nguoi_duyet ELSE :u END,
                ngay_duyet    = CASE WHEN trang_thai = 'cho_duyet' THEN ngay_duyet ELSE now() END,
                ghi_chu_duyet = CASE WHEN trang_thai = 'cho_duyet' THEN ghi_chu_duyet ELSE :ly END
            WHERE id = :id AND loai = 'de_xuat_tra'
              AND trang_thai IN ('cho_duyet', 'kt_duyet', 'duyet')
              AND NOT COALESCE(da_chi, FALSE)
            RETURNING id
        """),
        {"id": congno_id, "u": username, "ly": f"{ly_do} (từ chối kèm Đề nghị thanh toán Sale Admin)"},
    ).scalar_one_or_none()
