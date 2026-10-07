"""Bảng nghiệp vụ (mã định khoản) của hộp Lập phiếu thu/chi ở Sổ quỹ — NGUỒN DUY NHẤT.

Đặc tả: Tài liệu/ban-giao-2026-09-30/cat-moc-30-09/spec_phieu_chon_ma_dinh_khoan.md (mục 2, 4).
Bản máy đọc cùng thư mục: nghiep_vu_so_quy.csv — `tools/kiem_nghiep_vu.py` so bảng này với CSV từng ô.

Ba lớp, đọc từ trên xuống:
1. DANH_MUC_TK — tài khoản theo TÊN LOGIC, mỗi tên một cặp số (TT133, TT99). Đổi chuẩn kế toán hay đổi
   một tài khoản chỉ sửa một ô ở đây. Tên logic BẤT BIẾN: đã lưu vào dữ liệu thì không được đổi tên.
2. BANG — 48 hàng nghiệp vụ (15 thu, 33 chi). Hàng chỉ tham chiếu tên logic, không ghi số tài khoản.
   `cho_phep`: 'co' = lập tay được ở hộp này · 'chuyen' = phải lập ở màn khác (API trả 422 kèm chỉ đường)
   · 'an' = không hiện (luật chưa có, chờ kế toán).
3. Hàm thuần dùng CHUNG cho xem trước, API và (sau này) bộ dựng lại sổ: tra_nghiep_vu, suy_phan_loai_cf,
   tk_no_co, tra_dinh_khoan. Phiên bản này KHÔNG gọi post_journal — chỉ ghi nhận phiếu là việc gì.

Giám đốc chốt 01/10/2026: ứng lương ghi Nợ 334 / Có tiền (hàng `ung_luong`, lập tay được) thay cho
`tam_ung_luong` (Nợ 141, chuyển màn Tạm ứng). Tạm ứng công việc (141) vẫn ở màn Tạm ứng.
Cột TT133 chép từ luật v1.1 (chưa đối chiếu văn bản gốc); cột TT99 là ĐOÁN — kế toán xác nhận.

Service này KHÔNG import fastapi: lỗi nghiệp vụ là `LoiNghiepVu` (router đổi thành HTTP 422/409).
"""
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, NamedTuple, Optional

from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from ..models import SoQuy, TaiKhoanNH
from .phan_loai_cf import BANG as BANG_CF


# ─── 1. Danh mục tài khoản theo tên logic ─────────────────────────────────────

class TaiKhoanLogic(NamedTuple):
    tt133: Optional[str]   # None = chưa chốt số ở chế độ này (kiem_nghiep_vu.py báo thiếu)
    tt99: Optional[str]
    ten: str               # tên hiển thị ở dòng xem trước


CHE_DO_TEN = {"tt133": "Thông tư 133/2016", "tt99": "Thông tư 99/2025"}

# TIEN không nằm ở đây: tài khoản tiền là tk_ke_toan của quỹ đang chọn (1111, 1121…), xem tk_tien_cua_quy.
DANH_MUC_TK: dict[str, TaiKhoanLogic] = {
    "PHAI_THU_KH": TaiKhoanLogic("131", "131", "Phải thu khách hàng"),
    "PHAI_TRA_NCC": TaiKhoanLogic("331", "331", "Phải trả người bán"),
    "TK_CHO": TaiKhoanLogic("3388", "3388", "Phải trả khác — chờ phân loại"),   # phải về 0 khi kế toán phân loại
    "CP_BAN_HANG": TaiKhoanLogic("6421", "641", "Chi phí bán hàng"),
    "CP_QUAN_LY": TaiKhoanLogic("6422", "642", "Chi phí quản lý doanh nghiệp"),
    "CP_TAI_CHINH": TaiKhoanLogic("635", "635", "Chi phí tài chính"),
    "CP_KHAC": TaiKhoanLogic("811", "811", "Chi phí khác"),
    "DT_TAI_CHINH": TaiKhoanLogic("515", "515", "Doanh thu hoạt động tài chính"),   # Q15.2: 515 hay 711
    "THU_NHAP_KHAC": TaiKhoanLogic("711", "711", "Thu nhập khác"),
    "VI_QUANG_CAO": TaiKhoanLogic("1388", "1388", "Phải thu khác — ví quảng cáo"),
    "PHAI_TRA_NLD": TaiKhoanLogic("334", "334", "Phải trả người lao động"),
    "TAM_UNG": TaiKhoanLogic("141", "141", "Tạm ứng"),                             # chỉ màn Tạm ứng
    "BHXH_NOP": TaiKhoanLogic("3383", "3383", "Bảo hiểm xã hội"),                   # Q9.4: 3383 hay 6422
    "THUE_GTGT": TaiKhoanLogic("3331", "3331", "Thuế GTGT phải nộp"),
    "THUE_TNCN": TaiKhoanLogic("3335", "3335", "Thuế thu nhập cá nhân"),
    "THUE_TNDN": TaiKhoanLogic("3334", "3334", "Thuế thu nhập doanh nghiệp"),
    "VAY": TaiKhoanLogic("3411", "341", "Vay và nợ thuê tài chính"),                # TT99 ĐOÁN
    "LAI_VAY": TaiKhoanLogic("635", "635", "Chi phí tài chính — lãi vay"),
    "VON_CSH": TaiKhoanLogic("411", "411", "Vốn góp của chủ sở hữu"),
    # TT133 là "4211 hoặc 4212" — chưa chốt nên để None; chỉ dùng ở màn Vốn (hàng chia_co_tuc ghi chữ ở tk_van_ban).
    "LNST_CHUA_PHAN_PHOI": TaiKhoanLogic(None, "421", "Lợi nhuận sau thuế chưa phân phối"),
    "TSCD_HH": TaiKhoanLogic("211", "211", "Tài sản cố định hữu hình"),
    "TSCD_VH": TaiKhoanLogic("2113", "213", "Tài sản cố định vô hình"),             # TT99 ĐOÁN
    "CHI_PHI_TRA_TRUOC": TaiKhoanLogic("242", "242", "Chi phí chờ phân bổ"),
    "KHO": TaiKhoanLogic("156", "156", "Hàng tồn kho"),
    "DT_BAN_HANG": TaiKhoanLogic("511", "511", "Doanh thu bán hàng"),
    "GIAM_TRU_DT": TaiKhoanLogic("511", "521", "Giảm trừ doanh thu"),               # TT133 bỏ 521; TT99 ĐOÁN
}

# Ký hiệu không phải tài khoản cố định: quỹ đang chọn / quỹ đối ứng (chuyển nội bộ) / tự chọn (giai đoạn 2).
TIEN, TIEN_DOI_UNG, TK_DOI_UNG = "TIEN", "TIEN_DOI_UNG", "TK_DOI_UNG"


# ─── 2. Bảng nghiệp vụ ────────────────────────────────────────────────────────

class NghiepVu(NamedTuple):
    khoa: str
    ten: str
    nhom: str
    loai: str                    # 'thu' | 'chi'
    luat_id: str
    no: Optional[str]            # tên logic / TIEN / TIEN_DOI_UNG / TK_DOI_UNG; None khi bút toán không phải một cặp
    co: Optional[str]
    b03_khoa: str                # khoá có thật trong phan_loai_cf.py, đúng chiều — máy chủ ghi vào so_quy.phan_loai_cf
    b03_ma_so: str
    can_truong_csv: str          # nguyên văn cột can_truong của CSV: 'ma_don*;noi_dung' (* = bắt buộc)
    thu_tu: int
    cho_phep: str                # 'co' | 'chuyen' | 'an'
    tk_van_ban: Optional[tuple]  # (Nợ TT133, Có TT133, Nợ TT99, Có TT99) bằng chữ — chỉ hàng không phải một cặp
    ghi_chu: str


def _nv(khoa, ten, nhom, loai, luat_id, no, co, b03_khoa, b03_ma_so, can_truong, thu_tu, cho_phep,
        tk_van_ban=None, ghi_chu="") -> NghiepVu:
    return NghiepVu(khoa, ten, nhom, loai, luat_id, no, co, b03_khoa, b03_ma_so, can_truong, thu_tu, cho_phep,
                    tk_van_ban, ghi_chu)


