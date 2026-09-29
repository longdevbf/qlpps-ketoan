/* kt-phan-phoi.js — Phân phối lợi nhuận (khung: kt-danh-sach.js + hộp thoại lập phân phối).
   KHÔNG có endpoint /api/phan-phoi-ln thật — màn này ghép từ nhiều API thật đã có:
     - GET  /api/von-csh?limit=500          lịch sử VCSH — lấy trich_quy, chia_co_tuc và gop_von "Chuyển LN giữ lại thành vốn"
     - GET  /api/von-csh/summary            tong_chia_co_tuc / tong_trich_quy (2 thẻ số giống màn cũ)
     - GET  /api/quy-dn?active_only=true    số dư từng quỹ DN (không có cột "tk" — suy theo tên,
                                             cùng quy tắc map_quy_to_account() ở app/services/journal.py)
     - GET  /api/bao-cao/can-doi            LN giữ lại (TK 421) — "chưa phân phối"
     - GET  /api/bao-cao/pl?thang=          KQ tháng hiện tại (chưa kết chuyển)
     - GET  /api/tai-khoan                  tài khoản tiền để chi cổ tức
     - POST /api/von-csh/trich-quy          Nợ 421 / Có 414|415|353 — cần quy_id thật
     - POST /api/von-csh/chia-co-tuc        Nợ 421 / Có 111|112 — CHỈ ghi bút toán khi có tai_khoan_id (QA 25/09: bản
                                             trước không gửi tai_khoan_id nên máy chủ chỉ lưu dòng VCSH, KHÔNG có bút toán
                                             và không trừ tiền, dù định khoản trên màn ghi "Có tiền") → giờ bắt buộc chọn TK.
     - POST /api/von-csh/chuyen-ln-thanh-von  Nợ 421 / Có 411 (màn cũ có, bản trước thiếu)
     - DELETE /api/von-csh/{id}             xoá + đảo bút toán, hoàn quỹ (màn cũ có nút Xoá, bản trước thiếu)
   GHI CHÚ:
   1) Không có TK 332 "phải trả cổ tức" — chia cổ tức chi tiền ngay.
   2) "Lập phân phối" gọi các API TUẦN TỰ, KHÔNG atomic — gọi sau lỗi thì khoản trước đã ghi sổ (báo rõ khoản nào).
   3) Lịch sử gộp các dòng có cùng tiền tố `[PPLN <ngày>] …` do màn này tự gắn; dòng cũ/ghi nơi khác hiện riêng từng dòng.
   4) Màn cũ gọi /api/von-csh?loai=chia_co_tuc,trich_quy → máy chủ trả 400 (loai không hợp lệ) nên bảng lịch sử cũ
      luôn kẹt "Đang tải..." — màn mới lấy toàn bộ rồi lọc ở trình duyệt. */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-phan-phoi')) return;
  const H = KT.H;
  // Quyền (F3 28/09): trích quỹ / chia cổ tức / chuyển vốn / xoá = /api/von-csh/* chỉ admin/ceo (von_csh.py _require_vcsh_admin,
  // delete_von_csh — hẹp hơn KD.coQuyen('ceo'), không gồm trợ lý CEO). Người khác chỉ xem: ẩn "Lập phân phối" + cột thao tác.
  const GHI_DUOC = ['admin', 'ceo'].includes(document.getElementById('kd-kt-phan-phoi').dataset.vaiTroGoc);
  const TAG_RE = /^\[PPLN (\d{4}-\d{2}-\d{2})\]\s*/;
  const TIEN_TO_VON = 'Chuyển LN giữ lại thành vốn';
  const homNay = () => KD.iso(new Date());
  const thangHomNay = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0'); };
  function layTkQuy(tenQuy) {  // cùng quy tắc map_quy_to_account() thật (app/services/journal.py)
    const t = (tenQuy || '').toLowerCase();
    if (t.includes('khen thưởng') || t.includes('phúc lợi') || t.includes('phuc loi')) return '353';
    if (t.includes('dự phòng') || t.includes('du phong')) return '415';
    return '414';
  }

  /* Quỹ thuộc cột nào của bảng (ĐTPT / KT-PL / Quỹ khác) — dùng CHUNG cho bảng lịch sử và dòng phụ thẻ
     "Đã trích quỹ" (QA nhất quán 25/09: thẻ cũ cộng MỌI quỹ TK 414 — Du Lịch, Quỹ Công Ty… — dưới nhãn
     "quỹ ĐTPT", còn cột "Quỹ ĐTPT" chỉ gồm quỹ tên "đầu tư" → cùng nhãn, hai định nghĩa). */
  function cotQuy(tenQuy) {
    const tk = layTkQuy(tenQuy), ten = (tenQuy || '').toLowerCase();
    if (tk === '353' && ten.includes('khen thưởng')) return 'quy_ktpl';
    if (tk === '414' && ten.includes('đầu tư')) return 'quy_dtpt';
    return 'quy_khac';
  }

  /* ── Dữ liệu phụ (số dư quỹ, LN giữ lại, KQ kỳ hiện tại, tổng VCSH) — nạp nền, vẽ lại khi có. ── */
  let phu = { chua_phan_phoi: null, ky_chua_ket_chuyen: null, quy: [], quyTheoId: {}, tong_chia_co_tuc: null, tong_trich_quy: null, tk: [], den_ngay: homNay() };
  let dangTaiPhu = false, phuLoi = false;
  async function taiPhu() {
    if (dangTaiPhu || phuLoi) return; dangTaiPhu = true;
    try {
      const [canDoi, pl, quyDs, tomTat, tkDs] = await Promise.all([
        KD.api('/api/bao-cao/can-doi'),
        KD.api('/api/bao-cao/pl?thang=' + thangHomNay()).catch(() => null),
        KD.api('/api/quy-dn?active_only=true').catch(() => []),
        KD.api('/api/von-csh/summary').catch(() => null),
        KD.api('/api/tai-khoan').catch(() => []),
      ]);
      const quyTheoId = {}; (quyDs || []).forEach((q) => { quyTheoId[q.id] = q; });
      phu = {
        chua_phan_phoi: canDoi.nguon_von.von_csh.ln_giu_lai,
        ky_chua_ket_chuyen: pl ? pl.lnst : null,
        quy: (quyDs || []).map((q) => ({ id: q.id, tk: layTkQuy(q.ten_quy), cot: cotQuy(q.ten_quy), ten: q.ten_quy, so_du: +q.so_du })),
        quyTheoId,
        tong_chia_co_tuc: tomTat ? +tomTat.tong_chia_co_tuc : null,
        tong_trich_quy: tomTat ? +tomTat.tong_trich_quy : null,
        tk: (tkDs || []).filter((t) => t.active !== false),
        den_ngay: canDoi.thang ? KD.iso(new Date(+canDoi.thang.slice(0, 4), +canDoi.thang.slice(5, 7), 0)) : homNay(),   // ngày cuối tháng, giờ địa phương (toISOString lùi 1 ngày ở UTC+7)
      };
    } catch (e) { phuLoi = true; /* không tự thử lại vô hạn — thẻ số hiện "—", không chặn màn */ }
    dangTaiPhu = false;
    ds.tai();
  }

  /* /api/von-csh trả mảng phẳng mọi loại giao dịch VCSH — lọc + gộp thành "lần phân phối". */
  function chuyen(mang) {
    const laVon = (v) => v.loai_giao_dich === 'gop_von' && (v.ghi_chu || '').startsWith(TIEN_TO_VON);
    const rows = mang.filter((v) => v.loai_giao_dich === 'trich_quy' || v.loai_giao_dich === 'chia_co_tuc' || laVon(v));
    const nhom = new Map();
    rows.forEach((v) => {
      const gc = laVon(v) ? (v.ghi_chu || '').slice(TIEN_TO_VON.length).replace(/^\s*—\s*/, '') : (v.ghi_chu || '');
      const m = TAG_RE.exec(gc);
      const key = m ? 'PPLN_' + m[1] + '_' + gc.slice(m[0].length) : 'DON_' + v.id;
      if (!nhom.has(key)) nhom.set(key, { id: v.id, ids: [], ngay: v.ngay, quy_dtpt: 0, quy_ktpl: 0, quy_khac: 0, chia_csh: 0, chuyen_von: 0, chu: new Set(), ghi_chu: m ? gc.slice(m[0].length) : gc, nguoi_lap: v.created_by });
      const g = nhom.get(key); g.ids.push(v.id); if (v.chu_so_huu && v.chu_so_huu !== 'DN') g.chu.add(v.chu_so_huu);
      if (v.loai_giao_dich === 'chia_co_tuc') { g.chia_csh += +v.so_tien; return; }
      if (v.loai_giao_dich === 'gop_von') { g.chuyen_von += +v.so_tien; return; }
      const q = v.quy_id != null ? phu.quyTheoId[v.quy_id] : null;
      g[q ? cotQuy(q.ten_quy) : 'quy_dtpt'] += +v.so_tien;   // chưa rõ quỹ → gộp ĐTPT như trước
    });
    const dong = [...nhom.values()].map((g) => Object.assign(g, { so_ct: '#' + g.id, doi_tuong: [...g.chu].join(', '), tong: g.quy_dtpt + g.quy_ktpl + g.quy_khac + g.chia_csh + g.chuyen_von }))
      .sort((a, b) => (a.ngay < b.ngay ? 1 : a.ngay > b.ngay ? -1 : b.id - a.id));
    return {
      dong, den_ngay: phu.den_ngay, chua_phan_phoi: phu.chua_phan_phoi, ky_chua_ket_chuyen: phu.ky_chua_ket_chuyen,
      quy: phu.quy, tong_chia_co_tuc: phu.tong_chia_co_tuc, tong_trich_quy: phu.tong_trich_quy,
    };
  }
  /* SUM mọi quỹ cùng cột (xem cotQuy) — KHÔNG dùng .find() (bỏ sót số dư các quỹ còn lại). */
  const quy = (d, cot) => (d.quy || []).filter((q) => q.cot === cot).reduce((s, q) => s + (q.so_du || 0), 0);

  const ds = KT.danhSach({
    pfx: 'pp', api: () => '/api/von-csh?' + KT.url.qs({ limit: 500 }), donVi: 'lần phân phối', khongTrang: true, chuyen,
    macDinh: { page: 1, size: 20, sort: '' },
    cot: [
      // Gọn cột (đợt 4): tham chiếu dưới ngày; đối tượng + người lập dưới căn cứ.
      { key: 'ngay', nhan: 'Ngày', ve: (r) => KD.ngay(r.ngay) + '<span class="kt-khach__ma">' + esc(r.so_ct) + '</span>' },
      { key: 'ghi_chu', nhan: 'Căn cứ', ve: (r) => H.ten(r.ghi_chu || '—', [r.doi_tuong, r.nguoi_lap ? 'Lập: ' + r.nguoi_lap : ''].filter(Boolean).join(' · ')) },
      { key: 'quy_dtpt', nhan: 'Quỹ ĐTPT', num: true, ve: (r) => H.tien(r.quy_dtpt) },
      { key: 'quy_ktpl', nhan: 'Quỹ KT-PL', num: true, ve: (r) => H.tien(r.quy_ktpl) },
      { key: 'quy_khac', nhan: 'Quỹ khác', num: true, ve: (r) => H.tien(r.quy_khac) },
      { key: 'chia_csh', nhan: 'Cổ tức', num: true, ve: (r) => H.tien(r.chia_csh) },
      { key: 'chuyen_von', nhan: 'Vốn góp', num: true, ve: (r) => H.tien(r.chuyen_von) },
      { key: 'tong', nhan: 'Tổng', num: true, cls: 'kd-strong', ve: (r) => KD.tien(r.tong) },
      { key: 'act', nhan: 'Thao tác', act: true, nhanDong: (r) => 'lần phân phối ' + r.so_ct },
    ].filter((k) => GHI_DUOC || !k.act),
    kpi: {
      chua_pp: (d) => (d.chua_phan_phoi == null ? { v: null, phu: phuLoi ? 'Không tải được' : 'Đang tải…' } : { v: H.tienKpi(d.chua_phan_phoi), title: KD.tienVnd(d.chua_phan_phoi), phu: 'Đến ' + KD.ngay(d.den_ngay) }),
      chua_kc: (d) => (d.ky_chua_ket_chuyen == null ? { v: null, phu: phuLoi ? 'Không tải được' : 'Đang tải…' } : { v: H.tienKpi(d.ky_chua_ket_chuyen), title: KD.tienVnd(d.ky_chua_ket_chuyen), phu: 'Chưa kết chuyển' }),
      da_trich: (d) => (d.tong_trich_quy == null ? { v: null, phu: phuLoi ? 'Không tải được' : 'Đang tải…' } : { v: H.tienKpi(d.tong_trich_quy), title: KD.tienVnd(d.tong_trich_quy), phu: 'Số dư các quỹ' + KD.tip('Số dư quỹ ĐTPT ' + KD.tienGon(quy(d, 'quy_dtpt')) + ' · KT-PL ' + KD.tienGon(quy(d, 'quy_ktpl')) + ' · quỹ khác ' + KD.tienGon(quy(d, 'quy_khac'))) }),
      phai_tra: (d) => (d.tong_chia_co_tuc == null ? { v: null, phu: phuLoi ? 'Không tải được' : 'Đang tải…' } : { v: H.tienKpi(d.tong_chia_co_tuc), title: KD.tienVnd(d.tong_chia_co_tuc), phu: 'Chi ngay khi ghi sổ' + KD.tip('Không có khoản "phải trả cổ tức" (TK 332).', 'kd-tip--trai') }),
    },
    cong: (d) => { const S = (k) => d.dong.reduce((s, r) => s + (r[k] || 0), 0);
      return [{ html: 'Cộng ' + KD.soDem(d.dong.length) + ' lần', span: 2 }, { html: KD.tien(S('quy_dtpt')), num: true }, { html: KD.tien(S('quy_ktpl')), num: true }, { html: KD.tien(S('quy_khac')), num: true },
        { html: KD.tien(S('chia_csh')), num: true }, { html: KD.tien(S('chuyen_von')), num: true }, { html: KD.tien(S('tong')), num: true }, { html: '' }].slice(0, GHI_DUOC ? undefined : -1); },
    rong: () => ['Chưa phân phối lợi nhuận lần nào', GHI_DUOC ? 'Khi có nghị quyết phân phối, bấm "Lập phân phối" để trích quỹ, chia cổ tức hoặc chuyển thành vốn góp.' : 'CEO / Admin lập phân phối khi có nghị quyết — bạn xem lịch sử ở đây.'],
    loi: 'Không tải được số liệu phân phối lợi nhuận',
    sauTai: (d) => { du = d; const co = d.chua_phan_phoi > 0; $('pp-lap').disabled = !co; $('pp-lap').title = co ? '' : 'Chưa có lợi nhuận đã kết chuyển để phân phối (hoặc đang tải)'; },
    khiLoi: () => { $('pp-lap').disabled = true; },
    menu: GHI_DUOC ? (r) => [{ nhan: 'Xoá và đảo bút toán', icon: 'bi-trash', danger: true, onClick: () => moXoa(r) }] : null,
  });

  /* ── Hộp thoại lập phân phối — gọi các API thật tuần tự (xem ghi chú #2 ở đầu tệp). ── */
  let du = null;
  const KHOAN = [['quy_dtpt', '414', 'Quỹ đầu tư phát triển'], ['quy_ktpl', '353', 'Quỹ khen thưởng, phúc lợi'], ['quy_khac', null, 'Quỹ khác'], ['chia_csh', null, 'Chia cổ tức (chi tiền)'], ['chuyen_von', '411', 'Vốn góp của chủ sở hữu']];
  const dlg = document.getElementById('pp-dlg'), $ = (id) => document.getElementById(id);
  if (!GHI_DUOC) { $('pp-lap').hidden = true; $('pp-chi-xem').hidden = false; }
  const docSo = (el) => { const n = Number(String(el.value).replace(/[^\d]/g, '')); return Number.isFinite(n) ? n : 0; };
  const giaTri = () => { const v = {}; KHOAN.forEach(([k]) => { v[k] = docSo($('pp-' + k)); }); return v; };
  const quyKhac = () => phu.quyTheoId[$('pp-quy-khac-id').value] || null;
  const tkChi = () => phu.tk.find((t) => String(t.id) === $('pp-tk').value) || null;
  function veDk() {
    const v = giaTri(), tong = KHOAN.reduce((s, [k]) => s + v[k], 0);
    KHOAN.forEach(([k]) => { $('pp-g-' + k).textContent = v[k] && du.chua_phan_phoi ? KD.phanTram(v[k] / du.chua_phan_phoi * 100) + ' lợi nhuận chưa phân phối' : ''; });
    const vuot = tong > (du.chua_phan_phoi || 0);
    const qk = quyKhac(), tk = tkChi();
    const tkCua = (k, tkMacDinh) => (k === 'quy_khac' ? (qk ? layTkQuy(qk.ten_quy) : '—') : k === 'chia_csh' ? (tk ? tk.tk_ke_toan || (tk.loai === 'tien_mat' ? '111' : '112') : '111/112') : tkMacDinh);
    const tenCua = (k, ten) => (k === 'quy_khac' && qk ? qk.ten_quy : k === 'chia_csh' && tk ? 'Chi cổ tức từ ' + tk.ten_tk : ten);
    $('pp-dk').innerHTML = tong ? '<tr><td><span class="kt-tk">421</span><span class="kt-dk__phu">Lợi nhuận sau thuế chưa phân phối</span></td><td class="num">' + KD.tien(tong) + '</td><td class="num">' + KT.tienSo(0) + '</td></tr>'
      + KHOAN.filter(([k]) => v[k]).map(([k, tkMd, ten]) => '<tr><td><span class="kt-tk">' + esc(tkCua(k, tkMd)) + '</span><span class="kt-dk__phu">' + esc(tenCua(k, ten)) + '</span></td><td class="num">' + KT.tienSo(0) + '</td><td class="num">' + KD.tien(v[k]) + '</td></tr>').join('')
      : '<tr><td colspan="3" class="kd-muted">Nhập số tiền để xem định khoản.</td></tr>';
    $('pp-co-the').innerHTML = 'Có thể phân phối: <strong class="num">' + (du.chua_phan_phoi != null ? KD.tienVnd(du.chua_phan_phoi) : '—') + '</strong>' + (tong ? ' · Đang lập: <strong class="num">' + KD.tienVnd(tong) + '</strong>' + (vuot ? ' ' + H.pill('danger', 'Vượt số có thể phân phối') : ' · Còn lại ' + KD.tienVnd((du.chua_phan_phoi || 0) - tong)) : '');
    return { v, tong, vuot };
  }
  KHOAN.forEach(([k]) => $('pp-' + k).addEventListener('input', (e) => { const n = docSo(e.target); e.target.value = n ? KD.tien(n) : ''; veDk(); }));
  ['pp-quy-khac-id', 'pp-tk'].forEach((id) => $(id).addEventListener('change', veDk));
  $('pp-lap').addEventListener('click', () => {
    if (!du) return; KHOAN.forEach(([k]) => { $('pp-' + k).value = ''; }); $('pp-ghi-chu').value = ''; $('pp-chu').value = ''; $('pp-ngay').value = homNay();
    $('pp-quy-khac-id').innerHTML = '<option value="">— Không trích —</option>' + phu.quy.map((q) => '<option value="' + q.id + '">' + esc(q.ten + ' — TK ' + q.tk) + '</option>').join('');
    $('pp-tk').innerHTML = '<option value="">— Chọn tài khoản —</option>' + phu.tk.map((t) => '<option value="' + t.id + '">' + esc(t.ten_tk + (t.ten_nh ? ' — ' + t.ten_nh : '')) + '</option>').join('');
    veDk(); KD.moHopThoai(dlg);
  });
  $('pp-form').addEventListener('submit', async (e) => {
    e.preventDefault(); const x = veDk();
    if (!x.tong) return KD.baoLoiHopThoai(dlg, 'Nhập ít nhất một khoản phân phối lớn hơn 0.');
    if (x.vuot) return KD.baoLoiHopThoai(dlg, 'Tổng phân phối vượt lợi nhuận chưa phân phối — giảm bớt số tiền.');
    const ghiChuNhap = $('pp-ghi-chu').value.trim();
    if (!ghiChuNhap) { $('pp-ghi-chu').focus(); return KD.baoLoiHopThoai(dlg, 'Ghi căn cứ phân phối (số nghị quyết / quyết định).'); }
    const ngay = $('pp-ngay').value; if (!ngay) return KD.baoLoiHopThoai(dlg, 'Chọn ngày ghi sổ.');
    /* BUG THẬT (sửa 2026-09-25): nhiều quỹ "khác" (Du Lịch, Quỹ Công Ty…) cũng map về TK 414 (và "Quỹ Phúc Lợi"
       cũng map về 353) — dùng .find() theo tk suông sẽ ghi tiền NHẦM QUỸ. Ưu tiên đúng tên quỹ chính theo
       từ khoá, chỉ fallback về quỹ đầu tiên cùng TK khi không tìm thấy tên chính xác. */
    const timQuyChinh = (tk, tuKhoa) => { const ung = phu.quy.filter((q) => q.tk === tk); return ung.find((q) => (q.ten || '').toLowerCase().includes(tuKhoa)) || ung[0]; };
    const nhomDTPT = timQuyChinh('414', 'đầu tư'), nhomKTPL = timQuyChinh('353', 'khen thưởng'), qk = quyKhac(), tk = tkChi();
    if (x.v.quy_dtpt > 0 && !nhomDTPT) return KD.baoLoiHopThoai(dlg, 'Chưa có quỹ đầu tư phát triển trong Quản lý quỹ (TK 414) — tạo quỹ đó trước.');
    if (x.v.quy_ktpl > 0 && !nhomKTPL) return KD.baoLoiHopThoai(dlg, 'Chưa có quỹ khen thưởng, phúc lợi trong Quản lý quỹ (TK 353) — tạo quỹ đó trước.');
    if (x.v.quy_khac > 0 && !qk) { $('pp-quy-khac-id').focus(); return KD.baoLoiHopThoai(dlg, 'Chọn quỹ cần trích cho khoản "Quỹ khác".'); }
    if (x.v.chia_csh > 0 && !tk) { $('pp-tk').focus(); return KD.baoLoiHopThoai(dlg, 'Chọn tài khoản chi tiền cổ tức — không có tài khoản thì máy chủ không ghi bút toán.'); }
    const chu = $('pp-chu').value.trim() || null;

    const tag = '[PPLN ' + ngay + '] ' + ghiChuNhap;
    const nut = $('pp-luu'); nut.disabled = true;
    const daGhi = [];
    try {
      if (x.v.quy_dtpt > 0) { await KD.api('/api/von-csh/trich-quy', KD.JSON_POST({ ngay, so_tien: x.v.quy_dtpt, ghi_chu: tag, quy_id: nhomDTPT.id })); daGhi.push('quỹ ĐTPT'); }
      if (x.v.quy_ktpl > 0) { await KD.api('/api/von-csh/trich-quy', KD.JSON_POST({ ngay, so_tien: x.v.quy_ktpl, ghi_chu: tag, quy_id: nhomKTPL.id })); daGhi.push('quỹ KT-PL'); }
      if (x.v.quy_khac > 0) { await KD.api('/api/von-csh/trich-quy', KD.JSON_POST({ ngay, so_tien: x.v.quy_khac, ghi_chu: tag, quy_id: qk.id })); daGhi.push(qk.ten_quy); }
      if (x.v.chia_csh > 0) { await KD.api('/api/von-csh/chia-co-tuc', KD.JSON_POST({ ngay, so_tien: x.v.chia_csh, ghi_chu: tag, chu_so_huu: chu, tai_khoan_id: tk.id })); daGhi.push('chia cổ tức'); }
      if (x.v.chuyen_von > 0) { await KD.api('/api/von-csh/chuyen-ln-thanh-von', KD.JSON_POST({ ngay, so_tien: x.v.chuyen_von, ghi_chu: tag, chu_so_huu: chu })); daGhi.push('chuyển vốn góp'); }
      dlg.close();
      window.showToast && window.showToast('ok', 'Đã ghi sổ phân phối (' + daGhi.join(', ') + ') — tổng ' + KD.tienVnd(x.tong));
      phu = Object.assign({}, phu, { chua_phan_phoi: null }); phuLoi = false; // buộc nạp lại số dư thật sau khi ghi
      taiPhu();
    } catch (err) {
      KD.baoLoiHopThoai(dlg, (daGhi.length ? 'Đã ghi được ' + daGhi.join(', ') + ', nhưng dừng lại: ' : 'Chưa ghi sổ được: ') + err.message);
      if (daGhi.length) { phu = Object.assign({}, phu, { chua_phan_phoi: null }); phuLoi = false; taiPhu(); }
    } finally { nut.disabled = false; }
  });

  /* ── Xoá một lần phân phối — DELETE /api/von-csh/{id} cho từng dòng gộp (đảo bút toán + hoàn quỹ) ── */
  const dXoa = $('pp-dlg-xoa'); let xoaDang = null;
  function moXoa(r) {
    xoaDang = r;
    $('pp-xoa-td').textContent = 'Xoá lần phân phối ' + r.so_ct + ' (' + KD.ngay(r.ngay) + ')?';
    $('pp-xoa-nd').textContent = 'Xoá ' + KD.soDem(r.ids.length) + ' giao dịch, tổng ' + KD.tienVnd(r.tong) + ': máy chủ đảo bút toán và hoàn lại số dư quỹ đã trích. Chỉ admin/CEO được xoá.';
    KD.moHopThoai(dXoa);
  }
  $('pp-xoa-ok').addEventListener('click', async () => {
    if (!xoaDang) return; const nut = $('pp-xoa-ok'); nut.disabled = true; let daXoa = 0;
    try {
      for (const id of xoaDang.ids) { await KD.api('/api/von-csh/' + id, { method: 'DELETE', headers: { Accept: 'application/json' } }); daXoa++; }
      dXoa.close(); window.showToast && window.showToast('ok', 'Đã xoá ' + daXoa + ' giao dịch phân phối');
    } catch (e) { KD.baoLoiHopThoai(dXoa, (daXoa ? 'Đã xoá ' + daXoa + ' giao dịch, dừng lại: ' : 'Chưa xoá được: ') + e.message); }
    finally { nut.disabled = false; if (daXoa) { phu = Object.assign({}, phu, { chua_phan_phoi: null }); phuLoi = false; taiPhu(); } }
  });
  // Nạp dữ liệu phụ TRƯỚC rồi taiPhu() tự gọi ds.tai() một lần (bản trước: ds.tai() → sauTai → taiPhu() → ds.tai() lần 2
  // = /api/von-csh bị gọi 2 lần mỗi lần mở màn; và nếu API không trả ln_giu_lai thì sauTai gọi taiPhu lặp vô hạn).
  $('pp-tbody').innerHTML = KT.hangCho(9, 3);
  taiPhu();
})();
