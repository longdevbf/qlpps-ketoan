"""Kiểm Đợt 1 (07/10/2026) — "chỉ phơi lỗi, không đổi một con số nào" — trên dữ liệu thật. CHỈ ĐỌC.

Ba chế độ:

  chup [tháng…]   Chụp MỌI con số của Cân đối kế toán, Kết quả kinh doanh, Lưu chuyển tiền tệ và Cân đối
                  phát sinh ra JSON (stdout). Chỉ gọi các hàm có ở CẢ code cũ lẫn code mới, nên chạy được
                  TRƯỚC và SAU khi deploy. Mặc định 6 tháng gần nhất.
  so A.json B.json  So hai bản chụp: in mọi số lệch > 0,5 đ. Thoát mã 1 nếu có lệch. Chạy ở đâu cũng được
                  (chỉ cần Python, không import gì của app).
  chan-doan [tháng]  (chỉ code MỚI) In cảnh báo kỳ, bảng đối chiếu sổ cái ↔ bảng nghiệp vụ, số tài khoản chưa
                  có bút toán, và các bảng không đọc được — đúng những gì 4 màn mới sẽ hiện.

Cách chạy trên VPS — script đi qua stdin nên KHÔNG cần chép file vào container trước:

    # 1. TRƯỚC khi deploy (container còn chạy code cũ)
    docker exec -i qlpps_ketoan python - chup < tools/kiem_dot1.py > truoc.json
    # 2. Deploy Đợt 1, khởi động lại container, rồi chụp lần nữa
    docker exec -i qlpps_ketoan python - chup < tools/kiem_dot1.py > sau.json
    # 3. So — phải ra "KHỚP"
    python3 tools/kiem_dot1.py so truoc.json sau.json
    # 4. Xem chẩn đoán của tháng 10/2026
    docker exec -i qlpps_ketoan python - chan-doan 2026-10 < tools/kiem_dot1.py

Không ghi gì vào DB: mọi truy vấn chạy trong một phiên và rollback ở cuối.
Lưu ý: dữ liệu thay đổi giữa hai lần chụp (có người nhập phiếu) cũng tạo ra lệch — chụp sát nhau,
ngoài giờ làm việc, hoặc đọc kỹ dòng lệch trước khi kết luận code sai.
"""
import json
import sys
from calendar import monthrange
from datetime import date

NGUONG = 0.5   # VND


# ─── so: không import app ────────────────────────────────────────────────────

def so(a_path: str, b_path: str) -> int:
    with open(a_path, encoding="utf-8") as f:
        a = json.load(f)
    with open(b_path, encoding="utf-8") as f:
        b = json.load(f)
    chung = sorted(set(a) & set(b))
    lech = [(k, a[k], b[k]) for k in chung if abs(float(a[k]) - float(b[k])) > NGUONG]
    chi_a, chi_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
    print(f"So {len(chung)} con số có ở cả hai bản chụp.")
    if chi_a:
        print(f"{len(chi_a)} số chỉ có ở {a_path} (vd {chi_a[:3]}) — kiểm xem có phải do chọn khác tháng không.")
    if chi_b:
        print(f"{len(chi_b)} số chỉ có ở {b_path} (vd {chi_b[:3]}).")
    if not lech:
        print("KHỚP: không con số nào thay đổi.")
        return 0
    print(f"\nLỆCH {len(lech)} số (trước → sau):")
    for k, x, y in lech:
        print(f"  {k}: {x:,.2f} → {y:,.2f}  (chênh {y - x:,.2f})")
    return 1


# ─── chup / chan-doan: chạy trong container, import được ketoan.app.* ────────

def _nguoi_kiem():
    from shared.auth import JWTPayload
    return JWTPayload(sub=0, username="kiem_dot1", role="admin", apps=["ketoan"], jti="kiem_dot1", exp=0, iat=0)


def _cac_thang(args: list[str], mac_dinh: int = 6) -> list[str]:
    if args:
        return args
    h = date.today()
    out, y, m = [], h.year, h.month
    for _ in range(mac_dinh):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return sorted(out)


def _phang(tien_to: str, d, out: dict) -> None:
    """Dàn phẳng mọi số trong dict lồng nhau thành {đường.dẫn: số}. Bỏ chuỗi, list, bool."""
    if isinstance(d, bool) or d is None:
        return
    if isinstance(d, (int, float)) or type(d).__name__ == "Decimal":
        out[tien_to] = float(d)
    elif isinstance(d, dict):
        for k, v in d.items():
            _phang(f"{tien_to}.{k}", v, out)