# Thứ tự hàng = thứ tự CSV (kiem_nghiep_vu.py so từng ô, kể cả ghi_chu). Sửa ở đây thì sửa cả CSV.
BANG: tuple[NghiepVu, ...] = (
    _nv('thu_coc', 'Khách đặt cọc đơn hàng', 'Tiền của khách', 'thu', 'L01', 'TIEN', 'PHAI_THU_KH', 'thu_kh', '01',
        'ma_don*;noi_dung', 1, 'co',
        ghi_chu='[Chốt] Khách tự điền theo báo giá của mã đơn. Dev từ 01/05: 206 phiếu, 1.727 triệu, tất cả do Báo giá/Duyệt cọc tự ghi; phiếu tay chỉ khi tiền về ngoài hai đường đó, không cập nhật số cọc trên báo giá. Cảnh báo trùng mã đơn+ngày+số tiền. Mã đơn lệch báo giá: 422, hướng sang thu_khong_ro.'),
    _nv('thu_khach_thanh_toan', 'Khách trả tiền hàng (thu nốt, thu ship, COD)', 'Tiền của khách', 'thu', 'L02', 'TIEN', 'PHAI_THU_KH', 'thu_kh', '01',
        'ma_don*;noi_dung', 2, 'co',
        ghi_chu='[Chốt] Dev từ 01/05: 182 phiếu, 1.749 triệu. Phiếu tay KHÔNG trừ công nợ phải thu; nếu đơn còn khoản phải thu thì nhắc dùng thu_cong_no_khach. Khách trả thừa nhỏ để dư Có 131 (Q2.1 chưa trả lời).'),
    _nv('thu_cong_no_khach', 'Thu công nợ khách đã ghi nhận (có sẵn khoản phải thu)', 'Tiền của khách', 'thu', 'L02', 'TIEN', 'PHAI_THU_KH', 'thu_kh', '01',
        '', 3, 'chuyen',
        ghi_chu='[Chốt] [Màn: Công nợ, hộp Ghi nhận thu (POST /api/cong-no/{id}/tra)] Hộp đó vừa trừ công nợ khách vừa ghi sổ quỹ; phiếu tay không trừ nợ. Dev: 59 khoản phải thu, 689,8 triệu.'),
    _nv('thu_ncc_hoan_tien', 'Nhà cung cấp trả lại tiền (hoàn tiền trả trước)', 'Nhà cung cấp & hàng', 'thu', '- (suy từ L07 + Q7.1)', 'TIEN', 'PHAI_TRA_NCC', 'khac', '06',
        'ncc*;ma_don;noi_dung*', 4, 'co',
        ghi_chu='[Khoảng trống luật, suy ra] Chiều ngược của trả trước (331 dư Nợ). Hiện nhãn Chờ kế toán xác nhận. Nếu là trả hàng đã nhập kho còn cần phiếu hàng Nợ 331/Có 156 (không phải phiếu tiền). Dev: 0 trường hợp.'),
    _nv('thu_hoan_ung', 'Nhân viên trả lại tiền tạm ứng', 'Nhân viên', 'thu', 'L09b', 'TIEN', 'TAM_UNG', 'khac', '06',
        'nhan_vien*', 5, 'chuyen',
        ghi_chu='[Cần xác nhận Q9.2] [Màn: Tạm ứng (quyết toán)] Màn Tạm ứng kiểm kỳ chốt, đủ tiền, đảo khi sửa; phiếu tay Có 141 làm sổ cái 141 lệch bảng tạm ứng. Dev: 0 khoản tạm ứng.'),
    _nv('thu_giai_ngan_vay', 'Nhận tiền vay (giải ngân)', 'Vay, vốn & tài chính', 'thu', 'L11a', 'TIEN', 'VAY', 'vay_nh', '33',
        'khoan_vay*', 6, 'chuyen',
        ghi_chu='[Chốt] [Màn: Khoản vay] Cần bản ghi khoản vay để có lịch trả gốc/lãi; phiếu tay Có 3411 không có khoản vay thì không có gì để trả sau này. Dev: 9 dòng giải ngân. TT99 = 341: ĐOÁN (app cũ ghi 311 nếu <=12 tháng).'),
    _nv('thu_gop_von', 'Chủ sở hữu góp vốn', 'Vay, vốn & tài chính', 'thu', 'L17', 'TIEN', 'VON_CSH', 'nhan_von', '31',
        '', 7, 'chuyen',
        ghi_chu='[Cần xác nhận] [Màn: Vốn chủ sở hữu, Góp vốn] Bảng vốn chỉ cập nhật qua màn đó; phiếu tay không cập nhật.'),
    _nv('thu_lai_tien_gui', 'Lãi tiền gửi ngân hàng', 'Vay, vốn & tài chính', 'thu', 'L15b', 'TIEN', 'DT_TAI_CHINH', 'thu_lai', '27',
        'noi_dung', 8, 'co',
        ghi_chu='[Cần xác nhận Q15.2: 515 hay 711] Dev: 9 dòng, khoảng 55 nghìn đồng cả kỳ, hiện nhập thành Doanh thu khác. B03 mã 27 theo thông lệ (ĐOÁN).'),
    _nv('thu_hoi_cho_vay', 'Thu hồi tiền đã cho vay đơn vị khác', 'Vay, vốn & tài chính', 'thu', '- (luật KHÔNG có)', None, None, 'thu_hoi_cho_vay', '24',
        'noi_dung', 9, 'an',
        tk_van_ban=('TIEN', '128 (ĐOÁN)', 'TIEN', '128 (ĐOÁN)'),
        ghi_chu='[Khoảng trống luật] Ẩn tới khi kế toán chốt tài khoản và danh mục có 128 (journal.py chưa có, post_journal sẽ từ chối). Trong lúc chờ dùng thu_khong_ro.'),
    _nv('thu_hoi_gop_von', 'Thu hồi vốn đã góp vào đơn vị khác', 'Vay, vốn & tài chính', 'thu', '- (luật KHÔNG có)', None, None, 'thu_hoi_gop_von', '26',
        'noi_dung', 10, 'an',
        tk_van_ban=('TIEN', '228 (ĐOÁN)', 'TIEN', '228 (ĐOÁN)'),
        ghi_chu='[Khoảng trống luật] Ẩn như trên. Cổ tức/lợi nhuận được chia (B03 27) nên là Có 515, tách thành nghiệp vụ riêng khi cần.'),
    _nv('thu_thanh_ly_tscd', 'Bán / thanh lý tài sản cố định', 'Tài sản', 'thu', 'L12c', None, None, 'thanh_ly_tscd', '22',
        'tai_san*', 11, 'chuyen',
        tk_van_ban=('TIEN+214', '211 hoặc 2113 (lãi: +711; lỗ: Nợ +811)', 'TIEN+214', '211 hoặc 213 (ĐOÁN)'),
        ghi_chu='[Chốt] [Màn: Tài sản cố định, Thanh lý] Bút toán nhiều dòng, cần nguyên giá và hao mòn của chính tài sản (tscd_calc.thanh_ly_tscd). Luật chưa nói thuế GTGT khi bán tài sản.'),
    _nv('thu_khong_ro', 'Tiền về chưa biết của ai / chưa rõ lý do (chờ phân loại)', 'Nội bộ, khác & chưa rõ', 'thu', 'L01b (+L20)', 'TIEN', 'TK_CHO', 'khac', '06',
        'noi_dung*;ma_don', 12, 'co',
        ghi_chu='[Cần xác nhận M2/Q1.2] Tài khoản chờ, số dư 3388 phải về 0 khi phân loại (hệ thống đảo bút toán tạm rồi ghi lại). Dev: 22 phiếu không mã đơn (513 triệu) + 14 phiếu mã đơn lệch (106 triệu). B03 06 chỉ là tạm. Phải có số đếm 3388.'),
    _nv('thu_nhap_khac', 'Thu nhập khác (tiền phạt, tiền bồi thường nhận được)', 'Nội bộ, khác & chưa rõ', 'thu', '- (không có luật riêng)', 'TIEN', 'THU_NHAP_KHAC', 'khac', '06',
        'noi_dung*', 13, 'co',
        ghi_chu='[Khoảng trống luật, suy ra] 711 đã có trong danh mục (L12c dùng cho lãi thanh lý). Hiện nhãn Chờ kế toán xác nhận. Không dùng cho tiền khách trả hàng hay tiền vay.'),
    _nv('chuyen_noi_bo', 'Chuyển tiền giữa hai quỹ (rút, nộp, chuyển ngân hàng)', 'Nội bộ, khác & chưa rõ', 'thu', 'L10', 'TIEN', 'TIEN_DOI_UNG', 'noi_bo', '',
        'quy_doi_ung*;noi_dung', 14, 'co',
        ghi_chu='[Chốt, Q10.1 không dùng TK 113] Chiều thu: quỹ đang chọn là quỹ NHẬN, ô Quỹ chuyển bắt buộc. Lưu gọi POST /api/so-quy/chuyen-noi-bo (ghi cặp hai dòng cùng ref_id, kiểm đủ số dư), KHÔNG POST /api/so-quy. Một bút toán cho cả cặp. Không lên B03. Dev: 26 cặp, 1.551 triệu mỗi chiều.'),
    _nv('khac_thu_chon_tk', 'Khác: tự chọn tài khoản đối ứng (chỉ CEO/admin)', 'Nội bộ, khác & chưa rõ', 'thu', '- (ngoài 58 luật)', 'TIEN', 'TK_DOI_UNG', 'khac', '06',
        'tk_doi_ung*;noi_dung*', 15, 'an',
        ghi_chu='[GĐ2, mặc định TẮT] Chỉ bật nếu giám đốc đồng ý (xem mục 7). Chỉ admin/ceo/assistant_ceo; chỉ chọn trong danh sách trắng; lưu TÊN LOGIC tài khoản, không lưu mã chữ số. Không chọn được 128/228/153 vì chưa có trong danh mục.'),
    _nv('hoan_tien_khach', 'Hoàn tiền cho khách (trả thừa, huỷ cọc, chưa ghi doanh thu)', 'Tiền của khách', 'chi', 'L05', 'PHAI_THU_KH', 'TIEN', 'khac', '07',
        'ma_don*;ly_do*;noi_dung', 1, 'co',
        ghi_chu='[Cần xác nhận] 5 khoản, 65,12 triệu đang nhập như chi phí (rơi vào 811) chuyển sang đây. ly_do = tra_thua | huy_coc. API chặn hoàn quá số đã thu của đơn (422). B03 07 là ĐOÁN (app chưa có khoá riêng). Không dùng cho trả hàng/giảm giá sau bán.'),
    _nv('hoan_tien_tra_hang_giam_gia', 'Hoàn tiền / giảm giá cho đơn ĐÃ hoàn thành (trả hàng, giảm giá sau bán)', 'Tiền của khách', 'chi', 'L05', None, None, 'khac', '07',
        'ma_don*;ly_do*', 2, 'an',
        tk_van_ban=('511+3331 (bước 1); 131 (bước 2)', '131 (bước 1); TIEN (bước 2)', '521+3331 (bước 1; ĐOÁN); 131 (bước 2)', '131 (bước 1); TIEN (bước 2)'),
        ghi_chu='[Cần xác nhận] Hai bút toán, phải tách VAT; nút Hoàn tiền khách chưa tồn tại (kế hoạch Bước 4). Ẩn. Đây là chỗ TT133 (Nợ 511, bỏ 521) khác TT99 (Nợ 521, ĐOÁN).'),
    _nv('tra_ncc_ngoai_cong_no', 'Trả tiền nhà cung cấp (trả trước / ngoài công nợ)', 'Nhà cung cấp & hàng', 'chi', 'L07', 'PHAI_TRA_NCC', 'TIEN', 'tra_ncc', '02',
        'ncc*;ma_don;noi_dung', 3, 'co',
        ghi_chu='[Chốt Q7.1] Nhà cung cấp chọn từ danh sách Mua hàng, lưu mã NCC. Phiếu tay làm giảm 331 trên sổ cái nhưng KHÔNG giảm công nợ Mua hàng (da_chi). Nếu NCC đang nợ thực > 0 thì cảnh báo cam kèm nút mở Ghi nhận trả; vẫn cho lưu nếu người dùng xác nhận là trả trước.'),
    _nv('tra_ncc_cong_no', 'Trả nhà cung cấp theo công nợ / đề xuất đã có', 'Nhà cung cấp & hàng', 'chi', 'L07', 'PHAI_TRA_NCC', 'TIEN', 'tra_ncc', '02',
        '', 4, 'chuyen',
        ghi_chu='[Chốt] [Màn: hộp Ghi nhận trả (Đề xuất NCC / Đề nghị TT / Trả công nợ)] Đường chính của 88 dòng, 1.977 triệu từ 01/05. Các nút đó vừa ghi sổ quỹ vừa trừ nợ Mua hàng nên phải đi qua đó.'),
    _nv('mua_hang_nhap_kho', 'Mua hàng nhập kho trả ngay (không gắn đơn, không qua công nợ)', 'Nhà cung cấp & hàng', 'chi', 'L06b', 'KHO', 'TIEN', 'tra_ncc', '02',
        'ncc;noi_dung', 5, 'chuyen',
        ghi_chu='[Chốt] [Màn: Kho, nhập kho tay] Cần phiếu nhập kho. Hàng về theo đơn do Mua hàng đẩy sang rồi trả bằng tra_ncc_*, KHÔNG dùng mục này. Dev: 0 dòng.'),
    _nv('chi_phi_ban_hang', 'Chi phí bán hàng (xăng dầu, kho, điện nước, internet, vật tư đóng hàng)', 'Chi phí', 'chi', 'L08a', 'CP_BAN_HANG', 'TIEN', 'khac', '07',
        'noi_dung*;ma_don', 6, 'co',
        ghi_chu='[Chốt] Có hay không có mã đơn đều 6421. Dev 01/05: xăng 16 dòng ~44 triệu, điện nước+internet 17 dòng ~42 triệu, vật tư 15 dòng ~18 triệu. Phiếu quỹ tay KHÔNG vào báo cáo kết quả kinh doanh cũ (N07): cần giám đốc quyết, xem mục 7. B03 07 giữ như báo cáo hiện gom; thông lệ có thể 02 (ĐOÁN).'),
    _nv('chi_phi_quan_ly', 'Chi phí quản lý (văn phòng, thuê nhà theo tháng, tuyển dụng, phần mềm, tiếp khách)', 'Chi phí', 'chi', 'L08a', 'CP_QUAN_LY', 'TIEN', 'khac', '07',
        'noi_dung*', 7, 'co',
        ghi_chu='[Chốt] Khoá quyết định 6422; KHÔNG nhận ma_don (có mã đơn thì luật L08a đưa sang 6421: API trả 422 bảo chọn chi_phi_ban_hang hoặc chi_van_chuyen_theo_don). Dev: văn phòng khác 44 dòng 188,9 triệu, Khối VP 16 dòng 151,8 triệu. Cùng lưu ý báo cáo như chi_phi_ban_hang.'),
    _nv('chi_van_chuyen_theo_don', 'Chi vận chuyển / chi theo mã đơn (thuê ship ngoài)', 'Chi phí', 'chi', 'L07 (ngoại lệ ĐVVC) + L08a', 'CP_BAN_HANG', 'TIEN', 'tra_ncc', '02',
        'ma_don*;noi_dung', 8, 'co',
        ghi_chu='[Chốt] Không qua kho 156. Dev: 25 dòng, 37 triệu. Nếu đơn vị vận chuyển đã có công nợ phải trả thì chọn tra_ncc_ngoai_cong_no hoặc tra_ncc_cong_no. B03 02 theo cách app ghi cước ĐVVC (ĐOÁN).'),
    _nv('nap_vi_quang_cao', 'Nạp tiền ví quảng cáo / công cụ AI', 'Chi phí', 'chi', 'L08c1', 'VI_QUANG_CAO', 'TIEN', 'nap_ads', '02',
        'ky;noi_dung*', 9, 'co',
        ghi_chu='[Chốt Q8.2 cách A] Dev: 35 dòng, 572 triệu (có 9 dòng AI ~15,5 triệu cần quyết là ví quảng cáo hay phần mềm). Nạp ví CHƯA là chi phí; hằng tháng Nợ 6421/Có 1388 theo chi phí thực dùng (L08c2, bước khác).'),
    _nv('phi_ngan_hang', 'Phí ngân hàng (quản lý tài khoản, chuyển khoản, rút tiền)', 'Chi phí', 'chi', 'L15a', 'CP_QUAN_LY', 'TIEN', 'khac', '07',
        'noi_dung', 10, 'co',
        ghi_chu='[Cần xác nhận Q15.1: 6422 hay 635] Dev: 30 dòng, tổng 1,55 triệu, hiện lẫn trong Chi phí văn phòng khác. Đổi sang 635 chỉ sửa một ô trong bảng tài khoản logic.'),
    _nv('chi_phi_tai_chinh', 'Chi phí tài chính khác (không phải lãi vay)', 'Chi phí', 'chi', 'L08a', 'CP_TAI_CHINH', 'TIEN', 'khac', '07',
        'noi_dung*', 11, 'co',
        ghi_chu='[Chốt] Nhóm tai_chinh của chi phí. Lãi vay đi qua màn Khoản vay; phí ngân hàng là nghiệp vụ riêng.'),
    _nv('chi_khac_811', 'Chi phí khác (bất thường, chưa xếp được nhóm nào)', 'Chi phí', 'chi', 'L08a', 'CP_KHAC', 'TIEN', 'khac', '07',
        'noi_dung*', 12, 'co',
        ghi_chu='[Chốt Q8.1] Cố ý để thấp trong danh sách: dev cho thấy đang là túi rác (25 dòng, 554 triệu: chuyển giám đốc, thuê nhà, vay ACB, lương). Nhãn ghi rõ: không dùng cho trả nợ vay, hoàn tiền khách, chuyển tiền giám đốc.'),
    _nv('chi_phi_tra_truoc_242', 'Trả một lần cho nhiều tháng (thuê showroom/kho, bảo hiểm cả năm)', 'Chi phí', 'chi', 'L13a', 'CHI_PHI_TRA_TRUOC', 'TIEN', 'tra_ncc', '02',
        'ky;tk_chi_phi_dich', 13, 'chuyen',
        ghi_chu='[Cần xác nhận Q13.1/Q13.2] [Màn: Chi phí chờ phân bổ] Phải sinh lịch phân bổ hằng tháng Nợ 6421/6422 / Có 242. Hai lần thuê 127,5 triệu cho 3 tháng (11/06, 17/09) hợp với 242. B03 02 là ĐOÁN.'),
    _nv('tra_luong', 'Trả lương nhân viên', 'Nhân viên', 'chi', 'L09a2', 'PHAI_TRA_NLD', 'TIEN', 'tra_luong', '03',
        'ky*;nhan_vien;noi_dung', 14, 'co',
        ghi_chu='[Chốt Q9.1; nguồn số lương M3 còn mở] ky mặc định tháng trước; nhan_vien bỏ trống nếu trả gộp. Dev: 30 dòng, 881,6 triệu. KHÔNG dùng cho ứng lương. Thiếu số dư đầu kỳ 334 thì 334 dư Nợ bất thường.'),
    _nv('ung_luong', 'Ứng lương cho nhân viên (trừ thẳng vào lương)', 'Nhân viên', 'chi', 'L09b (giám đốc chốt 01/10: Nợ 334)', 'PHAI_TRA_NLD', 'TIEN', 'tra_luong', '03',
        'nhan_vien*;ky*;noi_dung', 15, 'co',
        ghi_chu='[Chốt — giám đốc chốt 01/10: ứng lương Nợ 334] Thay hàng tam_ung_luong (Nợ 141, chuyển màn Tạm ứng): ứng lương ghi Nợ 334 / Có TIEN, trừ thẳng vào lương, KHÔNG qua 141, nên lập tay được ở hộp này. ky = tháng lương sẽ trừ (mặc định tháng hiện tại); nhan_vien chọn từ danh sách nhân viên. Dev: 4-5 dòng, 18-19 triệu đang nhập ở màn Chi phí. B03 03 là ĐOÁN. Tạm ứng công việc (141) vẫn ở màn Tạm ứng.'),
    _nv('tam_ung_cong_viec', 'Tạm ứng cho nhân viên đi làm việc công ty (chờ quyết toán)', 'Nhân viên', 'chi', 'L09b', 'TAM_UNG', 'TIEN', 'khac', '07',
        'nhan_vien*;noi_dung*', 16, 'chuyen',
        ghi_chu='[Cần xác nhận Q9.2] [Màn: Tạm ứng] Quyết toán sinh bút toán nhiều vế (Nợ chi phí / Có 141). B03 07 là ĐOÁN.'),
    _nv('nop_bhxh', 'Nộp bảo hiểm xã hội (BHXH, BHYT, BHTN)', 'Thuế & bảo hiểm', 'chi', 'L09c', 'BHXH_NOP', 'TIEN', 'tra_luong', '03',
        'ky*;noi_dung', 17, 'co',
        ghi_chu='[Cần xác nhận Q9.4] Dev: 5 dòng, 84,3 triệu. Nợ 3383 chỉ đúng khi 3383 đã được trích từ lương; chưa chốt cách trích thì 3383 dư Nợ (phương án khác: 6422 như hiện nay). Đổi một ô trong bảng tài khoản logic. Công đoàn 3382 chưa có trong danh mục.'),
    _nv('nop_thue_gtgt', 'Nộp thuế GTGT', 'Thuế & bảo hiểm', 'chi', 'L14b', 'THUE_GTGT', 'TIEN', 'khac', '07',
        'ky*;noi_dung', 18, 'co',
        ghi_chu='[Cần xác nhận Q14.3, M4] Không màn nào ghi nộp thuế nên hộp phiếu là nơi hợp lý. Không có phiếu nộp thì 3331 chỉ tăng. Tiền Thuế 3 dòng 18,3 triệu (thuế HKD) hiện là chi phí quản lý, kế toán cho biết thuế gì.'),
    _nv('nop_thue_tncn', 'Nộp thuế thu nhập cá nhân (đã giữ lại từ lương)', 'Thuế & bảo hiểm', 'chi', 'L14b (+L09c)', 'THUE_TNCN', 'TIEN', 'khac', '07',
        'ky*;noi_dung', 19, 'co',
        ghi_chu='[Cần xác nhận] 3335 tăng khi trích từ lương (màn Thuế TNCN). B03 07 theo nhãn khac; có thể xếp 03 (ĐOÁN).'),
    _nv('nop_thue_tndn', 'Nộp thuế thu nhập doanh nghiệp', 'Thuế & bảo hiểm', 'chi', 'L14b (trích: L18)', 'THUE_TNDN', 'TIEN', 'nop_thue_tndn', '05',
        'ky*;noi_dung', 20, 'co',
        ghi_chu='[Cần xác nhận] Trích thuế Nợ 821/Có 3334 đã Chốt (L18); chưa trích mà đã nộp thì 3334 dư Nợ. B03 05.'),
    _nv('tra_goc_vay', 'Trả nợ gốc vay', 'Vay, vốn & tài chính', 'chi', 'L11b', 'VAY', 'TIEN', 'tra_nh', '34',
        'khoan_vay*', 21, 'chuyen',
        ghi_chu='[Chốt] [Màn: Khoản vay, Trả nợ] Phiếu tay không giảm dư nợ gốc. Dev 01/05: 2 dòng, 685,7 triệu. Khoản Thanh toán vay ACB 95 triệu đang ở Chi phí khác cần tách gốc/lãi ở màn này. TT99 = 341: ĐOÁN.'),
    _nv('tra_lai_vay', 'Trả lãi vay', 'Vay, vốn & tài chính', 'chi', 'L11c', 'LAI_VAY', 'TIEN', 'tra_lai_vay', '04',
        'khoan_vay*', 22, 'chuyen',
        ghi_chu='[Chốt; L11d trích trước 335 còn Mở] [Màn: Khoản vay, Trả nợ] Màn tách gốc/lãi và tránh ghi 635 hai lần (trả lãi còn tạo dòng chi phí Lãi vay). Dev: 8 dòng, 95,8 triệu, đang bị ghi như chi phí hoặc mang mã tra_nh (sai).'),
    _nv('rut_von', 'Chủ sở hữu rút vốn / trả lại vốn góp', 'Vay, vốn & tài chính', 'chi', 'L17', 'VON_CSH', 'TIEN', 'tra_von', '32',
        '', 23, 'chuyen',
        ghi_chu='[Cần xác nhận] [Màn: Vốn chủ sở hữu, Rút vốn] Xoá bản ghi vốn hiện không đảo bút toán và không xoá dòng sổ quỹ, nên không tạo rời bằng phiếu tay.'),
    _nv('chia_co_tuc', 'Chia cổ tức / lợi nhuận cho chủ sở hữu', 'Vay, vốn & tài chính', 'chi', 'L17', None, None, 'chia_co_tuc', '36',
        'ky', 24, 'chuyen',
        tk_van_ban=('4211 hoặc 4212', 'TIEN', '421', 'TIEN'),
        ghi_chu='[Cần xác nhận] [Màn: Vốn chủ sở hữu / Phân phối lợi nhuận, Chia cổ tức] 4211/4212 cần kế toán xác nhận với văn bản gốc. Luật chưa nói thuế TNCN khấu trừ trên cổ tức.'),
    _nv('chi_cho_vay', 'Cho vay / mua công cụ nợ của đơn vị khác', 'Vay, vốn & tài chính', 'chi', '- (luật KHÔNG có)', None, None, 'chi_cho_vay', '23',
        'noi_dung*', 25, 'an',
        tk_van_ban=('128 (ĐOÁN)', 'TIEN', '128 (ĐOÁN)', 'TIEN'),
        ghi_chu='[Khoảng trống luật] Ẩn: chưa có màn và luật; journal.py chưa có 128. Tạm dùng chi_khong_ro.'),
    _nv('chi_gop_von', 'Góp vốn / đầu tư vào đơn vị khác', 'Vay, vốn & tài chính', 'chi', '- (luật KHÔNG có)', None, None, 'chi_gop_von', '25',
        'noi_dung*', 26, 'an',
        tk_van_ban=('228 (ĐOÁN)', 'TIEN', '228 (ĐOÁN)', 'TIEN'),
        ghi_chu='[Khoảng trống luật] Ẩn như chi_cho_vay.'),
    _nv('mua_tscd', 'Mua tài sản cố định', 'Tài sản', 'chi', 'L12a', None, None, 'mua_ccdc', '21',
        'tai_san*', 27, 'chuyen',
        tk_van_ban=('211 (hữu hình) hoặc 2113 (vô hình)', 'TIEN', '211 hoặc 213 (ĐOÁN)', 'TIEN'),
        ghi_chu='[Chốt] [Màn: Tài sản cố định, Thêm tài sản] Cần bản ghi tài sản (nguyên giá, số tháng) để chạy khấu hao Nợ 6421/6422 / Có 214; phiếu tay Nợ 211 không có bản ghi thì không khấu hao được. Dev: 2 tài sản, 1.699,5 triệu.'),
    _nv('sua_chua_lon_tscd', 'Sửa chữa lớn tài sản cố định', 'Tài sản', 'chi', '- (luật KHÔNG có)', None, None, 'sua_chua_lon', '21',
        'tai_san;noi_dung', 28, 'an',
        tk_van_ban=('242 | 211 | 6422 (ĐOÁN, CHƯA KIỂM)', 'TIEN', 'như TT133 (ĐOÁN)', 'TIEN'),
        ghi_chu='[Khoảng trống luật] Ẩn. Khoá sua_chua_lon có sẵn trong phan_loai_cf.py (B03 21) nhưng luật chưa nói tài khoản.'),
    _nv('mua_ccdc', 'Mua công cụ dụng cụ', 'Tài sản', 'chi', '- (luật KHÔNG có)', None, None, 'mua_ccdc', '21',
        'noi_dung', 29, 'an',
        tk_van_ban=('242 | 6421/6422 | 153 (ĐOÁN, CHƯA KIỂM)', 'TIEN', 'như TT133 (ĐOÁN)', 'TIEN'),
        ghi_chu='[Khoảng trống luật] Ẩn. 153 chưa có trong danh mục. Công cụ nhỏ tạm dùng chi_phi_quan_ly hoặc chi_phi_ban_hang.'),
    _nv('chuyen_noi_bo', 'Chuyển tiền giữa hai quỹ (rút, nộp, chuyển ngân hàng)', 'Nội bộ, khác & chưa rõ', 'chi', 'L10', 'TIEN_DOI_UNG', 'TIEN', 'noi_bo', '',
        'quy_doi_ung*;noi_dung', 30, 'co',
        ghi_chu="[Chốt, Q10.1] Chiều chi: quỹ đang chọn là quỹ CHUYỂN, ô Quỹ nhận bắt buộc (khác quỹ chính). Lưu gọi POST /api/so-quy/chuyen-noi-bo, ghi ma_dinh_khoan='chuyen_noi_bo' lên cả hai dòng và phan_loai_cf='noi_bo' (hiện ghi khac). Replay gom cặp theo ref_id thành MỘT bút toán."),
    _nv('chi_khong_ro', 'Tiền ra chưa rõ trả cho ai / việc gì (chờ phân loại)', 'Nội bộ, khác & chưa rõ', 'chi', 'L07b', 'TK_CHO', 'TIEN', 'khac', '07',
        'noi_dung*', 31, 'co',
        ghi_chu='[Cần xác nhận M2] Tài khoản chờ, phân loại xong hệ thống đảo rồi ghi lại. B03 07 là tạm. Dev: 5 dòng, 177,4 triệu (vd Trả nợ HD 022025 100 triệu). Phải có số đếm 3388.'),
    _nv('chi_cho_giam_doc', 'Chi / chuyển tiền cho giám đốc hoặc chủ sở hữu (chưa rõ bản chất)', 'Nội bộ, khác & chưa rõ', 'chi', '- (luật MỞ: M6/E11)', 'TK_CHO', 'TIEN', 'khac', '07',
        'noi_dung*', 32, 'co',
        ghi_chu='[Mở] Dev: 12 dòng, 198,95 triệu hiện nhập như chi phí. Luật yêu cầu giám đốc nói bản chất (141/1388 | 411 | 3411) rồi mới chọn tài khoản; trong lúc chờ ghi tạm 3388 để tách khỏi chi phí. Chiều ngược (giám đốc nộp tiền vào) dùng thu_khong_ro.'),
    _nv('khac_chi_chon_tk', 'Khác: tự chọn tài khoản đối ứng (chỉ CEO/admin)', 'Nội bộ, khác & chưa rõ', 'chi', '- (ngoài 58 luật)', 'TK_DOI_UNG', 'TIEN', 'khac', '07',
        'tk_doi_ung*;noi_dung*', 33, 'an',
        ghi_chu='[GĐ2, mặc định TẮT] Như khac_thu_chon_tk. Danh sách trắng chiều chi gợi ý: 3388, 6421, 6422, 635, 811, 331, 334, 1388, 3331, 3334, 3335, 3383.'),
)

