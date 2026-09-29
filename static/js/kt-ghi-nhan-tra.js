/* ═══════════════════════════════════════════════════════════════════════════
   kt-ghi-nhan-tra.js — Hộp "Ghi nhận thu / trả công nợ" dùng cho Công nợ KH, Công nợ NCC và
   Chi tiết đối tượng. Theo ĐÚNG cơ chế kế toán cũ (index.html: traCongNo / submitCongNoTra).

   2 chế độ (tab trong hộp):
   · Một khoản   — POST /api/cong-no/{id}/tra {da_tra: đã_trả_cũ + số_trả_thêm, tai_khoan, ngay_tra, ghi_chu}
                   (y nguyên lời gọi màn cũ). Ô Đối tượng + Khoản là combobox gõ-để-tìm.
   · Nhiều khoản — POST /api/cong-no/tra-nhieu {tai_khoan, ngay_tra, ghi_chu, dong:[{id, so_tien}]}
                   (một giao dịch, lỗi một dòng là huỷ cả lô — app/services/cong_no_tra_nhieu.py).
   "Xem trước" ở cả hai chế độ gọi /api/cong-no/tra-nhieu?dry_run=true: máy chủ chạy ĐÚNG hàm ghi
   thật rồi rollback, trả về da_tra/còn lại mới + dòng sổ quỹ sẽ tạo — không ghi gì.
   Tác dụng khi ghi thật: ketoan.cong_no (da_tra, con_lai, trang_thai, ngay_tra, ghi_chu),
   ketoan.so_quy (1 dòng thu/chi mỗi khoản), shared.audit_log (tra_cong_no).

   API: KTGhiNhanTra.mo({ loai:'phai_thu'|'phai_tra', doiTuong:[{ten, khoan:[{id,ma_don,so_tien,da_tra,con_lai}]}],
                          chonDoiTuong, chonKhoan, cheDo:'mot'|'nhieu', xong: () => {} })
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const bao = (loai, cau) => (window.showToast ? window.showToast(loai, cau) : console.info(cau));
  const soTienNhap = (v) => Math.round(Number(String(v || '').replace(/[^\d]/g, '')) || 0);
  /* So khớp không phân biệt hoa/thường và dấu tiếng Việt (đ → d). */
  const khongDau = (s) => String(s == null ? '' : s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').toLowerCase();
  const khop = (chuoi, q) => { const t = khongDau(q).trim(); if (!t) return true; const c = khongDau(chuoi), cSo = c.replace(/[.,\s]/g, '');
    return t.split(/\s+/).every((tu) => c.indexOf(tu) >= 0 || (/^[\d.,]+$/.test(tu) && cSo.indexOf(tu.replace(/[.,]/g, '')) >= 0)); };

  let dlg = null, ctx = null, dsTk = null, cheDo = 'mot', cbDt = null, cbKhoan = null, cbLoc = null;
  const tatCaKhoan = () => ctx.doiTuong.flatMap((d) => d.khoan.filter((k) => k.con_lai > 0).map((k) => Object.assign({ ten: d.ten }, k)));
  const nhanKhoan = (k) => k.ten + ' · ' + (k.ma_don || '—') + ' · còn ' + KD.tienVnd(k.con_lai);
  const chuoiTimKhoan = (k) => [k.ten, k.ma_don, k.id, k.con_lai, k.so_tien].join(' ');

  /* ── Combobox gõ-để-tìm (ARIA 1.2, cùng khuôn KT.oTk của kt-chung.js — KT.oTk gắn cứng danh mục
     tài khoản kế toán nên không dùng lại được; CSS dùng lại .kt-o-tk/.kt-o-tk__ds của kt-chung.css). ── */
  let soCb = 0;
  function combobox(inp, o) {
    const id = inp.id || ('gnt-cb-' + (++soCb)); inp.id = id;
    const ul = document.createElement('ul'); ul.className = 'kt-o-tk__ds kt-gnt-ds'; ul.id = id + '-ds'; ul.setAttribute('role', 'listbox'); ul.hidden = true;
    inp.insertAdjacentElement('afterend', ul);
    inp.setAttribute('role', 'combobox'); inp.setAttribute('aria-autocomplete', 'list'); inp.setAttribute('aria-expanded', 'false'); inp.setAttribute('aria-controls', ul.id); inp.autocomplete = 'off';
    let hien = [], dang = -1, daChon = null;
    function dong() { ul.hidden = true; inp.setAttribute('aria-expanded', 'false'); inp.removeAttribute('aria-activedescendant'); dang = -1; }
    function ve() {
      const q = daChon && inp.value === o.nhan(daChon) ? '' : inp.value;
      hien = o.nguon().filter((x) => khop(o.tim(x), q)).slice(0, 60);
      ul.innerHTML = hien.length ? hien.map((x, i) => '<li role="option" id="' + id + '-o' + i + '" data-i="' + i + '" aria-selected="' + (i === dang) + '">' + o.ve(x) + '</li>').join('')
        : '<li class="kt-o-tk__rong" role="presentation">Không có kết quả khớp "' + esc(inp.value.trim()) + '"</li>';
      ul.hidden = false; inp.setAttribute('aria-expanded', 'true');
      if (dang >= 0) inp.setAttribute('aria-activedescendant', id + '-o' + dang); else inp.removeAttribute('aria-activedescendant');
    }
    function chon(x, imLang) { daChon = x || null; inp.value = x ? o.nhan(x) : ''; dong(); if (!imLang && o.khiChon) o.khiChon(daChon); }
    inp.addEventListener('focus', () => { inp.select(); ve(); });
    inp.addEventListener('click', () => { if (ul.hidden) ve(); });
    inp.addEventListener('input', () => { daChon = null; dang = -1; ve(); });
    inp.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); if (ul.hidden) return ve(); if (!hien.length) return;
        dang = (dang + (e.key === 'ArrowDown' ? 1 : -1) + hien.length) % hien.length; ve(); const li = $(id + '-o' + dang); if (li) li.scrollIntoView({ block: 'nearest' }); }
      else if (e.key === 'Enter' && !ul.hidden) { e.preventDefault(); if (dang >= 0) chon(hien[dang]); else if (hien.length === 1) chon(hien[0]); }
      else if (e.key === 'Escape' && !ul.hidden) { e.preventDefault(); e.stopPropagation(); dong(); if (daChon) inp.value = o.nhan(daChon); }
    });
    ul.addEventListener('mousedown', (e) => { const li = e.target.closest('[data-i]'); if (li) { e.preventDefault(); chon(hien[+li.dataset.i]); } });
    inp.addEventListener('blur', () => setTimeout(() => { dong(); if (!daChon && hien.length === 1 && inp.value.trim()) chon(hien[0]); else if (daChon) inp.value = o.nhan(daChon); }, 120));
    return { chon, lay: () => daChon, moDs: ve };
  }

  function taoHop() {
    if (dlg) return;
    document.body.insertAdjacentHTML('beforeend',
      '<dialog class="kd-dialog kt-gnt-dlg" id="gnt-dlg" aria-labelledby="gnt-td">'
      + '<form method="dialog" novalidate id="gnt-form">'
      + '<header class="kd-dialog__head"><h2 class="kd-dialog__title"><span id="gnt-td">Ghi nhận thu công nợ</span><span id="gnt-tip"></span></h2>'
      + '<button type="button" class="kd-icon-btn" data-dong aria-label="Đóng"><i class="bi bi-x-lg" aria-hidden="true"></i></button></header>'
      + '<div class="kd-dialog__body">'
      + '<div class="kd-tabs" role="tablist" aria-label="Chế độ ghi nhận" id="gnt-tabs">'
      + '<button type="button" role="tab" id="gnt-tab-mot" data-tab="mot" aria-controls="gnt-mot" aria-selected="true">Một khoản</button>'
      + '<button type="button" role="tab" id="gnt-tab-nhieu" data-tab="nhieu" aria-controls="gnt-nhieu" aria-selected="false" tabindex="-1">Nhiều khoản</button></div>'
      // ── Một khoản
      + '<section id="gnt-mot" role="tabpanel" aria-labelledby="gnt-tab-mot" class="kt-gnt-pane">'
      + '<div class="kd-row2">'
      + '<div class="kd-field kt-o-tk"><label class="kd-field__label" for="gnt-dt"><span data-nhan-dt>Khách hàng</span></label><input class="kd-input" id="gnt-dt" placeholder="Gõ tên để lọc…"></div>'
      + '<div class="kd-field kt-o-tk"><label class="kd-field__label" for="gnt-khoan">Khoản công nợ <span class="kd-field__req" aria-hidden="true">*</span></label>'
      + '<input class="kd-input" id="gnt-khoan" placeholder="Gõ mã đơn hoặc số tiền…" aria-describedby="gnt-khoan-loi"><p class="kd-form-err" id="gnt-khoan-loi" role="alert" hidden></p></div>'
      + '</div>'
      + '<dl class="kt-tq kt-gnt-so" id="gnt-so"></dl>'
      + '<div class="kd-field"><label class="kd-field__label" for="gnt-tien"><span data-nhan-tien>Số tiền thu thêm</span> (VND) <span class="kd-field__req" aria-hidden="true">*</span></label>'
      + '<input class="kd-input num kt-gnt-tien" id="gnt-tien" inputmode="numeric" autocomplete="off" aria-describedby="gnt-tien-loi"><p class="kd-form-err" id="gnt-tien-loi" role="alert" hidden></p>'
      + '<button type="button" class="kd-btn kd-btn--sm kt-gnt-du" id="gnt-du"><i class="bi bi-check2-all" aria-hidden="true"></i>Điền đủ số còn lại</button></div>'
      + '</section>'
      // ── Nhiều khoản
      + '<section id="gnt-nhieu" role="tabpanel" aria-labelledby="gnt-tab-nhieu" class="kt-gnt-pane" hidden>'
      + '<div class="kd-row2">'
      + '<label class="kd-search kt-search"><i class="bi bi-search" aria-hidden="true"></i><input type="search" id="gnt-n-tim" placeholder="Tìm tên, mã đơn, số tiền…" aria-label="Tìm khoản công nợ" autocomplete="off"></label>'
      + '<div class="kd-field kt-o-tk kt-gnt-loc"><input class="kd-input" id="gnt-n-dt" placeholder="Lọc theo đối tượng…" aria-label="Thêm đối tượng vào bộ lọc"></div>'
      + '</div>'
      + '<div class="kt-gnt-chips" id="gnt-n-chips" aria-live="polite"></div>'
      + '<div class="kd-table-scroll kt-gnt-bang-cuon"><table class="kd-table kd-table--gon kt-gnt-bang"><caption class="visually-hidden">Các khoản còn nợ</caption><thead><tr>'
      + '<th scope="col" class="kt-gnt-cot-chon"><input type="checkbox" id="gnt-n-tat-ca" aria-label="Chọn tất cả khoản theo bộ lọc"></th>'
      + '<th scope="col">Đối tượng</th><th scope="col">Đơn hàng / mã CN</th><th scope="col" class="num">Còn lại</th><th scope="col" class="num" data-nhan-so-tra>Số trả</th></tr></thead>'
      + '<tbody id="gnt-n-ds"></tbody></table></div>'
      + '<p class="kd-form-err" id="gnt-n-loi" role="alert" hidden></p>'
      + '</section>'
      // ── Chung
      + '<div class="kd-row2">'
      + '<div class="kd-field"><label class="kd-field__label" for="gnt-tk"><span data-nhan-tk>Tài khoản nhận</span> <span class="kd-field__req" aria-hidden="true">*</span></label>'
      + '<select class="kd-input" id="gnt-tk" aria-describedby="gnt-tk-loi"></select><p class="kd-form-err" id="gnt-tk-loi" role="alert" hidden></p></div>'
      + '<div class="kd-field"><label class="kd-field__label" for="gnt-ngay">Ngày thanh toán</label><input class="kd-input" type="date" id="gnt-ngay"></div>'
      + '</div>'
      + '<div class="kd-field"><label class="kd-field__label" for="gnt-gc">Ghi chú</label><input class="kd-input" id="gnt-gc" maxlength="200" placeholder="VD: chuyển khoản, số chứng từ…"></div>'
      + '<div class="kt-gnt-tong" id="gnt-tong" aria-live="polite"></div>'
      + '<div class="kt-gnt-xt" id="gnt-xt" hidden></div>'
      + '<p class="kd-form-err" id="gnt-loi" role="alert" hidden></p>'
      + '</div>'
      + '<footer class="kd-dialog__foot"><button type="button" class="kd-btn" data-dong>Huỷ</button>'
      + '<button type="button" class="kd-btn" id="gnt-xem"><i class="bi bi-eye" aria-hidden="true"></i>Xem trước</button>'
      + '<button type="submit" class="kd-btn kd-btn--primary" id="gnt-luu"><i class="bi bi-check2" aria-hidden="true"></i>Ghi nhận</button></footer>'
      + '</form></dialog>');
    dlg = $('gnt-dlg');

    KD.ganTab($('gnt-tabs'), (t) => { cheDo = t; dlg.classList.toggle('is-nhieu', t === 'nhieu'); anXemTruoc(); baoLoi(''); veTong(); });
    cbDt = combobox($('gnt-dt'), {
      nguon: () => [{ ten: '', tatCa: true }].concat(ctx.doiTuong), tim: (d) => d.tatCa ? '' : d.ten,
      nhan: (d) => d.tatCa ? '' : d.ten,
      ve: (d) => d.tatCa ? '<span class="kt-o-tk__ten">Tất cả ' + esc(ctx.thu ? 'khách hàng' : 'nhà cung cấp') + '</span>'
        : '<span>' + esc(d.ten) + '</span><span class="kt-o-tk__ten">' + KD.soDem(d.khoan.filter((k) => k.con_lai > 0).length) + ' khoản · còn ' + KD.tienVnd(d.khoan.reduce((a, k) => a + Math.max(0, k.con_lai), 0)) + '</span>',
      khiChon: () => { cbKhoan.chon(null); veSo(true); $('gnt-khoan').focus(); },
    });
    cbKhoan = combobox($('gnt-khoan'), {
      nguon: () => { const d = cbDt.lay(); return tatCaKhoan().filter((k) => !d || d.tatCa || k.ten === d.ten); },
      tim: chuoiTimKhoan, nhan: nhanKhoan,
      ve: (k) => '<span><b>' + esc(k.ten) + '</b> · ' + esc(k.ma_don || '—') + '</span><span class="kt-o-tk__ten">' + esc(k.id) + ' · còn ' + KD.tienVnd(k.con_lai) + '</span>',
      khiChon: (k) => { if (k) { const d = ctx.doiTuong.find((x) => x.ten === k.ten); if (d) cbDt.chon(d, true); } veSo(true); },
    });
    cbLoc = combobox($('gnt-n-dt'), {
      nguon: () => ctx.doiTuong.filter((d) => !ctx.locDt.has(d.ten)), tim: (d) => d.ten, nhan: () => '',
      ve: (d) => '<span>' + esc(d.ten) + '</span><span class="kt-o-tk__ten">' + KD.soDem(d.khoan.filter((k) => k.con_lai > 0).length) + ' khoản</span>',
      khiChon: (d) => { if (d) { ctx.locDt.add(d.ten); veNhieu(); } $('gnt-n-dt').value = ''; },
    });
    $('gnt-n-chips').addEventListener('click', (e) => { const b = e.target.closest('[data-bo]'); if (b) { ctx.locDt.delete(b.dataset.bo); veNhieu(); } });
    $('gnt-n-tim').addEventListener('input', KD.debounce(veNhieu, 150));
    $('gnt-n-tat-ca').addEventListener('change', (e) => { dsLoc().forEach((k) => { if (e.target.checked) ctx.chon.set(k.id, ctx.chon.get(k.id) || k.con_lai); else ctx.chon.delete(k.id); }); veNhieu(); });
    $('gnt-n-ds').addEventListener('change', (e) => {
      const cb = e.target.closest('[data-chon]'); if (!cb) return;
      const k = tatCaKhoan().find((x) => String(x.id) === cb.dataset.chon);
      if (cb.checked) ctx.chon.set(k.id, k.con_lai); else ctx.chon.delete(k.id);
      veNhieu();
    });
    $('gnt-n-ds').addEventListener('input', (e) => {
      const o = e.target.closest('[data-so-tra]'); if (!o) return;
      const k = tatCaKhoan().find((x) => String(x.id) === o.dataset.soTra); const v = soTienNhap(o.value);
      if (v > 0) ctx.chon.set(k.id, v); else ctx.chon.delete(k.id);
      const cb = $('gnt-n-ds').querySelector('[data-chon="' + CSS.escape(String(k.id)) + '"]'); if (cb) cb.checked = v > 0;
      o.setAttribute('aria-invalid', String(v > k.con_lai)); veTong(); anXemTruoc();
    });
    $('gnt-n-ds').addEventListener('blur', (e) => { const o = e.target.closest('[data-so-tra]'); if (o) { const v = soTienNhap(o.value); o.value = v ? KD.tien(v) : ''; } }, true);
    $('gnt-tien').addEventListener('input', () => { veTong(); anXemTruoc(); });
    $('gnt-tien').addEventListener('blur', () => { const v = soTienNhap($('gnt-tien').value); $('gnt-tien').value = v ? KD.tien(v) : ''; });
    $('gnt-du').addEventListener('click', () => { const k = cbKhoan.lay(); if (k) { $('gnt-tien').value = KD.tien(Math.max(0, k.con_lai)); veTong(); } });
    ['gnt-tk', 'gnt-ngay'].forEach((id) => $(id).addEventListener('change', anXemTruoc));
    $('gnt-xem').addEventListener('click', xemTruoc);
    $('gnt-form').addEventListener('submit', (e) => { e.preventDefault(); luu(); });
  }

  function baoLoi(cau) { const p = $('gnt-loi'); p.textContent = cau || ''; p.hidden = !cau; }
  function loiO(id, cau) { const o = $(id), p = $(id + '-loi'); o.setAttribute('aria-invalid', String(!!cau)); if (p) { p.textContent = cau || ''; p.hidden = !cau; } return !cau; }
  function anXemTruoc() { $('gnt-xt').hidden = true; $('gnt-xt').innerHTML = ''; }

  /* ── Một khoản ── */
  function veSo(datTien) {
    const k = cbKhoan.lay();
    $('gnt-so').innerHTML = k ? '<dt>Mã công nợ</dt><dd>' + esc(String(k.id)) + '</dd><dt>Tổng</dt><dd>' + KD.tienVnd(k.so_tien) + '</dd><dt>' + (ctx.thu ? 'Đã thu' : 'Đã trả') + '</dt><dd>' + KD.tienVnd(k.da_tra) + '</dd><dt class="is-dam">Còn lại</dt><dd>' + KD.tienVnd(k.con_lai) + '</dd>' : '';
    if (datTien) $('gnt-tien').value = k && k.con_lai > 0 ? KD.tien(k.con_lai) : '';
    ['gnt-khoan', 'gnt-tien', 'gnt-tk'].forEach((id) => loiO(id, '')); anXemTruoc(); veTong();
  }

  /* ── Nhiều khoản ── */
  function dsLoc() {
    const q = $('gnt-n-tim').value;
    return tatCaKhoan().filter((k) => (!ctx.locDt.size || ctx.locDt.has(k.ten)) && khop(chuoiTimKhoan(k), q));
  }
  function veNhieu() {
    $('gnt-n-chips').innerHTML = [...ctx.locDt].map((t) => '<span class="kd-chip kd-chip--xam">' + esc(t) + '<button type="button" class="kt-gnt-bo" data-bo="' + esc(t) + '" aria-label="Bỏ lọc ' + esc(t) + '"><i class="bi bi-x" aria-hidden="true"></i></button></span>').join('');
    const ds = dsLoc();
    $('gnt-n-ds').innerHTML = ds.length ? ds.map((k) => {
      const v = ctx.chon.get(k.id);
      return '<tr' + (v ? ' class="is-chon"' : '') + '><td class="kt-gnt-cot-chon"><input type="checkbox" data-chon="' + esc(String(k.id)) + '"' + (v ? ' checked' : '') + ' aria-label="Chọn ' + esc(k.ma_don || k.id) + ' của ' + esc(k.ten) + '"></td>'
        + '<td><span class="kt-gnt-ten">' + esc(k.ten) + '</span></td><td>' + esc(k.ma_don || '—') + '<span class="kt-khach__ma">' + esc(k.id) + '</span></td>'
        + '<td class="num">' + KD.tien(k.con_lai) + '</td>'
        + '<td class="num"><input class="kd-input num kt-gnt-so-tra" data-so-tra="' + esc(String(k.id)) + '" inputmode="numeric" value="' + (v ? KD.tien(v) : '') + '" placeholder="' + KD.tien(k.con_lai) + '" aria-label="Số trả khoản ' + esc(k.ma_don || k.id) + '"' + (v > k.con_lai ? ' aria-invalid="true"' : '') + '></td></tr>';
    }).join('') : '<tr><td colspan="5" class="kd-muted kt-gnt-rong">Không có khoản còn nợ nào khớp bộ lọc.</td></tr>';
    const soChon = ds.filter((k) => ctx.chon.has(k.id)).length;
    $('gnt-n-tat-ca').checked = ds.length > 0 && soChon === ds.length; $('gnt-n-tat-ca').indeterminate = soChon > 0 && soChon < ds.length;
    veTong(); anXemTruoc();
  }
  function dongChon() {
    const tat = tatCaKhoan();
    return [...ctx.chon.entries()].map(([id, so]) => ({ k: tat.find((x) => x.id === id), so })).filter((x) => x.k);
  }

  /* Dòng gửi máy chủ theo chế độ hiện tại + kiểm lỗi phía trình duyệt (máy chủ kiểm lại lần nữa). */
  function thuThap() {
    const tk = $('gnt-tk').value;
    let dong = [], ok = true;
    if (cheDo === 'mot') {
      const k = cbKhoan.lay(), v = soTienNhap($('gnt-tien').value);
      ok = [loiO('gnt-khoan', k ? '' : 'Chọn khoản công nợ.'),
        loiO('gnt-tien', !v ? 'Nhập số tiền lớn hơn 0.' : k && v > k.con_lai ? 'Không vượt số còn lại ' + KD.tienVnd(k.con_lai) + '.' : '')].every(Boolean);
      if (k && v) dong = [{ k, so: v }];
    } else {
      dong = dongChon();
      const vuot = dong.filter((x) => x.so > x.k.con_lai);
      const cau = !dong.length ? 'Tick chọn ít nhất một khoản.' : vuot.length ? KD.soDem(vuot.length) + ' khoản có số trả vượt số còn lại.' : '';
      $('gnt-n-loi').textContent = cau; $('gnt-n-loi').hidden = !cau; ok = !cau;
    }
    ok = loiO('gnt-tk', tk ? '' : 'Chọn tài khoản ' + (ctx.thu ? 'nhận' : 'chi') + '.') && ok;
    return ok ? { dong, tk } : null;
  }
  function veTong() {
    if (!ctx) return;
    const dong = cheDo === 'mot' ? (cbKhoan.lay() && soTienNhap($('gnt-tien').value) ? [{ k: cbKhoan.lay(), so: soTienNhap($('gnt-tien').value) }] : []) : dongChon();
    const tong = dong.reduce((a, x) => a + x.so, 0), soDt = new Set(dong.map((x) => x.k.ten)).size;
    $('gnt-tong').innerHTML = '<span>Tổng ' + (ctx.thu ? 'thu' : 'trả') + '</span><b class="num">' + KD.tienVnd(tong) + '</b><span class="kd-muted">' + KD.soDem(dong.length) + ' khoản · ' + KD.soDem(soDt) + ' ' + (ctx.thu ? 'khách hàng' : 'nhà cung cấp') + '</span>';
  }
  const thanBody = (x) => ({ tai_khoan: x.tk, ngay_tra: $('gnt-ngay').value || null, ghi_chu: $('gnt-gc').value.trim() || null, dong: x.dong.map((d) => ({ id: d.k.id, so_tien: d.so })) });
  const loiMayChu = (e) => e.message;

  async function xemTruoc() {
    baoLoi(''); const x = thuThap(); if (!x) return;
    const nut = $('gnt-xem'); nut.disabled = true;
    try {
      const r = await KD.api('/api/cong-no/tra-nhieu?dry_run=true', KD.JSON_POST(thanBody(x)));
      $('gnt-xt').innerHTML = '<h3 class="kd-block__title"><i class="bi bi-eye" aria-hidden="true"></i>Xem trước (chưa ghi)</h3>'
        + '<div class="kd-table-scroll"><table class="kd-table kd-table--gon"><thead><tr><th scope="col">Khoản</th><th scope="col" class="num">' + (ctx.thu ? 'Thu' : 'Trả') + '</th><th scope="col" class="num">' + (ctx.thu ? 'Đã thu' : 'Đã trả') + ' sau</th><th scope="col" class="num">Còn lại sau</th><th scope="col">Sổ quỹ sẽ ghi</th></tr></thead><tbody>'
        + r.dong.map((d) => '<tr><td>' + esc(d.ma_don || d.id) + '<span class="kt-khach__ma">' + esc(d.id) + ' · ' + esc(d.doi_tac) + '</span></td><td class="num">' + KD.tien(d.so_tien_tra) + '</td><td class="num">' + KD.tien(d.da_tra_moi) + '</td>'
          + '<td class="num">' + KD.tien(d.con_lai_moi) + (d.trang_thai_moi === 'da_tra' ? '<span class="kt-khach__ma">Trả đủ</span>' : '') + '</td>'
          + '<td>Phiếu ' + esc(d.so_quy.loai) + ' ' + KD.tien(d.so_quy.so_tien) + '<span class="kt-khach__ma">' + esc(d.so_quy.tai_khoan) + ' · ' + KD.ngay(d.so_quy.ngay) + '</span></td></tr>').join('')
        + '</tbody></table></div><p class="kd-meta">Tổng ' + KD.tienVnd(r.tong) + ' · ' + KD.soDem(r.so_khoan) + ' khoản</p>';
      $('gnt-xt').hidden = false; $('gnt-xt').scrollIntoView({ block: 'nearest' });
    } catch (e) { baoLoi('Không xem trước được: ' + loiMayChu(e)); } finally { nut.disabled = false; }
  }

  async function luu() {
    baoLoi(''); const x = thuThap(); if (!x) return;
    const nut = $('gnt-luu'); nut.disabled = true;
    try {
      if (cheDo === 'mot') {
        const { k, so } = x.dong[0];
        await KD.api('/api/cong-no/' + encodeURIComponent(k.id) + '/tra', KD.JSON_POST({
          da_tra: (Number(k.da_tra) || 0) + so, tai_khoan: x.tk, ngay_tra: $('gnt-ngay').value || null, ghi_chu: $('gnt-gc').value.trim() || null }));
        bao('ok', 'Đã ghi nhận ' + (ctx.thu ? 'thu ' : 'trả ') + KD.tienVnd(so) + ' — ' + (k.ma_don || k.id) + (ctx.thu ? ' vào ' : ' từ ') + x.tk);
      } else {
        const r = await KD.api('/api/cong-no/tra-nhieu', KD.JSON_POST(thanBody(x)));
        bao('ok', 'Đã ghi nhận ' + (ctx.thu ? 'thu ' : 'trả ') + KD.tienVnd(r.tong) + ' cho ' + KD.soDem(r.so_khoan) + ' khoản');
      }
      dlg.close();
      if (ctx.xong) ctx.xong();
    } catch (e) { baoLoi('Chưa ghi nhận được: ' + loiMayChu(e)); } finally { nut.disabled = false; }
  }

  async function napTaiKhoan() {
    if (!dsTk) { const m = await KD.api('/api/meta'); dsTk = (m && (m.tai_khoan_nh || m.ngan_hang)) || []; }
    const cu = $('gnt-tk').value;
    $('gnt-tk').innerHTML = '<option value="">— Chọn tài khoản —</option>' + dsTk.map((t) => {
      const v = t.ten_tk || t.ten || t.label || t.id;
      return '<option value="' + esc(String(v)) + '">' + esc(t.ten_nh ? v + ' (' + t.ten_nh + (t.so_tk ? ' · ' + t.so_tk : '') + ')' : String(v)) + '</option>';
    }).join('');
    $('gnt-tk').value = cu;
  }

  async function mo(o) {
    taoHop(); ctx = Object.assign({}, o, { thu: o.loai === 'phai_thu', locDt: new Set(), chon: new Map() });
    ctx.doiTuong = o.doiTuong.filter((d) => d.khoan.some((k) => k.con_lai > 0));
    if (!ctx.doiTuong.length) { bao('info', 'Không còn khoản nào ' + (ctx.thu ? 'phải thu' : 'phải trả') + ' để ghi nhận'); return; }
    const thu = ctx.thu;
    $('gnt-td').textContent = thu ? 'Ghi nhận thu công nợ' : 'Ghi nhận trả công nợ';
    dlg.querySelector('[data-nhan-dt]').textContent = thu ? 'Khách hàng' : 'Nhà cung cấp';
    dlg.querySelector('[data-nhan-tien]').textContent = thu ? 'Số tiền thu thêm' : 'Số tiền trả thêm';
    dlg.querySelector('[data-nhan-tk]').textContent = thu ? 'Tài khoản nhận' : 'Tài khoản chi';
    dlg.querySelector('[data-nhan-so-tra]').textContent = thu ? 'Số thu' : 'Số trả';
    $('gnt-tip').innerHTML = KD.tip('Ghi nhận xong: công nợ trừ ngay và Sổ quỹ tự ghi 1 phiếu ' + (thu ? 'thu' : 'chi') + ' mỗi khoản'
      + (thu ? '' : ' (chặn nếu tài khoản không đủ số dư)') + '. "Xem trước" chỉ chạy thử, không ghi gì.');
    const dt = ctx.doiTuong.find((d) => d.ten === o.chonDoiTuong) || null;
    cbDt.chon(dt, true);
    const k = o.chonKhoan != null ? tatCaKhoan().find((x) => String(x.id) === String(o.chonKhoan)) : (dt ? tatCaKhoan().find((x) => x.ten === dt.ten) : null);
    cbKhoan.chon(k || null, true); veSo(true);
    if (dt) ctx.locDt.add(dt.ten);
    $('gnt-n-tim').value = ''; veNhieu();
    $('gnt-ngay').value = KD.iso(new Date()); $('gnt-gc').value = ''; baoLoi(''); anXemTruoc();
    const tab = $(o.cheDo === 'nhieu' ? 'gnt-tab-nhieu' : 'gnt-tab-mot'); tab.click();
    KD.moHopThoai(dlg);
    try { await napTaiKhoan(); } catch (e) { baoLoi('Không tải được danh sách tài khoản: ' + e.message); }
    (o.cheDo === 'nhieu' ? $('gnt-n-tim') : (k ? $('gnt-tien') : $('gnt-khoan'))).focus();
  }

  window.KTGhiNhanTra = { mo };
})();
