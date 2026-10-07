"""Chi tiết từng dòng Cân đối kế toán — "con số này ở đâu ra".

Khác KQKD và LCTT ở một điểm quan trọng
───────────────────────────────────────
Cân đối chạy chế độ `source='auto'`: mỗi dòng lấy `max(sổ cái, số legacy)` để tránh
sổ cái chưa đủ bút toán thì đè số 0 lên dữ liệu cũ. Nghĩa là số hiển thị có thể đến
từ MỘT TRONG HAI nguồn, tuỳ dòng và tuỳ kỳ.

Vì thế `tong` ở đây KHÔNG tự tính lại mà đọc thẳng từ kết quả `bao_cao_can_doi()` —
đúng con số người dùng đang nhìn, không có đường nào lệch. Danh sách dòng lấy từ
nguồn legacy (nơi có chứng từ để xem); nếu cộng lại không bằng `tong` thì ghi rõ
cảnh báo chứ không im lặng — chênh đó chính là dấu hiệu sổ cái và sổ legacy đang
nói khác nhau, là thứ cần biết.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

SO_DONG_MAC_DINH = 50
SO_DONG_TOI_DA = 200

_C_TIEN = {"key": "so_tien", "nhan": "Số tiền", "kieu": "tien"}
_C_NGAY = {"key": "ngay", "nhan": "Ngày", "kieu": "ngay"}

# khoá → (đường dẫn trong kết quả bao_cao_can_doi, nhãn, nguồn, giải thích, SQL, cột)
KHOAN: dict[str, dict[str, Any]] = {
    "tai_san.tien_va_td.tk_ngan_hang": {
        "duong_dan": ("tai_san", "tien_va_td", "tk_ngan_hang"),
        "nhan": "Tiền gửi ngân hàng",
        "nguon": "ketoan.tai_khoan_nh + ketoan.so_quy",
        "giai_thich": ("Số dư đầu kỳ đã khai của từng tài khoản, cộng mọi giao dịch từ mốc "
                       "đó đến ngày xem."),
        "sql": """
            WITH neo AS (
                SELECT DISTINCT ON (s.tai_khoan_id) s.tai_khoan_id, s.thang, s.so_du
                FROM ketoan.so_du_dau_ky s
                WHERE s.thang <= DATE_TRUNC('month', CAST(:den AS date))::date
                ORDER BY s.tai_khoan_id, s.thang DESC
            )
            SELECT NULL::int AS id, neo.thang AS ngay, 'so_du_dau' AS loai, tk.ten_tk,
                   'Số dư đầu kỳ đã khai' AS noi_dung, '' AS lien_quan, neo.so_du AS so_tien
            FROM ketoan.tai_khoan_nh tk JOIN neo ON neo.tai_khoan_id = tk.id
            WHERE tk.active IS TRUE AND tk.loai = 'ngan_hang'
            UNION ALL
            SELECT sq.id, sq.ngay, sq.loai, sq.tai_khoan,
                   COALESCE(sq.noi_dung,''), COALESCE(sq.lien_quan,''),
                   CASE sq.loai WHEN 'thu' THEN sq.so_tien ELSE -sq.so_tien END
            FROM ketoan.so_quy sq
            JOIN ketoan.tai_khoan_nh tk ON tk.ten_tk = sq.tai_khoan
            LEFT JOIN neo ON neo.tai_khoan_id = tk.id
            WHERE tk.active IS TRUE AND tk.loai = 'ngan_hang'
              AND sq.ngay <= :den AND sq.ngay >= COALESCE(neo.thang, DATE '1900-01-01')
            ORDER BY 2 DESC, 1 DESC
        """,
        "cot": [{"key": "ngay", "nhan": "Ngày", "kieu": "ngay"},
                {"key": "ten_tk", "nhan": "Tài khoản"}, {"key": "loai", "nhan": "Loại"},
                {"key": "noi_dung", "nhan": "Nội dung"}, _C_TIEN],
    },
    "tai_san.tien_va_td.tien_mat_so_quy": {
        "duong_dan": ("tai_san", "tien_va_td", "tien_mat_so_quy"),
        "nhan": "Tiền mặt tại quỹ",
        "nguon": "ketoan.so_quy · tài khoản tiền mặt",
        "giai_thich": ("Số dư đầu kỳ đã khai, cộng mọi phiếu thu/chi tiền mặt từ mốc đó "
                       "đến ngày xem."),
        "sql": """
            WITH neo AS (
                SELECT DISTINCT ON (s.tai_khoan_id) s.tai_khoan_id, s.thang, s.so_du
                FROM ketoan.so_du_dau_ky s
                WHERE s.thang <= DATE_TRUNC('month', CAST(:den AS date))::date
                ORDER BY s.tai_khoan_id, s.thang DESC
            )
            SELECT NULL::int AS id, neo.thang AS ngay, 'so_du_dau' AS loai, tk.ten_tk,
                   'Số dư đầu kỳ đã khai' AS noi_dung, '' AS lien_quan, neo.so_du AS so_tien
            FROM ketoan.tai_khoan_nh tk JOIN neo ON neo.tai_khoan_id = tk.id
            WHERE tk.active IS TRUE AND tk.loai = 'tien_mat'
            UNION ALL
            SELECT sq.id, sq.ngay, sq.loai, sq.tai_khoan,
                   COALESCE(sq.noi_dung,''), COALESCE(sq.lien_quan,''),
                   CASE sq.loai WHEN 'thu' THEN sq.so_tien ELSE -sq.so_tien END
            FROM ketoan.so_quy sq
            JOIN ketoan.tai_khoan_nh tk ON tk.ten_tk = sq.tai_khoan
            LEFT JOIN neo ON neo.tai_khoan_id = tk.id
            WHERE tk.active IS TRUE AND tk.loai = 'tien_mat'
              AND sq.ngay <= :den AND sq.ngay >= COALESCE(neo.thang, DATE '1900-01-01')
            ORDER BY 2 DESC, 1 DESC
        """,
        "cot": [_C_NGAY, {"key": "loai", "nhan": "Loại"}, {"key": "noi_dung", "nhan": "Nội dung"},
                {"key": "lien_quan", "nhan": "Liên quan"}, _C_TIEN],
    },
    "tai_san.phai_thu": {
        "duong_dan": ("tai_san", "phai_thu"),
        "nhan": "Các khoản phải thu",
        "nguon": "ketoan.cong_no (phải thu) + tạm ứng TK 141",
        "giai_thich": ("Công nợ khách hàng chưa thu hết tính đến ngày xem, CỘNG số dư tạm ứng "
                       "TK 141 — mẫu B01-DN xếp tạm ứng vào phải thu ngắn hạn."),
        "sql": """
            SELECT cn.id::text, cn.ngay, cn.doi_tac, cn.so_tien AS phai_thu, cn.da_tra AS da_thu,
                   cn.con_lai AS so_tien, COALESCE(cn.ma_don,'') AS ma_don,
                   COALESCE(cn.ghi_chu,'') AS ghi_chu
            FROM ketoan.cong_no cn
            WHERE cn.loai = 'phai_thu' AND cn.ngay <= :den AND cn.trang_thai <> 'da_tra'
            UNION ALL
            SELECT jl.id::text, je.ngay, COALESCE(jl.doi_tuong_ten, 'Tạm ứng') AS doi_tac,
                   0 AS phai_thu, 0 AS da_thu,
                   CASE jl.loai WHEN 'no' THEN jl.so_tien ELSE -jl.so_tien END AS so_tien,
                   '' AS ma_don, 'Tạm ứng TK 141 — mẫu B01-DN gộp vào phải thu ngắn hạn' AS ghi_chu
            FROM ketoan.journal_line jl JOIN ketoan.journal_entry je ON je.id = jl.journal_id
            WHERE jl.account_code = '141' AND je.trang_thai = 'da_post' AND je.ngay <= :den
            ORDER BY 6 DESC
        """,
        "cot": [_C_NGAY, {"key": "doi_tac", "nhan": "Khách hàng"},
                {"key": "ma_don", "nhan": "Mã đơn"},
                {"key": "phai_thu", "nhan": "Phải thu", "kieu": "tien"},
                {"key": "da_thu", "nhan": "Đã thu", "kieu": "tien"}, _C_TIEN],
    },
    "tai_san.tam_ung": {
        "duong_dan": ("tai_san", "tam_ung"),
        "nhan": "Tạm ứng (TK 141)",
        "nguon": "ketoan.journal_line · TK 141",
        "giai_thich": "Bút toán tạm ứng đã post, chưa hoàn.",
        "sql": """
            SELECT jl.id, je.ngay, je.ma_but_toan, COALESCE(je.mo_ta,'') AS mo_ta,
                   COALESCE(jl.doi_tuong_ten,'') AS doi_tuong_ten,
                   CASE jl.loai WHEN 'no' THEN jl.so_tien ELSE -jl.so_tien END AS so_tien
            FROM ketoan.journal_line jl JOIN ketoan.journal_entry je ON je.id = jl.journal_id
            WHERE jl.account_code = '141' AND je.trang_thai = 'da_post' AND je.ngay <= :den
            ORDER BY je.ngay DESC, jl.id DESC
        """,
        "cot": [_C_NGAY, {"key": "ma_but_toan", "nhan": "Bút toán"},
                {"key": "doi_tuong_ten", "nhan": "Người tạm ứng"},
                {"key": "mo_ta", "nhan": "Diễn giải"}, _C_TIEN],
    },
    "tai_san.hang_ton_kho": {
        "duong_dan": ("tai_san", "hang_ton_kho"),
        "nhan": "Hàng tồn kho",
        "nguon": "ketoan.inventory_movement",
        "giai_thich": "Nhập trừ xuất của sổ kho kế toán đến ngày xem.",
        "sql": """
            SELECT im.id, im.ngay, im.loai, im.so_luong, COALESCE(im.source_app,'') AS source_app,
                   COALESCE(p.ten_sp, '') AS ten_sp, COALESCE(im.ghi_chu,'') AS ghi_chu,
                   CASE im.loai WHEN 'nhap' THEN im.thanh_tien
                                WHEN 'xuat' THEN -im.thanh_tien
                                ELSE im.thanh_tien END AS so_tien
            FROM ketoan.inventory_movement im
            LEFT JOIN ketoan.product p ON p.id = im.product_id
            WHERE im.ngay <= :den
            ORDER BY im.ngay DESC, im.id DESC
        """,
        "cot": [_C_NGAY, {"key": "loai", "nhan": "Loại"}, {"key": "ten_sp", "nhan": "Sản phẩm"},
                {"key": "so_luong", "nhan": "Số lượng"},
                {"key": "source_app", "nhan": "Nguồn"}, _C_TIEN],
    },
    "tai_san.tscd_nguyen_gia": {
        "duong_dan": ("tai_san", "tscd_nguyen_gia"),
        "nhan": "Nguyên giá tài sản cố định",
        "nguon": "ketoan.tai_san_co_dinh",
        "giai_thich": "Tài sản đã đưa vào sử dụng và chưa thanh lý tại ngày xem.",
        "sql": """
            SELECT id, ma_tscd, ten_tscd, bo_phan, ngay_su_dung AS ngay, so_thang_kh,
                   nguyen_gia AS so_tien
            FROM ketoan.tai_san_co_dinh
            WHERE ngay_su_dung <= :den
              AND (ngay_thanh_ly IS NULL OR ngay_thanh_ly > :den)
            ORDER BY nguyen_gia DESC
        """,
        "cot": [{"key": "ma_tscd", "nhan": "Mã TSCĐ"}, {"key": "ten_tscd", "nhan": "Tài sản"},
                {"key": "bo_phan", "nhan": "Bộ phận"}, _C_NGAY,
                {"key": "so_thang_kh", "nhan": "Số tháng KH"}, _C_TIEN],
    },
    "tai_san.tscd_hao_mon_luy_ke": {
        "duong_dan": ("tai_san", "tscd_hao_mon_luy_ke"),
        "nhan": "Hao mòn luỹ kế",
        "nguon": "ketoan.khau_hao_log",
        "giai_thich": "Toàn bộ bút toán khấu hao đã ghi đến ngày xem.",
        "sql": """
            SELECT kh.id, kh.thang, ts.ma_tscd, ts.ten_tscd, ts.bo_phan,
                   kh.so_tien, kh.hao_mon_luy_ke_sau
            FROM ketoan.khau_hao_log kh JOIN ketoan.tai_san_co_dinh ts ON ts.id = kh.tscd_id
            WHERE kh.thang <= :thang_den
            ORDER BY kh.thang DESC, kh.id DESC
        """,
        "cot": [{"key": "thang", "nhan": "Tháng"}, {"key": "ma_tscd", "nhan": "Mã TSCĐ"},
                {"key": "ten_tscd", "nhan": "Tài sản"}, {"key": "bo_phan", "nhan": "Bộ phận"},
                _C_TIEN],
    },
    "nguon_von.no_phai_tra.phai_tra_ncc": {
        "duong_dan": ("nguon_von", "no_phai_tra", "phai_tra_ncc"),
        "nhan": "Phải trả người bán",
        "nguon": "ketoan.v_cong_no_phai_tra_phan_loai",
        "giai_thich": "Công nợ nhà cung cấp còn phải trả, nhóm 'nợ thực' và 'cần kiểm'.",
        "sql": """
            SELECT v.khoa_ncc, v.nhom_no, v.loai_dong, COUNT(*) AS so_dong_gop,
                   SUM(v.con_lai) AS so_tien
            FROM ketoan.v_cong_no_phai_tra_phan_loai v
            JOIN ketoan.cong_no cn ON cn.id = v.id
            WHERE v.nhom_no <> 'du_kien'
              AND cn.loai = 'phai_tra' AND cn.ngay <= :den AND cn.trang_thai <> 'da_tra'
            GROUP BY v.khoa_ncc, v.nhom_no, v.loai_dong
            ORDER BY SUM(v.con_lai) DESC
        """,
        "cot": [{"key": "khoa_ncc", "nhan": "Nhà cung cấp"}, {"key": "nhom_no", "nhan": "Nhóm nợ"},
                {"key": "loai_dong", "nhan": "Loại dòng"},
                {"key": "so_dong_gop", "nhan": "Số dòng"}, _C_TIEN],
    },
    "nguon_von.no_phai_tra.phai_tra_nv": {
        "duong_dan": ("nguon_von", "no_phai_tra", "phai_tra_nv"),
        "nhan": "Phải trả người lao động",
        "nguon": "ketoan.journal_line · TK 334",
        "giai_thich": ("Bút toán lương còn phải trả. Chưa có bút toán 334 nào nên dòng này "
                       "đang bằng 0 — lương đang được ghi thẳng vào chi phí, không qua 334."),
        "sql": """
            SELECT jl.id::text, je.ngay, je.ma_but_toan, COALESCE(je.mo_ta,'') AS mo_ta,
                   CASE jl.loai WHEN 'co' THEN jl.so_tien ELSE -jl.so_tien END AS so_tien
            FROM ketoan.journal_line jl JOIN ketoan.journal_entry je ON je.id = jl.journal_id
            WHERE jl.account_code = '334' AND je.trang_thai = 'da_post' AND je.ngay <= :den
            ORDER BY je.ngay DESC, jl.id DESC
        """,
        "cot": [_C_NGAY, {"key": "ma_but_toan", "nhan": "Bút toán"},
                {"key": "mo_ta", "nhan": "Diễn giải"}, _C_TIEN],
    },
    "nguon_von.no_phai_tra.vay_ngan_han": {
        "duong_dan": ("nguon_von", "no_phai_tra", "vay_ngan_han"),
        "nhan": "Vay và nợ thuê tài chính ngắn hạn",
        "nguon": "ketoan.khoan_vay",
        "giai_thich": "Các khoản vay đang còn dư nợ, kỳ hạn từ 12 tháng trở xuống.",
        "sql": """
            SELECT v.id, v.ma_khoan, v.nguon_vay, v.loai_vay, v.ngay_vay AS ngay,
                   v.ky_han_thang, v.status,
                   v.so_tien_vay - COALESCE((SELECT SUM(g.so_tien)
                       FROM ketoan.khoan_vay_giao_dich g
                       WHERE g.khoan_vay_id = v.id AND g.loai = 'tra_goc'), 0) AS so_tien
            FROM ketoan.khoan_vay v
            WHERE v.status = 'dang_vay' AND COALESCE(v.ky_han_thang, 0) <= 12
              AND v.ngay_vay <= :den
            ORDER BY so_tien DESC
        """,
        "cot": [{"key": "ma_khoan", "nhan": "Mã khoản vay"}, {"key": "nguon_vay", "nhan": "Nguồn vay"},
                _C_NGAY, {"key": "ky_han_thang", "nhan": "Kỳ hạn (tháng)"}, _C_TIEN],
    },
    "nguon_von.no_phai_tra.vay_dai_han": {
        "duong_dan": ("nguon_von", "no_phai_tra", "vay_dai_han"),
        "nhan": "Vay và nợ thuê tài chính dài hạn",
        "nguon": "ketoan.khoan_vay",
        "giai_thich": "Các khoản vay đang còn dư nợ, kỳ hạn trên 12 tháng.",
        "sql": """
            SELECT v.id, v.ma_khoan, v.nguon_vay, v.loai_vay, v.ngay_vay AS ngay,
                   v.ky_han_thang, v.status,
                   v.so_tien_vay - COALESCE((SELECT SUM(g.so_tien)
                       FROM ketoan.khoan_vay_giao_dich g
                       WHERE g.khoan_vay_id = v.id AND g.loai = 'tra_goc'), 0) AS so_tien
            FROM ketoan.khoan_vay v
            WHERE v.status = 'dang_vay' AND COALESCE(v.ky_han_thang, 0) > 12
              AND v.ngay_vay <= :den
            ORDER BY so_tien DESC
        """,
        "cot": [{"key": "ma_khoan", "nhan": "Mã khoản vay"}, {"key": "nguon_vay", "nhan": "Nguồn vay"},
                _C_NGAY, {"key": "ky_han_thang", "nhan": "Kỳ hạn (tháng)"}, _C_TIEN],
    },
    "nguon_von.von_csh.von_gop": {
        "duong_dan": ("nguon_von", "von_csh", "von_gop"),
        "nhan": "Vốn góp của chủ sở hữu",
        "nguon": "ketoan.von_chu_so_huu",
        "giai_thich": "Các lần góp vốn trừ các lần rút vốn, đến ngày xem.",
        "sql": """
            SELECT id, ngay, loai_giao_dich, COALESCE(chu_so_huu,'') AS chu_so_huu,
                   COALESCE(ghi_chu,'') AS ghi_chu,
                   CASE loai_giao_dich WHEN 'gop_von' THEN so_tien
                                       WHEN 'rut_von' THEN -so_tien ELSE 0 END AS so_tien
            FROM ketoan.von_chu_so_huu WHERE ngay <= :den
            ORDER BY ngay DESC, id DESC
        """,
        "cot": [_C_NGAY, {"key": "chu_so_huu", "nhan": "Chủ sở hữu"},
                {"key": "loai_giao_dich", "nhan": "Loại"},
                {"key": "ghi_chu", "nhan": "Ghi chú"}, _C_TIEN],
    },
    "nguon_von.von_csh.quy_dn": {
        "duong_dan": ("nguon_von", "von_csh", "quy_dn"),
        "nhan": "Quỹ doanh nghiệp",
        "nguon": "ketoan.quy_dn",
        "giai_thich": "Số dư từng quỹ.",
        "sql": """
            SELECT id, ten_quy, COALESCE(ghi_chu,'') AS ghi_chu, nguon_compute,
                   ty_le_pct, so_du AS so_tien
            FROM ketoan.quy_dn WHERE active IS TRUE ORDER BY so_du DESC, thu_tu
        """,
        "cot": [{"key": "ten_quy", "nhan": "Quỹ"}, {"key": "nguon_compute", "nhan": "Cách tính"},
                {"key": "ty_le_pct", "nhan": "Tỉ lệ %"}, {"key": "ghi_chu", "nhan": "Ghi chú"},
                _C_TIEN],
    },
    "nguon_von.von_csh.ln_giu_lai": {
        "duong_dan": ("nguon_von", "von_csh", "ln_giu_lai"),
        "nhan": "Lợi nhuận sau thuế chưa phân phối",
        "nguon": "ketoan.ky_ke_toan",
        "giai_thich": ("Lấy từ kỳ kế toán ĐÃ CHỐT gần nhất. Chưa chốt kỳ nào thì dòng này "
                       "luôn bằng 0 — đó là lý do bảng cân đối không cân."),
        "sql": """
            SELECT thang, trang_thai, COALESCE(ln_giu_lai_dau_ky, 0) AS dau_ky,
                   COALESCE(lnst_ky, 0) AS lnst_ky,
                   COALESCE(ln_giu_lai_cuoi_ky, 0) AS so_tien
            FROM ketoan.ky_ke_toan WHERE thang <= :thang_den
            ORDER BY thang DESC
        """,
        "cot": [{"key": "thang", "nhan": "Kỳ"}, {"key": "trang_thai", "nhan": "Trạng thái"},
                {"key": "dau_ky", "nhan": "LN giữ lại đầu kỳ", "kieu": "tien"},
                {"key": "lnst_ky", "nhan": "LNST trong kỳ", "kieu": "tien"}, _C_TIEN],
    },
}


def _lay(d: Any, duong_dan: tuple[str, ...]) -> Optional[float]:
    for k in duong_dan:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    try:
        return float(d)
    except (TypeError, ValueError):
        return None


def chi_tiet(
    db: Session, khoa: str, den: date, so_bao_cao: Optional[float],
    trang: int = 1, so_dong: int = SO_DONG_MAC_DINH,
) -> Optional[dict[str, Any]]:
    """Chi tiết một dòng Cân đối. `so_bao_cao` là số đang hiện trên báo cáo."""
    kh = KHOAN.get(khoa)
    if kh is None:
        return None
    so_dong = max(1, min(int(so_dong or SO_DONG_MAC_DINH), SO_DONG_TOI_DA))
    trang = max(1, int(trang or 1))
    p = {"den": den, "thang_den": den.strftime("%Y-%m")}

    sql = kh["sql"].strip()
    tt = db.execute(text(
        f"SELECT COALESCE(SUM(so_tien), 0) AS tong, COUNT(*) AS n FROM ({sql}) t"
    ), p).mappings().first()
    tong_dong = float(tt["tong"] or 0) if tt else 0.0
    n = int(tt["n"] or 0) if tt else 0
    so_trang = max(1, -(-n // so_dong))
    trang = min(trang, so_trang)
    rows = db.execute(text(
        f"{sql} OFFSET :_off LIMIT :_lim"
    ), {**p, "_off": (trang - 1) * so_dong, "_lim": so_dong}).mappings().all()

    ghi_chu = ""
    if so_bao_cao is not None and abs(tong_dong - so_bao_cao) > 0.5:
        ghi_chu = (f"Cộng các dòng dưới đây ra {tong_dong:,.0f}đ, nhưng báo cáo đang hiện "
                   f"{so_bao_cao:,.0f}đ. Cân đối chạy chế độ 'auto' — mỗi dòng lấy số lớn hơn "
                   "giữa sổ cái và sổ cũ, nên hai bên đang nói khác nhau ở dòng này.")

    return {
        "ok": True, "khoa": khoa, "nhan": kh["nhan"], "nguon": kh["nguon"],
        "giai_thich": kh["giai_thich"], "ghi_chu": ghi_chu,
        "den": den.isoformat(),
        "tong": round(so_bao_cao if so_bao_cao is not None else tong_dong, 2),
        "tong_dong": round(tong_dong, 2),
        "so_dong": n, "trang": trang, "so_trang": so_trang, "so_dong_moi_trang": so_dong,
        "cot": kh["cot"], "dong": [dict(r) for r in rows], "dieu_chinh": [],
    }


# Dòng TỔNG của Cân đối: phép cộng của các dòng trên, không có chứng từ riêng.
CONG_THUC: dict[str, tuple[str, str, list]] = {
    "tai_san.tien_va_td.tong": ("Tiền và các khoản tương đương tiền",
                                "tai_san.tien_va_td.tong", [
        ("Tiền mặt (sổ quỹ)", "tai_san.tien_va_td.tien_mat_so_quy", 1),
        ("Tiền gửi ngân hàng", "tai_san.tien_va_td.tk_ngan_hang", 1)]),
    "tai_san.tscd_rong": ("Tài sản cố định (giá trị còn lại)", "tai_san.tscd_rong", [
        ("Nguyên giá", "tai_san.tscd_nguyen_gia", 1),
        ("Hao mòn luỹ kế", "tai_san.tscd_hao_mon_luy_ke", -1)]),
    "tai_san.tong_tai_san": ("TỔNG CỘNG TÀI SẢN", "tai_san.tong_tai_san", [
        ("Tiền và tương đương tiền", "tai_san.tien_va_td.tong", 1),
        ("Các khoản phải thu (gồm tạm ứng)", "tai_san.phai_thu", 1),
        ("Hàng tồn kho", "tai_san.hang_ton_kho", 1),
        ("Tài sản cố định (còn lại)", "tai_san.tscd_rong", 1)]),
    "nguon_von.no_phai_tra.tong": ("Tổng nợ phải trả", "nguon_von.no_phai_tra.tong", [
        ("Phải trả người bán", "nguon_von.no_phai_tra.phai_tra_ncc", 1),
        ("Phải trả người lao động", "nguon_von.no_phai_tra.phai_tra_nv", 1),
        ("Vay ngắn hạn", "nguon_von.no_phai_tra.vay_ngan_han", 1),
        ("Vay dài hạn", "nguon_von.no_phai_tra.vay_dai_han", 1)]),
    "nguon_von.von_csh.tong": ("Tổng vốn chủ sở hữu", "nguon_von.von_csh.tong", [
        ("Vốn góp của chủ sở hữu", "nguon_von.von_csh.von_gop", 1),
        ("Quỹ doanh nghiệp", "nguon_von.von_csh.quy_dn", 1),
        ("Lợi nhuận sau thuế chưa phân phối", "nguon_von.von_csh.ln_giu_lai", 1)]),
    "nguon_von.tong_nguon_von": ("TỔNG CỘNG NGUỒN VỐN", "nguon_von.tong_nguon_von", [
        ("Tổng nợ phải trả", "nguon_von.no_phai_tra.tong", 1),
        ("Tổng vốn chủ sở hữu", "nguon_von.von_csh.tong", 1)]),
}


def chi_tiet_cong_thuc(khoa: str, bc: dict, den: date) -> Optional[dict]:
    """Popup cho dòng tổng: hiện công thức + số của từng số hạng."""
    ct = CONG_THUC.get(khoa)
    if ct is None:
        return None
    nhan, duong_dan, so_hang = ct
    lay = lambda p: (_lay(bc, tuple(p.split("."))) or 0.0)
    return {
        "ok": True, "khoa": khoa, "nhan": nhan,
        "nguon": "Tính từ các dòng khác của báo cáo",
        "giai_thich": "Dòng này không có chứng từ riêng — nó là phép cộng của các dòng trên.",
        "den": den.isoformat(),
        "tong": round(lay(duong_dan), 2), "tong_dong": round(lay(duong_dan), 2),
        "so_dong": len(so_hang), "trang": 1, "so_trang": 1, "so_dong_moi_trang": len(so_hang) or 1,
        "cot": [{"key": "khoan", "nhan": "Số hạng"},
                {"key": "so_tien", "nhan": "Số tiền", "kieu": "tien"}],
        "dong": [{"khoan": ("− " if d < 0 else "+ ") + n, "so_tien": round(lay(p) * d, 2)}
                 for n, p, d in so_hang],
        "dieu_chinh": [], "ghi_chu": "",
    }