# Thứ tự nhóm trong ô chọn (<optgroup>); trong nhóm sắp theo thu_tu.
NHOM_THU_TU: tuple[str, ...] = (
    "Tiền của khách", "Nhà cung cấp & hàng", "Chi phí", "Nhân viên", "Thuế & bảo hiểm",
    "Vay, vốn & tài chính", "Tài sản", "Nội bộ, khác & chưa rõ",
)

# Nút "Hay dùng" trên ô chọn (khoá, nhãn ngắn). Chi: theo tần suất dev + ứng lương (quyết định 01/10).
HAY_DUNG: dict[str, tuple[tuple[str, str], ...]] = {
    "chi": (("tra_ncc_ngoai_cong_no", "Trả nhà cung cấp"), ("tra_luong", "Trả lương"),
            ("nap_vi_quang_cao", "Nạp ví quảng cáo"), ("phi_ngan_hang", "Phí ngân hàng"), ("ung_luong", "Ứng lương")),
    "thu": (("thu_coc", "Khách đặt cọc"), ("thu_khach_thanh_toan", "Khách trả tiền hàng")),
}


class ManRieng(NamedTuple):
    ten: str
    url: str      # route trang có thật (mục sidebar trong templates/_header.html)
    ly_do: str


# Nghiệp vụ 'chuyen': lập ở màn nào, vì sao không lập tay (đặc tả mục 2.3).
MAN_RIENG: dict[str, ManRieng] = {
    "thu_cong_no_khach": ManRieng("Công nợ khách hàng (hộp Ghi nhận thu)", "/ketoan/cong-no-kh",
                                  "Hộp đó vừa trừ công nợ của khách vừa ghi sổ quỹ; phiếu tay không trừ nợ."),
    "tra_ncc_cong_no": ManRieng("Công nợ nhà cung cấp (hộp Ghi nhận trả)", "/ketoan/cong-no-ncc",
                                "Các nút ở đó vừa ghi sổ quỹ vừa trừ công nợ Mua hàng."),
    "mua_hang_nhap_kho": ManRieng("Tồn kho (nhập kho)", "/ketoan/ton-kho", "Cần phiếu nhập kho để hàng vào kho."),
    "thu_giai_ngan_vay": ManRieng("Khoản vay", "/ketoan/khoan-vay", "Cần bản ghi khoản vay để có lịch trả gốc và lãi."),
    "tra_goc_vay": ManRieng("Khoản vay (Trả nợ)", "/ketoan/khoan-vay", "Phiếu tay không làm giảm dư nợ gốc của khoản vay."),
    "tra_lai_vay": ManRieng("Khoản vay (Trả nợ)", "/ketoan/khoan-vay",
                            "Màn đó tách gốc và lãi, tránh ghi chi phí lãi vay hai lần."),
    "thu_hoan_ung": ManRieng("Tạm ứng (quyết toán)", "/ketoan/tam-ung",
                             "Màn Tạm ứng kiểm kỳ chốt, đủ tiền và đảo bút toán khi sửa."),
    "tam_ung_cong_viec": ManRieng("Tạm ứng", "/ketoan/tam-ung", "Tạm ứng phải quyết toán sau, sinh bút toán nhiều dòng."),
    "thu_gop_von": ManRieng("Vốn chủ sở hữu (Góp vốn)", "/ketoan/phan-phoi-ln", "Phiếu tay không cập nhật bảng vốn."),
    "rut_von": ManRieng("Vốn chủ sở hữu (Rút vốn)", "/ketoan/phan-phoi-ln",
                        "Bảng vốn chỉ cập nhật qua màn đó; phiếu tay làm lệch số vốn."),
    "chia_co_tuc": ManRieng("Phân phối lợi nhuận (Chia cổ tức)", "/ketoan/phan-phoi-ln",
                            "Tài khoản 4211/4212 cần kế toán xác nhận."),
    "thu_thanh_ly_tscd": ManRieng("Phiếu tài sản cố định (Thanh lý)", "/ketoan/tscd/phieu",
                                  "Bút toán nhiều dòng, cần nguyên giá và hao mòn của tài sản."),
    "mua_tscd": ManRieng("Phiếu tài sản cố định (Ghi tăng)", "/ketoan/tscd/phieu", "Cần bản ghi tài sản để chạy khấu hao."),
    "chi_phi_tra_truoc_242": ManRieng("Chi phí chờ phân bổ", "/ketoan/phan-bo", "Phải sinh lịch phân bổ chi phí hằng tháng."),
}

