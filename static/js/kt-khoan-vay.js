/* kt-khoan-vay.js — Khoản vay (khung: kt-danh-sach.js).
   API thật: app/routers/khoan_vay.py — GET /api/khoan-vay (mảng phẳng, không phân trang) ·
   GET /api/khoan-vay/summary (thẻ "Tổng dư nợ gốc / Lãi đã trả YTD / Khoản đang vay / Sắp đáo hạn 30 ngày",
   cùng nguồn với màn cũ /app#khoan-vay) · GET /{id} (lai_suats + giao_dichs) · GET /{id}/lich-tra.
   Thao tác (giống màn cũ): POST /{id}/tra-lai|tra-goc|tra-goc-lai · POST /{id}/lai-suat · POST /{id}/tat-toan · DELETE /{id}.
   Ghi chú:
   - Hệ thống chỉ theo dõi khoản ĐI VAY (loai_vay = hình thức vay: tín chấp/thế chấp/trả góp…).
   - Trạng thái "Quá hạn" / "Sắp đáo hạn" suy từ ngày đáo hạn (CSDL chỉ lưu dang_vay/da_tat_toan/qua_han).
     Thẻ số "Sắp đáo hạn 30 ngày" đếm đúng như /summary: khoản status=dang_vay có 0 ≤ còn ngày ≤ 30.
   - Lọc "Đang vay"/"Đã tất toán" theo đúng status lưu trong CSDL (như màn cũ); "Quá hạn" = status qua_han
     HOẶC đang vay mà đã qua ngày đáo hạn. */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-khoan-vay')) return;
  // Quyền (F3 28/09): xoá khoản vay = DELETE /api/khoan-vay/{id} chỉ admin/ceo (khoan_vay.py delete_khoan_vay). Thêm / sửa hợp đồng,
  // trả lãi / gốc, đổi lãi suất, tất toán mở cho Kế toán (manager/kt) như API.
  const XOA_DUOC = ['admin', 'ceo'].includes(document.getElementById('kd-kt-khoan-vay').dataset.vaiTroGoc);
  const H = KT.H, $ = (id) => document.getElementById(id);
  const TT = { dang_vay: ['success', 'Đang vay'], sap_dao_han: ['warning', 'Sắp đáo hạn'], qua_han: ['danger', 'Quá hạn'], da_tat_toan: ['muted', 'Đã tất toán'] };
  const pillTT = (k) => { const x = TT[k]; return H.pill(x ? x[0] : 'muted', x ? x[1] : 'Chưa đặt tên', k === 'qua_han'); };
  const conNgay = (n) => (n == null ? '' : n < 0 ? 'Quá hạn ' + KD.soDem(-n) + ' ngày' : n === 0 ? 'Đáo hạn hôm nay' : 'Còn ' + KD.soDem(n) + ' ngày');
  const LOAI_VAY = { tin_chap: 'Tín chấp', the_chap: 'Thế chấp', tra_gop_xe: 'Trả góp xe', tra_gop_nha: 'Trả góp nhà', khac: 'Khác' };
  const PT_TRA = { tra_deu: 'Trả đều', chi_lai_dinh_ky: 'Chỉ lãi định kỳ', goc_lai_cuoi_ky: 'Gốc + lãi cuối kỳ', tu_do: 'Tự do' };
  const NHAN_GD = { giai_ngan: 'Giải ngân', tra_goc: 'Trả gốc', tra_lai: 'Trả lãi', tra_goc_lai: 'Trả gốc + lãi' };
  const NGAY_MS = 86400000, SAP_DAO_HAN_NGAY = 30;
  const homNay = () => KD.iso(new Date());
  const docSo = (el) => Number(String(el.value || '').replace(/[^\d]/g, '')) || 0;
  let tomTat = null, tkDs = null;

  function soNgayConLai(kv) {
    return kv.ngay_dao_han ? Math.round((new Date(kv.ngay_dao_han + 'T00:00:00') - new Date(new Date().toDateString())) / NGAY_MS) : null;
  }
  function trangThai(kv) {
    if (kv.status === 'da_tat_toan') return 'da_tat_toan';
    if (kv.status === 'qua_han') return 'qua_han';
    const n = soNgayConLai(kv);
    if (n == null) return 'dang_vay';
    if (n < 0) return 'qua_han';
    return n <= SAP_DAO_HAN_NGAY ? 'sap_dao_han' : 'dang_vay';
  }

  /* API trả mảng phẳng — thẻ số tính trên TOÀN BỘ khoản (như /summary của màn cũ), bảng theo bộ lọc. */
  function chuyen(mang, q) {
    const tatCa = mang.map((kv) => ({
      id: kv.id, ma: kv.ma_khoan, ben: kv.nguon_vay, loai_vay: kv.loai_vay, status: kv.status,
      goc: +kv.so_tien_vay, da_tra_goc: +kv.da_tra_goc || 0, du_no: +kv.con_lai_goc || 0, da_tra_lai: +kv.da_tra_lai || 0,
      lai_suat: kv.lai_suat_hien_tai != null ? +kv.lai_suat_hien_tai : null, pt: kv.phuong_thuc_tra, ky_han: kv.ky_han_thang,
      dao_han: kv.ngay_dao_han, con_ngay: soNgayConLai(kv), trang_thai: trangThai(kv),
    }));
    const tim = q.tim || '';
    const dong = tatCa.filter((r) => {
      // "Quá hạn" / "Sắp đáo hạn" suy từ ngày đáo hạn; "Đang vay" / "Đã tất toán" theo status CSDL (Đang vay gồm cả khoản đã quá hạn — khớp thẻ Tổng dư nợ gốc).
      if (q.status === 'qua_han' || q.status === 'sap_dao_han' ? r.trang_thai !== q.status : (q.status && r.status !== q.status)) return false;
      return KT.khopTim([r.ma, r.ben], tim);
    });
    const dangVay = tatCa.filter((r) => r.status === 'dang_vay');
    const sap = dangVay.filter((r) => r.con_ngay != null && r.con_ngay >= 0 && r.con_ngay <= SAP_DAO_HAN_NGAY);
    const tong = {
      du_no: dangVay.reduce((s, r) => s + r.du_no, 0), so_dang_vay: dangVay.length,
      so_qua_han: tatCa.filter((r) => r.trang_thai === 'qua_han').length,
      sap_so: sap.length, sap_tien: sap.reduce((s, r) => s + r.du_no, 0),
      lai_thang: dangVay.reduce((s, r) => s + (r.lai_suat ? r.du_no * (r.lai_suat / 100) / 12 : 0), 0),
      // Cộng chân bảng theo các dòng đang hiện
      goc_hien: dong.reduce((s, r) => s + r.goc, 0), da_tra_goc_hien: dong.reduce((s, r) => s + r.da_tra_goc, 0),
      du_no_hien: dong.reduce((s, r) => s + r.du_no, 0), da_tra_lai_hien: dong.reduce((s, r) => s + r.da_tra_lai, 0),
      du_no_dv_hien: dong.filter((r) => r.status === 'dang_vay').reduce((s, r) => s + r.du_no, 0), so_dv_hien: dong.filter((r) => r.status === 'dang_vay').length,
    };
    return { dong, tong };
  }

  const kpiLaiYtd = () => (tomTat
    ? { v: H.tienKpi(tomTat.tong_lai_ytd), title: KD.tienVnd(tomTat.tong_lai_ytd), phu: 'Từ 01/01 tới nay' }
    : { v: null, phu: '' });
  function veKpiLaiYtd() {
    const el = document.querySelector('#kv-kpi [data-kpi="lai_ytd"]'); if (!el) return; const x = kpiLaiYtd();
    el.querySelector('[data-v]').innerHTML = x.v == null ? '<span class="kd-muted">—</span>' : x.v; el.querySelector('[data-v]').title = x.title || '';
    el.querySelector('[data-phu]').innerHTML = x.phu;
  }

  const ds = KT.danhSach({
    pfx: 'kv', api: () => '/api/khoan-vay', donVi: 'khoản vay', khongTrang: true, chuyen,
    macDinh: { tim: '', status: '', page: 1, size: 20, sort: '' },
    cot: [
      // Gọn cột (đợt 4): mã + hình thức thành dòng phụ dưới nguồn vay; "đã trả gốc" dưới số gốc; phương thức trả dưới lãi suất.
      { key: 'ben', nhan: 'Khoản vay', ve: (r) => H.ten(r.ben, [r.ma, LOAI_VAY[r.loai_vay] || r.loai_vay].filter(Boolean).join(' · ')) },
      { key: 'goc', nhan: 'Gốc vay', num: true, ve: (r) => KD.tien(r.goc) + (r.da_tra_goc ? '<span class="kt-khach__ma">Đã trả ' + KD.tien(r.da_tra_goc) + '</span>' : '') },
      { key: 'du_no', nhan: 'Còn nợ gốc', num: true, cls: 'kt-so--con', ve: (r) => H.tien(r.du_no) + (r.status === 'da_tat_toan' && r.du_no > 0 ? '<span class="kt-khach__ma kt-so--xau">Còn dư gốc' + KD.tip('Khoản đã tất toán nhưng số đã trả gốc chưa đủ — kiểm tra lại giao dịch trả gốc, lãi.', 'kd-tip--trai') + '</span>' : '') },
      { key: 'lai', nhan: 'Lãi suất', num: true, ve: (r) => (r.lai_suat != null ? KD.phanTram(r.lai_suat) + '/năm' : '—') + '<span class="kt-khach__ma">' + esc(PT_TRA[r.pt] || r.pt || '—') + '</span>' },
      { key: 'da_tra_lai', nhan: 'Đã trả lãi', num: true, ve: (r) => H.tien(r.da_tra_lai) },
      { key: 'dao_han', nhan: 'Đáo hạn', ve: (r) => KD.ngay(r.dao_han) + (r.status === 'da_tat_toan' ? '' : '<span class="kt-khach__ma">' + conNgay(r.con_ngay) + '</span>') },
      { key: 'tt', nhan: 'Trạng thái', ve: (r) => pillTT(r.trang_thai) },
      { key: 'act', nhan: 'Thao tác', act: true, nhanDong: (r) => r.ma },
    ],
    kpi: {
      du_no: (d) => ({ v: H.tienKpi(d.tong.du_no), title: KD.tienVnd(d.tong.du_no), phu: KD.soDem(d.tong.so_dang_vay) + ' khoản đang vay' + (d.tong.so_qua_han ? ' · ' + H.pill('danger', KD.soDem(d.tong.so_qua_han) + ' quá hạn') : '') }),
      lai_ytd: kpiLaiYtd,
      sap_dao_han: (d) => ({ v: H.dem(d.tong.sap_so, 'khoản'), phu: d.tong.sap_so ? H.pill('warning', 'Cần chuẩn bị ' + KD.tienVnd(d.tong.sap_tien)) : 'Không có khoản nào' }),
      lai_thang: (d) => ({ v: H.tienKpi(d.tong.lai_thang), title: KD.tienVnd(d.tong.lai_thang), phu: 'Ước tính, chưa ghi sổ' }),
    },
    cong: (d) => [{ html: 'Cộng (' + KD.soDem(d.dong.length) + ' khoản)' }, { html: KD.tien(d.tong.goc_hien) + '<span class="kt-khach__ma">Đã trả ' + KD.tien(d.tong.da_tra_goc_hien) + '</span>', num: true },
      // Cộng "Còn nợ gốc" gồm cả khoản đã tất toán mà CSDL vẫn còn dư gốc → ghi rõ phần đang vay (= thẻ Tổng dư nợ gốc khi không lọc).
      { html: KD.tien(d.tong.du_no_hien) + (d.tong.du_no_dv_hien !== d.tong.du_no_hien ? '<span class="kt-khach__ma">Đang vay ' + KD.tien(d.tong.du_no_dv_hien) + KD.tip(KD.soDem(d.tong.so_dv_hien) + ' khoản đang vay — bằng thẻ Tổng dư nợ gốc (chỉ cộng khoản đang vay).', 'kd-tip--trai') + '</span>' : ''), num: true }, { html: '' }, { html: KD.tien(d.tong.da_tra_lai_hien), num: true }, { html: '' }, { html: '' }, { html: '' }],
    rong: (d, coLoc) => (coLoc ? ['Không có khoản vay nào khớp bộ lọc', 'Thử bỏ bớt điều kiện lọc.'] : ['Chưa có khoản vay nào', 'Bấm "Thêm hợp đồng vay" để theo dõi dư nợ và lịch trả lãi.']),
    loi: 'Không tải được danh sách khoản vay',
    sauTai: () => {
      // Lãi YTD không phụ thuộc bộ lọc → chỉ tải 1 lần; sau khi ghi giao dịch (tomTat = null) mới tải lại.
      if (tomTat) return;
      KD.api('/api/khoan-vay/summary').then((s) => { tomTat = s; veKpiLaiYtd(); })
        .catch(() => { const el = document.querySelector('#kv-kpi [data-kpi="lai_ytd"] [data-phu]'); if (el) el.textContent = 'Không tải được số lãi đã trả'; });
    },
    panel: {
      tai: (r) => '/api/khoan-vay/' + encodeURIComponent(r.id),
      ve: (v, r) => {
        const gd = (v.giao_dichs || []).slice().sort((a, b) => (a.ngay < b.ngay ? 1 : -1));
        const ls = (v.lai_suats || []).slice().sort((a, b) => (a.tu_ngay < b.tu_ngay ? 1 : -1));
        const soGoc = (g) => (g.loai === 'tra_goc' ? g.so_tien : g.loai === 'tra_goc_lai' ? g.so_tien_goc : 0);
        const soLai = (g) => (g.loai === 'tra_lai' ? g.so_tien : g.loai === 'tra_goc_lai' ? g.so_tien_lai : 0);
        return H.dauPanel('bi-bank', 'danger', v.ma_khoan, esc(v.nguon_vay), pillTT(r.trang_thai))
          + H.kv([['Hình thức vay', esc(LOAI_VAY[v.loai_vay] || v.loai_vay)], ['Ngày vay', KD.ngay(v.ngay_vay)], ['Kỳ hạn', KD.soDem(v.ky_han_thang) + ' tháng'],
            ['Ngày đáo hạn', KD.ngay(v.ngay_dao_han) + (r.status === 'da_tat_toan' ? '' : ' · ' + conNgay(r.con_ngay))], ['Lãi suất hiện hành', v.lai_suat_hien_tai != null ? KD.phanTram(v.lai_suat_hien_tai) + '/năm' : 'Chưa đặt'],
            ['Phương thức trả', esc(PT_TRA[v.phuong_thuc_tra] || v.phuong_thuc_tra)], ['Tài sản thế chấp', esc(v.tai_san_the_chap || '—')], ['TK giải ngân', esc(v.tai_khoan_giai_ngan || '—')],
            v.ghi_chu ? ['Ghi chú', esc(v.ghi_chu)] : null])
          + H.khoi('bi-cash-stack', 'Số tiền', H.kv([['Số gốc', KD.tienVnd(v.so_tien_vay)], ['Đã trả gốc', KD.tienVnd(v.da_tra_goc)], ['Còn lại gốc', KD.tienVnd(v.con_lai_goc), true], ['Đã trả lãi', KD.tienVnd(v.da_tra_lai)]]))
          + H.khoi('bi-percent', 'Lịch sử lãi suất', ls.length ? '<div class="kd-table-scroll"><table class="kt-bang-nho"><thead><tr><th scope="col">Từ ngày</th><th scope="col" class="num">%/năm</th><th scope="col" class="num">%/tháng</th><th scope="col">Ghi chú</th></tr></thead><tbody>'
            + ls.map((x) => '<tr><td>' + KD.ngay(x.tu_ngay) + '</td><td class="num">' + Number(x.lai_suat_nam).toFixed(2) + '</td><td class="num">' + (Number(x.lai_suat_nam) / 12).toFixed(3) + '</td><td>' + esc(x.ghi_chu || '—') + '</td></tr>').join('') + '</tbody></table></div>'
            : KD.khoiRong('Chưa có lịch sử lãi suất', ''))
          + H.khoi('bi-clock-history', 'Giao dịch (' + KD.soDem(gd.length) + ')', gd.length ? '<div class="kd-table-scroll"><table class="kt-bang-nho"><thead><tr><th scope="col">Ngày</th><th scope="col">Loại</th><th scope="col" class="num">Gốc</th><th scope="col" class="num">Lãi</th><th scope="col">Sổ quỹ</th></tr></thead><tbody>'
            + gd.map((g) => '<tr' + (g.ghi_chu ? ' title="' + esc(g.ghi_chu) + '"' : '') + '><td>' + KD.ngay(g.ngay) + '</td><td>' + esc(NHAN_GD[g.loai] || g.loai) + '</td><td class="num">' + KT.tienSo(g.loai === 'giai_ngan' ? g.so_tien : soGoc(g)) + '</td><td class="num">' + KT.tienSo(soLai(g)) + '</td><td>' + (g.ref_so_quy_id ? '#' + g.ref_so_quy_id : '—') + '</td></tr>').join('')
            + '</tbody></table></div>' : KD.khoiRong('Chưa có giao dịch nào', ''))
          + '<section class="kd-block" id="kv-p-du-kien"><h3 class="kd-block__title"><i class="bi bi-calendar3" aria-hidden="true"></i>Lịch trả dự kiến</h3><p class="kd-muted">Đang tải…</p></section>';
      },
      sau: (nd, v) => {
        const el = nd.querySelector('#kv-p-du-kien'); if (!el) return;
        const dau = '<h3 class="kd-block__title"><i class="bi bi-calendar3" aria-hidden="true"></i>Lịch trả dự kiến';
        KD.api('/api/khoan-vay/' + encodeURIComponent(v.id) + '/lich-tra').then((lt) => {
          if (!nd.isConnected) return;
          const items = lt.items || [];
          if (!items.length) { el.innerHTML = dau + '</h3>' + KD.khoiRong('Không có lịch dự kiến', lt.note || 'Phương thức trả tự do — không tính lịch.'); return; }
          const tGoc = items.reduce((s, x) => s + (+x.so_tien_goc || 0), 0), tLai = items.reduce((s, x) => s + (+x.so_tien_lai || 0), 0);
          const hn = homNay(), toi = items.findIndex((x) => x.ngay >= hn);
          const tu = Math.max(0, (toi < 0 ? items.length : toi) - 2), doan = items.slice(tu, tu + 8);
          el.innerHTML = dau + ' (' + KD.soDem(items.length) + ' kỳ)' + KD.tip('Tính theo lãi suất hiện hành.', 'kd-tip--trai') + '</h3>'
            + H.kv([['Tổng gốc', KD.tienVnd(Math.round(tGoc))], ['Tổng lãi dự kiến', KD.tienVnd(Math.round(tLai))], ['Tổng phải trả', KD.tienVnd(Math.round(tGoc + tLai)), true]])
            + '<div class="kd-table-scroll"><table class="kt-bang-nho"><thead><tr><th scope="col">Kỳ</th><th scope="col">Ngày</th><th scope="col" class="num">Gốc</th><th scope="col" class="num">Lãi</th><th scope="col" class="num">Tổng</th></tr></thead><tbody>'
            + doan.map((x, i) => '<tr class="' + (tu + i === toi ? 'is-nay' : '') + '"><td>' + (tu + i + 1) + '</td><td>' + KD.ngay(x.ngay) + '</td><td class="num">' + KT.tienSo(Math.round(x.so_tien_goc)) + '</td><td class="num">' + KT.tienSo(Math.round(x.so_tien_lai)) + '</td><td class="num">' + KD.tien(Math.round(x.so_tien_tong)) + '</td></tr>').join('') + '</tbody></table></div>';
        }).catch(() => { if (nd.isConnected) el.innerHTML = dau + '</h3><p class="kd-muted">Không tải được lịch dự kiến.</p>'; });
      },
      nut: (v) => '<a class="kd-btn kd-btn--grow" href="/ketoan/khoan-vay/phieu?id=' + v.id + '"><i class="bi bi-pencil" aria-hidden="true"></i>Sửa hợp đồng</a>'
        + '<a class="kd-btn kd-btn--grow" href="/ketoan/so-cai?tk=' + (v.ky_han_thang > 12 ? '341' : '311') + '&ky=nam_nay"><i class="bi bi-journal-text" aria-hidden="true"></i>Sổ cái TK ' + (v.ky_han_thang > 12 ? '341' : '311') + '</a>',
    },
    menu: (r) => {
      const mo = r.status !== 'da_tat_toan';
      return [
        { nhan: 'Sửa hợp đồng', icon: 'bi-pencil', href: '/ketoan/khoan-vay/phieu?id=' + r.id },
        mo ? { nhan: 'Trả lãi', icon: 'bi-percent', onClick: () => moTra(r, 'tra_lai') } : null,
        mo ? { nhan: 'Trả gốc', icon: 'bi-cash-coin', onClick: () => moTra(r, 'tra_goc') } : null,
        mo ? { nhan: 'Trả gốc + lãi', icon: 'bi-cash-stack', onClick: () => moTra(r, 'tra_goc_lai') } : null,
        { nhan: 'Đổi lãi suất', icon: 'bi-graph-up-arrow', onClick: () => moLaiSuat(r) },
        mo ? { nhan: 'Tất toán khoản vay', icon: 'bi-check2-circle', onClick: () => hoi(r, 'tat_toan') } : null,
        XOA_DUOC ? '-' : null,
        XOA_DUOC ? { nhan: 'Xoá khoản vay', icon: 'bi-trash', danger: true, onClick: () => hoi(r, 'xoa') } : null,
      ].filter(Boolean);
    },
  });

  /* ── Trả lãi / gốc / gốc + lãi ── */
  const dTra = $('kv-dlg-tra'); let traDang = null;
  const TIEU_DE_TRA = { tra_lai: 'Trả lãi', tra_goc: 'Trả gốc', tra_goc_lai: 'Trả gốc + lãi' };
  async function napTk() {
    if (tkDs) return tkDs;
    try { tkDs = (await KD.api('/api/tai-khoan')).filter((t) => t.active); } catch (e) { tkDs = []; }
    return tkDs;
  }
  async function moTra(r, kieu) {
    traDang = { r, kieu };
    $('kv-tra-td').textContent = TIEU_DE_TRA[kieu] + ' — ' + r.ma;
    $('kv-tra-tt').innerHTML = '<dt>Nguồn vay</dt><dd>' + esc(r.ben) + '</dd><dt>Còn lại gốc</dt><dd>' + KD.tienVnd(r.du_no) + '</dd>'
      + '<dt>Lãi ước tính 1 tháng</dt><dd>' + (r.lai_suat ? KD.tienVnd(Math.round(r.du_no * r.lai_suat / 100 / 12)) : '—') + '</dd>';
    $('kv-tra-goc-o').hidden = kieu === 'tra_lai'; $('kv-tra-lai-o').hidden = kieu === 'tra_goc';
    ['kv-tra-goc', 'kv-tra-lai', 'kv-tra-gc'].forEach((id) => { $(id).value = ''; });
    $('kv-tra-ngay').value = homNay();
    $('kv-tra-gy').innerHTML = 'Tự ghi phiếu chi sổ quỹ và bút toán' + KD.tip(kieu === 'tra_goc'
      ? 'Nợ ' + (r.ky_han > 12 ? '341' : '311') + ' / Có 111 hoặc 112 (theo tài khoản trả).'
      : 'Phần lãi ghi chi phí "Lãi vay" (TK 635).');
    const sel = $('kv-tra-tk'); const tks = await napTk();
    sel.innerHTML = '<option value="">— Không chọn —</option>' + tks.map((t) => '<option value="' + t.id + '">' + esc(t.ten_tk + (t.so_tk ? ' — ' + t.so_tk : '')) + '</option>').join('');
    KD.moHopThoai(dTra);
  }
  ['kv-tra-goc', 'kv-tra-lai'].forEach((id) => $(id).addEventListener('input', (e) => { const n = docSo(e.target); e.target.value = n ? KD.tien(n) : ''; }));
  $('kv-form-tra').addEventListener('submit', async (e) => {
    e.preventDefault(); if (!traDang) return;
    const { r, kieu } = traDang, ngay = $('kv-tra-ngay').value, goc = docSo($('kv-tra-goc')), lai = docSo($('kv-tra-lai'));
    const tkId = +$('kv-tra-tk').value || null, tk = tkId ? (tkDs.find((t) => t.id === tkId) || {}).ten_tk : null;
    const gc = $('kv-tra-gc').value.trim() || null;
    if (!ngay) return KD.baoLoiHopThoai(dTra, 'Chọn ngày trả.');
    let body;
    if (kieu === 'tra_goc_lai') {
      if (goc <= 0) return KD.baoLoiHopThoai(dTra, 'Nhập số tiền gốc lớn hơn 0.');
      body = { ngay, so_tien_goc: goc, so_tien_lai: lai, tai_khoan: tk, tai_khoan_id: tkId, ghi_chu: gc };
    } else {
      const so = kieu === 'tra_lai' ? lai : goc;
      if (so <= 0) return KD.baoLoiHopThoai(dTra, 'Nhập số tiền lớn hơn 0.');
      body = { ngay, so_tien: so, tai_khoan: tk, tai_khoan_id: tkId, ghi_chu: gc };
    }
    if (kieu !== 'tra_lai' && goc > r.du_no) return KD.baoLoiHopThoai(dTra, 'Số tiền gốc vượt dư nợ còn lại (' + KD.tienVnd(r.du_no) + ').');
    const nut = $('kv-tra-ok'); nut.disabled = true;
    try {
      await KD.api('/api/khoan-vay/' + r.id + '/' + kieu.replace(/_/g, '-'), KD.JSON_POST(body));
      dTra.close(); window.showToast && window.showToast('ok', 'Đã ghi ' + TIEU_DE_TRA[kieu].toLowerCase() + ' cho ' + r.ma);
      ds.dongPanel(); tomTat = null; ds.tai();
    } catch (err) { KD.baoLoiHopThoai(dTra, 'Chưa ghi được: ' + err.message); } finally { nut.disabled = false; }
  });

  /* ── Đổi lãi suất ── */
  const dLs = $('kv-dlg-ls'); let lsDang = null;
  function moLaiSuat(r) {
    lsDang = r;
    $('kv-ls-td').textContent = 'Đổi lãi suất — ' + r.ma;
    $('kv-ls-tt').innerHTML = '<dt>Lãi suất hiện hành</dt><dd>' + (r.lai_suat != null ? KD.phanTram(r.lai_suat) + '/năm' : 'Chưa đặt') + '</dd>';
    $('kv-ls-ngay').value = homNay(); $('kv-ls-muc').value = ''; $('kv-ls-gc').value = '';
    KD.moHopThoai(dLs);
  }
  $('kv-form-ls').addEventListener('submit', async (e) => {
    e.preventDefault(); if (!lsDang) return;
    const tu = $('kv-ls-ngay').value, raw = $('kv-ls-muc').value;
    const muc = Number(String(raw).replace(',', '.'));
    if (!tu) return KD.baoLoiHopThoai(dLs, 'Chọn ngày áp dụng.');
    if (raw === '' || !(muc >= 0 && muc <= 100)) return KD.baoLoiHopThoai(dLs, 'Lãi suất phải từ 0 đến 100 %/năm.');
    const nut = $('kv-ls-ok'); nut.disabled = true;
    try {
      await KD.api('/api/khoan-vay/' + lsDang.id + '/lai-suat', KD.JSON_POST({ tu_ngay: tu, lai_suat_nam: muc, ghi_chu: $('kv-ls-gc').value.trim() || null }));
      dLs.close(); window.showToast && window.showToast('ok', 'Đã áp dụng lãi suất ' + KD.phanTram(muc) + ' cho ' + lsDang.ma);
      ds.dongPanel(); tomTat = null; ds.tai();
    } catch (err) { KD.baoLoiHopThoai(dLs, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; }
  });

  /* ── Tất toán / xoá (hỏi lại) ── */
  const dHoi = $('kv-dlg-hoi'); let hoiDang = null;
  function hoi(r, viec) {
    hoiDang = { r, viec };
    const xoa = viec === 'xoa';
    $('kv-hoi-td').textContent = xoa ? 'Xoá khoản vay ' + r.ma + '?' : 'Tất toán khoản vay ' + r.ma + '?';
    $('kv-hoi-nd').textContent = xoa
      ? 'Xoá hợp đồng cùng toàn bộ lịch sử lãi suất và giao dịch của nó. Không hoàn tác được — chỉ admin/CEO được xoá.'
      : 'Đánh dấu khoản vay là ĐÃ TẤT TOÁN (còn lại gốc hiện tại: ' + KD.tienVnd(r.du_no) + '). Thao tác này không ghi thêm bút toán trả nợ.';
    const ok = $('kv-hoi-ok'); ok.className = 'kd-btn ' + (xoa ? 'kd-btn--danger' : 'kd-btn--primary');
    ok.innerHTML = xoa ? '<i class="bi bi-trash" aria-hidden="true"></i>Xoá khoản vay' : '<i class="bi bi-check2-circle" aria-hidden="true"></i>Tất toán';
    KD.moHopThoai(dHoi); $('kv-hoi-ok').focus();
  }
  $('kv-hoi-ok').addEventListener('click', async () => {
    if (!hoiDang) return; const { r, viec } = hoiDang, nut = $('kv-hoi-ok'); nut.disabled = true;
    try {
      if (viec === 'xoa') await KD.api('/api/khoan-vay/' + r.id, { method: 'DELETE', headers: { Accept: 'application/json' } });
      else await KD.api('/api/khoan-vay/' + r.id + '/tat-toan', KD.JSON_POST({}));
      dHoi.close(); window.showToast && window.showToast('ok', (viec === 'xoa' ? 'Đã xoá ' : 'Đã tất toán ') + r.ma);
      ds.dongPanel(); tomTat = null; ds.tai();
    } catch (err) { KD.baoLoiHopThoai(dHoi, 'Chưa thực hiện được: ' + err.message); } finally { nut.disabled = false; }
  });

  ds.tai();
})();
