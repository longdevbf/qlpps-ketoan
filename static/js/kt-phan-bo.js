/* kt-phan-bo.js — Chi phí chờ phân bổ TK 242 (khung: kt-danh-sach.js). API thật: app/routers/phan_bo.py.
   Khoản = dòng Chi phí cố định phân bổ nhiều tháng — báo cáo KQKD tự phân bổ vào chi phí hằng tháng (chia đều, kỳ cuối lấy phần lẻ).
   Thêm khoản: Nợ 242 / Có nguồn (111, 112 hoặc TK con 111x/112x của tài khoản tiền, 331). "Phân bổ tháng": ghi Nợ 641/642 / Có 242 phần đã tới hạn của các khoản đã có bút toán 242. */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-phan-bo')) return;
  const H = KT.H, $ = (id) => document.getElementById(id);
  const LOAI = { tra_truoc: 'Chi phí trả trước', ccdc: 'Công cụ dụng cụ' };
  const TT = { dang: ['success', 'Đang phân bổ'], xong: ['muted', 'Đã phân bổ hết'] };
  const TK_CP = ['641', '642'], TK_NGUON = ['111', '112', '331'];   // cùng danh sách máy chủ kiểm (services/phan_bo_242.py)
  // TK nguồn: 3 TK trên + TK con của 111/112 (TK kế toán của từng tài khoản tiền, có trong /api/journal/accounts).
  const laTkNguon = (ma) => TK_NGUON.includes(ma) || (ma.length > 3 && ['111', '112'].includes(ma.slice(0, 3)));
  const pillTT = (k) => { const x = TT[k]; if (!x) console.warn('[Phân bổ] trạng thái chưa có nhãn:', k); return H.pill(x ? x[0] : 'muted', x ? x[1] : 'Chưa đặt tên'); };
  const thangChu = (m) => m.slice(5, 7) + '/' + m.slice(0, 4);
  const dongDk = (tk, phu, no, co) => '<tr><td><span class="kt-tk">' + esc(tk || '…') + '</span>' + (phu ? '<span class="kt-dk__phu">' + esc(phu) + '</span>' : '') + '</td><td class="num">' + (no ? KD.tien(no) : KT.tienSo(0)) + '</td><td class="num">' + (co ? KD.tien(co) : KT.tienSo(0)) + '</td></tr>';
  /* Dòng phụ dưới tên khoản: loại · bộ phận · TK chi phí · ngày ghi nhận (thay 2 cột riêng) */
  const phuDong = (r) => [LOAI[r.loai] || 'Chưa đặt tên', r.bo_phan, 'TK ' + r.tk_cp, 'từ ' + KD.ngay(r.ngay)].filter(Boolean).join(' · ');
  const tipTrang = document.querySelector('#kd-kt-phan-bo .kd-sub').appendChild(document.createElement('span'));
  let thang = null;

  const ds = KT.danhSach({
    pfx: 'pb', api: (q) => '/api/phan-bo?' + KT.url.qs(q), donVi: 'khoản', khongTrang: true,
    macDinh: { tim: '', loai: '', trang_thai: '', page: 1, size: 50, sort: '' },
    cot: [
      { key: 'ma', nhan: 'Mã', ve: (r) => H.ma(r.ma) },
      { key: 'ten', nhan: 'Khoản chi phí', ve: (r) => '<span class="kt-khach__ten">' + esc(r.ten) + (r.nguon_nhap === 'chi_phi_co_dinh' ? KD.tip('Nhập từ Chi phí cố định') : '') + '</span><span class="kt-khach__ma" title="' + esc(r.ten_tk_cp) + '">' + esc(phuDong(r)) + '</span>' },
      { key: 'tong', nhan: 'Tổng tiền (VND)', num: true, ve: (r) => KD.tien(r.tong) },
      { key: 'ky', nhan: 'Tiến độ', title: 'Số tháng đã vào chi phí (tính cả tháng này) / tổng số tháng', ve: (r) => KD.soDem(r.da_ky) + '/' + KD.soDem(r.so_ky) + ' tháng' },
      { key: 'muc', nhan: 'Tháng này (VND)', num: true, ve: (r) => H.tien(r.muc_thang) },
      { key: 'con', nhan: 'Còn lại (VND)', num: true, cls: 'kd-strong', ve: (r) => H.tien(r.con_lai) },
      { key: 'tt', nhan: 'Trạng thái', ve: (r) => pillTT(r.trang_thai) },
      { key: 'act', nhan: 'Thao tác', act: true, nhanDong: (r) => r.ma },
    ],
    kpi: {
      con_lai: (d) => ({ v: H.tienKpi(d.tong.con_lai), title: KD.tienVnd(d.tong.con_lai), phu: 'Sau tháng ' + thangChu(d.thang) }),
      muc_thang: (d) => ({ v: H.tienKpi(d.tong.muc_thang), title: KD.tienVnd(d.tong.muc_thang), phu: 'Vào chi phí tháng ' + thangChu(d.thang) }),
      so_khoan: (d) => ({ v: H.dem(d.tong.so_khoan, 'khoản'), phu: 'Tổng giá trị ' + KD.tienGon(d.tong.tong) }),
      thang: (d) => ({ v: '<span>' + thangChu(d.thang) + '</span>', phu: d.so_sach.cho_ghi_so ? H.pill('warning', 'Chờ ghi sổ ' + KD.tienGon(d.so_sach.cho_ghi_so))
        : d.ct_thang ? H.pill('success', 'Đã ghi sổ · ' + d.ct_thang.so_ct) : 'Không có phần chờ ghi sổ' }),
    },
    cong: () => { const r = ds.dsHien(); return [{ html: 'Cộng ' + KD.soDem(r.length) + ' khoản', span: 2 }, { html: KD.tien(r.reduce((s, x) => s + x.tong, 0)), num: true }, { html: '' }, { html: KD.tien(r.reduce((s, x) => s + x.muc_thang, 0)), num: true }, { html: KD.tien(r.reduce((s, x) => s + x.con_lai, 0)), num: true }, { html: '' }, { html: '' }]; },
    rong: (d, coLoc) => (coLoc ? ['Không có khoản nào khớp bộ lọc', 'Thử bỏ bớt điều kiện lọc.'] : ['Chưa có khoản chi phí chờ phân bổ nào', 'Bấm "Thêm khoản phân bổ" khi trả trước tiền thuê, bảo hiểm, phần mềm hoặc xuất dùng công cụ dụng cụ.']),
    loi: 'Không tải được danh sách chi phí chờ phân bổ',
    sauTai: (d) => { thang = d; const cho = d.so_sach.cho_ghi_so; veGiaiThich(d); $('pb-chay-chu').textContent = (cho ? 'Phân bổ tháng ' : d.ct_thang ? 'Đã phân bổ tháng ' : 'Phân bổ tháng ') + thangChu(d.thang);
      $('pb-chay').disabled = !cho; $('pb-chay').title = cho ? '' : 'Không có khoản nào có bút toán 242 chờ ghi sổ tháng này'; },
    khiLoi: () => { $('pb-chay').disabled = true; tipTrang.innerHTML = ''; $('pb-pham-vi').hidden = true; },
    panel: {
      tai: (r) => '/api/phan-bo/' + encodeURIComponent(r.id),
      ve: (p) => {
        const toi = p.lich.findIndex((x) => !x.da), tu = Math.max(0, (toi < 0 ? p.lich.length : toi) - 2), lich = p.lich.slice(tu, tu + 8);
        return H.dauPanel(p.loai === 'ccdc' ? 'bi-tools' : 'bi-hourglass-split', p.trang_thai === 'dang' ? 'success' : 'info', p.ma, esc(p.ten), pillTT(p.trang_thai))
          + H.kv([['Loại', esc(LOAI[p.loai] || '—')], ['Bộ phận', esc(p.bo_phan || '—')], ['Ngày ghi nhận', KD.ngay(p.ngay)], ['Nguồn', p.doi ? '<span class="kt-tk">' + esc(p.doi) + '</span>' : '<span class="kd-muted">Từ Chi phí cố định</span>'], ['Vào chi phí', '<span class="kt-tk">' + esc(p.tk_cp) + '</span> ' + esc(p.ten_tk_cp)]])
          + H.khoi('bi-cash-stack', 'Số tiền', H.kv([['Tổng tiền', KD.tienVnd(p.tong)], ['Đã vào chi phí', KD.tienVnd(p.da_pb) + ' · ' + KD.soDem(p.da_ky) + '/' + KD.soDem(p.so_ky) + ' tháng'], ['Còn lại', KD.tienVnd(p.con_lai), true],
            ['Sổ cái TK 242', p.tren_so_cai ? 'Đã ghi Có 242 ' + KD.tienVnd(p.da_ghi_so) + (p.cho_ghi_so ? ' · chờ ghi ' + KD.tienVnd(p.cho_ghi_so) : '') : '<span class="kd-muted">Chưa có bút toán Nợ 242</span>']]))
          + H.khoi('bi-calendar3', 'Lịch phân bổ', '<table class="kt-bang-nho"><thead><tr><th scope="col">Tháng</th><th scope="col" class="num">Phân bổ</th><th scope="col">Tình trạng</th></tr></thead><tbody>'
            + lich.map((x, i) => '<tr class="' + (x.da ? '' : 'is-cho') + (tu + i === toi ? ' is-nay' : '') + '"><td>' + thangChu(x.thang) + '</td><td class="num">' + KD.tien(x.so_tien) + '</td><td>' + (x.da ? 'Đã vào chi phí' : tu + i === toi ? 'Kỳ tới' : 'Chờ') + '</td></tr>').join('') + '</tbody></table>'
            + (p.lich.length > lich.length ? '<p class="kd-meta">Hiển thị ' + KD.soDem(lich.length) + '/' + KD.soDem(p.lich.length) + ' kỳ quanh kỳ tới.</p>' : ''));
      },
      nut: () => '<a class="kd-btn kd-btn--grow" href="/ketoan/so-cai?tk=242&ky=nam_nay"><i class="bi bi-journal-text" aria-hidden="true"></i>Sổ cái TK 242</a>',
    },
    menu: (r) => [
      { nhan: 'Xem sổ cái TK 242', icon: 'bi-journal-text', href: '/ketoan/so-cai?tk=242&ky=nam_nay' },
      { nhan: 'Xem sổ cái TK ' + r.tk_cp, icon: 'bi-journal-text', href: '/ketoan/so-cai?tk=' + encodeURIComponent(r.tk_cp) + '&ky=nam_nay' },
    ],
  });

  /* Cách tính → ⓘ cạnh dòng phụ tiêu đề; sổ cái TK 242 lệch là việc cần kiểm → nhãn đỏ dưới hàng thẻ số. */
  function veGiaiThich(d) {
    const s = d.so_sach, lech = s.tk242 - s.con_lai_tren_so;
    tipTrang.innerHTML = KD.tip('Báo cáo KQKD tự đưa phần của từng tháng vào chi phí; "Còn lại" là phần chưa vào chi phí sau tháng ' + thangChu(d.thang) + '.'
      + ' Sổ cái TK 242 đang dư ' + KD.tienVnd(s.tk242) + (lech ? '.' : ', khớp các khoản đã ghi Nợ 242.')
      + (s.so_khoan_ngoai_so ? ' ' + KD.soDem(s.so_khoan_ngoai_so) + ' khoản nhập từ Chi phí cố định chưa có bút toán Nợ 242 (chỉ phân bổ trong báo cáo, không ghi sổ cái).' : '')
      + ' Phần còn phân bổ trên 12 tháng là tài sản dài hạn.');
    $('pb-pham-vi').hidden = !lech;
    $('pb-pham-vi').innerHTML = lech ? H.pill('danger', 'Sổ cái TK 242 lệch ' + KD.tienVnd(lech) + ' so với các khoản đã ghi Nợ 242') : '';
  }

  /* ── Phân bổ tháng (ghi sổ → hỏi lại) ── */
  const dlg = $('pb-dlg');
  $('pb-chay').addEventListener('click', async () => {
    if (!thang || !thang.so_sach.cho_ghi_so) return;
    let all; try { all = (await KD.api('/api/phan-bo')).dong.filter((p) => p.cho_ghi_so > 0); } catch (e) { window.showToast && window.showToast('err', 'Không tải được danh sách khoản: ' + e.message); return; }
    const theoTk = {}; all.forEach((p) => { theoTk[p.tk_cp] = theoTk[p.tk_cp] || { ten: p.ten_tk_cp, v: 0 }; theoTk[p.tk_cp].v += p.cho_ghi_so; });
    const tong = all.reduce((s, p) => s + p.cho_ghi_so, 0);
    $('pb-dlg-td').textContent = 'Phân bổ chi phí tháng ' + thangChu(thang.thang) + '?';
    $('pb-dlg-nd').textContent = 'Ghi sổ ' + KD.tienVnd(tong) + ' từ TK 242 vào chi phí cho ' + KD.soDem(all.length) + ' khoản (phần đã tới hạn mà chưa lên sổ cái). Chi phí không bị tính thêm lần nữa.';
    $('pb-dlg-dk').innerHTML = Object.keys(theoTk).sort().map((tk) => dongDk(tk, theoTk[tk].ten, theoTk[tk].v, 0)).join('') + dongDk('242', 'Chi phí chờ phân bổ', 0, tong);
    KD.moHopThoai(dlg); $('pb-dlg-ok').focus();
  });
  $('pb-dlg-ok').addEventListener('click', async () => {
    const nut = $('pb-dlg-ok'); nut.disabled = true;
    try { const r = await KD.api('/api/phan-bo/thang', KD.JSON_POST({ thang: thang.thang })); dlg.close(); ds.dongPanel();
      window.showToast && window.showToast('ok', 'Đã ghi sổ phân bổ ' + r.so_ct + ' — ' + KD.tienVnd(r.so_tien)); ds.tai(); }
    catch (e) { KD.baoLoiHopThoai(dlg, 'Chưa ghi sổ được: ' + e.message); } finally { nut.disabled = false; }
  });

  /* ── Thêm khoản ── */
  const dlgT = $('pb-dlg-them');
  const oCp = KT.oTk($('pb-tk-cp'), { loc: (t) => TK_CP.includes(t.ma), khiChon: () => veThem() });
  const oDoi = KT.oTk($('pb-doi'), { loc: (t) => laTkNguon(t.ma), khiChon: () => veThem() });
  let loai = 'tra_truoc', choTk = Promise.resolve();
  const docSo = (el) => Number(String(el.value || '').replace(/[^\d]/g, '')) || 0;
  function veThem() {
    const tong = docSo($('pb-tong')), ky = Math.round(+$('pb-so-ky').value || 0), ng = $('pb-ngay').value;
    const moi = ky >= 2 ? Math.round(tong / ky) : 0, cuoi = tong - moi * (ky - 1);
    $('pb-goi-y').textContent = tong && ky >= 2 ? 'Mỗi tháng phân bổ ' + KD.tienVnd(moi) + (cuoi !== moi ? ' (tháng cuối ' + KD.tienVnd(cuoi) + ')' : '') + (ng ? ', từ tháng ' + thangChu(ng.slice(0, 7)) : '') + ' — báo cáo KQKD tự tính vào chi phí từng tháng.' + (ky > 12 ? ' Trên 12 tháng: phần phân bổ sau 12 tháng tới trình bày dài hạn.' : '')
      : 'Nhập tổng tiền và số tháng (2–36) để xem mức phân bổ hằng tháng.';
    $('pb-them-dk').innerHTML = dongDk('242', 'Chi phí chờ phân bổ', tong, 0) + dongDk(oDoi.lay(), loai === 'ccdc' ? 'Mua công cụ dụng cụ đưa vào dùng' : 'Thanh toán / ghi nợ', 0, tong);
  }
  function datLoai(k) { loai = k; $('pb-f-loai').querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.loai === k))); veThem(); }
  $('pb-f-loai').addEventListener('click', (e) => { const b = e.target.closest('[data-loai]'); if (b) datLoai(b.dataset.loai); });
  $('pb-tong').addEventListener('input', (e) => { const n = docSo(e.target); e.target.value = n ? KD.tien(n) : ''; veThem(); });
  ['pb-so-ky', 'pb-ngay'].forEach((id) => $(id).addEventListener('input', veThem));
  $('pb-them').addEventListener('click', () => {
    $('pb-form').reset(); $('pb-so-ky').value = '12'; $('pb-ngay').value = KD.iso(new Date()); choTk = Promise.all([oCp.dat('642'), oDoi.dat('112')]); datLoai('tra_truoc');
    KD.moHopThoai(dlgT); $('pb-ten').focus();
  });
  $('pb-form').addEventListener('submit', async (e) => {
    e.preventDefault(); await choTk; await Promise.all([oCp.xacNhan(), oDoi.xacNhan()]);
    const d = { ten: $('pb-ten').value.trim(), loai, tong: docSo($('pb-tong')), so_ky: Math.round(+$('pb-so-ky').value || 0), tk_cp: oCp.lay(), doi: oDoi.lay(), ngay: $('pb-ngay').value || null, bo_phan: $('pb-bp').value.trim() || null };
    if (!d.ten) { $('pb-ten').focus(); return KD.baoLoiHopThoai(dlgT, 'Nhập tên khoản chi phí.'); }
    if (!d.tong) { $('pb-tong').focus(); return KD.baoLoiHopThoai(dlgT, 'Nhập tổng số tiền.'); }
    if (!(d.so_ky >= 2 && d.so_ky <= 36)) { $('pb-so-ky').focus(); return KD.baoLoiHopThoai(dlgT, 'Số tháng phân bổ từ 2 đến 36.'); }
    if (!TK_CP.includes(d.tk_cp) || !laTkNguon(d.doi)) return KD.baoLoiHopThoai(dlgT, 'Chọn TK chi phí (641/642) và TK nguồn (111, 112 hoặc TK con, 331).');
    const nut = $('pb-them-ok'); nut.disabled = true;
    try { const r = await KD.api('/api/phan-bo', KD.JSON_POST(d)); dlgT.close(); window.showToast && window.showToast('ok', 'Đã thêm ' + r.ma + ' (' + r.so_ct + ') — mỗi tháng ' + KD.tienVnd(r.muc_thang)); ds.tai(); }
    catch (err) { KD.baoLoiHopThoai(dlgT, 'Chưa thêm được: ' + err.message); } finally { nut.disabled = false; }
  });
  ds.tai();
})();