_CB_CHO = "Khoản chờ phân loại (tài khoản 3388) — kế toán sẽ xếp lại sau."
_CB_CHI_PHI = ("Khoản này đã nhập ở màn Doanh thu & Chi phí chưa? Màn đó tự ghi sổ quỹ rồi — đừng lập thêm phiếu ở đây. "
               "Phiếu quỹ tay chưa vào báo cáo kết quả kinh doanh.")
# Cảnh báo mềm (không chặn lưu) — đặc tả mục 3.4.
CANH_BAO: dict[str, str] = {
    "thu_khong_ro": _CB_CHO, "chi_khong_ro": _CB_CHO, "chi_cho_giam_doc": _CB_CHO,
    "chi_phi_ban_hang": _CB_CHI_PHI, "chi_phi_quan_ly": _CB_CHI_PHI, "chi_phi_tai_chinh": _CB_CHI_PHI,
    "phi_ngan_hang": _CB_CHI_PHI,
    "chi_khac_811": _CB_CHI_PHI + " Không dùng cho trả nợ vay, hoàn tiền khách, chuyển tiền giám đốc.",
    "thu_khach_thanh_toan": ("Phiếu này KHÔNG trừ công nợ phải thu. Đơn đã có khoản phải thu ở Công nợ khách hàng "
                             "thì thu ở hộp Ghi nhận thu."),
    "tra_ncc_ngoai_cong_no": ("Phiếu này KHÔNG làm giảm công nợ Mua hàng. Đã có đề xuất / công nợ thì chi từ hộp "
                              "Ghi nhận trả ở Công nợ NCC."),
    "ung_luong": "Ứng lương ghi thẳng Nợ 334 (giám đốc chốt 01/10) — tháng lương đã chọn sẽ trừ khoản này.",
}

