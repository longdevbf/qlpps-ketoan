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
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..models import JournalEntry, JournalLine
from .tai_khoan_tien import tk_chi_tiet


# ─── Chart of Accounts (TT200 — quy ước Papasan) ─────────────────────────────

ACCOUNTS: dict[str, str] = {
    "111": "Tiền mặt tại quỹ",
    "112": "Tiền gửi ngân hàng",
    "131": "Phải thu khách hàng",
    # 2026-09-25: thêm 141 cho màn Tạm ứng (services/tam_ung.py) — trước đó
    # hệ thống chưa hạch toán tạm ứng nhân viên nên CoA không có TK này.
    "141": "Tạm ứng",
    "156": "Hàng tồn kho",
    "211": "Tài sản cố định hữu hình",
    "213": "Tài sản cố định vô hình",
    "214": "Hao mòn lũy kế TSCĐ",
    # 242/3334/3335: bút toán của màn Chi phí chờ phân bổ + Thuế TNCN/TNDN (2026-09-25)
    "242": "Chi phí chờ phân bổ",
    "311": "Vay & nợ thuê tài chính ngắn hạn",
    "331": "Phải trả người bán",
    "3334": "Thuế thu nhập doanh nghiệp",
    "3335": "Thuế thu nhập cá nhân",
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
ASSET_ACCOUNTS: set[str] = {"111", "112", "131", "141", "156", "211", "213", "242"}
EXPENSE_ACCOUNTS: set[str] = {"632", "635", "641", "642", "811", "821"}

# Số dư bên Có tăng (Nguồn vốn + Doanh thu + Hao mòn lũy kế contra-asset)
LIABILITY_EQUITY_ACCOUNTS: set[str] = {
    "214",  # contra-asset, normal balance = credit
    "311", "331", "3334", "3335", "334", "341",
    "353", "411", "414", "415", "421",
}
REVENUE_ACCOUNTS: set[str] = {"511", "711"}

_TOL = Decimal("0.01")


def danh_muc_tk(db: Session) -> dict[str, str]:
    """ACCOUNTS + TK con của từng tài khoản tiền (1111, 1121… — ketoan.tai_khoan_nh.tk_ke_toan)."""
    return {**ACCOUNTS, **tk_chi_tiet(db)}


def tk_cha_cua(code: str) -> Optional[str]:
    """TK cấp 1 chứa TK con `code` (1121 → 112); None nếu `code` là TK trong ACCOUNTS."""
    if code in ACCOUNTS:
        return None
    return next((code[:n] for n in range(len(code) - 1, 2, -1) if code[:n] in ACCOUNTS), None)


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


_DONG = Decimal("1")  # VND là số nguyên — mọi dòng bút toán làm tròn về đồng khi ghi


def _lam_tron_dong(x: Decimal) -> Decimal:
    return x.quantize(_DONG, rounding=ROUND_HALF_UP)


def _can_bang_sau_lam_tron(lines: list[dict]) -> None:
    """Làm tròn từng dòng có thể làm lệch Nợ/Có vài đồng (vd 0,5 + 0,5 = 1 → 1 + 1 = 2).
    Dồn phần lệch vào dòng lớn nhất của bên thừa để bút toán vẫn cân."""
    no = sum((ln["so_tien"] for ln in lines if ln["loai"] == "no"), Decimal(0))
    co = sum((ln["so_tien"] for ln in lines if ln["loai"] == "co"), Decimal(0))
    lech = no - co
    if not lech:
        return
    ben_thua = "no" if lech > 0 else "co"
    dong = max((ln for ln in lines if ln["loai"] == ben_thua), key=lambda ln: ln["so_tien"])
    dong["so_tien"] -= abs(lech)


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
    tk_con: Optional[dict[str, str]] = None   # nạp khi gặp TK ngoài ACCOUNTS (TK con 111x/112x)
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
        ten_tk = ACCOUNTS.get(code)
        if ten_tk is None:
            tk_con = tk_chi_tiet(db) if tk_con is None else tk_con
            ten_tk = tk_con.get(code)
        if ten_tk is None:
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
            "account_name": raw.get("account_name") or ten_tk,
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
    # Kiểm cân trên số gốc (như cũ), rồi mới làm tròn về đồng + cân lại phần lẻ.
    for ln in norm_lines:
        ln["so_tien"] = _lam_tron_dong(ln["so_tien"])
    _can_bang_sau_lam_tron(norm_lines)
    if any(ln["so_tien"] <= 0 for ln in norm_lines):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "so_tien sau làm tròn về đồng phải > 0")
    sum_no = sum((ln["so_tien"] for ln in norm_lines if ln["loai"] == "no"), Decimal(0))

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
    # Bút toán đảo lưu trạng thái 'da_huy' giống bút toán gốc: mọi tổng hợp
    # (get_balance_sheet_aggregates, chốt kỳ, P&L) chỉ đếm 'da_post', nên nếu
    # bút toán đảo là 'da_post' còn gốc là 'da_huy' thì số dư bị ĐỔI DẤU (−X)
    # thay vì về 0. Cặp gốc + đảo cùng 'da_huy' = triệt tiêu, vẫn giữ vết
    # kiểm toán (sửa 2026-09-25 khi làm màn Tạm ứng — trước đó DB chưa có
    # bút toán nào bị đảo nên không ảnh hưởng số liệu cũ).
    rev = post_journal(
        db,
        ngay=date_cls.today(),
        mo_ta=f"Đảo bút toán {je.ma_but_toan}: {je.mo_ta or ''}".strip(),
        source_type=f"reversal_of_{je.source_type or 'other'}",
        source_id=str(je.id),
        lines=reversal_lines,
        by_user=by_user,
        trang_thai="da_huy",
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


# ─── Cân đối phát sinh + Sổ cái theo TK (màn /ketoan/can-doi, /ketoan/so-cai) ─

def tinh_chat_tk(code: str) -> str:
    """Chiều số dư tự nhiên: 'no' (Tài sản, Chi phí) hoặc 'co' (Nguồn vốn, Doanh thu, 214)."""
    if code in LIABILITY_EQUITY_ACCOUNTS or code in REVENUE_ACCOUNTS:
        return "co"
    return "no"


def _chia_du(no: Decimal, co: Decimal) -> tuple[Decimal, Decimal]:
    """Luỹ kế Nợ/Có → (dư Nợ, dư Có) — chỉ một bên khác 0."""
    net = no - co
    return (net, Decimal("0")) if net >= 0 else (Decimal("0"), -net)


def _khop_tk(tk: str):
    """Điều kiện dòng thuộc TK `tk` hoặc TK chi tiết bắt đầu bằng `tk`."""
    return JournalLine.account_code.like(f"{tk}%")


def trial_balance(db: Session, tu: date_cls, den: date_cls) -> list[dict]:
    """Bảng cân đối phát sinh THẬT từ journal_line (chỉ bút toán 'da_post'):
    dư đầu kỳ (< tu), phát sinh Nợ/Có trong [tu, den], dư cuối kỳ — cho MỌI TK
    trong ACCOUNTS (kể cả 5xx-8xx chưa kết chuyển). `so_dong` = số dòng định
    khoản từ trước tới `den` (dùng làm cờ "đã phát sinh").
    TK con của tài khoản tiền (1121…) trả thêm dòng `cap`=2 kèm `tk_cha`; dòng TK cha đã gồm
    số của TK con → cộng tổng chỉ lấy `cap`=1.
    """
    truoc = JournalEntry.ngay < tu
    trong = (JournalEntry.ngay >= tu) & (JournalEntry.ngay <= den)

    def _sum(cond, loai):
        return func.coalesce(func.sum(case(
            (cond & (JournalLine.loai == loai), JournalLine.so_tien), else_=0,
        )), 0)

    rows = db.execute(
        select(
            JournalLine.account_code,
            _sum(truoc, "no"), _sum(truoc, "co"),
            _sum(trong, "no"), _sum(trong, "co"),
            func.count(JournalLine.id),
        )
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .where(JournalEntry.trang_thai == "da_post")
        .where(JournalEntry.ngay <= den)
        .group_by(JournalLine.account_code)
    ).all()
    ten = danh_muc_tk(db)
    zero = (Decimal("0"),) * 4 + (0,)
    so = {code: [_to_dec(v) if i < 4 else int(v) for i, v in enumerate(zero)] for code in set(ten)}
    for r in rows:
        so[r[0]] = [_to_dec(v) if i < 4 else int(v) for i, v in enumerate(r[1:])]
    # TK con (1121…) cộng dồn lên TK cha (112) — dòng cha = tổng cả nhóm, dòng con cap=2 chỉ để xem chi tiết.
    for code, v in list(so.items()):
        cha = tk_cha_cua(code)
        if cha:
            so.setdefault(cha, list(zero))
            so[cha] = [a + b for a, b in zip(so[cha], v)]

    out: list[dict] = []
    for code in sorted(so):
        dau_no_lk, dau_co_lk, ps_no, ps_co, so_dong = so[code]
        dau_no, dau_co = _chia_du(dau_no_lk, dau_co_lk)
        cuoi_no, cuoi_co = _chia_du(dau_no_lk + ps_no, dau_co_lk + ps_co)
        cha = tk_cha_cua(code)
        out.append({
            "ma": code, "ten": ten.get(code, code), "tinh_chat": tinh_chat_tk(cha or code),
            "cap": 2 if cha else 1, "tk_cha": cha,
            "dau_no": dau_no, "dau_co": dau_co, "ps_no": ps_no, "ps_co": ps_co,
            "cuoi_no": cuoi_no, "cuoi_co": cuoi_co, "so_dong": so_dong,
        })
    return out


def ledger(db: Session, tk: str, tu: date_cls, den: date_cls) -> dict:
    """Sổ cái TK `tk` (gồm TK chi tiết cùng đầu số) trong [tu, den], chỉ 'da_post'.
    Dư luỹ kế tính theo thời gian (ngày, id bút toán) ở máy chủ; TK đối ứng = các
    TK khác trong cùng bút toán.
    """
    base = (
        select(JournalLine.loai, func.coalesce(func.sum(JournalLine.so_tien), 0))
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .where(JournalEntry.trang_thai == "da_post", JournalEntry.ngay < tu, _khop_tk(tk))
        .group_by(JournalLine.loai)
    )
    dau = {loai: _to_dec(v) for loai, v in db.execute(base).all()}
    lk_no, lk_co = dau.get("no", Decimal("0")), dau.get("co", Decimal("0"))
    so_du_dau = _chia_du(lk_no, lk_co)

    rows = db.execute(
        select(JournalEntry, JournalLine)
        .join(JournalLine, JournalEntry.id == JournalLine.journal_id)
        .where(JournalEntry.trang_thai == "da_post")
        .where(JournalEntry.ngay >= tu, JournalEntry.ngay <= den, _khop_tk(tk))
        .order_by(JournalEntry.ngay, JournalEntry.id, JournalLine.id)
    ).all()

    je_ids = {je.id for je, _ in rows}
    doi_ung: dict[int, list[str]] = {}
    if je_ids:
        for jid, code in db.execute(
            select(JournalLine.journal_id, JournalLine.account_code)
            .where(JournalLine.journal_id.in_(je_ids), ~_khop_tk(tk))
            .order_by(JournalLine.id)
        ).all():
            ds = doi_ung.setdefault(jid, [])
            if code not in ds:
                ds.append(code)

    dong: list[dict] = []
    ps_no = ps_co = Decimal("0")
    for je, ln in rows:
        no = ln.so_tien if ln.loai == "no" else Decimal("0")
        co = ln.so_tien if ln.loai == "co" else Decimal("0")
        ps_no += no
        ps_co += co
        du_no, du_co = _chia_du(lk_no + ps_no, lk_co + ps_co)
        dong.append({
            "entry_id": je.id, "ngay": je.ngay, "so_ct": je.ma_but_toan,
            "dien_giai": ln.ghi_chu or je.mo_ta, "source_type": je.source_type,
            "tk": ln.account_code, "tk_doi_ung": ", ".join(doi_ung.get(je.id, [])),
            "nghiep_vu": tom_tat_dinh_khoan(je)["nghiep_vu"],
            "ref_table": ln.ref_table, "ref_id": ln.ref_id,
            "no": no, "co": co, "du_no": du_no, "du_co": du_co,
        })
    so_du_cuoi = _chia_du(lk_no + ps_no, lk_co + ps_co)
    return {
        "tk": tk, "ten": danh_muc_tk(db).get(tk, tk), "tinh_chat": tinh_chat_tk(tk_cha_cua(tk) or tk),
        "tu_ngay": tu, "den_ngay": den,
        "so_du_dau": {"no": so_du_dau[0], "co": so_du_dau[1]},
        "phat_sinh": {"no": ps_no, "co": ps_co},
        "so_du_cuoi": {"no": so_du_cuoi[0], "co": so_du_cuoi[1]},
        "dong": dong,
    }


# ─── Loại nghiệp vụ của bút toán (cột "Loại" + lọc Thu / Chi trên Sổ kế toán) ─

_TK_TIEN = ("111", "112")
_TK_DOANH_THU = ("511", "711")
_TK_THUE = ("333", "821")
_TK_CONG_NO = ("131", "141", "331")

# Thứ tự = thứ tự hiện trong ô lọc.
NGHIEP_VU: dict[str, str] = {
    "thu": "Thu tiền",
    "chi": "Chi tiền",
    "chuyen_tien": "Chuyển tiền nội bộ",
    "doanh_thu": "Ghi nhận doanh thu",
    "gia_von": "Giá vốn",
    "khau_hao": "Khấu hao",
    "phan_bo": "Phân bổ chi phí",
    "thue": "Thuế",
    "cong_no": "Công nợ",
    "dao": "Đảo bút toán",
    "khac": "Khác",
}


def _co_dau(ds: set[str], dau: tuple[str, ...]) -> bool:
    return any(tk.startswith(dau) for tk in ds)


def phan_loai_nghiep_vu(tk_no: Iterable[str], tk_co: Iterable[str], source_type: Optional[str] = None) -> str:
    """Suy loại nghiệp vụ từ định khoản (không phụ thuộc source_type, trừ bút toán đảo):
    tiền (111x/112x) ghi Nợ → Thu, ghi Có → Chi, cả hai → Chuyển tiền; không qua tiền thì theo TK đặc trưng."""
    if (source_type or "").startswith("reversal_of_"):
        return "dao"
    no, co = set(tk_no), set(tk_co)
    if _co_dau(no, _TK_TIEN) and _co_dau(co, _TK_TIEN):
        return "chuyen_tien"
    if _co_dau(no, _TK_TIEN):
        return "thu"
    if _co_dau(co, _TK_TIEN):
        return "chi"
    if _co_dau(co, _TK_DOANH_THU):
        return "doanh_thu"
    if _co_dau(no, ("632",)):
        return "gia_von"
    if _co_dau(co, ("214",)):
        return "khau_hao"
    if _co_dau(co, ("242",)):
        return "phan_bo"
    if _co_dau(no | co, _TK_THUE):
        return "thue"
    if _co_dau(no | co, _TK_CONG_NO):
        return "cong_no"
    return "khac"


def tom_tat_dinh_khoan(je: JournalEntry) -> dict:
    """{nghiep_vu, tk_no, tk_co} của một bút toán (je.lines nạp sẵn kiểu selectin — không thêm truy vấn)."""
    tk_no = sorted({ln.account_code for ln in je.lines if ln.loai == "no"})
    tk_co = sorted({ln.account_code for ln in je.lines if ln.loai == "co"})
    return {"nghiep_vu": phan_loai_nghiep_vu(tk_no, tk_co, je.source_type), "tk_no": tk_no, "tk_co": tk_co}


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
