"""Phase 2 — Journal posting service (double-entry bookkeeping).

API chính:
  - ACCOUNTS                                  — chart of accounts (TT200 chuẩn Papasan)
  - next_ma_but_toan(db)                      — sinh BT-YYYY-NNNN
  - post_journal(db, ngay, mo_ta, source_type, source_id, lines, by_user)
  - void_journal(db, je_id, by_user)          — đảo bút toán
  - get_balance_sheet_aggregates(db, den_ngay) → dict[account_code -> net]

Quy ước nợ/có:
  - Tài sản (TS, 1xx-2xx): SỐ DƯ NỢ. net = SUM(no) - SUM(co).
  - Nguồn vốn (NV, 3xx-4xx): SỐ DƯ CÓ. net = SUM(co) - SUM(no).
  - Doanh thu (5xx, 7xx): SỐ DƯ CÓ.
  - Chi phí (6xx, 8xx): SỐ DƯ NỢ.

`get_balance_sheet_aggregates` chỉ trả về net cho các tài khoản TS + NV
(loại trừ 5xx/6xx/7xx/8xx — đã reflect vào 421 LN giữ lại sau khi chốt kỳ).
"""
from datetime import date as date_cls, datetime
from decimal import Decimal
from typing import Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..models import JournalEntry, JournalLine


# ─── Chart of Accounts (TT200 — quy ước Papasan) ─────────────────────────────

ACCOUNTS: dict[str, str] = {
    "111": "Tiền mặt tại quỹ",
    "112": "Tiền gửi ngân hàng",
    "131": "Phải thu khách hàng",
    "156": "Hàng tồn kho",
    "211": "Tài sản cố định hữu hình",
    "213": "Tài sản cố định vô hình",
    "214": "Hao mòn lũy kế TSCĐ",
    "311": "Vay & nợ thuê tài chính ngắn hạn",
    "331": "Phải trả người bán",
    "334": "Phải trả người lao động",
    "341": "Vay & nợ thuê tài chính dài hạn",
    "353": "Quỹ khen thưởng phúc lợi",
    "411": "Vốn góp của chủ sở hữu",
    "414": "Quỹ đầu tư phát triển",
    "415": "Quỹ dự phòng tài chính",
    "421": "Lợi nhuận sau thuế chưa phân phối",
    "511": "Doanh thu bán hàng",
    "632": "Giá vốn hàng bán",
    "635": "Chi phí tài chính",
    "641": "Chi phí bán hàng",
    "642": "Chi phí quản lý DN",
    "711": "Thu nhập khác",
    "811": "Chi phí khác",
    "821": "Chi phí thuế TNDN",
}

# Số dư bên Nợ tăng (Tài sản + Chi phí)
# 211/213 là TSCĐ HH/VH; 214 là contra-asset (hao mòn) — số dư bên CÓ
# (xem LIABILITY_EQUITY_ACCOUNTS) → BS dùng (211+213) - 214 = TSCĐ ròng.
ASSET_ACCOUNTS: set[str] = {"111", "112", "131", "156", "211", "213"}
EXPENSE_ACCOUNTS: set[str] = {"632", "635", "641", "642", "811", "821"}

# Số dư bên Có tăng (Nguồn vốn + Doanh thu + Hao mòn lũy kế contra-asset)
LIABILITY_EQUITY_ACCOUNTS: set[str] = {
    "214",  # contra-asset, normal balance = credit
    "311", "331", "334", "341",
    "353", "411", "414", "415", "421",
}
REVENUE_ACCOUNTS: set[str] = {"511", "711"}

_TOL = Decimal("0.01")


# ─── ID generator BT-YYYY-NNNN ───────────────────────────────────────────────