# Kỳ mặc định ở giao diện: lương, bảo hiểm, thuế = tháng trước; nạp ví quảng cáo, ứng lương = tháng này.
KY_MAC_DINH: dict[str, str] = {
    "tra_luong": "thang_truoc", "nop_bhxh": "thang_truoc", "nop_thue_gtgt": "thang_truoc",
    "nop_thue_tncn": "thang_truoc", "nop_thue_tndn": "thang_truoc",
    "nap_vi_quang_cao": "thang_nay", "ung_luong": "thang_nay",
}

NHAN_TRUONG: dict[str, str] = {
    "ma_don": "Mã đơn", "noi_dung": "Nội dung", "ncc": "Nhà cung cấp", "nhan_vien": "Nhân viên",
    "ky": "Tháng (kỳ)", "ly_do": "Lý do hoàn", "quy_doi_ung": "Quỹ đối ứng", "khoan_vay": "Khoản vay",
    "tai_san": "Tài sản", "tk_doi_ung": "Tài khoản đối ứng", "tk_chi_phi_dich": "Tài khoản chi phí phân bổ",
}
LY_DO_HOAN: dict[str, str] = {"tra_thua": "Khách trả thừa", "huy_coc": "Huỷ cọc"}

_THEO_KHOA: dict[tuple[str, str], NghiepVu] = {(x.khoa, x.loai): x for x in BANG}
_B03 = {(x.khoa, x.loai): x for x in BANG_CF}

