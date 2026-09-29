"""SePay webhook handler — thu tiền auto vào sổ quỹ.

Flow khi SePay POST payload về `/api/sepay/webhook`:
1. Verify header `Authorization: Apikey <SEPAY_WEBHOOK_SECRET>` (env).
2. Bỏ qua nếu `transferType != 'in'` (chỉ care tiền vào).
3. Idempotent: nếu `sepay_id` đã tồn tại → return 200 (SePay retry policy).
4. Parse memo `content` → regex extract quote_number `NV\\d+-\\d+-\\d+`.
5. Nếu match:
   - INSERT sepay_transactions status='matched'
   - UPDATE baogia.quotes cộng dồn coc_so_tien
   - UPSERT ketoan.so_quy (ref_sepay='SEPAY-{id}') loại='thu', phan_loai_cf='thu_kh'
6. Nếu không match: INSERT status='orphan', KT xử lý tay.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import SepayTransaction, SoQuy

logger = logging.getLogger(__name__)

# Regex extract quote_number từ memo: NV<digits>-<digits>-<digits>
# Tolerate: khoảng trắng thay dấu gạch, chữ hoa/thường
_QN_RE = re.compile(r"NV\d+[\s\-_]*\d+[\s\-_]*\d+", re.IGNORECASE)

# TK ACB — hard-code cho MVP. Sau này mở rộng: đọc từ ENV hoặc tra
# `ketoan.tai_khoan_nh` theo account_number.
_TK_ACB = "ACB Hộ Kinh Doanh"


def verify_api_key(auth_header: Optional[str]) -> bool:
    """Verify `Authorization: Apikey <secret>` khớp env `SEPAY_WEBHOOK_SECRET`.

    Trả False nếu thiếu env / thiếu header / prefix sai / secret không khớp.
    """
    secret = os.environ.get("SEPAY_WEBHOOK_SECRET", "").strip()
    if not secret:
        logger.error("SEPAY_WEBHOOK_SECRET env not set — rejecting all webhooks")
        return False
    if not auth_header:
        return False
    parts = auth_header.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "apikey":
        return False
    # constant-time (chống timing side-channel dò secret) — SEC-04, 2026-08-28
    import hmac
    return hmac.compare_digest(parts[1].strip(), secret)


def _normalize_qn(raw: str) -> str:
    """`NV26005 26 00018` → `NV26005-26-00018` (canonical form)."""
    digits_dashes = re.sub(r"[\s_]+", "-", raw.strip())
    parts = re.split(r"[-\s_]+", digits_dashes)
    # Ghép lại đúng 3 phần: NV<x>-<y>-<z>
    if len(parts) >= 3:
        first = parts[0].upper()
        return f"{first}-{parts[1]}-{parts[2]}"
    return digits_dashes.upper()


def _extract_quote_number(content: Optional[str]) -> Optional[str]:
    if not content:
        return None
    m = _QN_RE.search(content)
    if not m:
        return None
    return _normalize_qn(m.group(0))


def _parse_transaction_date(raw: Any) -> Optional[datetime]:
    """SePay gửi format `YYYY-MM-DD HH:MM:SS` (naive local time VN)."""
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw
    s = str(raw).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _find_quote_by_number(db: Session, qn: str) -> Optional[dict]:
    """Cross-schema lookup `baogia.quotes` — trả `{id, quote_number, coc_so_tien}`.

    KHÔNG import model Quote (tránh cross-app coupling). Dùng raw SQL.
    """
    try:
        row = db.execute(
            text(
                "SELECT id, quote_number, COALESCE(coc_so_tien, 0) AS coc "
                "FROM baogia.quotes WHERE quote_number = :qn LIMIT 1"
            ),
            {"qn": qn},
        ).first()
        if not row:
            return None
        return {"id": row[0], "quote_number": row[1], "coc_so_tien": Decimal(row[2] or 0)}
    except Exception:
        db.rollback()
        return None


def _apply_deposit_to_quote(
    db: Session, quote: dict, amount: Decimal, tx_date: Optional[date],
) -> None:
    """Cộng dồn `coc_so_tien` + set `coc_hinh_thuc='chuyen_khoan'` + `coc_ngay`."""
    new_coc = (quote["coc_so_tien"] or Decimal(0)) + amount
    ngay = tx_date or date.today()
    db.execute(
        text(
            "UPDATE baogia.quotes SET "
            "  coc_so_tien = :coc, "
            "  coc_hinh_thuc = 'chuyen_khoan', "
            "  coc_ngay = COALESCE(coc_ngay, :ngay) "
            "WHERE id = :qid"
        ),
        {"coc": new_coc, "ngay": ngay, "qid": quote["id"]},
    )


def _upsert_so_quy_sepay(
    db: Session,
    *,
    sepay_id: int,
    amount: Decimal,
    tx_date: date,
    quote_number: str,
    content: str,
    reference_code: Optional[str],
) -> SoQuy:
    """Upsert vào `ketoan.so_quy` theo `ref_sepay='SEPAY-{sepay_id}'`.

    Idempotent: nếu bản ghi tồn tại → update số tiền / mô tả; nếu chưa → tạo mới.
    """
    ref_sepay = f"SEPAY-{sepay_id}"
    rec = db.execute(
        select(SoQuy).where(SoQuy.ref_sepay == ref_sepay)
    ).scalar_one_or_none()
    noi_dung = f"Thu cọc/thanh toán {quote_number} qua SePay"
    mo_ta_parts = [content or ""]
    if reference_code:
        mo_ta_parts.append(f"[REF: {reference_code}]")
    mo_ta = " ".join(p for p in mo_ta_parts if p).strip()
    if rec is None:
        rec = SoQuy(
            ref_sepay=ref_sepay,
            lien_quan="sepay",
            ref_id=ref_sepay,  # dùng cùng chuỗi để hiển thị đồng nhất
            ngay=tx_date,
            loai="thu",
            so_tien=amount,
            tai_khoan=_TK_ACB,
            noi_dung=noi_dung,
            mo_ta=mo_ta,
            phan_loai_cf="thu_kh",
            ma_don=quote_number,
            created_by="sepay-webhook",
        )
        db.add(rec)
    else:
        rec.ngay = tx_date
        rec.so_tien = amount
        rec.tai_khoan = _TK_ACB
        rec.noi_dung = noi_dung
        rec.mo_ta = mo_ta
        rec.phan_loai_cf = "thu_kh"
        rec.ma_don = quote_number
    db.flush()
    return rec


def handle_webhook(db: Session, payload: dict) -> dict:
    """Entry point cho router. Trả `{status, action, sepay_id, quote_number, ...}`.

    Không raise ngoại lệ nghiệp vụ — luôn commit + trả 200 để SePay không retry
    vô nghĩa. Chỉ raise nếu payload sai schema.
    """
    sepay_id = payload.get("id")
    if not isinstance(sepay_id, int) or sepay_id <= 0:
        raise ValueError("Missing or invalid 'id' in payload")

    transfer_type = (payload.get("transferType") or "").lower()
    amount_raw = payload.get("transferAmount") or 0
    try:
        amount = Decimal(str(amount_raw))
    except Exception:
        amount = Decimal(0)

    content = payload.get("content") or ""
    reference_code = payload.get("referenceCode") or None
    tx_dt = _parse_transaction_date(payload.get("transactionDate"))
    tx_date = tx_dt.date() if tx_dt else date.today()

    # Idempotent — nếu đã xử lý sepay_id này rồi → return luôn.
    existing = db.execute(
        select(SepayTransaction).where(SepayTransaction.sepay_id == sepay_id)
    ).scalar_one_or_none()
    if existing is not None:
        return {
            "status": "duplicate",
            "action": "skipped_idempotent",
            "sepay_id": sepay_id,
            "so_quy_id": existing.so_quy_id,
            "quote_number": existing.quote_number,
        }

    # Chỉ care tiền vào — tiền ra vẫn log để trace nhưng status='ignored'.
    if transfer_type != "in":
        txn = SepayTransaction(
            sepay_id=sepay_id,
            transaction_date=tx_dt,
            gateway=payload.get("gateway"),
            account_number=payload.get("accountNumber"),
            transfer_type=transfer_type or None,
            amount=amount,
            content=content,
            reference_code=reference_code,
            raw_payload=payload,
            status="ignored",
            note="transferType != 'in'",
        )
        db.add(txn)
        db.commit()
        return {"status": "ignored", "action": "not_incoming", "sepay_id": sepay_id}

    # Parse memo → quote_number
    qn = _extract_quote_number(content)
    quote = _find_quote_by_number(db, qn) if qn else None

    if quote is None:
        # Orphan — không tìm được quote → chờ KT xử lý
        txn = SepayTransaction(
            sepay_id=sepay_id,
            transaction_date=tx_dt,
            gateway=payload.get("gateway"),
            account_number=payload.get("accountNumber"),
            transfer_type=transfer_type,
            amount=amount,
            content=content,
            reference_code=reference_code,
            raw_payload=payload,
            quote_number=qn,
            status="orphan",
            note=(
                "Memo không parse được quote_number"
                if not qn else f"Quote '{qn}' không tồn tại trong baogia.quotes"
            ),
        )
        db.add(txn)
        db.commit()
        return {
            "status": "orphan",
            "action": "queued_for_manual_review",
            "sepay_id": sepay_id,
            "quote_number": qn,
        }

    # Matched — cộng deposit + upsert so_quy
    try:
        _apply_deposit_to_quote(db, quote, amount, tx_date)
        sq = _upsert_so_quy_sepay(
            db,
            sepay_id=sepay_id,
            amount=amount,
            tx_date=tx_date,
            quote_number=quote["quote_number"],
            content=content,
            reference_code=reference_code,
        )
        txn = SepayTransaction(
            sepay_id=sepay_id,
            transaction_date=tx_dt,
            gateway=payload.get("gateway"),
            account_number=payload.get("accountNumber"),
            transfer_type=transfer_type,
            amount=amount,
            content=content,
            reference_code=reference_code,
            raw_payload=payload,
            quote_number=quote["quote_number"],
            so_quy_id=sq.id,
            status="matched",
            matched_by="auto",
            matched_at=datetime.now(timezone.utc),
        )
        db.add(txn)
        db.commit()
        return {
            "status": "matched",
            "action": "so_quy_created",
            "sepay_id": sepay_id,
            "quote_number": quote["quote_number"],
            "so_quy_id": sq.id,
            "amount": str(amount),
        }
    except Exception as e:
        db.rollback()
        logger.exception("sepay_webhook match+commit fail sepay_id=%s: %s", sepay_id, e)
        # Vẫn log audit — mark orphan để KT xử lý sau, tránh mất giao dịch
        txn = SepayTransaction(
            sepay_id=sepay_id,
            transaction_date=tx_dt,
            gateway=payload.get("gateway"),
            account_number=payload.get("accountNumber"),
            transfer_type=transfer_type,
            amount=amount,
            content=content,
            reference_code=reference_code,
            raw_payload=payload,
            quote_number=quote["quote_number"] if quote else qn,
            status="orphan",
            note=f"Exception khi apply: {type(e).__name__}: {e}"[:500],
        )
        db.add(txn)
        db.commit()
        return {
            "status": "orphan",
            "action": "exception_during_apply",
            "sepay_id": sepay_id,
            "error": str(e)[:200],
        }