def next_ma_but_toan(db: Session) -> str:
    """Sinh mã bút toán mới: BT-YYYY-NNNN (NNNN auto-increment trong năm)."""
    year = datetime.now().year
    prefix = f"BT-{year}-"
    rows = db.execute(
        select(JournalEntry.ma_but_toan).where(
            JournalEntry.ma_but_toan.like(f"{prefix}%")
        )
    ).all()
    max_seq = 0
    for (m,) in rows:
        try:
            seq = int(m[len(prefix):])
            if seq > max_seq:
                max_seq = seq
        except (ValueError, TypeError):
            continue
    return f"{prefix}{max_seq + 1:04d}"


# ─── post_journal ────────────────────────────────────────────────────────────

def _to_dec(x) -> Decimal:
    if x is None:
        return Decimal("0")
    return x if isinstance(x, Decimal) else Decimal(str(x))


def post_journal(
    db: Session,
    *,
    ngay: date_cls,
    mo_ta: Optional[str],
    source_type: Optional[str],
    source_id: Optional[str],
    lines: Iterable[dict],
    by_user: Optional[str],
    trang_thai: str = "da_post",
    flush: bool = True,
) -> JournalEntry:
    """Insert 1 bút toán + các dòng nợ/có. Validate nợ = có (tolerance 0.01).

    `lines` là list dict với key: loai, account_code, [account_name],
        [ref_table], [ref_id], so_tien, [ghi_chu].
    """
    line_list = list(lines)
    if len(line_list) < 2:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Bút toán phải có ít nhất 2 dòng (1 nợ + 1 có)",
        )

    has_no = False
    has_co = False
    sum_no = Decimal("0")
    sum_co = Decimal("0")
    norm_lines: list[dict] = []
    for raw in line_list:
        loai = (raw.get("loai") or "").strip().lower()
        if loai not in ("no", "co"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"loai phải là 'no' hoặc 'co' (nhận {raw.get('loai')!r})",
            )
        code = str(raw.get("account_code") or "").strip()
        if code not in ACCOUNTS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"account_code {code!r} không thuộc Chart of Accounts",
            )
        amount = _to_dec(raw.get("so_tien"))
        if amount <= 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"so_tien phải > 0 (nhận {amount})",
            )
        if loai == "no":
            has_no = True
            sum_no += amount
        else:
            has_co = True
            sum_co += amount
        norm_lines.append({
            "loai": loai,
            "account_code": code,
            "account_name": raw.get("account_name") or ACCOUNTS[code],
            "ref_table": raw.get("ref_table"),
            "ref_id": raw.get("ref_id"),
            "so_tien": amount,
            "ghi_chu": raw.get("ghi_chu"),
        })

    if not (has_no and has_co):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Bút toán phải có ít nhất 1 dòng 'no' và 1 dòng 'co'",
        )
    if abs(sum_no - sum_co) > _TOL:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Bút toán mất cân: SUM(no)={sum_no}, SUM(co)={sum_co}",
        )

    je = JournalEntry(
        ma_but_toan=next_ma_but_toan(db),
        ngay=ngay,
        mo_ta=mo_ta,
        source_type=source_type,
        source_id=str(source_id) if source_id is not None else None,
        tong_tien=sum_no,
        trang_thai=trang_thai,
        created_by=by_user,
    )
    db.add(je)
    db.flush()

    for ln in norm_lines:
        db.add(JournalLine(
            journal_id=je.id,
            loai=ln["loai"],
            account_code=ln["account_code"],
            account_name=ln["account_name"],
            ref_table=ln["ref_table"],
            ref_id=ln["ref_id"],
            so_tien=ln["so_tien"],
            ghi_chu=ln["ghi_chu"],
        ))

    if flush:
        db.flush()
    return je


# ─── void_journal — sinh bút toán đảo ────────────────────────────────────────