# Lệch bảng thì dừng ngay lúc nạp module (giống _B03_MOI ở bao_cao_cashflow.py) — không để lỗi lộ ra lúc ghi phiếu.
assert len(_THEO_KHOA) == len(BANG), "Trùng cặp (khoa, loai) trong BANG"
assert all((x.b03_khoa, x.loai) in _B03 for x in BANG), "b03_khoa không có trong phan_loai_cf.py hoặc sai chiều"
assert set(MAN_RIENG) == {x.khoa for x in BANG if x.cho_phep == "chuyen"}, "MAN_RIENG lệch các hàng 'chuyen'"
assert all(tra[0] in {x.khoa for x in BANG if x.cho_phep == "co"} for v in HAY_DUNG.values() for tra in v)
assert all(x.no and x.co for x in BANG if x.cho_phep == "co"), "Hàng lập tay phải là đúng một cặp Nợ/Có"


# ─── 3. Hàm thuần ─────────────────────────────────────────────────────────────

class LoiNghiepVu(Exception):
    """Phiếu không qua kiểm. `ma` cho máy đọc (vd 'thieu_truong'), `thong_bao` là câu tiếng Việt cho người dùng,
    `them` là dữ liệu kèm (truong, man_rieng, dong…). Router đổi thành HTTPException(http, chi_tiet())."""

    def __init__(self, ma: str, thong_bao: str, http: int = 422, **them: Any):
        super().__init__(thong_bao)
        self.ma, self.thong_bao, self.http, self.them = ma, thong_bao, http, them

    def chi_tiet(self) -> dict[str, Any]:
        return {"ma": self.ma, "thong_bao": self.thong_bao, **self.them}


def tk_so(ten_logic: str, che_do: str) -> Optional[str]:
    """Số tài khoản của một tên logic theo chế độ ('tt133' | 'tt99'). None = chưa chốt số ở chế độ đó."""
    if che_do not in CHE_DO_TEN:
        raise ValueError(f"Chế độ kế toán lạ: {che_do!r}")
    tk = DANH_MUC_TK[ten_logic]
    return tk.tt133 if che_do == "tt133" else tk.tt99


def can_truong(nv: NghiepVu) -> tuple[tuple[str, bool], ...]:
    """'ma_don*;noi_dung' → (('ma_don', True), ('noi_dung', False))."""
    return tuple((p.rstrip("*"), p.endswith("*")) for p in (s.strip() for s in nv.can_truong_csv.split(";")) if p)


def trang_thai_luat(nv: NghiepVu) -> str:
    """Nhãn trạng thái luật đọc từ đầu ghi_chu: chot | can_xac_nhan | khoang_trong | mo | gd2."""
    for tien_to, ma in (("[Chốt", "chot"), ("[Cần xác nhận", "can_xac_nhan"), ("[Khoảng trống", "khoang_trong"),
                        ("[Mở", "mo"), ("[GĐ2", "gd2")):
        if nv.ghi_chu.startswith(tien_to):
            return ma
    return "khac"


def tra_nghiep_vu(khoa: str, loai: Optional[str] = None) -> Optional[NghiepVu]:
    """Hàng nghiệp vụ theo khoá (và chiều). chuyen_noi_bo có ở cả hai chiều nên nên truyền `loai`."""
    if loai:
        return _THEO_KHOA.get((khoa, loai))
    return next((x for x in BANG if x.khoa == khoa), None)


def suy_phan_loai_cf(khoa: str, loai: str) -> str:
    """Dòng tiền B03 (giá trị cột so_quy.phan_loai_cf) suy ra từ nghiệp vụ. Khoá lạ → KeyError."""
    nv = tra_nghiep_vu(khoa, loai)
    if nv is None:
        raise KeyError(f"Không có nghiệp vụ {khoa!r} cho phiếu {loai!r}")
    return nv.b03_khoa


def tk_tien_cua_quy(tk: Optional[TaiKhoanNH]) -> str:
    """Tài khoản tiền của một quỹ: tk_ke_toan đã gán (1111, 1121…), chưa gán thì 111 tiền mặt / 112 còn lại.
    Cùng luật với tai_khoan_tien.tk_tien_cua — chép lại ở đây vì file đó import fastapi (service này thì không)."""
    if tk is None:
        return "112"
    return tk.tk_ke_toan or ("111" if (tk.loai or "").strip() == "tien_mat" else "112")


def _mot_ve(ky_hieu: str, che_do: str, tk_tien: str, tk_tien_doi_ung: Optional[str],
            tk_doi_ung_logic: Optional[str]) -> str:
    if ky_hieu == TIEN:
        return tk_tien
    if ky_hieu == TIEN_DOI_UNG:
        if not tk_tien_doi_ung:
            raise ValueError("Chuyển nội bộ cần tài khoản tiền của quỹ đối ứng")
        return tk_tien_doi_ung
    if ky_hieu == TK_DOI_UNG:
        if not tk_doi_ung_logic or tk_doi_ung_logic not in DANH_MUC_TK:
            raise ValueError("Nghiệp vụ 'Khác' cần tên logic tài khoản đối ứng (tk_doi_ung)")
        ky_hieu = tk_doi_ung_logic
    so = tk_so(ky_hieu, che_do)
    if not so:
        raise ValueError(f"Tài khoản {ky_hieu} chưa có số ở chế độ {che_do}")
    return so


def tk_no_co(khoa: str, loai: str, che_do: str, tk_tien: str, tk_tien_doi_ung: Optional[str] = None,
             tk_doi_ung_logic: Optional[str] = None) -> tuple[str, str]:
    """(TK Nợ, TK Có) của MỘT bút toán. tk_tien = tài khoản tiền của quỹ trên dòng;
    tk_tien_doi_ung = của quỹ còn lại (chỉ chuyển nội bộ). Hàng không phải một cặp → ValueError."""
    nv = tra_nghiep_vu(khoa, loai)
    if nv is None:
        raise KeyError(f"Không có nghiệp vụ {khoa!r} cho phiếu {loai!r}")
    if not (nv.no and nv.co):
        raise ValueError(f"Nghiệp vụ {khoa!r} không phải một cặp Nợ/Có — lập ở màn riêng")
    return (_mot_ve(nv.no, che_do, tk_tien, tk_tien_doi_ung, tk_doi_ung_logic),
            _mot_ve(nv.co, che_do, tk_tien, tk_tien_doi_ung, tk_doi_ung_logic))


def tra_dinh_khoan(dong: Any, che_do: str, tk_tien_theo_quy: dict[str, str],
                   quy_doi_ung: Optional[str] = None) -> tuple[str, str, Decimal]:
    """Một dòng sổ quỹ đã gắn nghiệp vụ → (TK Nợ, TK Có, số tiền) của đúng MỘT bút toán.

    tk_tien_theo_quy = {ten_tk: mã TK tiền}. Quỹ không có trong danh mục → KeyError (bộ dựng lại sổ đưa vào
    danh sách ngoại lệ, không đoán). Chuyển nội bộ: cặp hai dòng cùng ref_id là MỘT bút toán — truyền quỹ của
    dòng còn lại ở `quy_doi_ung`."""
    tk_tien = tk_tien_theo_quy[dong.tai_khoan]
    tk_du = tk_tien_theo_quy[quy_doi_ung] if quy_doi_ung else None
    no, co = tk_no_co(dong.ma_dinh_khoan, dong.loai, che_do, tk_tien, tk_du, getattr(dong, "tk_doi_ung", None))
    return no, co, Decimal(dong.so_tien)


def _ten_tk(ky_hieu: Optional[str]) -> str:
    if not ky_hieu or ky_hieu in (TIEN, TIEN_DOI_UNG, TK_DOI_UNG):
        return ""          # trình duyệt thay bằng tên quỹ đang chọn
    return DANH_MUC_TK[ky_hieu].ten


def _tk_api(ky_hieu: Optional[str], che_do: str, van_ban: Optional[str]) -> str:
    if ky_hieu is None:
        return van_ban or ""
    if ky_hieu in (TIEN, TIEN_DOI_UNG, TK_DOI_UNG):
        return ky_hieu
    return tk_so(ky_hieu, che_do) or "chưa chốt"


