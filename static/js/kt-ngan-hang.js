/* kt-ngan-hang.js — Ngân hàng + tiền mặt, nối API THẬT của app ketoan.
   ─────────────────────────────────────────────────────────────────────────
   Thay màn cũ /app#tai-khoan-nh (thẻ từng tài khoản: đầu kỳ/cuối kỳ, sửa, chốt số dư đầu kỳ)
   + bảng "Số dư theo tài khoản" và nút "Chuyển nội bộ" của /app#so-quy. API:
     GET/POST/PUT /api/tai-khoan                     danh mục TaiKhoanNH (ten_tk, loai, ten_nh, so_tk,
                                                     chu_tk, chi_nhanh, so_du_dau, mo_ta, active, tk_ke_toan)
                                                     tk_ke_toan = TK con của 111 (tiền mặt) / 112 (ngân hàng, ví) mà bút
                                                     toán tự sinh ghi vào; máy chủ kiểm mẫu/trùng, 409 nếu đổi mã đã có bút toán
     GET  /api/tai-khoan/ma-tk-tiep-theo?loai        {tk_ke_toan} — mã con còn trống kế tiếp (gợi ý ở hộp thoại)
     GET  /api/so-quy/summary?tu_ngay&den_ngay       đầu kỳ/thu/chi/cuối kỳ TỪNG tài khoản đúng kỳ lọc
                                                     (so_quy_auto.so_du_truoc_ngay — cùng thuật toán neo
                                                     SoDuDauKy với Sổ quỹ; chỉ tài khoản đang dùng)
     GET  /api/tai-khoan/{id}/giao-dich?from&to      sổ giao dịch (nguồn ketoan.so_quy) + so_du_sau
     POST /api/so-du-dau-ky {tai_khoan_id,thang,so_du}  chốt số dư đầu tháng (upsert, chỉ CEO/admin)
     POST /api/so-quy/chuyen-noi-bo                  chuyển tiền giữa 2 tài khoản (idempotent ref_id)
     → /ketoan/so-cai?tk=<tk_ke_toan>                liên kết "Xem sổ cái" của tài khoản đang xem
   `ten_tk` là KHOÁ nối sang ketoan.so_quy.tai_khoan / doanh_thu.ngan_hang / chi_phi.ngan_hang (chuỗi,
   không phải id) — đổi tên sẽ tách tài khoản khỏi toàn bộ lịch sử giao dịch, nên khi SỬA tài khoản
   ô "Tên tài khoản" bị khoá. (Bug cũ của bản dot3b: sửa tài khoản gửi ten_tk = tên ngân hàng và
   loai = 'ngan_hang' → "BIDV - Công ty" thành "BIDV", tài khoản Tiền mặt bị đổi loại.)
   Không có API đối soát sao kê (sepay.py chỉ nhận webhook) — nút "Nhập sao kê" chỉ báo rõ.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-ngan-hang')) return;
  const H = KT.H, $ = (id) => document.getElementById(id);
  { const pv = $('nh-pham-vi'); pv.classList.add('kt-nh-dang-xem'); pv.parentNode.insertBefore(pv, pv.parentNode.firstChild); }
  const soTien = (v) => (v > 0 ? '<span class="kt-vao">+' + KD.tien(v) + '</span>' : v < 0 ? '−' + KD.tien(-v) : KT.tienSo(0));
  const soDu = (v) => (v < 0 ? '<span class="kt-so--xau">' + KD.tien(v) + '</span>' : KD.tien(v));
  const docSo = (v) => Number(String(v || '').replace(/[^\d]/g, '')) || 0;
  const LOAI = { ngan_hang: ['info', 'Ngân hàng'], tien_mat: ['muted', 'Tiền mặt'], vi_dien_tu: ['warning', 'Ví điện tử'] };
  // TK cha của TK kế toán theo loại (khớp services/tai_khoan_tien.py:tk_cha) — mã con cụ thể luôn lấy từ API.
  const TK_CHA_TIEN_MAT = '111', TK_CHA_TIEN_GUI = '112';
  const tkCha = (loai) => (loai === 'tien_mat' ? TK_CHA_TIEN_MAT : TK_CHA_TIEN_GUI);
  const MAU_TK_CON = /^\d{4,6}$/;
  const dungCha = (ma, loai) => MAU_TK_CON.test(ma || '') && ma.startsWith(tkCha(loai));
  const urlSoCai = (ma) => { const k = kyHienTai(); return '/ketoan/so-cai?' + KT.url.qs({ tk: ma, ky: 'tuy_chinh', tu: k.tu, den: k.den }); };
  const NGUON = { doanh_thu: 'Doanh thu', chi_phi: 'Chi phí', cong_no: 'Công nợ', chuyen_noi_bo: 'Chuyển nội bộ', denghitt: 'Đề nghị thanh toán', tam_ung: 'Tạm ứng' };
  const nhanNguon = (v) => NGUON[v] || (/^vay_\d+$/.test(v || '') ? 'Khoản vay #' + v.slice(4) : v || 'Nhập tay');
  const tenHt = (t) => (t ? t.ten_tk + (t.so_tk ? ' · ' + t.so_tk : '') : '');

  let taiKhoan = [];     // /api/tai-khoan — danh mục đang hiện
  let tongHop = { key: null, map: {} };   // /api/so-quy/summary theo kỳ: { [tai_khoan_id]: item }

  /* ── Tổng hợp đầu kỳ/thu/chi/cuối kỳ theo kỳ đang lọc ── */
  function kyHienTai() { const k = ds.khoang(); return { tu: k.tu || '2000-01-01', den: k.den || KD.iso(new Date()), tatCa: !k.tu }; }
  async function napTongHop(ky) {
    const key = ky.tu + '|' + ky.den;
    if (tongHop.key === key) return false;
    const d = await KD.api('/api/so-quy/summary?' + KT.url.qs({ tu_ngay: ky.tu, den_ngay: ky.den }));
    const map = {};
    (d.items || []).forEach((it) => { map[it.tai_khoan_id] = { dau: +it.so_du_dau_thang || 0, thu: +it.thu || 0, chi: +it.chi || 0, cuoi: +it.so_du_cuoi || 0 }; });
    tongHop = { key, map };
    return true;
  }

  /* ── Sổ giao dịch của tài khoản đang xem ── */
  const ds = KT.danhSach({
    pfx: 'nh', donVi: 'giao dịch',
    api: (q) => (q.tk ? '/api/tai-khoan/' + encodeURIComponent(q.tk) + '/giao-dich?' + KT.url.qs({ from: q.tu || '2000-01-01', to: q.den, limit: 5000 }) : ''),
    macDinh: { ky: 'thang_nay', tu: '', den: '', tk: '', trang_thai: '', page: 1, size: 20, sort: '' },
    kyThem: ['tat_ca'],
    dong: { id: (r) => r.id },
    chuyen: (raw, q) => {
      const all = raw || [];
      let list = all.slice();
      if (q.trang_thai) list = list.filter((r) => r.loai === q.trang_thai);
      list.sort((a, b) => (a.ngay < b.ngay ? 1 : a.ngay > b.ngay ? -1 : b.id - a.id)); // API trả tăng dần → đảo mới nhất trước
      const size = +q.size || 20, page = Math.max(1, +q.page || 1);
      const tong_dong = list.length, so_trang = Math.max(1, Math.ceil(tong_dong / size)), trang = Math.min(page, so_trang);
      // Thẻ Thu/Chi = CẢ tài khoản trong kỳ (không theo lọc Thu/Chi) để đầu kỳ + thu − chi = cuối kỳ
      // và khớp dòng của tài khoản trong bảng trên; dòng Cộng của bảng giao dịch = đúng các dòng đang lọc.
      const thu = all.reduce((s, r) => s + (r.loai === 'thu' ? Number(r.so_tien || 0) : 0), 0);
      const chi = all.reduce((s, r) => s + (r.loai === 'chi' ? Number(r.so_tien || 0) : 0), 0);
      const netLoc = list.reduce((s, r) => s + (r.loai === 'thu' ? 1 : -1) * Number(r.so_tien || 0), 0);
      return {
        ky: { tu: q.tu, den: q.den }, dang_xem: q.tk, loc: q.trang_thai,
        tk: tongHop.map[q.tk] || null,
        tong: { thu, chi, so_thu: all.filter((r) => r.loai === 'thu').length, so_chi: all.filter((r) => r.loai === 'chi').length }, net_loc: netLoc,
        trang, so_trang, tong_dong,
        dong: list.slice((trang - 1) * size, trang * size),
      };
    },
    cot: [
      { key: 'ngay', nhan: 'Ngày', ve: (r) => KD.ngay(r.ngay) },
      { key: 'nd', nhan: 'Nội dung', ve: (r) => (r.doi_tac ? '<span class="kt-nh-nd" title="' + esc(r.doi_tac) + '">' + esc(r.doi_tac) + '</span>' : '<span class="kd-muted">—</span>') + (r.ghi_chu ? '<span class="kt-khach__ma">' + esc(r.ghi_chu) + '</span>' : '') },
      // Cột "Loại" (Thu/Chi) gộp vào cột Nguồn — thẻ màu đứng trước tên nguồn.
      { key: 'nguon', nhan: 'Loại · nguồn', ve: (r) => (r.loai === 'thu' ? H.pill('success', 'Thu') : H.pill('danger', 'Chi')) + ' <span class="kt-tk">' + esc(nhanNguon(r.source_app)) + '</span>' + (r.source_doc_id ? '<span class="kt-khach__ma">' + esc(r.source_doc_id) + '</span>' : '') },
      { key: 'tien', nhan: 'Số tiền (VND)', num: true, ve: (r) => soTien(r.loai === 'thu' ? r.so_tien : -r.so_tien) },
      { key: 'sd', nhan: 'Số dư sau (VND)', num: true, cls: 'kd-strong', ve: (r) => soDu(Number(r.so_du_sau)) },
    ],
    kpi: {
      // Đầu kỳ/cuối kỳ luôn là của CẢ tài khoản trong kỳ (không phụ thuộc lọc Thu/Chi) — khớp dòng trong bảng trên.
      dau_ky: (d) => (d.tk ? { v: H.tienKpi(d.tk.dau), title: KD.tienVnd(d.tk.dau), phu: 'Trước ngày ' + KD.ngay(kyHienTai().tu) } : { v: null, phu: tenHt(tkDangXem()) }),
      thu: (d) => ({ v: H.tienKpi(d.tong.thu), title: KD.tienVnd(d.tong.thu), phu: KD.soDem(d.tong.so_thu) + ' giao dịch thu' }),
      chi: (d) => ({ v: H.tienKpi(d.tong.chi), title: KD.tienVnd(d.tong.chi), phu: KD.soDem(d.tong.so_chi) + ' giao dịch chi' }),
      cuoi_ky: (d) => (d.tk ? { v: H.tienKpi(d.tk.cuoi), title: KD.tienVnd(d.tk.cuoi), phu: d.tk.cuoi < 0 ? H.pill('danger', 'Số dư âm — kiểm tra lại') : 'Đến ngày ' + KD.ngay(kyHienTai().den) } : { v: null, phu: 'Tài khoản ngừng dùng' }),
    },
    cong: (d) => [{ html: 'Cộng ' + KD.soDem(d.tong_dong) + ' giao dịch' + (d.loc ? ' ' + (d.loc === 'thu' ? 'thu' : 'chi') + ' đang lọc' : ' (thu − chi)'), span: 3 }, { html: soTien(d.net_loc), num: true }, { html: '' }],
    rong: (d, coLoc) => (coLoc ? ['Không có giao dịch nào ở loại này', 'Chọn "Tất cả" để xem toàn bộ.'] : ['Kỳ này tài khoản chưa có giao dịch', 'Giao dịch tự lên khi ghi Doanh thu/Chi phí/Công nợ qua tài khoản này.']),
    loi: 'Không tải được sổ giao dịch',
    sauTai: (d) => {
      // Tiêu đề nhỏ phía trên hàng thẻ: tài khoản đang xem + ⓘ giải thích (thay đoạn chữ dài dưới thẻ).
      // Kèm TK kế toán + liên kết Sổ cái của TK đó (sổ cái = bút toán; sổ giao dịch = Sổ quỹ).
      const t = tkDangXem(), ma = t && t.tk_ke_toan;
      $('nh-pham-vi').innerHTML = 'Sổ giao dịch: <b>' + esc(tenHt(t)) + '</b>' + (ma ? '<span class="kt-nh-tkkt"> · TK ' + esc(ma) + '</span>' : '')
        + KD.tip('Giao dịch lấy từ Sổ quỹ (tự sinh khi ghi Doanh thu, Chi phí, Công nợ, Chuyển nội bộ, Khoản vay); "Số dư sau" cộng dồn từ số dư đầu kỳ.'
          + (d.loc ? ' Đang lọc chỉ giao dịch ' + (d.loc === 'thu' ? 'thu' : 'chi') + ' — các thẻ số vẫn tính mọi giao dịch.' : ''))
        + (ma ? '<a class="kt-nh-so-cai" href="' + esc(urlSoCai(ma)) + '">Xem sổ cái<i class="bi bi-arrow-right-short" aria-hidden="true"></i></a>' : '');
    },
    // Số dư theo kỳ nạp TRƯỚC khi gọi sổ giao dịch (bản trước tải sổ → nạp số dư → tải sổ lần 2).
    truocTai: () => napTongHop(kyHienTai()).then((doi) => { if (doi) veTk(); })
      .catch((e) => { window.showToast && window.showToast('err', 'Không tải được số dư theo kỳ: ' + e.message); }),
    panel: {
      ve: (r) => H.dauPanel(r.loai === 'thu' ? 'bi-box-arrow-in-down' : 'bi-box-arrow-up', r.loai === 'thu' ? 'success' : 'danger',
        'SQ-' + r.id, KD.ngay(r.ngay) + ' · ' + esc(tenHt(tkDangXem())), '')
        + '<p>' + esc(r.doi_tac || '(không có nội dung)') + '</p>'
        + H.kv([
          [r.loai === 'thu' ? 'Số tiền thu' : 'Số tiền chi', KD.tienVnd(r.so_tien), true],
          ['Số dư sau giao dịch', KD.tienVnd(r.so_du_sau)],
          ['Nguồn', esc(nhanNguon(r.source_app))],
          r.source_doc_id ? ['Mã tham chiếu', esc(r.source_doc_id)] : null,
          r.ghi_chu ? ['Ghi chú / mã đơn', esc(r.ghi_chu)] : null,
          ['Người tạo', esc(r.created_by || '—')],
        ]),
      nut: () => '',
    },
  });
  const tkDangXem = () => taiKhoan.find((x) => String(x.id) === String(ds.st.tk));

  /* ── Bảng tài khoản: đầu kỳ / thu / chi / cuối kỳ theo kỳ đang lọc ── */
  function veTk() {
    $('nh-tk-tt').innerHTML = ''; $('nh-tk-cuon').hidden = false;
    const ky = kyHienTai();
    $('nh-tk-ky').textContent = ky.tatCa ? 'Toàn bộ thời gian đến ' + KD.ngay(ky.den) : 'Kỳ ' + KD.ngay(ky.tu) + ' – ' + KD.ngay(ky.den);
    if (!taiKhoan.length) { $('nh-tk-cuon').hidden = true; $('nh-tk-tong').innerHTML = '';
      $('nh-tk-tt').innerHTML = KD.khoiRong('Chưa khai báo tài khoản ngân hàng / tiền mặt nào', 'Bấm "Thêm tài khoản" để bắt đầu.'); return; }
    const coSo = tongHop.key === ky.tu + '|' + ky.den;
    const o = (v) => '<td class="num">' + (!coSo ? '<span class="kd-skel"></span>' : v == null ? '<span class="kd-muted">—</span>' : v) + '</td>';
    $('nh-tk-ds').innerHTML = taiKhoan.map((t) => {
      const chon = String(t.id) === String(ds.st.tk), s = tongHop.map[t.id], l = LOAI[t.loai] || ['muted', t.loai || '—'];
      // Dòng phụ: TK kế toán · ngân hàng · chi nhánh.
      const phu = [t.tk_ke_toan ? '<span class="kt-nh-tkkt">TK ' + esc(t.tk_ke_toan) + '</span>' : ''].concat([t.ten_nh, t.chi_nhanh].map((x) => (x ? esc(x) : ''))).filter(Boolean);
      return '<tr data-tk="' + esc(t.id) + '" tabindex="0" class="' + (chon ? 'is-chon' : '') + (t.active ? '' : ' is-ngung') + '"' + (chon ? ' aria-current="true"' : '') + '>'
      // Gộp 4 cột cũ (Tài khoản · Số TK · Loại · Chủ TK) thành 2: tên + loại, số TK + chủ TK.
      + '<td><span class="kt-khach__ten">' + esc(t.ten_tk) + ' ' + H.pill(l[0], l[1]) + (t.active ? '' : ' ' + H.pill('muted', 'Ngừng dùng')) + '</span>'
        + (phu.length ? '<span class="kt-khach__ma">' + phu.join(' · ') + '</span>' : '') + '</td>'
      + '<td><span class="num">' + esc(t.so_tk || '—') + '</span>' + (t.chu_tk ? '<span class="kt-khach__ma kt-nh-chu">' + esc(t.chu_tk) + '</span>' : '') + '</td>'
      + o(s ? KD.tien(s.dau) : null) + o(s ? KT.tienSo(s.thu) : null) + o(s ? KT.tienSo(s.chi) : null) + o(s ? '<span class="kd-strong">' + soDu(s.cuoi) + '</span>' : null)
      + '<td class="kd-col-act"><button type="button" class="kd-icon-btn" data-tk-menu="' + esc(t.id) + '" aria-haspopup="menu" aria-expanded="false" aria-label="Thao tác với tài khoản ' + esc(t.ten_tk) + '"><i class="bi bi-three-dots" aria-hidden="true"></i></button></td></tr>'; }).join('');
    const S = (k) => taiKhoan.reduce((a, t) => a + ((tongHop.map[t.id] || {})[k] || 0), 0);
    const soDung = taiKhoan.filter((t) => tongHop.map[t.id]).length;
    $('nh-tk-tong').innerHTML = coSo ? '<tr><th scope="row" colspan="2">Cộng ' + KD.soDem(soDung) + ' tài khoản đang dùng</th><td class="num">' + KD.tien(S('dau')) + '</td><td class="num">' + KD.tien(S('thu')) + '</td><td class="num">' + KD.tien(S('chi')) + '</td><td class="num">' + soDu(S('cuoi')) + '</td><td class="kd-col-act"></td></tr>' : '';
  }
  function xemTk(id) { if (String(id) === String(ds.st.tk)) return; ds.st.tk = String(id); ds.st.page = 1; ds.dongPanel(); ds.tai(); veTk(); }
  const dsTk = $('nh-tk-ds');
  dsTk.addEventListener('click', (e) => { const m = e.target.closest('[data-tk-menu]'); if (m) return moMenuTk(m); const tr = e.target.closest('tr[data-tk]'); if (tr) xemTk(tr.dataset.tk); });
  dsTk.addEventListener('keydown', (e) => { if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('tr[data-tk]')) { e.preventDefault(); xemTk(e.target.dataset.tk); } });
  $('nh-ca-ngung').addEventListener('change', () => taiLaiTk());
  async function taiLaiTk() {
    $('nh-tk-tt').innerHTML = ''; $('nh-tk-cuon').hidden = false; dsTk.innerHTML = KT.hangCho(7, 3); $('nh-tk-tong').innerHTML = '';
    try {
      taiKhoan = await KD.api('/api/tai-khoan?active_only=' + ($('nh-ca-ngung').checked ? 'false' : 'true'));
      if ((!ds.st.tk || !tkDangXem()) && taiKhoan.length) ds.st.tk = String((taiKhoan.find((t) => t.active) || taiKhoan[0]).id);
      tongHop.key = null;
      await napTongHop(kyHienTai()).catch(() => {});
      veTk();
      if (ds.st.tk) ds.tai(); else { $('nh-cuon').hidden = true; }
    } catch (e) { $('nh-tk-cuon').hidden = true; KD.khoiLoi($('nh-tk-tt'), 'Không tải được danh sách tài khoản', e, taiLaiTk); }
  }
  /* Quyền (F3 28/09): sửa / ngừng dùng / dùng lại tài khoản = PUT /api/tai-khoan/{id} và chốt số dư đầu kỳ = POST /api/so-du-dau-ky
     đều require_ceo_thuchi (admin/ceo/assistant_ceo = KD.coQuyen('ceo')). Kế toán chỉ còn "Xem sổ giao dịch" + dòng nhắc cần quyền CEO;
     THÊM tài khoản (POST /api/tai-khoan) và Chuyển nội bộ vẫn mở cho Kế toán như API. */
  const SUA_TK_DUOC = KD.coQuyen('ceo');
  function moMenuTk(nut) {
    const t = taiKhoan.find((x) => String(x.id) === nut.dataset.tkMenu); if (!t) return;
    KD.menu(nut, [
      { nhan: 'Xem sổ giao dịch', icon: 'bi-list-ul', onClick: () => xemTk(t.id) },
      ...(t.tk_ke_toan ? [{ nhan: 'Xem sổ cái TK ' + t.tk_ke_toan, icon: 'bi-journal-text', href: urlSoCai(t.tk_ke_toan) }] : []),
      ...(SUA_TK_DUOC ? [
        { nhan: 'Sửa thông tin', icon: 'bi-pencil', onClick: () => moTk(t) },
        { nhan: 'Chốt số dư đầu kỳ', icon: 'bi-flag', onClick: () => moSoDu(t) },
        '-',
        t.active ? { nhan: 'Ngừng dùng', icon: 'bi-slash-circle', danger: true, onClick: () => moNgung(t) } : { nhan: 'Dùng lại', icon: 'bi-arrow-counterclockwise', onClick: () => doiTrangThai(t, true) },
      ] : ['-', { nhan: 'Sửa, ngừng dùng, số dư đầu kỳ: cần quyền CEO', icon: 'bi-lock' }]),
    ]);
  }
  const ok = (msg) => window.showToast && window.showToast('ok', msg);
  function sauGhi() { tongHop.key = null; taiLaiTk(); }

  /* ── Thêm / sửa tài khoản (POST/PUT /api/tai-khoan — field thật) ── */
  const dlgTk = $('nh-dlg-tk'); let tkDangSua = null;
  ['nh-t-dau', 'nh-sd-so', 'nh-c-tien'].forEach((id) => $(id).addEventListener('input', (e) => { const n = docSo(e.target.value); e.target.value = n ? KD.tien(n) : ''; }));

  /* TK kế toán: thêm mới → điền mã trống kế tiếp (GET ma-tk-tiep-theo); đổi loại → nạp lại gợi ý nếu người dùng
     chưa tự gõ mã hoặc mã đang có không còn thuộc TK cha của loại mới. Sửa → giữ mã cũ khi còn đúng TK cha. */
  const oTk = $('nh-t-tk'); let tkTuGo = false, luotGoiY = 0;
  const GY_THEM = 'Gợi ý mã trống kế tiếp.', GY_SUA = 'Có bút toán rồi thì không đổi được.';
  async function goiYMaTk() {
    const luot = ++luotGoiY, loai = $('nh-t-loai').value;
    try {
      const d = await KD.api('/api/tai-khoan/ma-tk-tiep-theo?' + KT.url.qs({ loai }));
      if (luot !== luotGoiY || !dlgTk.open) return;   // đã đổi loại lần nữa / người dùng đã tự gõ / đã đóng
      oTk.value = d.tk_ke_toan || ''; tkTuGo = false; $('nh-t-tk-gy').textContent = tkDangSua ? GY_SUA : GY_THEM;
    } catch (err) { if (luot === luotGoiY) $('nh-t-tk-gy').textContent = 'Không lấy được mã gợi ý — nhập tay.'; }
  }
  function datMaTkTheoLoai() {
    const loai = $('nh-t-loai').value;
    oTk.placeholder = 'VD: ' + tkCha(loai) + '1';
    if (tkDangSua) {
      if (dungCha(oTk.value, loai)) return;
      if (dungCha(tkDangSua.tk_ke_toan, loai)) { ++luotGoiY; oTk.value = tkDangSua.tk_ke_toan; return; }   // quay lại loại cũ → mã cũ
      goiYMaTk();
    } else if (!tkTuGo || !dungCha(oTk.value, loai)) goiYMaTk();
  }
  $('nh-t-loai').addEventListener('change', datMaTkTheoLoai);
  oTk.addEventListener('input', () => { tkTuGo = true; ++luotGoiY; const so = oTk.value.replace(/\D/g, ''); if (so !== oTk.value) oTk.value = so; });

  function moTk(t) {
    tkDangSua = t || null;
    $('nh-tk-dlg-td').textContent = t ? 'Sửa tài khoản ' + t.ten_tk : 'Thêm tài khoản';
    const dat = (id, v) => { $(id).value = v || ''; };
    dat('nh-t-ten', t && t.ten_tk); dat('nh-t-nh', t && t.ten_nh); dat('nh-t-cn', t && t.chi_nhanh); dat('nh-t-stk', t && t.so_tk);
    dat('nh-t-chu', t && t.chu_tk); dat('nh-t-mt', t && t.mo_ta); $('nh-t-loai').value = (t && t.loai) || 'ngan_hang'; $('nh-t-dau').value = '';
    dat('nh-t-tk', t && t.tk_ke_toan); tkTuGo = false;
    $('nh-t-tk-gy').textContent = t ? GY_SUA : GY_THEM;
    $('nh-t-ten').readOnly = !!t;
    $('nh-t-ten-gy').textContent = t ? 'Không đổi được tên (đã gắn với giao dịch).' : 'Đặt ngắn, không trùng.';
    $('nh-t-dau-o').hidden = !!t;
    KD.moHopThoai(dlgTk);
    datMaTkTheoLoai();
    if (t) $('nh-t-nh').focus();
  }
  $('nh-them-tk').addEventListener('click', () => moTk(null));
  // Kiểm TK kế toán ở máy khách (máy chủ kiểm lại + kiểm trùng với cả tài khoản ngừng dùng không có trong danh sách).
  function loiMaTk(ma, loai) {
    const cha = tkCha(loai);
    if (!ma) return 'Nhập TK kế toán.';
    if (!dungCha(ma, loai)) return 'TK kế toán phải là TK con của ' + cha + ' (4–6 chữ số, VD ' + cha + '1).';
    const trung = taiKhoan.find((t) => t.tk_ke_toan === ma && (!tkDangSua || t.id !== tkDangSua.id));
    return trung ? 'TK ' + ma + ' đã gán cho tài khoản ' + trung.ten_tk + '.' : '';
  }
  $('nh-form-tk').addEventListener('submit', async (e) => {
    e.preventDefault();
    const v = (id) => $(id).value.trim() || null;
    const body = { loai: $('nh-t-loai').value, ten_nh: v('nh-t-nh'), chi_nhanh: v('nh-t-cn'), so_tk: v('nh-t-stk'), chu_tk: v('nh-t-chu'), mo_ta: v('nh-t-mt'), tk_ke_toan: v('nh-t-tk') };
    if (!tkDangSua) { body.ten_tk = v('nh-t-ten'); body.so_du_dau = docSo($('nh-t-dau').value); }
    if (!tkDangSua && !body.ten_tk) { $('nh-t-ten').focus(); return KD.baoLoiHopThoai(dlgTk, 'Nhập tên tài khoản.'); }
    if (!tkDangSua && taiKhoan.some((t) => t.ten_tk.toLowerCase() === body.ten_tk.toLowerCase())) { $('nh-t-ten').focus(); return KD.baoLoiHopThoai(dlgTk, 'Đã có tài khoản tên "' + body.ten_tk + '".'); }
    const loiTk = loiMaTk(body.tk_ke_toan, body.loai);
    if (loiTk) { oTk.focus(); return KD.baoLoiHopThoai(dlgTk, loiTk); }
    if (body.so_tk && !/^\d{6,20}$/.test(body.so_tk.replace(/\s/g, ''))) { $('nh-t-stk').focus(); return KD.baoLoiHopThoai(dlgTk, 'Số tài khoản chỉ gồm chữ số, dài 6–20 ký tự.'); }
    if (body.so_tk) body.so_tk = body.so_tk.replace(/\s/g, '');
    const nut = $('nh-t-luu'); nut.disabled = true;
    try {
      const r = tkDangSua ? await KD.api('/api/tai-khoan/' + tkDangSua.id, Object.assign(KD.JSON_POST(body), { method: 'PUT' }))
        : await KD.api('/api/tai-khoan', KD.JSON_POST(body));
      dlgTk.close(); ok((tkDangSua ? 'Đã lưu ' : 'Đã thêm ') + r.ten_tk);
      if (!tkDangSua) ds.st.tk = String(r.id);
      sauGhi();
    } catch (err) { KD.baoLoiHopThoai(dlgTk, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; }
  });

  /* ── Chốt số dư đầu kỳ (POST /api/so-du-dau-ky — upsert theo tháng × tài khoản) ── */
  const dlgSd = $('nh-dlg-sd'); let tkSoDu = null;
  async function goiYSoDu() {
    const th = $('nh-sd-thang').value; if (!th || !tkSoDu) return;
    try {
      const ds2 = await KD.api('/api/so-du-dau-ky?thang=' + th);
      const co = (ds2 || []).find((x) => String(x.tai_khoan_id) === String(tkSoDu.id));
      $('nh-sd-gy').textContent = co ? 'Tháng ' + th.slice(5) + '/' + th.slice(0, 4) + ' đã chốt ' + KD.tienVnd(co.so_du) + ' — lưu sẽ ghi đè.' : 'Tháng này chưa chốt số dư.';
      if (co && !$('nh-sd-so').value) $('nh-sd-so').value = KD.tien(Number(co.so_du));
    } catch (e) { $('nh-sd-gy').textContent = 'Không đọc được số dư đã chốt: ' + e.message; }
  }
  function moSoDu(t) {
    tkSoDu = t; $('nh-sd-tk').textContent = 'Tài khoản: ' + tenHt(t);
    $('nh-sd-thang').value = (ds.khoang().tu || KD.iso(new Date())).slice(0, 7); $('nh-sd-so').value = '';
    KD.moHopThoai(dlgSd); goiYSoDu();
  }
  $('nh-sd-thang').addEventListener('change', () => { $('nh-sd-so').value = ''; goiYSoDu(); });
  $('nh-form-sd').addEventListener('submit', async (e) => {
    e.preventDefault();
    const th = $('nh-sd-thang').value, so = $('nh-sd-so').value.trim();
    if (!/^\d{4}-\d{2}$/.test(th)) { $('nh-sd-thang').focus(); return KD.baoLoiHopThoai(dlgSd, 'Chọn tháng.'); }
    if (!so) { $('nh-sd-so').focus(); return KD.baoLoiHopThoai(dlgSd, 'Nhập số dư đầu tháng (nhập 0 nếu tài khoản trống).'); }
    const nut = $('nh-sd-luu'); nut.disabled = true;
    try {
      await KD.api('/api/so-du-dau-ky', KD.JSON_POST({ tai_khoan_id: tkSoDu.id, thang: th + '-01', so_du: docSo(so) }));
      dlgSd.close(); ok('Đã chốt số dư đầu tháng ' + th.slice(5) + '/' + th.slice(0, 4) + ' cho ' + tkSoDu.ten_tk); sauGhi();
    } catch (err) { KD.baoLoiHopThoai(dlgSd, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; }
  });

  /* ── Chuyển nội bộ (POST /api/so-quy/chuyen-noi-bo) ── */
  const dlgC = $('nh-dlg-cnb'); let refChuyen = null;
  $('nh-chuyen').addEventListener('click', () => {
    const dung = taiKhoan.filter((t) => t.active);
    if (dung.length < 2) return window.showToast && window.showToast('info', 'Cần ít nhất 2 tài khoản đang dùng để chuyển nội bộ.');
    const opts = dung.map((t) => '<option value="' + esc(t.ten_tk) + '">' + esc(t.ten_tk) + (tongHop.map[t.id] ? ' · ' + KD.tienGon(tongHop.map[t.id].cuoi) : '') + '</option>').join('');
    $('nh-c-tu').innerHTML = opts; $('nh-c-den').innerHTML = opts;
    const dx = tkDangXem(); if (dx && dx.active) $('nh-c-tu').value = dx.ten_tk;
    $('nh-c-den').value = (dung.find((t) => t.ten_tk !== $('nh-c-tu').value) || {}).ten_tk || '';
    $('nh-c-ngay').value = KD.iso(new Date()); ['nh-c-tien', 'nh-c-nd', 'nh-c-gc'].forEach((id) => { $(id).value = ''; });
    refChuyen = 'chuyennb_' + (window.crypto && crypto.randomUUID ? crypto.randomUUID().replace(/-/g, '').slice(0, 12) : Date.now().toString(36));
    KD.moHopThoai(dlgC);
  });
  $('nh-form-cnb').addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = { tu_tai_khoan: $('nh-c-tu').value, den_tai_khoan: $('nh-c-den').value, ngay: $('nh-c-ngay').value, so_tien: docSo($('nh-c-tien').value),
      noi_dung: $('nh-c-nd').value.trim(), ghi_chu: $('nh-c-gc').value.trim(), ref_id: refChuyen };
    if (body.tu_tai_khoan === body.den_tai_khoan) { $('nh-c-den').focus(); return KD.baoLoiHopThoai(dlgC, 'Tài khoản nguồn và đích phải khác nhau.'); }
    if (!body.ngay) { $('nh-c-ngay').focus(); return KD.baoLoiHopThoai(dlgC, 'Chọn ngày chuyển.'); }
    if (!body.so_tien) { $('nh-c-tien').focus(); return KD.baoLoiHopThoai(dlgC, 'Nhập số tiền lớn hơn 0.'); }
    const nut = $('nh-c-luu'); nut.disabled = true;
    try {
      await KD.api('/api/so-quy/chuyen-noi-bo', KD.JSON_POST(body));
      dlgC.close(); ok('Đã chuyển ' + KD.tienVnd(body.so_tien) + ' từ ' + body.tu_tai_khoan + ' sang ' + body.den_tai_khoan); sauGhi();
    } catch (err) { KD.baoLoiHopThoai(dlgC, 'Chưa chuyển được: ' + err.message); } finally { nut.disabled = false; }
  });

  /* ── Ngừng dùng / dùng lại (PUT active) ── */
  const dlgNg = $('nh-dlg-ngung'); let tkNgung = null;
  function moNgung(t) { tkNgung = t;
    $('nh-ng-nd').textContent = t.ten_tk + (t.so_tk ? ' ' + t.so_tk : '') + ' sẽ ẩn khỏi danh sách đang dùng và khỏi ô chọn tài khoản khi ghi thu/chi. Lịch sử giao dịch giữ nguyên.';
    KD.moHopThoai(dlgNg); }
  async function doiTrangThai(t, active) {
    try { await KD.api('/api/tai-khoan/' + t.id, Object.assign(KD.JSON_POST({ active }), { method: 'PUT' }));
      if (!active) { dlgNg.close(); if (String(ds.st.tk) === String(t.id)) ds.st.tk = ''; }
      ok((active ? 'Đã dùng lại ' : 'Đã ngừng dùng ') + t.ten_tk); sauGhi(); }
    catch (err) { if (!active) KD.baoLoiHopThoai(dlgNg, err.message); else window.showToast && window.showToast('err', err.message); }
  }
  $('nh-ng-ok').addEventListener('click', () => doiTrangThai(tkNgung, false));

  $('nh-nhap').addEventListener('click', () => { KD.moHopThoai($('nh-dlg-sk')); });

  taiLaiTk();
})();
