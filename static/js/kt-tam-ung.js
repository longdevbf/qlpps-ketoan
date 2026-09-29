/* kt-tam-ung.js — Tạm ứng nhân viên (TK 141) (khung: kt-danh-sach.js). API thật: app/routers/tam_ung.py
   Lập: Nợ 141 / Có TK tiền của tài khoản chi (TK con 111x/112x; chưa gán thì 111|112) + phiếu chi sổ quỹ.
   Quyết toán: Nợ TK chi phí (chi thực tế) / Có 141; thừa → Nợ 111|112 (nộp lại, cùng tài khoản đã chi) hoặc Nợ 334 (trừ lương);
   thiếu → Có 111|112 (chi bù). Sửa/xoá khoản chưa quyết toán + huỷ lần quyết toán gần nhất: chỉ CEO (quyen_sua). */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-tam-ung')) return;
  const H = KT.H, $ = (id) => document.getElementById(id);
  const TK_CP = ['641', '642', '635', '811'], TK_CP_MAC_DINH = '642', HAN_MAC_DINH_NGAY = 30;
  const TT = { chua_quyet_toan: ['info', 'Chưa quyết toán'], mot_phan: ['warning', 'Quyết toán một phần'], qua_han: ['danger', 'Quá hạn hoàn ứng'], da_quyet_toan: ['success', 'Đã quyết toán'] };
  const pillTT = (r) => { const x = TT[r.trang_thai]; if (!x) console.warn('[Tạm ứng] trạng thái chưa có nhãn:', r.trang_thai); return H.pill(x ? x[0] : 'muted', x ? x[1] : 'Chưa đặt tên', r.trang_thai === 'qua_han'); };
  const ctLink = (id, so) => (id ? '<a class="kt-ma" href="/ketoan/chung-tu?id=' + id + '">' + esc(so) + '</a>' : esc(so));
  const han = (r) => (r.trang_thai === 'da_quyet_toan' ? 'Đã xong' : r.qua_han_ngay ? 'Quá ' + KD.soDem(r.qua_han_ngay) + ' ngày' : 'Còn ' + KD.soDem(Math.max(0, Math.round((new Date(r.han_hoan) - new Date(KD.iso(new Date()))) / 864e5))) + ' ngày');
  const docTien = (el) => Number(String(el.value || '').replace(/[^\d]/g, '')) || 0;
  const congNgay = (iso, n) => { const d = new Date(iso + 'T00:00:00'); d.setDate(d.getDate() + n); return KD.iso(d); };
  const quyenSua = () => !!(ds.duLieu() && ds.duLieu().quyen_sua);
  const tkTienNhan = (r) => r.tai_khoan.tk + ' · ' + (r.tai_khoan.ten || '');
  // TK định khoản của tài khoản tiền: TK con đã gán (1111, 1121…), chưa gán thì 111/112 theo loại.
  const tkDinhKhoan = (t) => t.tk_ke_toan || (t.loai === 'tien_mat' ? '111' : '112');

  const ds = KT.danhSach({
    // "Tất cả" = 'tat_ca' trên ô chọn/URL (giữ được khi F5), API hiểu "tất cả" là trang_thai rỗng.
    pfx: 'tu', api: (q) => '/api/tam-ung?' + KT.url.qs(Object.assign({}, q, { trang_thai: q.trang_thai === 'tat_ca' ? '' : q.trang_thai })), donVi: 'khoản', khongTrang: true,
    macDinh: { tim: '', trang_thai: 'con_no', page: 1, size: 50, sort: '' },
    dong: { id: (r) => r.id },
    cot: [
      { key: 'nv', nhan: 'Nhân viên', ve: (r) => H.ten(r.nhan_vien.ten, r.nhan_vien.ma) },
      { key: 'nd', nhan: 'Nội dung tạm ứng', ve: (r) => H.cat(r.noi_dung, true) },
      { key: 'ngay', nhan: 'Ngày ứng', ve: (r) => KD.ngay(r.ngay) + '<span class="kt-khach__ma">' + esc(r.so_ct) + '</span>' },
      { key: 'da_ung', nhan: 'Đã ứng (VND)', num: true, ve: (r) => KD.tien(r.da_ung) },
      { key: 'qt', nhan: 'Đã quyết toán', num: true, ve: (r) => H.tien(r.da_quyet_toan) },
      { key: 'con', nhan: 'Còn lại (VND)', title: 'Số còn phải quyết toán', num: true, cls: 'kd-strong', ve: (r) => H.tien(r.con_lai) },
      { key: 'han', nhan: 'Hạn hoàn ứng', ve: (r) => KD.ngay(r.han_hoan) + '<span class="kt-khach__ma">' + han(r) + '</span>' },
      { key: 'tt', nhan: 'Trạng thái', ve: pillTT },
      { key: 'act', nhan: 'Thao tác', act: true, nhanDong: (r) => r.nhan_vien.ten + ' ' + r.so_ct },
    ],
    kpi: {
      con_lai: (d) => ({ v: H.tienKpi(d.tong.con_lai), title: KD.tienVnd(d.tong.con_lai), phu: 'Sổ cái TK 141: ' + KD.tienGon(d.so_sach.tk141) }),
      qua_han: (d) => ({ v: H.tienKpi(d.tong.qua_han), title: KD.tienVnd(d.tong.qua_han), phu: d.tong.so_qua_han ? H.pill('danger', KD.soDem(d.tong.so_qua_han) + ' khoản cần đôn đốc') : H.pill('success', 'Không có khoản quá hạn') }),
      so_nv: (d) => ({ v: H.dem(d.tong.so_nv, 'người'), phu: 'Chưa quyết toán xong' }),
      thang: (d) => ({ v: H.tienKpi(d.tong.da_ung_thang), title: KD.tienVnd(d.tong.da_ung_thang), phu: '' }),
    },
    phamVi: (d) => (d.so_sach.tk141 === d.tong.con_lai ? 'Khớp số dư TK 141 trên sổ cái.' : 'Lệch số dư TK 141: ' + KD.tienVnd(d.tong.con_lai - d.so_sach.tk141) + ' — kiểm tra sổ chi tiết.'),
    cong: () => { const r = ds.dsHien(); return [{ html: 'Cộng ' + KD.soDem(r.length) + ' khoản', span: 3 }, { html: KD.tien(r.reduce((s, x) => s + x.da_ung, 0)), num: true }, { html: KD.tien(r.reduce((s, x) => s + x.da_quyet_toan, 0)), num: true }, { html: KD.tien(r.reduce((s, x) => s + x.con_lai, 0)), num: true }, { html: '', span: 2 }, { html: '' }]; },
    rong: (d, coLoc) => (coLoc ? ['Không có khoản tạm ứng nào khớp bộ lọc', 'Chọn trạng thái "Tất cả" để xem cả khoản đã quyết toán.'] : ['Chưa có khoản tạm ứng nào', 'Bấm "Lập tạm ứng" để chi tạm ứng.']),
    loi: 'Không tải được danh sách tạm ứng',
    panel: {
      tai: (r) => '/api/tam-ung/' + encodeURIComponent(r.id),
      ve: (t) => H.dauPanel('bi-wallet2', t.trang_thai === 'qua_han' ? 'danger' : t.trang_thai === 'da_quyet_toan' ? 'success' : 'info', t.nhan_vien.ten, esc(t.noi_dung), pillTT(t))
        + H.kv([['Nhân viên', esc(t.nhan_vien.ma + ' · ' + t.nhan_vien.ten)], ['Phiếu chi tạm ứng', ctLink(t.ung_id, t.so_ct)], ['Chi từ', esc(tkTienNhan(t))], ['Ngày ứng', KD.ngay(t.ngay)], ['Hạn hoàn ứng', KD.ngay(t.han_hoan) + ' · ' + han(t)]])
        + H.khoi('bi-cash-stack', 'Số tiền', H.kv([['Đã ứng', KD.tienVnd(t.da_ung)], ['Đã quyết toán', KD.tienVnd(t.da_quyet_toan)], ['Còn phải quyết toán', KD.tienVnd(t.con_lai), true]]))
        + H.khoi('bi-receipt', 'Các lần quyết toán', t.quyet_toan.length ? '<table class="kt-bang-nho"><thead><tr><th scope="col">Chứng từ</th><th scope="col" class="num">Chi phí</th><th scope="col" class="num">Hoàn / chi bù</th></tr></thead><tbody>'
          + t.quyet_toan.map((x) => '<tr><td>' + ctLink(x.id, x.so_ct) + '<span class="kt-khach__ma">' + KD.ngay(x.ngay) + (x.tk_cp ? ' · TK ' + esc(x.tk_cp) : '') + '</span></td><td class="num">' + KT.tienSo(x.chi_phi) + '</td><td class="num">' + (x.hoan ? (x.xu_ly_thua === 'tru_luong' ? 'Trừ lương ' : 'Hoàn ') + KD.tien(x.hoan) : x.chi_bu ? 'Chi bù ' + KD.tien(x.chi_bu) : KT.tienSo(0)) + '</td></tr>').join('') + '</tbody></table>'
          : KD.khoiRong('Chưa quyết toán lần nào', '')),
      nut: (t) => (t.con_lai ? '<button type="button" class="kd-btn kd-btn--grow" data-qt="' + t.id + '"><i class="bi bi-check2-circle" aria-hidden="true"></i>Quyết toán</button>' : '')
        + (quyenSua() && t.quyet_toan.length ? '<button type="button" class="kd-btn kd-btn--grow" data-huy-qt="' + t.quyet_toan[t.quyet_toan.length - 1].qt_id + '" data-tu="' + t.id + '"><i class="bi bi-arrow-counterclockwise" aria-hidden="true"></i>Huỷ lần quyết toán gần nhất</button>' : '')
        + '<a class="kd-btn kd-btn--grow" href="/ketoan/so-cai?tk=141&ky=nam_nay"><i class="bi bi-journal-text" aria-hidden="true"></i>Sổ cái TK 141</a>',
    },
    menu: (r) => {
      const m = [r.con_lai ? { nhan: 'Quyết toán tạm ứng', icon: 'bi-check2-circle', onClick: () => moQt(r) } : { nhan: 'Đã quyết toán xong', icon: 'bi-info-circle' },
        { nhan: 'Xem phiếu chi tạm ứng', icon: 'bi-receipt', href: '/ketoan/chung-tu?id=' + r.ung_id }];
      if (quyenSua() && !r.so_lan_quyet_toan) m.push({ nhan: 'Sửa khoản tạm ứng', icon: 'bi-pencil', onClick: () => moUng(r) }, { nhan: 'Xoá khoản tạm ứng', icon: 'bi-trash', onClick: () => moXoa(r) });
      return m;
    },
  });

  /* ── Lập / sửa khoản tạm ứng ── */
  const dlgU = $('tu-dlg-ung');
  let dangSua = null, dsTkTien = null, dsNv = null;
  const tkTien = () => (dsTkTien || []).find((t) => String(t.id) === $('tu-u-tk').value);
  function veDkUng() {
    const n = docTien($('tu-u-tien')), t = tkTien(), nv = $('tu-u-nv').selectedOptions[0];
    const dong = (tk, phu, no, co) => '<tr><td><span class="kt-tk">' + esc(tk) + '</span><span class="kt-dk__phu">' + esc(phu) + '</span></td><td class="num">' + (no ? KD.tien(no) : KT.tienSo(0)) + '</td><td class="num">' + (co ? KD.tien(co) : KT.tienSo(0)) + '</td></tr>';
    $('tu-u-dk').innerHTML = n ? dong('141', nv && nv.value ? nv.textContent : 'Nhân viên', n, 0) + dong(t ? tkDinhKhoan(t) : '…', t ? t.ten_tk : 'Chọn tài khoản chi', 0, n)
      : '<tr><td colspan="3" class="kd-muted">Nhập số tiền để xem bút toán.</td></tr>';
  }
  async function napDanhMuc() {
    if (!dsNv) dsNv = await KD.api('/api/tam-ung/nhan-vien');
    if (!dsTkTien) dsTkTien = (await KD.api('/api/tai-khoan')).filter((t) => t.active);
    $('tu-u-nv').innerHTML = '<option value="">— Chọn nhân viên —</option>' + dsNv.map((x) => '<option value="' + esc(x.ma) + '">' + esc(x.ten) + ' · ' + esc(x.ma) + '</option>').join('');
    $('tu-u-tk').innerHTML = '<option value="">— Chọn tài khoản —</option>' + dsTkTien.map((t) => '<option value="' + t.id + '">' + esc(t.ten_tk) + (t.loai === 'tien_mat' ? ' (tiền mặt)' : '') + '</option>').join('');
  }
  async function moUng(r) {
    dangSua = r || null;
    try { await napDanhMuc(); } catch (e) { window.showToast && window.showToast('err', 'Không tải được danh sách nhân viên / tài khoản: ' + e.message); return; }
    $('tu-ung-td').textContent = r ? 'Sửa tạm ứng ' + r.so_ct : 'Lập phiếu chi tạm ứng';
    $('tu-u-ok').innerHTML = '<i class="bi bi-check2" aria-hidden="true"></i>' + (r ? 'Lưu và ghi lại sổ' : 'Chi và ghi sổ');
    $('tu-u-note').textContent = r ? 'Lưu sẽ đảo bút toán cũ và ghi lại theo số mới.' : 'Lưu là ghi sổ ngay: phiếu chi + bút toán Nợ 141.';
    if (r && !dsNv.some((x) => x.ma === r.nhan_vien.ma)) $('tu-u-nv').insertAdjacentHTML('beforeend', '<option value="' + esc(r.nhan_vien.ma) + '">' + esc(r.nhan_vien.ten) + ' · ' + esc(r.nhan_vien.ma) + '</option>');
    const homNay = KD.iso(new Date());
    $('tu-u-nv').value = r ? r.nhan_vien.ma : ''; $('tu-u-nd').value = r ? r.noi_dung : '';
    $('tu-u-tien').value = r ? KD.tien(r.da_ung) : ''; $('tu-u-tk').value = r && r.tai_khoan.id ? String(r.tai_khoan.id) : '';
    $('tu-u-ngay').value = r ? r.ngay : homNay; $('tu-u-han').value = r ? r.han_hoan : congNgay(homNay, HAN_MAC_DINH_NGAY);
    veDkUng(); KD.moHopThoai(dlgU);
  }
  $('tu-them').addEventListener('click', () => moUng(null));
  $('tu-u-tien').addEventListener('input', (e) => { const n = docTien(e.target); e.target.value = n ? KD.tien(n) : ''; veDkUng(); });
  ['tu-u-tk', 'tu-u-nv'].forEach((id) => $(id).addEventListener('change', veDkUng));
  $('tu-u-ngay').addEventListener('change', (e) => { if (!dangSua && e.target.value) $('tu-u-han').value = congNgay(e.target.value, HAN_MAC_DINH_NGAY); });
  $('tu-form-ung').addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = { nhan_vien_ma: $('tu-u-nv').value, noi_dung: $('tu-u-nd').value.trim(), so_tien: docTien($('tu-u-tien')), tai_khoan_id: +$('tu-u-tk').value || 0, ngay: $('tu-u-ngay').value, han_hoan: $('tu-u-han').value || null };
    const thieu = !body.nhan_vien_ma ? 'Chọn nhân viên nhận tạm ứng.' : !body.noi_dung ? 'Nhập nội dung tạm ứng.' : !body.so_tien ? 'Nhập số tiền tạm ứng.' : !body.tai_khoan_id ? 'Chọn tài khoản chi tiền.' : !body.ngay ? 'Chọn ngày ứng.' : body.han_hoan && body.han_hoan < body.ngay ? 'Hạn hoàn ứng phải từ ngày ứng trở đi.' : '';
    if (thieu) return KD.baoLoiHopThoai(dlgU, thieu);
    const nut = $('tu-u-ok'); nut.disabled = true;
    try {
      const r = await KD.api('/api/tam-ung' + (dangSua ? '/' + dangSua.id : ''), Object.assign(KD.JSON_POST(body), dangSua ? { method: 'PUT' } : {}));
      dlgU.close(); ds.dongPanel(); window.showToast && window.showToast('ok', (dangSua ? 'Đã sửa ' : 'Đã chi tạm ứng ') + r.so_ct + ' — ' + KD.tienVnd(r.da_ung) + ' cho ' + r.nhan_vien.ten); ds.tai();
    } catch (err) { KD.baoLoiHopThoai(dlgU, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; }
  });

  /* ── Xoá khoản / huỷ lần quyết toán (dùng chung hộp xác nhận) ── */
  const dlgX = $('tu-dlg-xoa'); let viecXoa = null;
  function moXoa(r) {
    viecXoa = { url: '/api/tam-ung/' + r.id, opt: { method: 'DELETE' }, xong: 'Đã xoá ' + r.so_ct };
    $('tu-xoa-td').textContent = 'Xoá khoản tạm ứng ' + r.so_ct + '?';
    $('tu-xoa-nd').textContent = 'Hệ thống lập bút toán đảo cho phiếu chi ' + KD.tienVnd(r.da_ung) + ' của ' + r.nhan_vien.ten + ' và xoá dòng chi trên sổ quỹ. Dùng khi lập nhầm; tiền đã thực chi thì phải quyết toán thay vì xoá.';
    $('tu-xoa-ok').innerHTML = '<i class="bi bi-trash" aria-hidden="true"></i>Xoá'; KD.moHopThoai(dlgX);
  }
  function moHuyQt(qtId, t) {
    const q = t.quyet_toan.find((x) => String(x.qt_id) === String(qtId)); if (!q) return;
    viecXoa = { url: '/api/tam-ung/quyet-toan/' + q.qt_id + '/huy', opt: KD.JSON_POST({}), xong: 'Đã huỷ quyết toán ' + q.so_ct };
    $('tu-xoa-td').textContent = 'Huỷ quyết toán ' + q.so_ct + '?';
    $('tu-xoa-nd').textContent = 'Đảo bút toán quyết toán ngày ' + KD.ngay(q.ngay) + ', xoá chi phí và dòng sổ quỹ (hoàn/chi bù) đã sinh ra. Khoản ' + t.so_ct + ' quay lại trạng thái còn phải quyết toán.';
    $('tu-xoa-ok').innerHTML = '<i class="bi bi-arrow-counterclockwise" aria-hidden="true"></i>Huỷ quyết toán'; KD.moHopThoai(dlgX);
  }
  $('tu-xoa-ok').addEventListener('click', async () => { const nut = $('tu-xoa-ok'); nut.disabled = true;
    try { await KD.api(viecXoa.url, viecXoa.opt); dlgX.close(); ds.dongPanel(); window.showToast && window.showToast('ok', viecXoa.xong); ds.tai(); }
    catch (e) { KD.baoLoiHopThoai(dlgX, 'Chưa thực hiện được: ' + e.message); } finally { nut.disabled = false; } });

  /* ── Quyết toán ── */
  const dlg = $('tu-dlg'), oTk = KT.oTk($('tu-tk'), { loc: (t) => TK_CP.includes(t.ma), khiChon: () => veDk() });
  let dang = null, xl = 'thu_tien', choTk = Promise.resolve();
  const docSo = () => docTien($('tu-cp'));
  const dongDk = (tk, phu, no, co) => '<tr><td><span class="kt-tk">' + esc(tk || '…') + '</span>' + (phu ? '<span class="kt-dk__phu">' + esc(phu) + '</span>' : '') + '</td><td class="num">' + (no ? KD.tien(no) : KT.tienSo(0)) + '</td><td class="num">' + (co ? KD.tien(co) : KT.tienSo(0)) + '</td></tr>';
  function veDk() {
    if (!dang) return; const cp = docSo(), con = dang.con_lai, thua = con - cp, het = $('tu-het').checked, tien = dang.tai_khoan.tk, tenTk = dang.tai_khoan.ten || '';
    $('tu-het-o').hidden = thua <= 0; $('tu-xl-o').hidden = thua <= 0 || !het;
    $('tu-ket-luan').textContent = thua < 0 ? 'Chi thực tế vượt tạm ứng ' + KD.tienVnd(-thua) + ' — công ty chi bù cho nhân viên từ ' + tenTk + '; khoản tạm ứng kết thúc.'
      : thua === 0 ? 'Chi thực tế bằng số còn lại — khoản tạm ứng kết thúc.'
        : het ? 'Nhân viên hoàn lại ' + KD.tienVnd(thua) + (xl === 'tru_luong' ? ' bằng cách trừ vào lương kỳ tới (nhớ trừ ở bảng lương HCNS).' : ' — nộp lại vào ' + tenTk + '.') + ' Khoản tạm ứng kết thúc.'
          : 'Quyết toán một phần — còn ' + KD.tienVnd(thua) + ' chờ nhân viên nộp chứng từ tiếp.';
    const nv = dang.nhan_vien.ten, r = [];
    if (cp) r.push(dongDk(oTk.lay(), 'Chi phí thực tế', cp, 0));
    if (thua > 0 && het) r.push(dongDk(xl === 'tru_luong' ? '334' : tien, xl === 'tru_luong' ? 'Trừ lương ' + nv : 'Nhân viên nộp lại · ' + tenTk, thua, 0));
    if (thua < 0) { r.push(dongDk('141', nv, 0, con)); r.push(dongDk(tien, 'Chi bù cho nhân viên · ' + tenTk, 0, -thua)); }
    else if (cp || het) r.push(dongDk('141', nv, 0, cp + (het ? thua : 0)));
    $('tu-dk').innerHTML = r.join('') || '<tr><td colspan="3" class="kd-muted">Nhập chi phí thực tế để xem bút toán.</td></tr>';
  }
  function moQt(r) {
    dang = r; $('tu-dlg-td').textContent = 'Quyết toán tạm ứng — ' + r.nhan_vien.ten;
    $('tu-xl-tien').textContent = 'Nộp lại ' + (String(r.tai_khoan.tk).startsWith('111') ? 'quỹ tiền mặt' : 'tài khoản') + ' (' + r.tai_khoan.tk + ')';
    $('tu-dlg-tt').innerHTML = '<dt>Nội dung</dt><dd>' + esc(r.noi_dung) + '</dd><dt>Đã ứng</dt><dd>' + KD.tienVnd(r.da_ung) + (r.da_quyet_toan ? ' · đã quyết toán ' + KD.tienVnd(r.da_quyet_toan) : '') + '</dd><dt class="is-dam">Còn phải quyết toán</dt><dd>' + KD.tienVnd(r.con_lai) + '</dd>';
    $('tu-cp').value = KD.tien(r.con_lai); $('tu-ngay').value = KD.iso(new Date()); $('tu-gc').value = ''; $('tu-het').checked = true; datXl('thu_tien'); choTk = oTk.dat(TK_CP_MAC_DINH).then(veDk); veDk(); KD.moHopThoai(dlg); $('tu-cp').select();
  }
  function datXl(k) { xl = k; $('tu-xl').querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.xl === k))); veDk(); }
  $('tu-xl').addEventListener('click', (e) => { const b = e.target.closest('[data-xl]'); if (b) datXl(b.dataset.xl); });
  $('tu-cp').addEventListener('input', (e) => { const n = docSo(); e.target.value = n ? KD.tien(n) : ''; veDk(); });
  $('tu-het').addEventListener('change', veDk);
  $('tu-form').addEventListener('submit', async (e) => {
    e.preventDefault(); await choTk; await oTk.xacNhan(); const cp = docSo();
    if (cp && !oTk.lay()) return KD.baoLoiHopThoai(dlg, 'Chọn TK chi phí cho phần chi thực tế (641, 642, 635 hoặc 811).');
    if (!cp && !$('tu-het').checked) return KD.baoLoiHopThoai(dlg, 'Nhập chi phí thực tế, hoặc đánh dấu kết thúc để ghi nhận nhân viên hoàn lại toàn bộ.');
    if (!$('tu-ngay').value) return KD.baoLoiHopThoai(dlg, 'Chọn ngày quyết toán.');
    const nut = $('tu-ok'); nut.disabled = true;
    try { const r = await KD.api('/api/tam-ung/quyet-toan', KD.JSON_POST({ id: dang.id, chi_phi: cp, tk_cp: cp ? oTk.lay() : null, het: $('tu-het').checked, xu_ly_thua: xl, ngay: $('tu-ngay').value, ghi_chu: $('tu-gc').value.trim() }));
      dlg.close(); ds.dongPanel(); window.showToast && window.showToast('ok', 'Đã ghi sổ quyết toán ' + r.so_ct + (r.con_lai ? ' — còn ' + KD.tienVnd(r.con_lai) : ' — khoản tạm ứng đã kết thúc')); ds.tai(); }
    catch (err) { KD.baoLoiHopThoai(dlg, 'Chưa ghi sổ được: ' + err.message); } finally { nut.disabled = false; }
  });
  document.addEventListener('click', async (e) => {
    const b = e.target.closest('#tu-p-nut [data-qt]');
    if (b) { const r = ds.dsHien().find((x) => String(x.id) === b.dataset.qt); if (r) moQt(r); return; }
    const h = e.target.closest('#tu-p-nut [data-huy-qt]');
    if (h) { try { moHuyQt(h.dataset.huyQt, await KD.api('/api/tam-ung/' + encodeURIComponent(h.dataset.tu))); } catch (err) { window.showToast && window.showToast('err', err.message); } }
  });
  ds.tai();
})();
