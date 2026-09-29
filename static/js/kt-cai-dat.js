/* kt-cai-dat.js — Cài đặt Kế toán.
   Sửa được (PUT /api/cai-dat/<phan>): Thông tin đơn vị, Năm tài chính & chính sách, Đánh số chứng từ.
   CHỈ ĐỌC: Duyệt chi + Phân quyền — hiển thị đúng luồng/vai trò đang gate request thật (không có bảng cấu hình giả).
   Thanh dưới gom thay đổi chưa lưu của các nhóm sửa được. */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-cai-dat')) return;
  const $ = (id) => document.getElementById(id), H = KT.H;
  const PHAN = { don_vi: 'Thông tin đơn vị', ke_toan: 'Năm tài chính & chính sách', danh_so: 'Đánh số chứng từ' };
  const TAB = ['don_vi', 'ke_toan', 'duyet_chi', 'danh_so', 'phan_quyen'];
  const VAI = { admin: 'Admin', ceo: 'CEO', assistant_ceo: 'Trợ lý CEO', manager: 'Manager', leader: 'Leader', kt: 'Kế toán viên' };
  const LAM_LAI = [['khong', 'Không, chạy liên tục'], ['nam', 'Mỗi năm'], ['thang', 'Mỗi tháng']];
  const sao = (x) => JSON.parse(JSON.stringify(x));
  let goc = null, dang = null, suaDuoc = false;

  const tabs = KD.ganTab($('cd-tabs'), (k) => { try { KT.url.ghi({ tab: k }, { tab: 'don_vi' }); } catch (e) { /* khung xem */ } });

  /* ── Ô nhập có data-k: nạp ↔ đọc ── */
  const oCua = (phan) => [...document.querySelectorAll('#cd-p-' + phan + ' [data-k]')];
  function napO(phan) {
    oCua(phan).forEach((el) => { const v = dang[phan][el.dataset.k];
      if (el.type === 'checkbox') el.checked = !!v; else el.value = v == null ? '' : v; });
  }
  ['don_vi', 'ke_toan'].forEach((phan) => oCua(phan).forEach((el) => {
    el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', () => {
      const v = el.value.trim();
      dang[phan][el.dataset.k] = v === '' && phan === 'don_vi' && el.dataset.k !== 'ten' ? null : v;
      if (phan === 'ke_toan') veMetaKy(); capNhat();
    });
  }));

  /* ── Năm tài chính: câu mô tả kỳ hiện tại ── */
  function veMetaKy() {
    const bd = +dang.ke_toan.nam_tc_bat_dau || 1, nay = new Date();
    const namBd = nay.getMonth() + 1 >= bd ? nay.getFullYear() : nay.getFullYear() - 1;
    const kt = new Date(namBd, bd - 1 + 12, 0);
    $('cd-kt-meta').textContent = (goc.khoa_so_den ? 'Đã khoá sổ đến hết ' + KD.ngay(goc.khoa_so_den) + '. ' : 'Chưa khoá sổ kỳ nào. ')
      + 'Năm tài chính hiện tại: 01/' + String(bd).padStart(2, '0') + '/' + namBd + ' – ' + KD.ngay(KD.iso(kt)) + '.';
  }

  /* ── Duyệt chi (chỉ đọc) ── */
  const DAI = 60;   // điều kiện dài hơn → đưa vào ⓘ, trên thẻ chỉ còn tên bước + vai trò
  const chipVai = (ds) => ds.map((v) => '<span class="kd-chip kd-chip--xam">' + esc(VAI[v] || v) + '</span>').join(' ');
  function veDuyetChi() {
    const d = goc.duyet_chi;
    $('cd-dc-cap').innerHTML = d.cap_duyet.map((c, i) => '<li class="kt-cd-buoc"><span class="kt-cd-so" aria-hidden="true">' + (i + 1) + '</span>'
      + '<div><p class="kt-cd-buoc__ten">' + esc(c.ten) + (c.dieu_kien.length > DAI ? ' ' + KD.tip(c.dieu_kien) : '') + '</p>' + (c.dieu_kien.length > DAI ? '' : '<p class="kd-meta">' + esc(c.dieu_kien) + '</p>') + '<div class="kt-cd-chips">' + chipVai(c.vai_tro_duyet) + '</div></div></li>').join('');
    $('cd-dc-tip').innerHTML = KD.tip('Luồng đang chạy thật cho mọi đề nghị chi. ' + d.chua_ho_tro);
    const o = (tieuDe, x) => '<div class="kd-field"><p class="kd-field__label">' + esc(tieuDe) + ' ' + KD.tip(x.ghi_chu.replace(/\s*\([^)]*\.py[^)]*\)\.?$/, '.')) + '</p><div class="kt-cd-chips">' + chipVai(x.vai_tro) + '</div></div>';
    $('cd-dc-quyen').innerHTML = o('Lập & đảo bút toán tay', d.ghi_so_but_toan_tay) + o('Sửa / xoá lệnh thu chi đã lập', d.sua_xoa_thu_chi);
  }

  /* ── Đánh số ── */
  // Cùng khuôn với số bút toán thật đang sinh (services/journal.py: BT-2026-0095).
  const NAY = new Date(), NAM = String(NAY.getFullYear()), THANG = String(NAY.getMonth() + 1).padStart(2, '0');
  const viDu = (x) => (x.tien_to ? x.tien_to + '-' : '') + (x.lam_lai === 'thang' ? NAM + THANG + '-' : x.lam_lai === 'nam' ? NAM + '-' : '') + '1'.padStart(+x.do_dai || 4, '0');
  function veDanhSo() {
    const khoa = suaDuoc ? '' : ' disabled';
    $('cd-ds').innerHTML = dang.danh_so.map((x, i) => '<tr><th scope="row">' + esc(x.ten) + '</th>'
      + '<td><input class="kd-input kt-cd-o-to" data-i="' + i + '" data-f="tien_to" value="' + esc(x.tien_to) + '" maxlength="8" aria-label="Tiền tố ' + esc(x.ten) + '" autocomplete="off"' + khoa + '></td>'
      + '<td><select class="kd-input kt-cd-o-dai" data-i="' + i + '" data-f="do_dai" aria-label="Số chữ số ' + esc(x.ten) + '"' + khoa + '>' + [3, 4, 5, 6].map((n) => '<option value="' + n + '"' + (n === +x.do_dai ? ' selected' : '') + '>' + n + ' chữ số</option>').join('') + '</select></td>'
      + '<td><select class="kd-input kt-cd-o-lai" data-i="' + i + '" data-f="lam_lai" aria-label="Đánh lại số ' + esc(x.ten) + '"' + khoa + '>' + LAM_LAI.map(([v, t]) => '<option value="' + v + '"' + (v === x.lam_lai ? ' selected' : '') + '>' + t + '</option>').join('') + '</select></td>'
      + '<td><span class="kd-strong num" id="cd-vd-' + i + '">' + esc(viDu(x)) + '</span></td></tr>').join('');
  }
  $('cd-ds').addEventListener('input', (e) => { const el = e.target.closest('[data-f]'); if (!el) return; const x = dang.danh_so[+el.dataset.i];
    x[el.dataset.f] = el.dataset.f === 'do_dai' ? +el.value : el.dataset.f === 'tien_to' ? el.value.toUpperCase().replace(/\s/g, '') : el.value;
    if (el.dataset.f === 'tien_to' && el.value !== x.tien_to) el.value = x.tien_to;
    $('cd-vd-' + el.dataset.i).textContent = viDu(x); capNhat(); });

  /* ── Phân quyền (chỉ đọc) ── */
  function vePhanQuyen() {
    const p = goc.phan_quyen;
    $('cd-pq').innerHTML = p.vai_tro.map((v) => '<tr><th scope="row">' + esc(v.ten) + '</th>'
      + '<td><div class="kt-cd-chips">' + (v.nguoi.length ? v.nguoi.map((n) => '<span class="kd-chip kd-chip--xam">' + esc(n) + '</span>').join(' ') : '<span class="kd-muted">—</span>') + '</div></td>'
      + '<td><ul class="kt-cd-quyen">' + v.quyen.map((q) => '<li>' + esc(q.replace(/\s*—\s*API trả 403 Forbidden$/, '')) + '</li>').join('') + '</ul></td></tr>').join('');
    $('cd-pq-tip').innerHTML = KD.tip('Danh sách lấy từ tài khoản đang hoạt động; đổi vai trò ở màn Nhân sự. ' + p.ghi_chu);
  }

  /* ── Theo dõi thay đổi ── */
  const doi = () => Object.keys(PHAN).filter((p) => goc && JSON.stringify(goc[p]) !== JSON.stringify(dang[p]));
  function capNhat() {
    const ds = doi();
    Object.keys(PHAN).forEach((p) => { const t = $('cd-tab-' + p); const c = t.querySelector('.kt-cd-cham');
      if (ds.includes(p) && !c) t.insertAdjacentHTML('beforeend', '<span class="kt-cd-cham" aria-hidden="true"></span><span class="visually-hidden kt-cd-cham-chu"> (chưa lưu)</span>');
      if (!ds.includes(p) && c) { c.remove(); t.querySelector('.kt-cd-cham-chu').remove(); } });
    $('cd-tt-luu').textContent = ds.length ? 'Chưa lưu: ' + ds.map((p) => PHAN[p]).join(', ') + '.' : 'Chưa có thay đổi.';
    $('cd-luu').disabled = !ds.length; $('cd-huy').disabled = !ds.length; $('cd-loi').hidden = true;
  }
  window.addEventListener('beforeunload', (e) => { if (doi().length) { e.preventDefault(); e.returnValue = ''; } });

  function veTatCa() {
    ['don_vi', 'ke_toan'].forEach(napO); veMetaKy(); veDuyetChi(); veDanhSo(); vePhanQuyen();
    $('cd-dv-rong').hidden = !!goc.don_vi.ten;
    capNhat();
  }
  $('cd-huy').addEventListener('click', () => { dang = sao(goc); veTatCa(); window.showToast && window.showToast('info', 'Đã bỏ các thay đổi chưa lưu'); });

  $('cd-luu').addEventListener('click', async () => {
    const ds = doi(); if (!ds.length) return;
    // kiểm nhanh phía trình duyệt — máy chủ vẫn kiểm lại
    if (ds.includes('don_vi') && !dang.don_vi.ten) return baoLoi('don_vi', 'Nhập tên đơn vị.', 'cd-ten');
    if (ds.includes('don_vi') && dang.don_vi.mst && !/^\d{10}(-\d{3})?$/.test(dang.don_vi.mst)) return baoLoi('don_vi', 'Mã số thuế gồm 10 chữ số (chi nhánh thêm "-" và 3 số).', 'cd-mst');
    const nut = $('cd-luu'); nut.disabled = true; const xong = [];
    for (const p of ds) {
      try {
        const kq = await KD.api('/api/cai-dat/' + p, Object.assign(KD.JSON_POST(dang[p]), { method: 'PUT' }));
        if (p === 'don_vi') { delete kq.hom_nay; Object.assign(dang.don_vi, kq); }
        if (p === 'ke_toan') Object.assign(dang.ke_toan, kq);
        goc[p] = sao(dang[p]); xong.push(PHAN[p]);
      } catch (e) { capNhat(); if (xong.length) window.showToast && window.showToast('ok', 'Đã lưu: ' + xong.join(', ')); return baoLoi(p, 'Chưa lưu được ' + PHAN[p] + ': ' + e.message); }
    }
    ['don_vi', 'ke_toan'].forEach(napO); $('cd-dv-rong').hidden = !!goc.don_vi.ten; capNhat();
    window.showToast && window.showToast('ok', 'Đã lưu: ' + xong.join(', '));
  });
  function baoLoi(p, msg, oId) { tabs.chon(p); $('cd-loi').textContent = msg; $('cd-loi').hidden = false; if (oId) $(oId).focus(); }

  /* Người không có quyền sửa (manager/kt): xem được, ô khoá, thanh lưu thay bằng câu giải thích. */
  function khoaSua() {
    ['don_vi', 'ke_toan'].forEach((p) => oCua(p).forEach((el) => { el.disabled = true; }));
    $('cd-luu').hidden = true; $('cd-huy').hidden = true;
    $('cd-tt-luu').textContent = 'Chỉ xem — cần quyền CEO để ghi. Chỉ CEO / Admin / Trợ lý CEO được sửa cài đặt.';
  }

  /* ── Tải: khung chờ / lỗi / dữ liệu ── */
  async function tai() {
    $('cd-tt').innerHTML = KD.KHUNG_TAI; $('cd-than').hidden = true; $('cd-thanh').hidden = true;
    try {
      const d = await KD.api('/api/cai-dat'); suaDuoc = !!d.quyen_sua;
      delete d.don_vi.hom_nay;
      goc = sao(d); dang = sao(d);
      H.napChon($('cd-nam'), Array.from({ length: 12 }, (_, i) => { const m = String(i + 1).padStart(2, '0'); return [m, 'Ngày 01/' + m]; }), '', d.ke_toan.nam_tc_bat_dau);
      veTatCa();
      $('cd-tt').innerHTML = ''; $('cd-than').hidden = false; $('cd-thanh').hidden = false;
      if (!suaDuoc) khoaSua();
      const t = KT.url.doc().tab; tabs.chon(TAB.includes(t) ? t : 'don_vi');
    } catch (e) { KD.khoiLoi($('cd-tt'), 'Không tải được cài đặt Kế toán', e, tai); }
  }
  tai();
})();
