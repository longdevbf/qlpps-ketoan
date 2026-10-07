"""Kiểm bảng nghiệp vụ Sổ quỹ (app/services/nghiep_vu_so_quy.py) với CSV đặc tả, TỪNG Ô.

Chạy trong container (cần import được ketoan.app.*); CSV nằm ngoài repo nên đưa qua stdin:
    docker exec -i qlpps_ketoan python /srv/apps/ketoan/tools/kiem_nghiep_vu.py \
        < "Tài liệu/ban-giao-2026-09-30/cat-moc-30-09/nghiep_vu_so_quy.csv"

Kiểm: (1) mỗi hàng Python = hàng CSV cùng vị trí, từng cột (tài khoản: tên logic đổi ra số theo cả TT133 lẫn
TT99 rồi so với ô CSV); (2) (khoa, loai) duy nhất; (3) b03_khoa có trong phan_loai_cf.py, đúng chiều, mã số khớp;
(4) hàng lập tay là đúng một cặp Nợ/Có; (5) tên logic nào chưa có số ở chế độ nào; (6) số tài khoản nào chưa có
trong journal.ACCOUNTS (chỉ BÁO — việc bổ sung journal.py thuộc phiên khác). Thoát mã 1 nếu (1)–(4) có lỗi.
"""
import csv
import io
import re
import sys
from collections import Counter

from ketoan.app.services import nghiep_vu_so_quy as M
from ketoan.app.services.phan_loai_cf import BANG as BANG_CF, KHOA_HOP_LE, khoa_dung_cho_loai
from ketoan.app.services.journal import ACCOUNTS

COT_TK = (("no", "tt133", "no_tk_tt133", 0), ("co", "tt133", "co_tk_tt133", 1),
          ("no", "tt99", "no_tk_tt99", 2), ("co", "tt99", "co_tk_tt99", 3))


def tk_ra_chu(nv, ben, che_do):
    """Ô tài khoản của một hàng Python, viết như CSV."""
    if nv.tk_van_ban:
        return nv.tk_van_ban[[c[3] for c in COT_TK if c[0] == ben and c[1] == che_do][0]]
    k = getattr(nv, ben)
    if k in (M.TIEN, M.TIEN_DOI_UNG) and nv.khoa == "chuyen_noi_bo":
        quy_chon_la_nhan = nv.loai == "thu"
        nhan = (k == M.TIEN) == quy_chon_la_nhan
        return "TIEN của quỹ nhận" if nhan else "TIEN của quỹ chuyển"
    if k in (M.TIEN, M.TK_DOI_UNG):
        return k
    return M.tk_so(k, che_do)


def chuan_o_csv(o):
    return re.sub(r"\s*\(tạm\)$", "", o.strip())


def main() -> int:
    t = sys.stdin.buffer.read().decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(t, newline="")))
    loi: list[str] = []
    if len(rows) != len(M.BANG):
        loi.append(f"Số hàng: CSV {len(rows)} ≠ Python {len(M.BANG)}")
    so_o = 0
    for i, (r, nv) in enumerate(zip(rows, M.BANG), start=2):
        so_sanh = {
            "khoa": nv.khoa, "ten": nv.ten, "nhom": nv.nhom, "loai": nv.loai, "luat_id": nv.luat_id,
            "b03_khoa": nv.b03_khoa, "b03_ma_so": nv.b03_ma_so, "can_truong": nv.can_truong_csv,
            "thu_tu": str(nv.thu_tu), "cho_phep_phieu_tay": nv.cho_phep, "ghi_chu": nv.ghi_chu,
        }
        for cot, gt in so_sanh.items():
            so_o += 1
            if r[cot] != gt:
                loi.append(f"Dòng CSV {i} ({r['khoa']}) cột {cot}: CSV {r[cot]!r} ≠ Python {gt!r}")
        for ben, che_do, cot, _ in COT_TK:
            so_o += 1
            py = tk_ra_chu(nv, ben, che_do)
            o = r[cot] if nv.tk_van_ban else chuan_o_csv(r[cot])
            if o != py:
                loi.append(f"Dòng CSV {i} ({r['khoa']}) cột {cot}: CSV {r[cot]!r} ≠ Python {py!r}")

    dem = Counter((x.khoa, x.loai) for x in M.BANG)
    loi += [f"Trùng (khoa, loai): {k}" for k, n in dem.items() if n > 1]

    ma_so_cf = {(x.khoa, x.loai): x.ma_so for x in BANG_CF}
    for x in M.BANG:
        if x.b03_khoa not in KHOA_HOP_LE:
            loi.append(f"{x.khoa}: b03_khoa {x.b03_khoa!r} không có trong phan_loai_cf.py")
        elif not khoa_dung_cho_loai(x.b03_khoa, x.loai):
            loi.append(f"{x.khoa}: b03_khoa {x.b03_khoa!r} sai chiều (phiếu {x.loai})")
        elif ma_so_cf[(x.b03_khoa, x.loai)] != x.b03_ma_so:
            loi.append(f"{x.khoa}: mã số B03 {x.b03_ma_so!r} ≠ phan_loai_cf.py {ma_so_cf[(x.b03_khoa, x.loai)]!r}")
        if x.cho_phep == "co" and not (x.no and x.co and not x.tk_van_ban):
            loi.append(f"{x.khoa}: lập tay được nhưng không phải đúng một cặp Nợ/Có")

    print(f"So {len(rows)} hàng CSV × {len(M.BANG)} hàng Python: {so_o} ô.")
    print("Đếm theo loại × cho_phep:", dict(sorted(Counter((x.loai, x.cho_phep) for x in M.BANG).items())))

    dung = sorted({k for x in M.BANG for k in (x.no, x.co) if k and k in M.DANH_MUC_TK})
    print("Tên logic dùng trong bảng:", ", ".join(dung))
    for ten, tk in M.DANH_MUC_TK.items():
        for che_do in ("tt133", "tt99"):
            if not M.tk_so(ten, che_do):
                print(f"  CHƯA CÓ SỐ: {ten} ở {che_do}" + (" (đang dùng trong bảng!)" if ten in dung else " (chưa dùng)"))
                if ten in dung:
                    loi.append(f"Tên logic {ten} đang dùng nhưng chưa có số ở {che_do}")

    thieu = {}
    for ten, tk in M.DANH_MUC_TK.items():
        for che_do, so in (("tt133", tk.tt133), ("tt99", tk.tt99)):
            if so and so not in ACCOUNTS:
                thieu.setdefault(so, set()).add(f"{ten}/{che_do}")
    print("Số tài khoản trong danh mục logic CHƯA có trong journal.ACCOUNTS (phiên sửa journal.py bổ sung):")
    for so in sorted(thieu):
        print(f"  {so}: {', '.join(sorted(thieu[so]))}")

    if loi:
        print(f"\nLỖI ({len(loi)}):")
        for x in loi:
            print("  -", x)
        return 1
    print("\nKHỚP: mọi ô CSV = bảng Python; b03 đúng khoá, đúng chiều, đúng mã số; hàng lập tay đúng một cặp.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
