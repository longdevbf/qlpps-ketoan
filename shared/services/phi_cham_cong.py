"""Cơ chế phí Đề xuất chấm công lại — trừ vào Tối ưu KD khi CEO duyệt và đồng ý trừ.

Config lưu hcns.app_config key='co_che_phi_cham_cong' (HCNS sửa ở màn Cơ chế), có
effective_from theo tháng — sửa KHÔNG hồi tố tháng trước, cùng khuôn co_che_di_muon /
co_che_cham_don / co_che_ke_toan. Đọc/ghi bằng SQL thô vì bảng thuộc schema `hcns`
còn module này nằm ở `shared` (các app khác không import được model của HCNS).

Config chỉ đặt MỨC TỐI THIỂU người gửi phải điền (`phi_moi_luot`). Số tiền thực trừ do CEO
quyết lúc duyệt cuối, ghi ở `de_xuat_cham_cong.phi_tru` (0 = không trừ); bảng lương chỉ
cộng cột đó theo THÁNG DUYỆT, đề xuất bị từ chối thì không tốn đồng nào.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

CONFIG_KEY = "co_che_phi_cham_cong"
HISTORY_KEY = "co_che_phi_cham_cong_history"

MUI_GIO_VN = "Asia/Ho_Chi_Minh"
DEFAULT_PHI_MOI_LUOT = 50_000      # đ / lượt gửi — HCNS đổi được
DEFAULT_SO_NGAY_TOI_DA = 7         # chỉ được đề xuất cho ngày trong N ngày gần nhất
MAX_PHI_MOI_LUOT = 10_000_000      # chặn gõ nhầm thừa số 0
MAX_SO_NGAY_TOI_DA = 60

DEFAULT_CONFIG: dict[str, Any] = {
    "phi_moi_luot": DEFAULT_PHI_MOI_LUOT,   # mức tối thiểu người gửi điền
    "so_ngay_toi_da": DEFAULT_SO_NGAY_TOI_DA,
}


def _doc_raw(db: Session, key: str):
    try:
        return db.execute(
            text("SELECT value FROM hcns.app_config WHERE key = :k LIMIT 1"), {"k": key}
        ).scalar()
    except Exception:
        db.rollback()
        return None


def _la_config(c: Any) -> bool:
    return isinstance(c, dict) and "phi_moi_luot" in c


def _them_mac_dinh(cfg: dict) -> dict:
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, list(v) if isinstance(v, list) else v)
    return cfg


def load_config(db: Session, thang: Optional[str] = None) -> dict[str, Any]:
    """thang=None → config hiện tại; thang='YYYY-MM' → config hiệu lực tháng đó."""
    cur = _doc_raw(db, CONFIG_KEY)
    current = cur if _la_config(cur) else dict(DEFAULT_CONFIG)
    if not thang:
        return _them_mac_dinh(dict(current))
    hist = _doc_raw(db, HISTORY_KEY)
    history = hist if isinstance(hist, list) else []
    cands = [c for c in (list(history) + [current]) if _la_config(c)]
    if not cands:
        return _them_mac_dinh(dict(DEFAULT_CONFIG))
    le = [c for c in cands if (c.get("effective_from") or "0000-00") <= thang]
    best = max(le, key=lambda c: c.get("effective_from") or "0000-00") if le \
        else min(cands, key=lambda c: c.get("effective_from") or "9999-99")
    return _them_mac_dinh(dict(best))


def chuan_hoa_config(body: dict[str, Any]) -> dict[str, Any]:
    """Kiểm tra + ép kiểu config từ client. Sai → ValueError (message hiển thị được)."""
    try:
        phi = int(round(float(body.get("phi_moi_luot", DEFAULT_PHI_MOI_LUOT))))
        so_ngay = int(body.get("so_ngay_toi_da", DEFAULT_SO_NGAY_TOI_DA))
    except (TypeError, ValueError):
        raise ValueError("Phí và số ngày phải là số")
    if not 0 <= phi <= MAX_PHI_MOI_LUOT:
        raise ValueError(f"Phí mỗi lượt phải từ 0 đến {MAX_PHI_MOI_LUOT:,}đ".replace(",", "."))
    if not 1 <= so_ngay <= MAX_SO_NGAY_TOI_DA:
        raise ValueError(f"Số ngày tối đa phải từ 1 đến {MAX_SO_NGAY_TOI_DA}")
    return {"phi_moi_luot": phi, "so_ngay_toi_da": so_ngay}


def luu_config(db: Session, body: dict[str, Any], thang_hien_tai: str, username: str) -> dict[str, Any]:
    """Lưu config mới, hiệu lực từ `thang_hien_tai`; bản cũ (tháng trước) đẩy vào history."""
    cfg = chuan_hoa_config(body)
    cfg["effective_from"] = thang_hien_tai
    cu = _doc_raw(db, CONFIG_KEY)
    if _la_config(cu) and (cu.get("effective_from") or "0000-00") < thang_hien_tai:
        hist = _doc_raw(db, HISTORY_KEY)
        hist = list(hist) if isinstance(hist, list) else []
        hist.append(cu)
        _ghi(db, HISTORY_KEY, hist, username)
    _ghi(db, CONFIG_KEY, cfg, username)
    db.commit()
    return cfg


def _ghi(db: Session, key: str, value: Any, username: str) -> None:
    import json

    db.execute(text("""
        INSERT INTO hcns.app_config (key, value, updated_at, updated_by)
        VALUES (:k, CAST(:v AS jsonb), now(), :u)
        ON CONFLICT (key) DO UPDATE
           SET value = EXCLUDED.value, updated_at = now(), updated_by = EXCLUDED.updated_by
    """), {"k": key, "v": json.dumps(value, ensure_ascii=False), "u": (username or "")[:64]})


def phi_theo_nv(db: Session, nbd, nkt) -> dict[str, dict[str, int]]:
    """Tổng tiền CEO quyết trừ + số lượt bị trừ theo mã NV (VIẾT HOA), tính theo NGÀY CEO DUYỆT
    trong [nbd, nkt]. Chỉ đề xuất đã duyệt xong và có `phi_tru` > 0."""
    out: dict[str, dict[str, int]] = {}
    try:
        rows = db.execute(text("""
            SELECT UPPER(ma_nv) AS ma, COUNT(*) AS so_luot, COALESCE(SUM(phi_tru), 0) AS phi
            FROM shared.de_xuat_cham_cong
            WHERE trang_thai = 'da_duyet' AND phi_tru > 0
              AND (ceo_luc AT TIME ZONE :tz)::date BETWEEN CAST(:nbd AS date) AND CAST(:nkt AS date)
            GROUP BY UPPER(ma_nv)
        """), {"tz": MUI_GIO_VN, "nbd": nbd, "nkt": nkt}).mappings().all()
    except Exception:
        db.rollback()
        return out
    for r in rows:
        out[r["ma"]] = {"so_luot": int(r["so_luot"]), "phi": int(r["phi"])}
    return out


def tru_vao_toi_uu(toi_uu: float, phi: float) -> tuple[float, float]:
    """Trừ phí vào Tối ưu KD, không để âm. Trả (tối ưu còn lại, phí thực trừ);
    phần phí vượt quá thưởng bỏ qua (không truy thu sang tháng sau)."""
    da_tru = min(max(toi_uu, 0.0), max(phi, 0.0))
    return toi_uu - da_tru, da_tru