def chup(thang: list[str]) -> int:
    from shared.db import SessionLocal
    from ketoan.app.routers.bao_cao_can_doi import bao_cao_can_doi
    from ketoan.app.routers.bao_cao_cashflow import bao_cao_cashflow
    from ketoan.app.services.journal import trial_balance
    from ketoan.app.services.pl_calculator import calc_pl_for_month

    u = _nguoi_kiem()
    db = SessionLocal()
    out: dict[str, float] = {}
    try:
        for t in thang:
            y, m = int(t[:4]), int(t[5:7])
            tu, den = date(y, m, 1), date(y, m, monthrange(y, m)[1])
            cd = bao_cao_can_doi(db, u, thang=t, source="auto")
            for nhom in ("tai_san", "nguon_von"):
                _phang(f"can_doi:{t}:{nhom}", cd[nhom], out)
            out[f"can_doi:{t}:check.lech"] = float(cd["check"]["lech"])
            _phang(f"kqkd:{t}", {k: v for k, v in calc_pl_for_month(db, t).items() if k != "metadata"}, out)
            lc = bao_cao_cashflow(db, u, from_=tu, to=den)
            for nhom in ("operating", "investing", "financing"):
                for k, v in lc[nhom].items():
                    out[f"lctt:{t}:{nhom}.{k}"] = float(v["total"] if isinstance(v, dict) else v)
            for k in ("so_du_dau_ky", "net_cashflow", "so_du_cuoi_ky"):
                out[f"lctt:{t}:{k}"] = float(lc[k])
            for r in trial_balance(db, tu, den):
                for k in ("dau_no", "dau_co", "ps_no", "ps_co", "cuoi_no", "cuoi_co"):
                    out[f"can_doi_ps:{t}:{r['ma']}.{k}"] = float(r[k])
            print(f"đã chụp {t}", file=sys.stderr)
    finally:
        db.rollback()
        db.close()
    json.dump(out, sys.stdout, ensure_ascii=False, indent=0, sort_keys=True)
    print(f"{len(out)} con số", file=sys.stderr)
    return 0


def _vnd(x) -> str:
    return "—" if x is None else f"{float(x):,.0f}".replace(",", ".")


def chan_doan(thang: list[str]) -> int:
    from shared.db import SessionLocal
    from ketoan.app.routers.doi_chieu import canh_bao_ky, doi_chieu_so_cai_nghiep_vu
    from ketoan.app.services.journal import ACCOUNTS, trial_balance

    t = (thang or [date.today().strftime("%Y-%m")])[0]
    u = _nguoi_kiem()
    db = SessionLocal()
    try:
        cb = canh_bao_ky(db, u, thang=t)
        print(f"═══ CẢNH BÁO KỲ {t} ({len(cb['canh_bao'])}) ═══")
        for x in cb["canh_bao"]:
            print(f"[{x['muc']}] {x['tieu_de']}")
            for n in x.get("nguyen_nhan") or []:
                print(f"    - {n}")
            if not x.get("nguyen_nhan"):
                print(f"    {x['chi_tiet']}")
        dc = doi_chieu_so_cai_nghiep_vu(db, u, thang=t)
        for ten, khoa in (("CÂN ĐỐI — số dư cuối tháng", "can_doi"), ("KQKD — phát sinh trong tháng", "kqkd")):
            print(f"\n═══ ĐỐI CHIẾU {ten} ═══")
            print(f"{'Khoản mục':<34}{'TK':<14}{'Sổ cái':>18}{'Bảng nghiệp vụ':>18}{'Chênh':>18}  Đang dùng")
            for r in dc[khoa]:
                print(f"{r['nhan'][:33]:<34}{','.join(r['tk']):<14}{_vnd(r['so_cai']):>18}{_vnd(r['nghiep_vu']):>18}"
                      f"{_vnd(r['chenh']):>18}  {r['dang_dung']}")
        y, m = int(t[:4]), int(t[5:7])
        tb = [r for r in trial_balance(db, date(y, m, 1), date(y, m, monthrange(y, m)[1])) if r["cap"] == 1]
        chua = [r["ma"] for r in tb if not r["so_dong"]]
        print(f"\n═══ CÂN ĐỐI PHÁT SINH: {len(tb)} tài khoản cấp 1 (danh mục ACCOUNTS: {len(ACCOUNTS)}) ═══")
        print(f"{len(chua)} tài khoản CHƯA có bút toán nào tới cuối kỳ: {', '.join(chua)}")
        # Gộp lỗi của cả hai lần gọi (cảnh báo đọc Cân đối; đối chiếu đọc thêm KQKD) — trùng thì in một lần.
        loi = list({(x["ham"], x["chi_tiet"]): x for x in
                    (cb.get("loi_doc_du_lieu") or []) + (dc.get("loi_doc_du_lieu") or [])}.values())
        print(f"\n═══ BẢNG KHÔNG ĐỌC ĐƯỢC ({len(loi)}) — số 0 ở dòng liên quan không phải số thật ═══")
        for x in loi:
            print(f"  {x['ham']}: {x['chi_tiet']}")
    finally:
        db.rollback()
        db.close()
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("chup", "so", "chan-doan"):
        print(__doc__)
        sys.exit(2)
    lenh, them = sys.argv[1], sys.argv[2:]
    if lenh == "so":
        sys.exit(so(*them[:2]))
    sys.exit(chup(_cac_thang(them)) if lenh == "chup" else chan_doan(them))