def void_journal(
    db: Session, *, je_id: int, by_user: Optional[str],
) -> JournalEntry:
    """Đảo bút toán — đổi trang_thai='da_huy' + tạo bút toán đảo (nợ↔có)."""
    je = db.get(JournalEntry, je_id)
    if not je:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bút toán không tồn tại")
    if je.trang_thai == "da_huy":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Bút toán đã ở trạng thái da_huy",
        )

    # Lấy các dòng gốc (lazy='selectin')
    orig_lines = list(je.lines)
    if not orig_lines:
        # Refetch nếu chưa load
        orig_lines = db.execute(
            select(JournalLine).where(JournalLine.journal_id == je.id)
        ).scalars().all()

    reversal_lines = [
        {
            "loai": "co" if ln.loai == "no" else "no",
            "account_code": ln.account_code,
            "account_name": ln.account_name,
            "ref_table": ln.ref_table,
            "ref_id": ln.ref_id,
            "so_tien": ln.so_tien,
            "ghi_chu": f"Đảo {je.ma_but_toan}",
        }
        for ln in orig_lines
    ]
    rev = post_journal(
        db,
        ngay=date_cls.today(),
        mo_ta=f"Đảo bút toán {je.ma_but_toan}: {je.mo_ta or ''}".strip(),
        source_type=f"reversal_of_{je.source_type or 'other'}",
        source_id=str(je.id),
        lines=reversal_lines,
        by_user=by_user,
    )

    je.trang_thai = "da_huy"
    db.flush()
    return rev


# ─── Aggregate utility cho Balance Sheet ─────────────────────────────────────

def get_balance_sheet_aggregates(
    db: Session, den_ngay: date_cls,
) -> dict[str, float]:
    """Trả dict {account_code: net_balance} từ journal_line ≤ den_ngay.

    - Asset accounts (111/112/131/156/211): net = SUM(no) - SUM(co).
    - Liability/Equity accounts (311/331/334/341/353/411/414/415/421):
        net = SUM(co) - SUM(no).
    - 5xx/6xx/7xx/8xx tạm BỎ (đã consolidate vào 421 sau chốt kỳ).
      Tuy nhiên nếu chưa chốt kỳ và muốn xem net P&L, có thể cộng riêng:
        revenue (511/711): net = SUM(co) - SUM(no)
        expense (632/635/641/642/811/821): net = SUM(no) - SUM(co)
      → trả luôn để caller có quyền sử dụng.
    Chỉ tính các bút toán trang_thai='da_post'.
    """
    rows = db.execute(
        select(
            JournalLine.account_code,
            func.coalesce(
                func.sum(case(
                    (JournalLine.loai == "no", JournalLine.so_tien),
                    else_=0,
                )), 0,
            ).label("sum_no"),
            func.coalesce(
                func.sum(case(
                    (JournalLine.loai == "co", JournalLine.so_tien),
                    else_=0,
                )), 0,
            ).label("sum_co"),
        )
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .where(JournalEntry.ngay <= den_ngay)
        .where(JournalEntry.trang_thai == "da_post")
        .group_by(JournalLine.account_code)
    ).all()

    out: dict[str, float] = {}
    for code, sum_no, sum_co in rows:
        sn = float(sum_no or 0)
        sc = float(sum_co or 0)
        if code in ASSET_ACCOUNTS or code in EXPENSE_ACCOUNTS:
            out[code] = sn - sc
        elif (
            code in LIABILITY_EQUITY_ACCOUNTS
            or code in REVENUE_ACCOUNTS
        ):
            out[code] = sc - sn
        else:
            # Lạ — vẫn trả về theo nợ-có thô để debug
            out[code] = sn - sc
    return out


# ─── Helper map quỹ DN → account_code ────────────────────────────────────────

def map_quy_to_account(ten_quy: Optional[str]) -> str:
    """Map tên quỹ DN sang account_code TT200.

    - 'Quỹ đầu tư phát triển'        → 414
    - 'Quỹ dự phòng tài chính'       → 415
    - 'Quỹ khen thưởng phúc lợi'     → 353
    - other                          → 414 (default)
    """
    if not ten_quy:
        return "414"
    t = ten_quy.strip().lower()
    if "khen thưởng" in t or "phúc lợi" in t or "phuc loi" in t:
        return "353"
    if "dự phòng" in t or "du phong" in t:
        return "415"
    if "đầu tư" in t or "dau tu" in t or "phát triển" in t or "phat trien" in t:
        return "414"
    return "414"
