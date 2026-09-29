/* kt-de-xuat-ncc.js — Đề xuất thanh toán NCC (L4): chọn NCC → chọn đơn mua còn nợ → số đề xuất ≤ số còn đề xuất được.
   ĐẤU NỐI THẬT (2026-09-25). Thiết kế gốc gọi /api/doi-tuong?loai=ncc, /api/bao-cao/cong-no-ncc/<id>, /api/duyet-chi/cau-hinh và
   POST /api/duyet-chi {nguon:'de_xuat_ncc'} — không cái nào tồn tại. Nay dùng công nợ NCC thật của Mua Hàng (muahang.congno):
     GET  /api/ncc-de-xuat/cong-no            NCC còn nợ (nợ − đã chi, trừ đề xuất đang chờ)
     GET  /api/ncc-de-xuat/cong-no/<ncc_id>   các đơn mua còn nợ của 1 NCC
     POST /api/ncc-de-xuat {ncc_id, ngay, mo_ta, dong:[{ref_order_id, so_tien}]}  → 1 đề xuất trả NCC 'cho_duyet'
   Gần đúng: công nợ không có "hạn thanh toán" và mọi khoản đã trả NCC hiện có đều không gắn đơn → "còn nợ từng đơn" do backend
   trừ dần (FIFO) vào đơn cũ nhất; chặn vượt theo TỔNG NCC. Không có nháp (model không có trạng thái nháp). */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-de-xuat')) return;
  const $ = (id) => document.getElementById(id), u = KT.url.doc();
  const docSo = (v) => Number(String(v || '').replace(/[^\d]/g, '')) || 0;
  let dsNcc = [], cn = null, chon = {};
  const key = (d) => d.id || '_';

  async function tai() {
    $('dx-tt').innerHTML = KD.KHUNG_TAI; $('dx-than').hidden = true; $('dx-thanh').hidden = true;
    try {
      dsNcc = await KD.api('/api/ncc-de-xuat/cong-no');
      $('dx-ncc').innerHTML = '<option value="">— Chọn nhà cung cấp (' + KD.soDem(dsNcc.length) + ' NCC còn nợ) —</option>'
        + dsNcc.map((x) => '<option value="' + esc(x.id) + '">' + esc(x.ten) + ' · còn nợ ' + KD.tien(x.con_no) + (x.co_the_de_xuat < x.con_no ? ' (đang đề xuất ' + KD.tien(x.dang_de_xuat) + ')' : '') + '</option>').join('');
      $('dx-ngay').value = KD.iso(new Date());
      $('dx-tt').innerHTML = ''; $('dx-than').hidden = false; $('dx-thanh').hidden = false;
      if (u.ncc) { $('dx-ncc').value = u.ncc; taiNcc(); } else veRong();
      veQt();
    } catch (e) { KD.khoiLoi($('dx-tt'), 'Không mở được mẫu đề xuất', e, tai); }
  }
  function veRong() {
    cn = null; chon = {}; $('dx-cuon').hidden = true; $('dx-ma').textContent = ''; $('dx-ma').hidden = true; $('dx-meta').innerHTML = '';
    $('dx-hd-tt').innerHTML = KD.khoiRong('Chưa chọn nhà cung cấp', 'Chọn nhà cung cấp ở trên để xem các đơn mua còn nợ.'); $('dx-chon-han').disabled = true; $('dx-hd-gy').innerHTML = ''; veTong();
  }
  let luotNcc = 0;   // đổi NCC nhanh: chỉ nhận phản hồi của lần chọn cuối (phản hồi cũ về sau không được đè NCC đang chọn)
  async function taiNcc() {
    const id = $('dx-ncc').value, l = ++luotNcc; if (!id) return veRong();
    $('dx-cuon').hidden = false; $('dx-hd-tt').innerHTML = ''; $('dx-hd').innerHTML = KT.hangCho(5, 3); $('dx-cong').innerHTML = '';
    try {
      const kq = await KD.api('/api/ncc-de-xuat/cong-no/' + encodeURIComponent(id)); if (l !== luotNcc) return;
      cn = kq; chon = {};
      $('dx-ma').textContent = cn.ncc.ten; $('dx-ma').hidden = false;
      $('dx-meta').innerHTML = '<span>Còn phải trả: <b>' + KD.tienVnd(cn.tong.con_no) + '</b></span><span>Đang đề xuất: <b>' + KD.tienVnd(cn.tong.dang_de_xuat) + '</b></span><span>Còn đề xuất được: <b>' + KD.tienVnd(cn.tong.co_the_de_xuat) + '</b></span>'
        // Còn đề xuất được = max(0, còn nợ − đang đề xuất). Khi đề xuất đang chờ VƯỢT số còn nợ (vd CHỊ LAN ĐỆM:
        // 30.544.404 − 35.191.800) phép trừ âm nhưng hiện 0 → ghi rõ phần vượt để ba số trên khớp nhau.
        + (cn.tong.dang_de_xuat > cn.tong.con_no ? '<span class="kt-o-tk__canh">Đang đề xuất vượt số nợ ' + KD.tienVnd(cn.tong.dang_de_xuat - cn.tong.con_no) + ' ' + KD.tip('Đề xuất đang chờ lớn hơn số còn nợ nên "Còn đề xuất được" tính là 0.') + '</span>' : '');
      if (!$('dx-nd').value || $('dx-nd').dataset.tu) { $('dx-nd').value = 'Thanh toán công nợ — ' + cn.ncc.ten; $('dx-nd').dataset.tu = '1'; }
      veHd();
    } catch (e) { if (l !== luotNcc) return; $('dx-cuon').hidden = true; KD.khoiLoi($('dx-hd-tt'), 'Không tải được công nợ của nhà cung cấp', e, taiNcc); }
  }
  // NCC đang chọn nằm trên URL (?ncc=) → F5 / gửi link mở lại đúng NCC.
  $('dx-ncc').addEventListener('change', () => { KT.url.ghi({ ncc: $('dx-ncc').value }, { ncc: '' }); taiNcc(); });
  $('dx-nd').addEventListener('input', (e) => { delete e.target.dataset.tu; });
  const tim = (k) => cn.don.find((x) => key(x) === k);
  function veHd() {
    const ds = cn.don;
    $('dx-hd-gy').innerHTML = ds.length ? KD.soDem(ds.length) + ' đơn ' + KD.tip('Xếp đơn cũ nhất trước; tiền đã trả được trừ dần vào đơn cũ nhất.') : '';
    $('dx-chon-han').disabled = !cn.tong.co_the_de_xuat;
    if (!ds.length) { $('dx-cuon').hidden = true; $('dx-hd-tt').innerHTML = KD.khoiRong('Nhà cung cấp này không còn đơn nợ', 'Chọn nhà cung cấp khác.'); veTong(); return; }
    $('dx-hd').innerHTML = ds.map((p) => { const k = key(p), co = chon[k] != null, het = !p.co_the_de_xuat;
      return '<tr' + (het ? ' class="kt-dx-het"' : '') + '><td class="kt-ct-stt"><input type="checkbox" class="kt-dx-chon" data-id="' + esc(k) + '" aria-label="Chọn đơn ' + esc(p.ma) + '"' + (co ? ' checked' : '') + (het ? ' disabled' : '') + '></td>'
        + '<td><span class="kd-strong">' + esc(p.ma) + '</span>' + (p.ten_don ? '<span class="kt-khach__ma">' + esc(p.ten_don) + '</span>' : '') + '</td>'
        + '<td>' + KD.ngay(p.ngay) + '</td>'
        + '<td class="num">' + KD.tien(p.con_no) + '</td>'
        + '<td class="num">' + (het ? '<span class="kd-muted" title="Đã nằm trong đề xuất đang chờ">Đang đề xuất</span>' : KD.tien(p.co_the_de_xuat)) + '</td>'
        + '<td class="num kt-ct-o-so"><input class="kd-input num" data-tien="' + esc(k) + '" inputmode="numeric" autocomplete="off" aria-label="Đề xuất trả đơn ' + esc(p.ma) + '" value="' + (co ? KD.tien(chon[k]) : '') + '" placeholder="—"' + (co ? '' : ' disabled') + '></td></tr>'; }).join('');
    veTong();
  }
  $('dx-hd').addEventListener('change', (e) => { const c = e.target.closest('.kt-dx-chon'); if (!c) return; const p = tim(c.dataset.id);
    if (c.checked) chon[c.dataset.id] = p.co_the_de_xuat; else delete chon[c.dataset.id];
    const o = document.querySelector('[data-tien="' + CSS.escape(c.dataset.id) + '"]'); o.disabled = !c.checked; o.value = c.checked ? KD.tien(p.co_the_de_xuat) : ''; if (c.checked) o.focus(); veTong(); });
  $('dx-hd').addEventListener('input', (e) => { const o = e.target.closest('[data-tien]'); if (!o) return; const n = docSo(o.value); o.value = n ? KD.tien(n) : ''; const p = tim(o.dataset.tien);
    chon[o.dataset.tien] = n; o.classList.toggle('kt-ct-sai', n > p.co_the_de_xuat); veTong(); });
  $('dx-chon-han').addEventListener('click', () => { cn.don.forEach((p) => { if (p.co_the_de_xuat) chon[key(p)] = p.co_the_de_xuat; }); veHd(); });
  function veTong() {
    const ids = Object.keys(chon), tong = ids.reduce((s, k) => s + (chon[k] || 0), 0);
    const vuotDon = cn ? ids.filter((k) => chon[k] > (tim(k) || {}).co_the_de_xuat) : [];
    const vuotTong = cn && tong > cn.tong.co_the_de_xuat;
    $('dx-cong').innerHTML = cn && ids.length ? '<tr><th scope="row" colspan="3">Cộng ' + KD.soDem(ids.length) + ' đơn</th><td class="num">' + KD.tien(ids.reduce((s, k) => s + ((tim(k) || {}).con_no || 0), 0)) + '</td><td class="num">' + KD.tien(ids.reduce((s, k) => s + ((tim(k) || {}).co_the_de_xuat || 0), 0)) + '</td><td class="num">' + KD.tien(tong) + '</td></tr>' : '';
    $('dx-tong').innerHTML = '<dl class="kt-tq"><dt>Số đơn chọn</dt><dd>' + KD.soDem(ids.length) + '</dd><dt>Còn phải trả NCC</dt><dd>' + (cn ? KD.tienVnd(cn.tong.con_no) : '—') + '</dd><dt>Còn đề xuất được</dt><dd>' + (cn ? KD.tienVnd(cn.tong.co_the_de_xuat) : '—') + '</dd><dt class="is-dam">Tổng đề xuất</dt><dd>' + KD.tienVnd(tong) + '</dd></dl>'
      + (tong ? '<p class="kd-meta">Bằng chữ: ' + esc(KT.bangChu(tong)) + '</p>' : '')
      + (vuotDon.length ? '<p class="kt-o-tk__canh">' + KD.soDem(vuotDon.length) + ' đơn đề xuất vượt số còn đề xuất được của đơn.</p>' : '')
      + (vuotTong ? '<p class="kt-o-tk__canh">Tổng vượt số còn đề xuất được của nhà cung cấp.</p>' : '');
  }
  function veQt() {
    $('dx-qt').innerHTML = '<ol class="kd-timeline">' + [['Kế toán duyệt', 'Ở màn Duyệt chi'], ['Giám đốc duyệt', 'Trong app Mua Hàng'], ['Kế toán chi tiền', 'Ghi sổ quỹ chi, giảm công nợ NCC']]
      .map((b, i) => '<li><div class="kd-tl"><div><div class="kd-strong">' + (i + 1) + '. ' + esc(b[0]) + '</div><div class="kd-muted">' + esc(b[1]) + '</div></div></div></li>').join('') + '</ol>';
  }
  const baoLoi = (m) => { $('dx-loi').textContent = m; $('dx-loi').hidden = !m; };
  async function gui() {
    baoLoi(''); if (!cn) { $('dx-ncc').focus(); return baoLoi('Chọn nhà cung cấp.'); }
    const dong = Object.keys(chon).filter((k) => chon[k] > 0).map((k) => ({ ref_order_id: tim(k).id || null, so_tien: chon[k] }));
    if (!dong.length) return baoLoi('Chọn ít nhất một đơn và số tiền đề xuất trả.');
    if (dong.some((d) => d.so_tien > tim(d.ref_order_id || '_').co_the_de_xuat)) return baoLoi('Có đơn đề xuất vượt số còn đề xuất được — sửa lại số tiền.');
    const nut = $('dx-gui'); nut.disabled = true;
    try {
      const r = await KD.api('/api/ncc-de-xuat', KD.JSON_POST({ ncc_id: cn.ncc.id, ngay: $('dx-ngay').value || null, mo_ta: $('dx-nd').value.trim() || null, dong }));
      window.showToast && window.showToast('ok', 'Đã gửi đề xuất ' + r.id + ' — chờ Kế toán duyệt');
      location.href = '/ketoan/kt-duyet?trang_thai=tat_ca&nguon=de_xuat_ncc&id=' + encodeURIComponent('ncc:' + r.id);
    } catch (e) { baoLoi('Chưa gửi được: ' + e.message); } finally { nut.disabled = false; }
  }
  $('dx-gui').addEventListener('click', gui);
  tai();
})();