def danh_sach(loai: str, che_do: str) -> dict[str, Any]:
    """Dữ liệu cho GET /api/so-quy/nghiep-vu?loai= — tài khoản đã chọn theo chế độ, mục 'an' không trả về."""
    if loai not in ("thu", "chi"):
        raise ValueError("loai phải là thu hoặc chi")
    ds = []
    for x in BANG:
        if x.loai != loai or x.cho_phep == "an":
            continue
        vb = x.tk_van_ban
        vb_no, vb_co = ((vb[0], vb[1]) if che_do == "tt133" else (vb[2], vb[3])) if vb else (None, None)
        m = MAN_RIENG.get(x.khoa) if x.cho_phep == "chuyen" else None
        b03 = _B03[(x.b03_khoa, x.loai)]
        tt = trang_thai_luat(x)
        ds.append({
            "khoa": x.khoa, "ten": x.ten, "nhom": x.nhom, "loai": x.loai, "thu_tu": x.thu_tu,
            "cho_phep": x.cho_phep,
            "man_rieng": {"ten": m.ten, "url": m.url, "ly_do": m.ly_do} if m else None,
            "tk_no": _tk_api(x.no, che_do, vb_no), "tk_co": _tk_api(x.co, che_do, vb_co),
            "ten_tk_no": _ten_tk(x.no), "ten_tk_co": _ten_tk(x.co),
            "b03_khoa": x.b03_khoa, "b03_ma_so": x.b03_ma_so, "b03_ten": b03.ten,
            "can_truong": [{"ten": t, "nhan": NHAN_TRUONG.get(t, t), "bat_buoc": bb} for t, bb in can_truong(x)],
            "trang_thai_luat": tt, "cho_xac_nhan": tt in ("can_xac_nhan", "khoang_trong", "mo"),
            "canh_bao": CANH_BAO.get(x.khoa), "ky_mac_dinh": KY_MAC_DINH.get(x.khoa),
        })
    vi_tri = {n: i for i, n in enumerate(NHOM_THU_TU)}
    ds.sort(key=lambda d: (vi_tri.get(d["nhom"], 99), d["thu_tu"]))
    nhom = [{"ten": n, "thu_tu": i + 1} for i, n in enumerate(NHOM_THU_TU) if any(d["nhom"] == n for d in ds)]
    return {
        "che_do": che_do, "che_do_ten": CHE_DO_TEN[che_do], "loai": loai, "nhom": nhom,
        "hay_dung": [{"khoa": k, "nhan": n} for k, n in HAY_DUNG[loai]],
        "ly_do_hoan": [{"ma": k, "nhan": v} for k, v in LY_DO_HOAN.items()],
        "nghiep_vu": ds,
    }


# ─── 4. Đọc DB (không ghi, không commit) ──────────────────────────────────────

def doc_che_do(db: Session) -> str:
    """Chế độ kế toán đang đặt (ketoan.cai_dat_he_thong.che_do). Giá trị lạ → lỗi rõ, KHÔNG âm thầm rơi về tt99."""
    gt = db.execute(text("SELECT che_do FROM ketoan.cai_dat_he_thong WHERE id = 1")).scalar()
    if gt not in CHE_DO_TEN:
        raise LoiNghiepVu("che_do_khong_hop_le",
                          f"Cài đặt kế toán đang có chế độ {gt!r} — chỉ nhận tt133 hoặc tt99. "
                          "Vào Cài đặt kế toán chọn lại chế độ rồi thử lại.", http=500)
    return gt


def _doc_ngoai(db: Session, sql: str, **p: Any) -> Optional[list[dict]]:
    """Đọc schema app khác bằng raw SQL. Không đọc được (schema chưa có / thiếu quyền) → None, KHÔNG nuốt
    thành 'không có dữ liệu': nơi gọi tự quyết bỏ qua bước kiểm và ghi cảnh báo."""
    try:
        return [dict(r._mapping) for r in db.execute(text(sql), p)]
    except (ProgrammingError, OperationalError):
        db.rollback()
        return None


def chuan_hoa_ma_don(ma_don: Optional[str]) -> Optional[str]:
    """'Nv26011-26-00122 ' → 'NV26011-26-00122'."""
    m = (ma_don or "").strip().upper()
    return m or None


def theo_don(db: Session, ma_don: str) -> dict[str, Any]:
    """Tên khách + đã thu / đã hoàn / còn lại của một mã đơn (GET /api/so-quy/theo-don/{ma_don}).

    da_thu = doanh_thu theo mã đơn (Báo giá / Duyệt cọc — mỗi dòng đã có dòng sổ quỹ lien_quan='doanh_thu', nên
    không cộng lại phía sổ quỹ) + phiếu thu sổ quỹ theo mã đơn KHÔNG đến từ doanh_thu (SePay, phiếu tay).
    Không dùng một mình so_quy.ma_don: phần lớn dòng thu không có cột này."""
    m = chuan_hoa_ma_don(ma_don)
    bg = _doc_ngoai(db, "SELECT quote_number, customer_id, customer_name, tong_don FROM baogia.quotes "
                        "WHERE upper(quote_number) = :m ORDER BY id DESC LIMIT 1", m=m)
    q = bg[0] if bg else None
    dt = db.execute(text("SELECT COALESCE(SUM(so_tien), 0), COUNT(*) FROM ketoan.doanh_thu WHERE upper(ma_don) = :m"),
                    {"m": m}).one()
    sq = db.execute(
        select(func.coalesce(func.sum(SoQuy.so_tien), 0), func.count(SoQuy.id)).where(
            func.upper(SoQuy.ma_don) == m, SoQuy.loai == "thu",
            func.coalesce(SoQuy.lien_quan, "") != "doanh_thu",
        )
    ).one()
    hoan = db.execute(
        select(func.coalesce(func.sum(SoQuy.so_tien), 0)).where(
            func.upper(SoQuy.ma_don) == m, SoQuy.loai == "chi", SoQuy.ma_dinh_khoan == "hoan_tien_khach",
        )
    ).scalar()
    da_thu = Decimal(dt[0]) + Decimal(sq[0])
    da_hoan = Decimal(hoan or 0)
    tong = Decimal(q["tong_don"]) if q and q.get("tong_don") is not None else None
    return {
        "ma_don": m,
        "co_bao_gia": q is not None,
        "doc_duoc_bao_gia": bg is not None,
        "khach": q.get("customer_name") if q else None,
        "khach_id": str(q["customer_id"]) if q and q.get("customer_id") is not None else None,
        "tong_don": tong,
        "da_thu": da_thu,
        "da_hoan": da_hoan,
        "con_lai": (tong - da_thu + da_hoan) if tong is not None else None,
        "so_phieu": int(dt[1]) + int(sq[1]),
    }


def phieu_da_co(db: Session, ref_id: Optional[str]) -> Optional[SoQuy]:
    """Phiếu lập tay đã ghi với cùng ref_id (bấm Lưu hai lần) → trả lại dòng cũ, không ghi thêm."""
    if not ref_id:
        return None
    return db.execute(
        select(SoQuy).where(SoQuy.lien_quan == "nhap_tay", SoQuy.ref_id == ref_id)
    ).scalars().first()


_MAU_KY = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _so_tien(v: Any) -> Optional[Decimal]:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d.is_finite() else None


