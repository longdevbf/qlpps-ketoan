/* ═══════════════════════════════════════════════════════════════════════════
   kt-so-cai.js — màn Sổ kế toán: nhật ký chung ↔ sổ cái theo tài khoản (đợt 1, API THẬT)

   Bản thiết kế (README mục 4.2) giả định `GET /api/journal?tu&den&tk&loai&tim&doi_tuong
   &page&size&sort` trả sẵn CHẾ ĐỘ (nhật ký/sổ cái), TỔNG số trang, và dư luỹ kế từng dòng
   do máy chủ tính. Backend thật (app/routers/journal.py) đơn giản hơn nhiều:
     · GET /api/journal/accounts                → Chart of Accounts (thay /api/tai-khoan) — từ 28/09/2026
       có cả TK con của tài khoản tiền (1111, 1121…), đọc qua KT.dmTk() (kt-chung.js suy cấp + TK cha)
     · GET /api/journal?from&to&source_type&trang_thai&limit&offset → DANH SÁCH BÚT TOÁN
       (JournalEntrySummary — không kèm dòng Nợ/Có, không lọc theo tài khoản, không phân
       trang theo tổng số trang, không "che_do")
     · GET /api/journal/<id>                     → chi tiết 1 bút toán, có `lines` (loai/
       account_code/so_tien — không phải {tk,no,co} như mock)
     · GET /api/journal/balance-summary?den_ngay → số dư RÒNG theo tài khoản đến 1 ngày

   Cách nối cho từng phần (mọi số vẫn lấy từ máy chủ — không bịa):
     · Sổ NHẬT KÝ CHUNG: hiện MỘT dòng / bút toán (không tách dòng Nợ/Có vì API danh sách
       không trả `lines`) — cột đổi thành Ngày/Số bút toán/Loại/Diễn giải/Người lập/Tổng
       tiền/Trạng thái. Tổng phát sinh Nợ = Tổng phát sinh Có = Σ tong_tien vì máy chủ đã
       BẮT BUỘC mỗi bút toán cân Nợ=Có trước khi cho ghi sổ (services/journal.py:post_journal,
       dòng `tong_tien=sum_no` sau khi kiểm `sum_no==sum_co`) — không phải số trùng hợp.
     · Sổ CÁI theo TK: GET /api/journal/so-cai?tk&tu_ngay&den_ngay (services/journal.py:ledger,
       QA 25/09/2026) — máy chủ trả dư đầu kỳ, từng dòng Nợ/Có, TK đối ứng và dư luỹ kế (chỉ bút
       toán 'da_post'), gồm cả TK chi tiết cùng đầu số. Thay cách cũ tải chi tiết TỪNG bút toán
       (N+1 request, trần 500) rồi tự cộng dồn ở trình duyệt — cách cũ còn lẫn bút toán đã huỷ vào
       phát sinh trong khi dư đầu kỳ lại chỉ tính 'da_post', và tự chép danh sách TK dư Có (thiếu
       3334/3335) để chia cột Dư Nợ/Dư Có.
     · Không có màn tương ứng ở giao diện cũ (SPA /app không có sổ nhật ký / sổ cái).
     · Xuất Excel: xuất CSV (UTF-8 BOM) ngay ở trình duyệt từ đúng dữ liệu đang lọc — link cũ
       /api/journal/xuat KHÔNG tồn tại (khớp route /{je_id} → lỗi 422).
     · "Đối tượng" mỗi dòng: JournalLine chỉ có ref_table/ref_id (không có tên KH/NCC) —
       hiện nhãn bảng nguồn + mã, không phải tên đối tượng như bản thiết kế.
     · Cột "Loại" + ô lọc "Loại nghiệp vụ" (28/09/2026, anh Quang: "phải thể hiện bút toán là thu hay chi… để lọc"):
       máy chủ suy từ định khoản (services/journal.py:phan_loai_nghiep_vu) — tiền 111x/112x ghi Nợ = Thu tiền, ghi Có =
       Chi tiền, cả hai = Chuyển tiền; không qua tiền thì Doanh thu / Giá vốn / Khấu hao / Thuế…; danh sách nhãn lấy từ
       GET /api/journal/nghiep-vu. /api/journal trả thêm nghiep_vu + tk_no + tk_co; /so-cai trả nghiep_vu từng dòng.
     · Bộ lọc "Nguồn chứng từ" (trước gọi "Loại chứng từ"): đổi vốn từ (KT.LOAI_CT — nhãn kế toán mock) sang source_type
       thật của JournalEntry (models/journal_entry.py). "Mã đối tượng" đổi thành "Mã tham
       chiếu" lọc theo source_id (gần nhất với khái niệm này ở dữ liệu thật).
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const trang = $('kd-kt-so-cai');
  if (!trang) return;

  const MAC_DINH = { ky: 'thang_nay', tu: '', den: '', tk: '', nv: '', loai: '', tim: '', doi_tuong: '', page: 1, size: 20, sort: 'ngay_asc' };
  const st = Object.assign({}, MAC_DINH, KT.url.doc());
  st.page = +st.page || 1; st.size = +st.size || 20;
  let luot = 0;

  /* Nguồn (source_type) — xem journal_entry.py. Khác từ vựng KT.LOAI_CT (viết cho backend mock),
     nên khai bản đồ riêng thay vì sửa kt-chung.js (file dùng chung nhiều màn). */
  const NGUON = ['gop_von', 'rut_von', 'chia_co_tuc', 'trich_quy', 'chi_phi_phat_sinh', 'chi_phi_co_dinh',
    'nhap_kho_manual', 'xuat_kho_manual', 'tao_khoan_vay', 'tra_no_vay', 'tk_nh_thu', 'tk_nh_chi',
    'khau_hao', 'vc_hoan_thanh', 'tam_ung', 'tam_ung_quyet_toan', 'other'];  // + source_type thật đang có trong DB (QA 25/09/2026)
  const NHAN_NGUON = {
    gop_von: 'Góp vốn', rut_von: 'Rút vốn', chia_co_tuc: 'Chia cổ tức', trich_quy: 'Trích quỹ',
    chi_phi_phat_sinh: 'Chi phí phát sinh', chi_phi_co_dinh: 'Chi phí cố định',
    nhap_kho_manual: 'Nhập kho', xuat_kho_manual: 'Xuất kho', tao_khoan_vay: 'Tạo khoản vay',
    tra_no_vay: 'Trả nợ vay', tk_nh_thu: 'Ngân hàng báo có', tk_nh_chi: 'Ngân hàng báo nợ', other: 'Khác',
    khau_hao: 'Khấu hao TSCĐ', vc_hoan_thanh: 'Hoàn thành đơn hàng', tam_ung: 'Tạm ứng', tam_ung_quyet_toan: 'Quyết toán tạm ứng',
  };
  function nhanNguon(s) { if (!s) return 'Khác'; if (NHAN_NGUON[s]) return NHAN_NGUON[s]; if (s.indexOf('reversal_of_') === 0) return 'Đảo bút toán'; return s; }
  const NHAN_TRANG_THAI = { du_thao: { nhan: 'Dự thảo', mau: 'warning' }, da_post: { nhan: 'Đã ghi sổ', mau: 'success' }, da_huy: { nhan: 'Đã huỷ', mau: 'danger' } };
  function pillTrangThai(k) { const x = NHAN_TRANG_THAI[k] || { nhan: k || '—', mau: 'muted' }; return '<span class="pill pill--' + x.mau + '">' + esc(x.nhan) + '</span>'; }
  /* Loại nghiệp vụ (Thu tiền / Chi tiền / …): nhãn từ GET /api/journal/nghiep-vu; màu thẻ chỉ là trình bày. */
  const MAU_NV = { thu: 'success', chi: 'danger', chuyen_tien: 'info', doanh_thu: 'brand', gia_von: 'warning' };
  const nhanNv = {};
  const tenNv = (k) => nhanNv[k] || k || 'Khác';
  const pillNv = (k) => '<span class="pill pill--' + (MAU_NV[k] || 'muted') + '">' + esc(tenNv(k)) + '</span>';
  const dinhKhoan = (b) => 'Nợ ' + (b.tk_no || []).join(', ') + ' · Có ' + (b.tk_co || []).join(', ');
  async function taiNv() {
    try {
      const ds = await KD.api('/api/journal/nghiep-vu');
      ds.forEach((x) => { nhanNv[x.ma] = x.nhan; });
      $('sc-nv').insertAdjacentHTML('beforeend', ds.map((x) => '<option value="' + esc(x.ma) + '">' + esc(x.nhan) + '</option>').join(''));
    } catch (e) {
      window.showToast && window.showToast('warn', 'Chưa tải được danh sách loại nghiệp vụ: ' + e.message);
    }
    if (st.nv && !nhanNv[st.nv]) $('sc-nv').insertAdjacentHTML('beforeend', '<option value="' + esc(st.nv) + '">' + esc(st.nv) + '</option>');
    $('sc-nv').value = st.nv;
  }
  const NHAN_REF = { cong_no: 'Công nợ', tai_khoan_nh: 'TK ngân hàng', inventory_balance: 'Kho', von_chu_so_huu: 'Vốn CSH', quy_dn: 'Quỹ', khoan_vay: 'Khoản vay',
    doanh_thu: 'Doanh thu', chi_phi_phat_sinh: 'Chi phí', 'baogia.quotes': 'Báo giá', tai_san_co_dinh: 'TSCĐ' };

  /* ── Khởi tạo ô lọc ── */
  $('sc-loai').insertAdjacentHTML('beforeend', NGUON.map((k) => '<option value="' + k + '">' + esc(nhanNguon(k)) + '</option>').join(''));
  $('sc-loai').value = st.loai; $('sc-tim').value = st.tim; $('sc-dt').value = st.doi_tuong; $('sc-co-trang').value = String(st.size);

  const loc = $('sc-loc'), nutLoc = $('sc-nut-loc');
  function moLoc(mo) { loc.hidden = !mo; nutLoc.setAttribute('aria-expanded', String(mo)); }
  moLoc(KD.MAN_RONG());   // boolean (bản trước .matches → undefined → khung lọc luôn gập)
  nutLoc.addEventListener('click', () => moLoc(loc.hidden));

  /* Ô chọn TK: danh mục chung KT.dmTk() (GET /api/journal/accounts, có cấp + TK cha) — TK con của tài khoản
     tiền (mã 4+ chữ số, vd ?tk=1121) thụt dưới TK cha. Mã trên URL không có trong danh mục vẫn giữ một ô riêng. */
  async function taiTk() {
    let ds = [];
    try {
      ds = await KT.dmTk();
      $('sc-tk').insertAdjacentHTML('beforeend', ds.map((t) => '<option value="' + esc(t.ma) + '">'
        + (t.cap === 2 ? '\u00a0\u00a0\u00a0└\u00a0' : '') + esc(t.ma + ' — ' + t.ten) + '</option>').join(''));
    } catch (e) {
      window.showToast && window.showToast('warn', 'Chưa tải được danh mục tài khoản: ' + e.message);
    }
    if (st.tk && !ds.some((t) => t.ma === st.tk)) $('sc-tk').insertAdjacentHTML('beforeend', '<option value="' + esc(st.tk) + '">' + esc(st.tk) + '</option>');
    $('sc-tk').value = st.tk;
  }

  const khoang = () => KT.khoangSt(st);
  function soLocBat() { return ['tk', 'nv', 'loai', 'tim', 'doi_tuong'].filter((k) => st[k]).length; }
  function truocNgay(iso) { const x = new Date(iso); x.setDate(x.getDate() - 1); return KD.iso(x); }

  /* ── Đầu bảng theo chế độ ── */
  const DAU = {
    nhat_ky: '<tr>'
      + '<th scope="col"><button type="button" class="kd-sort" data-sort="ngay">Ngày <i class="bi bi-arrow-down-up" aria-hidden="true"></i></button></th>'
      + '<th scope="col"><button type="button" class="kd-sort" data-sort="so_ct" data-kieu="chu">Số bút toán <i class="bi bi-arrow-down-up" aria-hidden="true"></i></button></th>'
      + '<th scope="col">Loại · định khoản</th><th scope="col">Diễn giải</th><th scope="col">Người lập</th>'
      + '<th scope="col" class="num">Tổng tiền (VND)</th><th scope="col">Trạng thái</th></tr>',
    so_cai: '<tr>'
      + '<th scope="col"><button type="button" class="kd-sort" data-sort="ngay">Ngày <i class="bi bi-arrow-down-up" aria-hidden="true"></i></button></th>'
      + '<th scope="col"><button type="button" class="kd-sort" data-sort="so_ct" data-kieu="chu">Số bút toán <i class="bi bi-arrow-down-up" aria-hidden="true"></i></button></th>'
      + '<th scope="col">Loại</th><th scope="col">Diễn giải</th><th scope="col" title="Tài khoản ghi ở vế đối diện của bút toán">TK đối ứng</th>'
      + '<th scope="col" class="num">Nợ (VND)</th><th scope="col" class="num">Có (VND)</th>'
      + '<th scope="col" class="num" title="Số dư luỹ kế sau dòng này">Dư Nợ (VND)</th><th scope="col" class="num">Dư Có (VND)</th></tr>',
  };
  // Đợt 4: "Loại" (nhật ký) và "Tham chiếu" (sổ cái) thành dòng phụ dưới Số bút toán → bớt 1 cột mỗi chế độ.
  const SO_COT = { nhat_ky: 7, so_cai: 9 };
  let cheDoDau = '';
  function dauBang(cheDo) {
    if (cheDoDau === cheDo) return;
    cheDoDau = cheDo; $('sc-thead').innerHTML = DAU[cheDo];
    sapXep.ve();
  }
  const sapXep = KT.ganSapXep($('sc-thead'), () => st.sort, (s) => { st.sort = s; st.page = 1; tai(); });

  /* ── Dải số ── */
  const O = trang.querySelectorAll('#sc-strip [data-o]');
  function veO(i, icon, mau, nhan, giaTri, phu) {
    const o = O[i];
    o.querySelector('[data-icon]').className = 'ico-tile ico-tile--sm' + (mau ? ' ico-tile--' + mau : '');
    o.querySelector('[data-icon]').innerHTML = '<i class="bi ' + icon + '"></i>';
    o.querySelector('[data-nhan]').textContent = nhan;
    o.querySelector('[data-v]').innerHTML = giaTri;
    o.querySelector('[data-phu]').innerHTML = phu || '';
  }
  const duChu = (x) => (x.no ? '<span>' + KD.tien(x.no) + '</span><span class="kd-kpi__don-vi">VND</span>' : x.co ? '<span>' + KD.tien(x.co) + '</span><span class="kd-kpi__don-vi">VND</span>' : '<span>0</span><span class="kd-kpi__don-vi">VND</span>');
  const duPhu = (x) => (x.no ? 'Dư Nợ' : x.co ? 'Dư Có' : 'Không có số dư');
  const tienO = (v) => '<span>' + KD.tien(v) + '</span><span class="kd-kpi__don-vi">VND</span>';
  function veStrip(d) {
    if (d.che_do === 'so_cai') {
      veO(0, 'bi-box-arrow-in-right', 'info', 'Số dư đầu kỳ', duChu(d.so_du_dau), duPhu(d.so_du_dau) + ' · đến hết ' + KD.ngay(truocNgay(d.ky.tu)));
      veO(1, 'bi-plus-lg', '', 'Phát sinh Nợ', tienO(d.phat_sinh.no), '');
      veO(2, 'bi-dash-lg', 'tim', 'Phát sinh Có', tienO(d.phat_sinh.co), '');
      veO(3, 'bi-box-arrow-right', 'success', 'Số dư cuối kỳ', duChu(d.so_du_cuoi), duPhu(d.so_du_cuoi) + ' · đến hết ' + KD.ngay(d.ky.den));
    } else {
      const lech = d.tong.no - d.tong.co;
      veO(0, 'bi-journal-text', '', 'Số bút toán', '<span>' + KD.soDem(d.tong.so_but_toan) + '</span>', 'Theo bộ lọc trong kỳ');
      veO(1, 'bi-plus-lg', '', 'Tổng phát sinh Nợ', tienO(d.tong.no), '');
      veO(2, 'bi-dash-lg', 'tim', 'Tổng phát sinh Có', tienO(d.tong.co), '');
      veO(3, lech ? 'bi-exclamation-triangle' : 'bi-check2-circle', lech ? 'danger' : 'success', 'Chênh lệch Nợ − Có', tienO(lech),
        lech ? '<span class="pill pill--danger">Sổ lệch — cần kiểm tra</span>' : '<span class="pill pill--success">Sổ cân</span>' + KD.tip('Mỗi bút toán đã được kiểm cân Nợ = Có khi ghi sổ.', 'kd-tip--trai'));
    }
  }

  /* ── Thân bảng ── */
  function dongNhatKy(ds) {
    return ds.map((b) => '<tr data-id="' + b.id + '" tabindex="0">'
      + '<td>' + KD.ngay(b.ngay) + '</td>'
      + '<td><span class="kd-strong">' + esc(b.ma_but_toan) + '</span><span class="kt-khach__ma">' + esc(nhanNguon(b.source_type)) + '</span></td>'
      + '<td class="kt-nv">' + pillNv(b.nghiep_vu) + '<span class="kt-khach__ma">' + esc(dinhKhoan(b)) + '</span></td>'
      + '<td><span class="kt-dg" title="' + esc(b.mo_ta || '') + '">' + esc(b.mo_ta || '—') + '</span></td>'
      + '<td>' + esc(b.created_by || '—') + '</td>'
      + '<td class="num">' + KD.tien(b.tong_tien) + '</td>'
      + '<td>' + pillTrangThai(b.trang_thai) + '</td></tr>').join('');
  }
  function oThamChieu(l) {
    if (!l.ref_table) return '<span class="kd-muted">—</span>';
    return '<span class="kt-cat kt-cat--hep" title="' + esc((NHAN_REF[l.ref_table] || l.ref_table) + ' #' + (l.ref_id != null ? l.ref_id : '')) + '">'
      + esc(NHAN_REF[l.ref_table] || l.ref_table) + (l.ref_id != null ? ' #' + esc(String(l.ref_id)) : '') + '</span>';
  }
  function dongSoCai(d) {
    const dau = d.trang === 1 ? '<tr class="kt-dong-so-du" aria-label="Số dư đầu kỳ"><td colspan="7">Số dư đầu kỳ (đến hết ' + KD.ngay(truocNgay(d.ky.tu)) + ')</td>'
      + '<td class="num">' + KT.tienSo(d.so_du_dau.no) + '</td><td class="num">' + KT.tienSo(d.so_du_dau.co) + '</td></tr>' : '';
    return dau + d.dong.map((l) => '<tr data-id="' + l.entry_id + '" tabindex="0">'
      + '<td>' + KD.ngay(l.ngay) + '</td><td><span class="kd-strong">' + esc(l.so_ct) + '</span>' + (l.ref_table ? '<span class="kt-khach__ma">' + oThamChieu(l) + '</span>' : '') + '</td>'
      + '<td class="kt-nv">' + pillNv(l.nghiep_vu) + '</td>'
      + '<td><span class="kt-dg" title="' + esc(l.dien_giai || '') + '">' + esc(l.dien_giai || '—') + '</span></td>'
      + '<td>' + (l.tk_doi_ung ? '<span class="kt-tk">' + esc(l.tk_doi_ung) + '</span>' : '<span class="kd-muted">—</span>') + '</td>'
      + '<td class="num">' + KT.tienSo(l.no) + '</td><td class="num">' + KT.tienSo(l.co) + '</td>'
      + '<td class="num">' + KT.tienSo(l.du_no) + '</td><td class="num">' + KT.tienSo(l.du_co) + '</td></tr>').join('');
  }
  function chanBang(d) {
    if (d.che_do === 'so_cai') {
      // Đang lọc loại/tìm: dòng Cộng = đúng các dòng đang hiện (nhãn ghi rõ); thẻ phía trên vẫn là cả kỳ.
      if (d.co_loc) return '<tr><th scope="row" colspan="5">Cộng phát sinh các dòng đang lọc (' + KD.soDem(d.tong_dong) + ' dòng)' + KD.tip('Cả kỳ xem thẻ số phía trên.') + '</th><td class="num">' + KD.tien(d.ps_loc.no) + '</td><td class="num">' + KD.tien(d.ps_loc.co) + '</td><td></td><td></td></tr>';
      return '<tr><th scope="row" colspan="5">Cộng phát sinh trong kỳ</th><td class="num">' + KD.tien(d.phat_sinh.no) + '</td><td class="num">' + KD.tien(d.phat_sinh.co) + '</td><td></td><td></td></tr>'
        + '<tr><th scope="row" colspan="7">Số dư cuối kỳ (đến hết ' + KD.ngay(d.ky.den) + ')</th><td class="num">' + KT.tienSo(d.so_du_cuoi.no) + '</td><td class="num">' + KT.tienSo(d.so_du_cuoi.co) + '</td></tr>';
    }
    // Mỗi bút toán cân Nợ = Có → một số tổng dưới cột Tổng tiền (thẻ phía trên ghi rõ Nợ và Có).
    return '<tr><th scope="row" colspan="5">Cộng phát sinh đã ghi sổ (' + KD.soDem(d.tong.so_ghi_so) + ' bút toán' + (st.nv ? ' — ' + esc(tenNv(st.nv)) : '') + ')</th><td class="num">' + KD.tien(d.tong.no) + '</td><td></td></tr>';
  }

  /* ── Tải danh sách bút toán khớp bộ lọc (dùng chung 2 chế độ) ── */
  async function taiDanhSachBT(ky) {
    const q = { from: ky.tu, to: ky.den, limit: 2000, offset: 0 };
    if (st.loai) q.source_type = st.loai;
    let ds = await KD.api('/api/journal?' + KT.url.qs(q));
    if (st.nv) ds = ds.filter((b) => b.nghiep_vu === st.nv);
    if (st.tim) ds = ds.filter((b) => KT.khopTim(b.ma_but_toan, st.tim) || KT.khopTim(b.mo_ta, st.tim));   // không phân biệt dấu
    if (st.doi_tuong) {
      const q_ = st.doi_tuong.trim().toLowerCase();
      ds = ds.filter((b) => (b.source_id || '').toLowerCase().indexOf(q_) >= 0);
    }
    return ds;
  }
  function apDungSapXep(ds, sort) {
    sort = sort || 'ngay_asc';
    const i = sort.lastIndexOf('_');
    const cot = i < 0 ? sort : sort.slice(0, i);
    const chieu = i < 0 ? 'asc' : sort.slice(i + 1);
    const dau = chieu === 'asc' ? 1 : -1;
    const key = cot === 'so_ct' ? 'ma_but_toan' : 'ngay';
    return ds.slice().sort((a, b) => (a[key] > b[key] ? 1 : a[key] < b[key] ? -1 : (a.id - b.id)) * dau);
  }
  /* Như apDungSapXep nhưng cho dòng sổ cái đã cộng dồn (field so_ct thay vì ma_but_toan) — CHỈ đổi
     thứ tự hiển thị, không đụng vào du_no/du_co đã tính sẵn theo đúng thời gian thật. */
  function sapXepDong(dong, sort) {
    sort = sort || 'ngay_asc';
    const i = sort.lastIndexOf('_');
    const cot = i < 0 ? sort : sort.slice(0, i);
    const chieu = i < 0 ? 'asc' : sort.slice(i + 1);
    const dau = chieu === 'asc' ? 1 : -1;
    const key = cot === 'so_ct' ? 'so_ct' : 'ngay';
    return dong.slice().sort((a, b) => (a[key] > b[key] ? 1 : a[key] < b[key] ? -1 : 0) * dau);
  }

  /* ── Chế độ Sổ cái: máy chủ trả sẵn dòng + dư luỹ kế (GET /api/journal/so-cai) ── */
  async function taiSoCai(ky) {
    const d = await KD.api('/api/journal/so-cai?' + KT.url.qs({ tk: st.tk, tu_ngay: ky.tu, den_ngay: ky.den }));
    const n = (x) => ({ no: KD.so(x.no) || 0, co: KD.so(x.co) || 0 });
    let dong = d.dong.map((l) => Object.assign({}, l, { no: KD.so(l.no) || 0, co: KD.so(l.co) || 0, du_no: KD.so(l.du_no) || 0, du_co: KD.so(l.du_co) || 0 }));
    const soDong = dong.length;
    const le = [d.so_du_dau.no, d.so_du_dau.co].concat(dong.map((l) => l.no + l.co)).some((v) => Math.abs((KD.so(v) || 0) % 1) > 1e-9);
    // Lọc tìm / mã tham chiếu / loại chứng từ áp lên dòng sổ cái (không đổi dư luỹ kế đã tính).
    if (st.nv) dong = dong.filter((l) => l.nghiep_vu === st.nv);
    if (st.loai) dong = dong.filter((l) => l.source_type === st.loai);
    if (st.tim) dong = dong.filter((l) => KT.khopTim(l.so_ct, st.tim) || KT.khopTim(l.dien_giai, st.tim));   // không phân biệt dấu
    /* "Mã tham chiếu" (28/09/2026): bản trước chỉ lọc ở chế độ Nhật ký — chọn tài khoản xong ô này bị bỏ qua.
       Dòng sổ cái không mang source_id → tra theo bút toán (entry_id) từ /api/journal cùng kỳ, chỉ khi đang lọc. */
    if (st.doi_tuong) {
      const q = st.doi_tuong.trim().toLowerCase();
      const bt = await KD.api('/api/journal?' + KT.url.qs({ from: ky.tu, to: ky.den, limit: 2000, offset: 0 }));
      const ma = {}; (bt || []).forEach((b) => { ma[b.id] = (b.source_id || '').toLowerCase(); });
      dong = dong.filter((l) => (ma[l.entry_id] || '').indexOf(q) >= 0);
    }
    const psLoc = { no: dong.reduce((a, l) => a + l.no, 0), co: dong.reduce((a, l) => a + l.co, 0) };
    return { dong, ten: d.ten, soDuDau: n(d.so_du_dau), soDuCuoi: n(d.so_du_cuoi), phatSinh: n(d.phat_sinh), coLoc: dong.length !== soDong, psLoc, le };
  }

  /* ── Tải ── */
  function veCho() {
    const cheDo = st.tk ? 'so_cai' : 'nhat_ky';
    dauBang(cheDo);
    $('sc-tbody').innerHTML = KT.hangCho(SO_COT[cheDo], 8); $('sc-tfoot').innerHTML = '';
    $('sc-cuon').hidden = false; $('sc-tt').innerHTML = ''; $('sc-foot').hidden = true;
    O.forEach((o) => { o.querySelector('[data-v]').innerHTML = '<span class="kd-skel kd-skel--kpi"></span>'; o.querySelector('[data-phu]').innerHTML = ''; });
  }
  function veTieuDe(cheDo, ky, tk) {
    const kyChu = KD.ngay(ky.tu) + ' – ' + KD.ngay(ky.den);
    if (cheDo === 'so_cai') {
      $('sc-td').textContent = 'Sổ cái tài khoản ' + tk.code + ' — ' + tk.name;
      // TK con: nói rõ TK cha đã gồm số này; TK cha: kể tên các TK con được gộp vào sổ.
      const gom = tk.cha ? 'Tài khoản con của ' + tk.cha + ' (sổ cái ' + tk.cha + ' đã gồm các dòng này)'
        : tk.con && tk.con.length ? 'Gồm cả tài khoản con ' + tk.con.join(', ') : 'Gồm cả tài khoản chi tiết bắt đầu bằng ' + tk.code;
      // Đợt 4: dòng phạm vi chỉ còn "Kỳ …" + ⓘ (giải thích chuyển vào bong bóng).
      $('sc-pham-vi').innerHTML = 'Kỳ ' + kyChu + KD.tip(gom + '; chỉ bút toán đã ghi sổ; dư luỹ kế theo thời gian.'
        + (tk.le ? ' Có bút toán lẻ dưới 1 đồng trong dữ liệu gốc (vd 9.044.110,5) — số hiển thị làm tròn nên cộng tay có thể lệch 1 đ.' : ''));
    } else {
      $('sc-td').textContent = 'Sổ nhật ký chung';
      $('sc-pham-vi').innerHTML = 'Kỳ ' + kyChu + KD.tip('Mỗi dòng là một bút toán đã ghi sổ. Bấm dòng để xem định khoản Nợ / Có.');
    }
    $('sc-cap').textContent = $('sc-td').textContent + ', kỳ ' + kyChu;
    $('sc-ve-nk').hidden = cheDo !== 'so_cai';
  }
  async function tai() {
    const l = ++luot; const ky = khoang();
    KT.url.ghi(st, MAC_DINH);
    const n = soLocBat(); $('sc-dem-loc').hidden = !n; $('sc-dem-loc').textContent = n;
    veCho();
    const cheDo = st.tk ? 'so_cai' : 'nhat_ky';
    try {
      const dsBT = cheDo === 'so_cai' ? [] : apDungSapXep(await taiDanhSachBT(ky), st.sort);
      if (l !== luot) return;

      let d;
      if (cheDo === 'so_cai') {
        // Danh mục TK (đã tải song song ở taiTk, cùng một lần gọi) chỉ để lấy tên + TK cha/con; lỗi thì dùng tên máy chủ trả.
        const [sc, dm] = await Promise.all([taiSoCai(ky), KT.dmTk().catch(() => [])]);
        if (l !== luot) return;
        // Dư luỹ kế luôn tính theo THỜI GIAN thật (taiSoCai trả sẵn thứ tự tăng dần) rồi mới sắp
        // xếp lại để HIỂN THỊ theo st.sort — đổi thứ tự không đổi số đã tính trên từng dòng. Khi sắp
        // giảm dần, dòng "Số dư đầu kỳ" (chỉ chèn ở trang 1) sẽ nằm trên các bút toán MỚI nhất thay vì
        // cũ nhất — biết trước, chấp nhận được ở quy mô màn này.
        const dongHienThi = sapXepDong(sc.dong, st.sort);
        const muc = dm.find((t) => t.ma === st.tk);
        d = {
          che_do: 'so_cai', ky,
          tai_khoan: { code: st.tk, name: muc ? muc.ten : sc.ten, cha: muc ? muc.cha : null, con: dm.filter((t) => t.cha === st.tk).map((t) => t.ma) },
          so_du_dau: sc.soDuDau, phat_sinh: sc.phatSinh, so_du_cuoi: sc.soDuCuoi, co_loc: sc.coLoc, ps_loc: sc.psLoc, le: sc.le,
          tong_dong: dongHienThi.length, trang: st.page, so_trang: Math.max(1, Math.ceil(dongHienThi.length / st.size)),
          dong: dongHienThi.slice((st.page - 1) * st.size, st.page * st.size), dong_tat_ca: dongHienThi,
        };
      } else {
        // Chỉ bút toán ĐÃ GHI SỔ mới là phát sinh (bút toán huỷ/dự thảo vẫn liệt kê nhưng không cộng).
        const daGhi = dsBT.filter((b) => b.trang_thai === 'da_post');
        const tongNo = daGhi.reduce((a, b) => a + KD.so(b.tong_tien), 0);
        d = {
          che_do: 'nhat_ky', ky, tong: { so_but_toan: dsBT.length, so_ghi_so: daGhi.length, no: tongNo, co: tongNo },
          tong_dong: dsBT.length, trang: st.page, so_trang: Math.max(1, Math.ceil(dsBT.length / st.size)),
          dong: dsBT.slice((st.page - 1) * st.size, st.page * st.size),
        };
      }

      if (d.tai_khoan) d.tai_khoan.le = d.le;
      dauBang(d.che_do); veTieuDe(d.che_do, ky, d.tai_khoan || {}); veStrip(d);
      duLieuXuat = { d, ky, tatCa: d.che_do === 'so_cai' ? d.dong_tat_ca : dsBT };
      const rong = !d.dong.length;
      if (rong) {
        $('sc-cuon').hidden = d.che_do !== 'so_cai';
        $('sc-tbody').innerHTML = d.che_do === 'so_cai' ? dongSoCai(d) : '';
        $('sc-tfoot').innerHTML = d.che_do === 'so_cai' ? chanBang(d) : '';
        const coLoc = st.nv || st.loai || st.tim || st.doi_tuong;
        $('sc-tt').innerHTML = coLoc
          ? KD.khoiRong('Không có bút toán nào khớp bộ lọc', 'Thử bỏ bớt điều kiện lọc hoặc đổi kỳ sổ.') + '<p class="kt-giua"><button type="button" class="kd-btn kd-btn--sm" data-dat-lai>Đặt lại bộ lọc</button></p>'
          : d.che_do === 'so_cai'
            ? KD.khoiRong('Tài khoản ' + d.tai_khoan.code + ' không phát sinh trong kỳ', 'Số dư đầu kỳ được giữ nguyên thành số dư cuối kỳ.')
            : KD.khoiRong('Chưa có bút toán nào trong kỳ này', 'Bút toán được ghi khi có nghiệp vụ phát sinh hoặc khi bấm "Tạo bút toán".');
        const b = $('sc-tt').querySelector('[data-dat-lai]'); if (b) b.addEventListener('click', datLai);
        return;
      }
      $('sc-tbody').innerHTML = d.che_do === 'so_cai' ? dongSoCai(d) : dongNhatKy(d.dong);
      $('sc-tfoot').innerHTML = chanBang(d);
      $('sc-foot').hidden = false;
      const donVi = d.che_do === 'so_cai' ? ' dòng' : ' bút toán';
      const a = (d.trang - 1) * st.size + 1, b = Math.min(d.trang * st.size, d.tong_dong);
      $('sc-hien-thi').textContent = 'Hiển thị ' + KD.soDem(a) + ' - ' + KD.soDem(b) + ' / ' + KD.soDem(d.tong_dong) + donVi;
      KD.phanTrang($('sc-trang'), d.trang, d.so_trang, (p) => { st.page = p; tai(); $('sc-cuon').scrollIntoView({ block: 'nearest' }); });
    } catch (e) {
      if (l !== luot) return;
      $('sc-cuon').hidden = true;
      O.forEach((o) => { o.querySelector('[data-v]').innerHTML = '<span class="kd-muted">—</span>'; });
      KD.khoiLoi($('sc-tt'), 'Không tải được sổ', e, tai);
    }
  }

  /* ── Xuất CSV (UTF-8 BOM — Excel mở thẳng) toàn bộ dòng khớp bộ lọc, mọi trang ── */
  let duLieuXuat = null;
  function xuatCsv() {
    if (!duLieuXuat || !duLieuXuat.tatCa.length) { if (window.showToast) window.showToast('info', 'Không có dòng nào để xuất'); return; }
    const { d, ky, tatCa } = duLieuXuat;
    const o = (v) => '"' + String(v == null ? '' : v).split('"').join('""') + '"';
    const soCai = d.che_do === 'so_cai';
    const dau = soCai ? ['Ngày', 'Số bút toán', 'Loại', 'Diễn giải', 'TK đối ứng', 'Nợ', 'Có', 'Dư Nợ', 'Dư Có']
      : ['Ngày', 'Số bút toán', 'Loại', 'Định khoản', 'Nguồn', 'Diễn giải', 'Người lập', 'Tổng tiền', 'Trạng thái'];
    const dong = soCai
      ? tatCa.map((l) => [l.ngay, l.so_ct, tenNv(l.nghiep_vu), l.dien_giai, l.tk_doi_ung, Math.round(l.no), Math.round(l.co), Math.round(l.du_no), Math.round(l.du_co)])
      : tatCa.map((b) => [b.ngay, b.ma_but_toan, tenNv(b.nghiep_vu), dinhKhoan(b), nhanNguon(b.source_type), b.mo_ta, b.created_by, Math.round(KD.so(b.tong_tien) || 0), (NHAN_TRANG_THAI[b.trang_thai] || {}).nhan || b.trang_thai]);
    const csv = '\ufeff' + [dau].concat(dong).map((x) => x.map(o).join(',')).join('\r\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    a.download = (soCai ? 'so-cai-' + st.tk : 'nhat-ky-chung') + '_' + ky.tu + '_' + ky.den + '.csv';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  $('sc-xuat').addEventListener('click', xuatCsv);

  /* ── Panel chi tiết bút toán ── */
  const panel = KT.ganPanel({ main: $('sc-main'), panel: $('sc-panel'), scrim: $('sc-scrim'), nutDong: $('sc-p-dong') });
  let luotP = 0;
  async function moBt(tr) {
    const id = tr.dataset.id;
    panel.mo(tr);
    const noiDung = $('sc-p-noi-dung'), nut = $('sc-p-nut');
    const l = ++luotP; noiDung.innerHTML = KD.KHUNG_TAI; nut.innerHTML = '';
    try {
      const b = await KD.api('/api/journal/' + encodeURIComponent(id));
      if (l !== luotP) return;
      const tongNo = b.lines.reduce((a, x) => a + (x.loai === 'no' ? KD.so(x.so_tien) : 0), 0);
      const tongCo = b.lines.reduce((a, x) => a + (x.loai === 'co' ? KD.so(x.so_tien) : 0), 0);
      const lech = Math.abs(tongNo - tongCo) > 0.01;
      noiDung.innerHTML = '<div class="kd-panel__id kt-p-id"><span class="ico-tile" aria-hidden="true"><i class="bi bi-journal-text"></i></span><div>'
        + '<div class="kd-panel__code">' + esc(b.ma_but_toan) + '<span class="kd-chip kd-chip--xam">' + esc(nhanNguon(b.source_type)) + '</span></div>'
        + '<p class="kd-meta">Ngày hạch toán ' + KD.ngay(b.ngay) + ' · ' + pillTrangThai(b.trang_thai) + '</p></div></div>'
        + '<dl class="kd-kv">'
        + '<dt><i class="bi bi-card-text kd-kv__icon" aria-hidden="true"></i><span class="kd-kv__label">Diễn giải</span></dt><dd>' + esc(b.mo_ta || '—') + '</dd>'
        + '<dt><i class="bi bi-person kd-kv__icon" aria-hidden="true"></i><span class="kd-kv__label">Người lập</span></dt><dd>' + esc(b.created_by || '—') + '<div class="kd-muted">' + KD.ngayGio(b.created_at) + '</div></dd>'
        + (b.source_id ? '<dt><i class="bi bi-link-45deg kd-kv__icon" aria-hidden="true"></i><span class="kd-kv__label">Mã tham chiếu</span></dt><dd>' + esc(b.source_id) + '</dd>' : '')
        + '</dl>'
        + '<section class="kd-block" aria-labelledby="sc-p-dk"><h3 class="kd-block__title" id="sc-p-dk"><i class="bi bi-list-columns" aria-hidden="true"></i>Định khoản</h3>'
        + '<table class="kt-dk"><thead><tr><th scope="col">Tài khoản</th><th scope="col" class="num">Nợ (VND)</th><th scope="col" class="num">Có (VND)</th></tr></thead><tbody>'
        + b.lines.map((x) => '<tr><td><span class="kt-tk">' + esc(x.account_code) + '</span><span class="kt-dk__phu">' + esc(x.account_name || '') + '</span></td>'
          + '<td class="num">' + KT.tienSo(x.loai === 'no' ? x.so_tien : 0) + '</td><td class="num">' + KT.tienSo(x.loai === 'co' ? x.so_tien : 0) + '</td></tr>').join('')
        + '</tbody><tfoot><tr><td>Cộng</td><td class="num">' + KD.tien(tongNo) + '</td><td class="num">' + KD.tien(tongCo) + '</td></tr></tfoot></table>'
        + (lech ? '<p class="kd-note kd-note--danger kd-mt" role="alert">Bút toán lệch ' + KD.tienVnd(tongNo - tongCo) + ' — không nên xảy ra, báo kỹ thuật kiểm tra.</p>' : '')
        + '</section>';
      nut.innerHTML = '<button type="button" class="kd-btn kd-btn--grow" data-in><i class="bi bi-printer" aria-hidden="true"></i>In bút toán</button>';
      nut.querySelector('[data-in]').addEventListener('click', () => window.print());
    } catch (e) {
      if (l !== luotP) return;
      KD.khoiLoi(noiDung, 'Không tải được bút toán', e, () => moBt(tr));
    }
  }
  KT.ganDongBang($('sc-tbody'), (tr) => { moBt(tr); });

  /* ── Sự kiện lọc ── */
  function doiLoc() { st.page = 1; panel.dong(); tai(); }
  function datLai() {
    Object.assign(st, { tk: '', nv: '', loai: '', tim: '', doi_tuong: '', page: 1 });
    $('sc-tk').value = ''; $('sc-nv').value = ''; $('sc-loai').value = ''; $('sc-tim').value = ''; $('sc-dt').value = '';
    panel.dong(); tai();
  }
  // Ô kỳ dùng chung (kt-chung.js): Tuỳ chỉnh điền sẵn ngày (đổi ngày chờ 400 ms, từ > đến báo đỏ), tháng/quý/năm cụ thể.
  KT.ganKy({ sel: $('sc-ky'), hop: $('sc-khoang'), tu: $('sc-tu'), den: $('sc-den'), st, doi: doiLoc, ghi: () => KT.url.ghi(st, MAC_DINH) });
  $('sc-tk').addEventListener('change', (e) => { st.tk = e.target.value; st.sort = 'ngay_asc'; doiLoc(); });
  $('sc-nv').addEventListener('change', (e) => { st.nv = e.target.value; doiLoc(); });
  $('sc-loai').addEventListener('change', (e) => { st.loai = e.target.value; doiLoc(); });
  const goTim = KD.debounce(() => { st.tim = $('sc-tim').value.trim(); doiLoc(); }, 350);
  const goDt = KD.debounce(() => { st.doi_tuong = $('sc-dt').value.trim(); doiLoc(); }, 350);
  $('sc-tim').addEventListener('input', goTim); $('sc-dt').addEventListener('input', goDt);
  loc.addEventListener('submit', (e) => e.preventDefault());
  $('sc-dat-lai').addEventListener('click', datLai);
  $('sc-ve-nk').addEventListener('click', () => { st.tk = ''; $('sc-tk').value = ''; st.sort = 'ngay_asc'; doiLoc(); });
  $('sc-co-trang').addEventListener('change', (e) => { st.size = +e.target.value; doiLoc(); });

  taiTk(); taiNv(); tai();   // song song: danh mục TK chậm hay lỗi không được chặn khung chờ của sổ
})();