def chuan_bi_phieu(db: Session, f: dict[str, Any], che_do: str) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Kiểm một phiếu lập tay CÓ ma_dinh_khoan (thứ tự mã lỗi theo đặc tả 4.3) → (cột để ghi, định khoản xem
    trước, cảnh báo mềm). Sai → LoiNghiepVu. Không ghi DB, không commit, không gọi post_journal."""
    loai = f.get("loai")
    khoa = (f.get("ma_dinh_khoan") or "").strip()
    nv = tra_nghiep_vu(khoa, loai)
    khac_chieu = None if nv else tra_nghiep_vu(khoa)
    goc = nv or khac_chieu
    if goc is None or goc.cho_phep == "an":
        raise LoiNghiepVu("ma_dinh_khoan_khong_hop_le",
                          "Việc đã chọn không có trong danh sách. Đóng hộp, mở lại rồi chọn việc khác.")
    if goc.cho_phep == "chuyen":
        m = MAN_RIENG[goc.khoa]
        raise LoiNghiepVu("nghiep_vu_phai_lap_o_man_khac", f"“{goc.ten}” phải lập ở màn {m.ten}. {m.ly_do}",
                          man_rieng={"ten": m.ten, "url": m.url})
    if nv is None:
        raise LoiNghiepVu("sai_chieu", f"“{goc.ten}” dùng cho phiếu {goc.loai}, không dùng cho phiếu {loai}. "
                                       "Đổi loại phiếu hoặc chọn việc khác.")
    if nv.khoa == "chuyen_noi_bo":
        raise LoiNghiepVu("dung_endpoint_chuyen_noi_bo",
                          "Chuyển tiền giữa hai quỹ ghi cùng lúc hai dòng — lưu bằng POST /api/so-quy/chuyen-noi-bo.")
    if (f.get("lien_quan") or "nhap_tay") != "nhap_tay":
        raise LoiNghiepVu("lien_quan_khong_hop_le", "Phiếu lập tay luôn có nguồn 'Nhập tay' — bỏ ô Liên quan rồi lưu lại.")

    ct = can_truong(nv)
    co_truong = {t for t, _ in ct}
    ma_don = chuan_hoa_ma_don(f.get("ma_don"))
    noi_dung = (f.get("noi_dung") or "").strip() or None
    ky = (f.get("ky") or "").strip() or None
    ly_do = (f.get("ly_do") or "").strip() or None
    dt_loai = (f.get("doi_tuong_loai") or "").strip() or None
    ncc_ma = (f.get("doi_tuong_ma") or "").strip() or None if dt_loai in (None, "ncc") else None
    nv_id = f.get("nhan_vien_id") or None
    gia_tri = {"ma_don": ma_don, "noi_dung": noi_dung, "ncc": ncc_ma, "nhan_vien": nv_id, "ky": ky, "ly_do": ly_do}
    thieu = [t for t, bb in ct if bb and not gia_tri.get(t)]
    if thieu:
        raise LoiNghiepVu("thieu_truong", "Còn thiếu: " + ", ".join(NHAN_TRUONG.get(t, t) for t in thieu) + ".",
                          truong=thieu)

    so_tien = _so_tien(f.get("so_tien"))
    if so_tien is None or so_tien <= 0:
        raise LoiNghiepVu("so_tien_phai_duong", "Số tiền phải là số lớn hơn 0.", truong=["so_tien"])

    quy = db.execute(
        select(TaiKhoanNH).where(TaiKhoanNH.ten_tk == (f.get("tai_khoan") or ""), TaiKhoanNH.active.is_(True))
    ).scalars().first()
    if quy is None:
        raise LoiNghiepVu("quy_khong_hop_le", "Tài khoản / quỹ không có trong danh mục quỹ đang dùng. Chọn lại quỹ.",
                          truong=["tai_khoan"])

    canh_bao: list[str] = []
    if ma_don and "ma_don" not in co_truong:
        if nv.khoa == "chi_phi_quan_ly":
            msg = ("Chi phí quản lý không gắn mã đơn. Chi cho một đơn cụ thể thì chọn “Chi phí bán hàng” "
                   "hoặc “Chi vận chuyển / chi theo mã đơn”.")
        else:
            msg = f"“{nv.ten}” không gắn mã đơn — bỏ mã đơn hoặc chọn việc khác."
        raise LoiNghiepVu("ma_don_khong_nhan", msg, truong=["ma_don"])
    bao_gia = None
    if ma_don:
        td = theo_don(db, ma_don)
        if not td["doc_duoc_bao_gia"]:
            canh_bao.append("Chưa kiểm được mã đơn: không đọc được dữ liệu Báo giá.")
        elif not td["co_bao_gia"] and nv.khoa == "thu_khong_ro":
            # Chính là chỗ chứa tiền về mang mã đơn lệch (dev: 14 phiếu) — giữ mã để kế toán phân loại sau, không chặn.
            canh_bao.append(f"Mã đơn {ma_don} chưa có báo giá — giữ nguyên để kế toán phân loại sau.")
        elif not td["co_bao_gia"]:
            goi_y =("Tiền về chưa rõ của đơn nào thì chọn “Tiền về chưa biết của ai”."
                     if loai == "thu" else "Kiểm tra lại mã đơn.")
            raise LoiNghiepVu("ma_don_khong_khop", f"Không có báo giá mã {ma_don}. {goi_y}", truong=["ma_don"],
                              goi_y="thu_khong_ro" if loai == "thu" else None)
        else:
            bao_gia = td
        if nv.khoa == "hoan_tien_khach" and bao_gia is not None:
            con = bao_gia["da_thu"] - bao_gia["da_hoan"]
            if so_tien > con:
                raise LoiNghiepVu("hoan_vuot_so_da_thu",
                                  f"Đơn {ma_don} mới thu {con:,.0f} đ (đã trừ phần đã hoàn) — không hoàn quá số đó."
                                  .replace(",", "."), truong=["so_tien"])

    if ky and not _MAU_KY.match(ky):
        raise LoiNghiepVu("ky_sai_dinh_dang", "Tháng (kỳ) phải có dạng NĂM-THÁNG, ví dụ 2026-09.", truong=["ky"])
    if "ky" not in co_truong:
        ky = None
    if "ly_do" in co_truong and ly_do not in LY_DO_HOAN:
        raise LoiNghiepVu("ly_do_khong_hop_le", "Chọn lý do hoàn: khách trả thừa hoặc huỷ cọc.", truong=["ly_do"])

    cf = f.get("phan_loai_cf")
    if cf and cf != nv.b03_khoa:
        raise LoiNghiepVu("phan_loai_cf_lech",
                          f"Dòng tiền gửi lên ({cf}) khác dòng tiền của việc “{nv.ten}” ({nv.b03_khoa}). "
                          "Bỏ ô dòng tiền — máy tự suy ra.")

    # Đối tượng theo tài khoản đối ứng (vế không phải tiền): 131 → khách, 331 → nhà cung cấp, 334 → nhân viên.
    doi_ung = nv.co if nv.no == TIEN else nv.no
    dt: dict[str, Optional[str]] = {"doi_tuong_loai": None, "doi_tuong_ma": None, "doi_tuong_ten": None}
    nv_ten = (f.get("nhan_vien_ten") or "").strip() or None
    if doi_ung == "PHAI_TRA_NCC" and ncc_ma:
        # muahang.suppliers.id là chuỗi ('ncc_01bf782e') — CAST để so được cả khi cột là số.
        r = _doc_ngoai(db, "SELECT id, name FROM muahang.suppliers WHERE CAST(id AS text) = :i", i=ncc_ma)
        if r == []:
            raise LoiNghiepVu("ncc_khong_hop_le", "Không có nhà cung cấp này ở Mua hàng. Chọn lại trong danh sách.",
                              truong=["ncc"])
        ten = r[0]["name"] if r else (f.get("doi_tuong_ten") or None)
        if r is None:
            canh_bao.append("Chưa kiểm được nhà cung cấp: không đọc được dữ liệu Mua hàng.")
        dt = {"doi_tuong_loai": "ncc", "doi_tuong_ma": ncc_ma, "doi_tuong_ten": ten}
    elif doi_ung == "PHAI_THU_KH" and bao_gia is not None:
        dt = {"doi_tuong_loai": "khach", "doi_tuong_ma": bao_gia["khach_id"], "doi_tuong_ten": bao_gia["khach"]}
    elif doi_ung == "PHAI_TRA_NLD" and nv_id:
        r = _doc_ngoai(db, "SELECT ma_nv, ho_ten FROM hcns.employees "
                           "WHERE regexp_replace(ma_nv, '\\D', '', 'g') = :d LIMIT 1", d=str(nv_id))
        if r == []:
            raise LoiNghiepVu("nhan_vien_khong_hop_le", "Không có nhân viên này ở danh sách nhân sự. Chọn lại.",
                              truong=["nhan_vien"])
        if r:
            nv_ten = r[0]["ho_ten"]
            dt = {"doi_tuong_loai": "nv", "doi_tuong_ma": r[0]["ma_nv"], "doi_tuong_ten": r[0]["ho_ten"]}
        else:
            canh_bao.append("Chưa kiểm được nhân viên: không đọc được dữ liệu Nhân sự.")
            dt = {"doi_tuong_loai": "nv", "doi_tuong_ma": None, "doi_tuong_ten": nv_ten}

    if not noi_dung:   # Diễn giải ở bảng sổ quỹ không bị trống khi nghiệp vụ không bắt buộc nội dung
        noi_dung = nv.ten + (f" — {dt['doi_tuong_ten']}" if dt["doi_tuong_ten"] else "") + (f" — kỳ {ky}" if ky else "")

    tk_tien = tk_tien_cua_quy(quy)
    no, co = tk_no_co(nv.khoa, loai, che_do, tk_tien)
    ten_quy = quy.ten_tk
    dinh_khoan = {
        "no_tk": no, "ten_no": ten_quy if nv.no == TIEN else _ten_tk(nv.no),
        "co_tk": co, "ten_co": ten_quy if nv.co == TIEN else _ten_tk(nv.co),
        "so_tien": so_tien, "che_do": che_do, "che_do_ten": CHE_DO_TEN[che_do],
    }
    if CANH_BAO.get(nv.khoa):
        canh_bao.insert(0, CANH_BAO[nv.khoa])

    if ma_don and not f.get("xac_nhan_trung"):
        trung = db.execute(
            select(SoQuy).where(func.upper(SoQuy.ma_don) == ma_don, SoQuy.ngay == f.get("ngay"),
                                SoQuy.so_tien == so_tien, SoQuy.loai == loai).limit(5)
        ).scalars().all()
        if trung:
            raise LoiNghiepVu(
                "nghi_trung", f"Có thể đã ghi rồi: đơn {ma_don} đã có {len(trung)} phiếu {loai} cùng ngày, cùng số tiền. "
                              "Kiểm tra lại; chắc chắn là khoản khác thì bấm “Vẫn lưu”.", http=409,
                dong=[{"id": r.id, "ngay": str(r.ngay), "so_tien": str(r.so_tien), "lien_quan": r.lien_quan,
                       "noi_dung": r.noi_dung} for r in trung])

    cot = {
        "ngay": f.get("ngay"), "loai": loai, "so_tien": so_tien, "tai_khoan": quy.ten_tk,
        "noi_dung": noi_dung, "lien_quan": "nhap_tay", "phan_loai_cf": nv.b03_khoa,
        "ref_id": f.get("ref_id") or None, "mo_ta": (f"Lý do hoàn: {LY_DO_HOAN[ly_do]}" if "ly_do" in co_truong
                                                     else f.get("mo_ta")),
        "ghi_chu": f.get("ghi_chu"), "ma_don": ma_don,
        "nhan_vien_id": nv_id, "nhan_vien_ten": nv_ten if nv_id else None,
        "ma_dinh_khoan": nv.khoa, "ky": ky, "tk_doi_ung": None, **dt,
    }
    return cot, dinh_khoan, canh_bao
