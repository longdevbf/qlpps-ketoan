/* ═══════════════════════════════════════════════════════════════════════════
   kt-tai-khoan.js — Danh mục tài khoản (CRUD) — ĐỢT 2, ghép API THẬT.

   ĐỌC (thật):  GET /api/journal/can-doi-phat-sinh → mã, tên, tính chất, số dòng đã phát sinh, cấp
                (cap 1|2 + tk_cha — 28/09/2026: TK con của tài khoản tiền, tên = tên tài khoản tiền)
                (xem chuyenDoi()). Không có màn tương ứng ở giao diện cũ. Backend không có bảng "danh mục tài khoản" đầy đủ (đối
                tượng theo dõi, trạng thái, ghi chú) nên các trường đó được đặt mặc định ở dưới
                (xem `chuyenDoi()`) — KHÔNG bịa số liệu, chỉ hiện "—" ở cột không có dữ liệu thật.
                Mã TK con đặt ở màn tài khoản tiền (PUT /api/tai-khoan), không sửa ở đây.
   GHI (ĐỀ XUẤT, CHƯA có backend): POST /api/danh-muc-tai-khoan · PUT/DELETE
                /api/danh-muc-tai-khoan/<ma>. Cố tình KHÔNG dùng /api/tai-khoan — path đó
                trong app này là API tài khoản NGÂN HÀNG/tiền mặt thật (tai_khoan_nh.py).
                Các nút Thêm/Sửa/Xoá/Ngừng dùng vẫn hoạt động đầy đủ ở giao diện (kiểm tra ô
                nhập, hộp thoại, hỏi lại khi xoá…) nhưng lệnh lưu thật sự sẽ BÁO LỖI (thay vì
                giả vờ thành công) cho tới khi backend bổ sung bảng dữ liệu này — xem báo cáo
                bàn giao của phiên dựng màn "Danh mục tài khoản" (đợt 2).
   Lọc (loại, trạng thái, tính chất, tìm) làm ở trình duyệt — danh mục chỉ vài chục dòng.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const trang = $('kd-kt-tai-khoan');
  if (!trang) return;

  // Đường dẫn GHI đề xuất — CHƯA tồn tại ở backend thật, xem docstring đầu file.
  const API_GHI = '/api/danh-muc-tai-khoan';
  // 28/09/2026: API_GHI chưa có backend (404 với mọi vai trò) → màn chỉ xem; bật lại khi đã làm backend.
  const CHO_PHEP_GHI = false;
  if (!CHO_PHEP_GHI) { const nut = document.getElementById('tk-them'); if (nut) nut.hidden = true; }

  const TINH_CHAT = { no: 'Dư Nợ', co: 'Dư Có', luong_tinh: 'Lưỡng tính' };
  const DOI_TUONG = { kh: 'Khách hàng', ncc: 'Nhà cung cấp', nv: 'Nhân viên' };
  const MAC_DINH = { loai: '', tt: 'dang_dung', tc: '', tim: '' };
  const st = Object.assign({}, MAC_DINH, KT.url.doc());
  let ds = []; let luot = 0; let vuaLuu = '';
  const bao = (loai, cau) => (window.showToast ? window.showToast(loai, cau) : console.info(cau));

  /* Danh mục: GET /api/journal/can-doi-phat-sinh (đến hôm nay) — trả đủ mã, tên, TÍNH CHẤT
     (chiều dư tự nhiên theo services/journal.py) và số dòng định khoản đã có (so_dong) → cột
     "Tính chất" và "Đã phát sinh" có số thật (QA 25/09/2026; bản trước chỉ gọi /accounts nên hai
     cột này luôn "—"). Loại (1-9) suy từ chữ số đầu của mã (quy ước TT200). Cấp + TK cha lấy từ
     cap/tk_cha của API; máy chủ trả theo thứ tự mã (chuỗi) nên TK con đứng ngay sau TK cha. Số "đã
     phát sinh" của TK cha đã gồm dòng của TK con. Đối tượng theo dõi, trạng thái ngừng dùng, ghi chú:
     backend chưa có → để trống/mặc định. */
  function chuyenDoi(rows) {
    const soCon = {}; rows.forEach((r) => { if (r.cap === 2 && r.tk_cha) soCon[r.tk_cha] = (soCon[r.tk_cha] || 0) + 1; });
    const tenCha = {}; rows.forEach((r) => { tenCha[r.ma] = r.ten; });
    return rows.map((r) => ({
      ma: r.ma, ten: r.ten, cap: r.cap === 2 ? 2 : 1, cha: r.cap === 2 ? r.tk_cha : null,
      ten_cha: r.cap === 2 ? tenCha[r.tk_cha] || '' : '',
      loai: String(r.ma).charAt(0),
      tinh_chat: r.tinh_chat || null, doi_tuong: null,
      dang_dung: true,          // backend không có cờ ngừng dùng
      ghi_chu: '', co_phat_sinh: (r.so_dong || 0) > 0, so_dong: r.so_dong || 0, so_tk_con: soCon[r.ma] || 0,
    }));
  }
  // Dòng phụ dưới tên: TK con ghi TK cha; TK cha ghi số TK con (TK con là tài khoản tiền cùng tên).
  function dongPhu(t) {
    if (t.cap === 2) return '<span class="kt-dk__phu">TK con của ' + esc(t.cha) + (t.ten_cha ? ' — ' + esc(t.ten_cha) : '') + '</span>';
    return t.so_tk_con ? '<span class="kt-dk__phu">Gồm ' + KD.soDem(t.so_tk_con) + ' TK con</span>' : '';
  }

  // "Tất cả" trạng thái = 'tat_ca' (trước là '' → KT.url.ghi bỏ giá trị rỗng nên F5 quay về "Đang dùng").
  // Giá trị URL lạ (vd tt= của link cũ) → về đúng giá trị ô đang hiện.
  [['tk-tt', 'tt'], ['tk-tc', 'tc']].forEach(([id, k]) => { const el = $(id); el.value = st[k]; if (el.value !== st[k]) { st[k] = st[k] === '' && k === 'tt' ? 'tat_ca' : MAC_DINH[k]; el.value = st[k]; } });
  $('tk-tim').value = st.tim;
  // Tab ở đây là BỘ LỌC của cùng một bảng (mọi tab điều khiển chung vùng #tk-bang-vung) → tự nối, không dùng KD.ganTab
  // (ganTab ẩn tabpanel của tab không chọn — với vùng dùng chung sẽ ẩn luôn bảng).
  const tabs = [...$('tk-loai').querySelectorAll('[role="tab"]')];
  const vung = $('tk-bang-vung');
  const tab = { chon(k, focus) {
    tabs.forEach((t) => { const on = t.dataset.loai === k; t.setAttribute('aria-selected', String(on)); t.tabIndex = on ? 0 : -1; if (on && focus) t.focus(); });
    if (st.loai !== k) { st.loai = k; ve(); }
  } };
  tabs.forEach((t, i) => {
    t.addEventListener('click', () => tab.chon(t.dataset.loai));
    t.addEventListener('keydown', (e) => { if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return; e.preventDefault();
      tab.chon(tabs[(i + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length].dataset.loai, true); });
  });
  if (!tabs.some((t) => t.dataset.loai === st.loai)) st.loai = '';
  tabs.forEach((t) => { const on = t.dataset.loai === st.loai; t.setAttribute('aria-selected', String(on)); t.tabIndex = on ? 0 : -1; });

  /* ── Vẽ bảng (lọc ở trình duyệt) ── */
  // Mọi điều kiện TRỪ loại (tab) — dùng cho cả bảng lẫn số đếm trên từng tab.
  function khopLoc(t) {
    return (st.tt === 'tat_ca' || !st.tt || (st.tt === 'dang_dung' ? t.dang_dung : !t.dang_dung))
      && (!st.tc || t.tinh_chat === st.tc)
      && KT.khopTim([t.ma, t.ten], st.tim);
  }
  function locDs() { return ds.filter((t) => (!st.loai || String(t.loai) === st.loai) && khopLoc(t)); }
  function ve() {
    KT.url.ghi(st, MAC_DINH);
    // Số trên tab = số dòng sẽ hiện khi bấm tab đó (theo trạng thái + tính chất + ô tìm hiện tại).
    const dem = {}; ds.forEach((t) => { if (khopLoc(t)) { dem[t.loai] = (dem[t.loai] || 0) + 1; dem[''] = (dem[''] || 0) + 1; } });
    $('tk-loai').querySelectorAll('[data-dem]').forEach((s) => { s.textContent = dem[s.dataset.dem] || 0; });
    const hien = locDs(); const tb = $('tk-tbody');
    if (!hien.length) {
      tb.innerHTML = ''; vung.hidden = true; $('tk-foot').hidden = true;
      const coLoc = st.tim || st.tc || st.loai || st.tt !== MAC_DINH.tt;
      $('tk-tt-khoi').innerHTML = coLoc
        ? KD.khoiRong('Không có tài khoản nào khớp bộ lọc', 'Thử bỏ bớt điều kiện hoặc chọn tab "Tất cả".') + '<p class="kt-giua"><button type="button" class="kd-btn kd-btn--sm" data-dat-lai>Đặt lại bộ lọc</button></p>'
        : KD.khoiRong('Danh mục tài khoản đang trống', 'Bấm "Thêm tài khoản" để tạo tài khoản cấp 1 đầu tiên theo Thông tư 99/2025/TT-BTC.');
      const b = $('tk-tt-khoi').querySelector('[data-dat-lai]'); if (b) b.addEventListener('click', datLai);
      return;
    }
    $('tk-tt-khoi').innerHTML = ''; vung.hidden = false; $('tk-foot').hidden = false;
    const gach = '<span class="kd-muted">—</span>';
    tb.innerHTML = hien.map((t) => '<tr data-id="' + esc(t.ma) + '" tabindex="0" class="kt-cap' + t.cap + (t.dang_dung ? '' : ' is-ngung') + (t.ma === vuaLuu ? ' kt-vua-luu' : '') + '">'
      // Thụt lề bằng span (padding của .kd-table td lấn class trên td nên đặt ở td không thụt được).
      + '<td><span class="kt-ma-tk' + (t.cap === 2 ? ' kt-cap-2' : '') + '">' + esc(t.ma) + '</span></td>'
      // Đợt 4: bỏ cột "Theo dõi chi tiết" (dữ liệu thật luôn trống) — nếu có thì hiện thẻ ngay dưới tên.
      + '<td>' + esc(t.ten) + (t.doi_tuong ? ' <span class="kd-chip kd-chip--xam">' + esc(DOI_TUONG[t.doi_tuong] || 'Chưa đặt tên') + '</span>' : '') + dongPhu(t) + (t.ghi_chu ? '<span class="kt-dk__phu">' + esc(t.ghi_chu) + '</span>' : '') + '</td>'
      + '<td>' + (t.tinh_chat ? esc(TINH_CHAT[t.tinh_chat] || 'Chưa đặt tên') : gach) + '</td>'
      + '<td>' + (t.co_phat_sinh ? 'Đã có · ' + KD.soDem(t.so_dong) + ' dòng' : '<span class="kd-muted">Chưa</span>') + '</td>'
      + '<td>' + (t.dang_dung ? '<span class="pill pill--success">Đang dùng</span>' : '<span class="pill pill--muted">Ngừng dùng</span>') + '</td>'
      + '<td class="kd-col-act"><button type="button" class="kd-icon-btn" data-menu="' + esc(t.ma) + '" aria-haspopup="menu" aria-expanded="false" aria-label="Thao tác với tài khoản ' + esc(t.ma) + '"><i class="bi bi-three-dots" aria-hidden="true"></i></button></td></tr>').join('');
    // Mỗi dòng là một tài khoản riêng (TK con không lặp số của cha trong danh mục) — nêu rõ bao nhiêu dòng là TK con.
    const soCon = hien.filter((t) => t.cap === 2).length;
    $('tk-hien-thi').textContent = 'Hiển thị ' + KD.soDem(hien.length) + ' / ' + KD.soDem(ds.length) + ' tài khoản'
      + (soCon ? ' (' + KD.soDem(hien.length - soCon) + ' cấp 1 · ' + KD.soDem(soCon) + ' TK con)' : '');
    vuaLuu = '';
  }

  async function tai() {
    const l = ++luot;
    vung.hidden = false; $('tk-tt-khoi').innerHTML = ''; $('tk-foot').hidden = true;
    $('tk-tbody').innerHTML = KT.hangCho(6, 10);
    try {
      const homNay = KD.iso(new Date());
      const d = await KD.api('/api/journal/can-doi-phat-sinh?' + KT.url.qs({ tu_ngay: homNay, den_ngay: homNay }));
      if (l !== luot) return;
      ds = chuyenDoi(d.tai_khoan || []); ve();
    } catch (e) {
      if (l !== luot) return;
      vung.hidden = true; KD.khoiLoi($('tk-tt-khoi'), 'Không tải được danh mục tài khoản', e, tai);
    }
  }

  /* ── Hộp thêm / sửa ── */
  const dlg = $('tk-dlg'), f = { cha: $('tk-f-cha'), ma: $('tk-f-ma'), ten: $('tk-f-ten'), tc: $('tk-f-tc'), dt: $('tk-f-dt'), gc: $('tk-f-gc') };
  let dangSua = null;
  function loiO(o, cau) {
    const p = $(o.id + '-loi'); o.setAttribute('aria-invalid', String(!!cau)); if (p) { p.textContent = cau || ''; p.hidden = !cau; }
    return !cau;
  }
  function kiemMa() {
    const v = f.ma.value.trim(), cha = f.cha.value;
    if (dangSua) return true;
    if (!v) return loiO(f.ma, 'Nhập số hiệu tài khoản — đây là ô bắt buộc.');
    if (!/^\d{3,6}$/.test(v)) return loiO(f.ma, 'Số hiệu chỉ gồm 3–6 chữ số (đang có "' + v + '").');
    if (cha && (v.indexOf(cha) !== 0 || v.length === cha.length)) return loiO(f.ma, 'Tài khoản chi tiết của ' + cha + ' phải bắt đầu bằng ' + cha + ' và dài hơn (VD: ' + cha + '1).');
    if (!cha && v.length !== 3) return loiO(f.ma, 'Tài khoản cấp 1 có đúng 3 chữ số — muốn tạo tài khoản chi tiết thì chọn "Tài khoản cấp trên".');
    if (ds.some((t) => t.ma === v)) return loiO(f.ma, 'Số hiệu ' + v + ' đã có trong danh mục — chọn số hiệu khác.');
    return loiO(f.ma, '');
  }
  function kiemTen() { return loiO(f.ten, f.ten.value.trim() ? '' : 'Nhập tên tài khoản — đây là ô bắt buộc.'); }
  f.ma.addEventListener('blur', kiemMa); f.ten.addEventListener('blur', kiemTen);
  f.cha.addEventListener('change', () => {
    const cha = ds.find((t) => t.ma === f.cha.value);
    if (cha) { if (!f.ma.value || f.ma.value.indexOf(cha.ma) !== 0) f.ma.value = cha.ma; f.tc.value = cha.tinh_chat || 'no'; f.dt.value = cha.doi_tuong || ''; }
    $('tk-f-meo').hidden = !cha;
    $('tk-f-meo').textContent = cha ? 'Tài khoản mới là chi tiết của ' + cha.ma + ' — ' + cha.ten + '. Tính chất và đối tượng lấy theo tài khoản cấp trên, sửa được.' : '';
    f.ma.focus();
  });

  function moHop(t, chaMa) {
    dangSua = t || null;
    f.cha.innerHTML = '<option value="">Không — tài khoản cấp 1</option>' + ds.filter((x) => x.cap === 1).map((x) => '<option value="' + esc(x.ma) + '">' + esc(x.ma + ' — ' + x.ten) + '</option>').join('');
    [f.ma, f.ten].forEach((o) => loiO(o, ''));
    $('tk-dlg-td').textContent = t ? 'Sửa tài khoản ' + t.ma : 'Thêm tài khoản';
    $('tk-f-luu').lastChild.textContent = t ? 'Lưu thay đổi' : 'Thêm tài khoản';
    f.cha.value = t ? t.cha || '' : chaMa || ''; f.cha.disabled = !!t;
    f.ma.value = t ? t.ma : chaMa || ''; f.ma.disabled = !!t;
    f.ten.value = t ? t.ten : ''; f.tc.value = t ? t.tinh_chat || 'no' : 'no'; f.dt.value = t ? t.doi_tuong || '' : ''; f.gc.value = t ? t.ghi_chu || '' : '';
    if (!t && chaMa) f.cha.dispatchEvent(new Event('change')); else $('tk-f-meo').hidden = true;
    if (t && t.co_phat_sinh) { $('tk-f-meo').hidden = false; $('tk-f-meo').textContent = 'Tài khoản đã có bút toán nên không đổi được số hiệu. Đổi tên không ảnh hưởng số liệu đã ghi.'; }
    KD.moHopThoai(dlg);
    (t ? f.ten : chaMa ? f.ma : f.cha).focus();
  }
  $('tk-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const ok = [kiemMa(), kiemTen()]; const dau = [f.ma, f.ten][ok.indexOf(false)];
    if (dau) { dau.focus(); return; }
    const nut = $('tk-f-luu'); nut.disabled = true;
    const body = { ten: f.ten.value.trim(), tinh_chat: f.tc.value, doi_tuong: f.dt.value, ghi_chu: f.gc.value.trim() };
    try {
      if (dangSua) {
        const cu = dangSua; const doi = body.ten !== cu.ten || body.tinh_chat !== cu.tinh_chat || body.doi_tuong !== (cu.doi_tuong || '') || body.ghi_chu !== (cu.ghi_chu || '');
        if (!doi) { dlg.close(); bao('info', 'Tài khoản ' + cu.ma + ' không thay đổi'); return; }
        await KD.api(API_GHI + '/' + encodeURIComponent(cu.ma), Object.assign(KD.JSON_POST(body), { method: 'PUT' }));
        vuaLuu = cu.ma; dlg.close(); bao('ok', 'Đã lưu tài khoản ' + cu.ma);
      } else {
        body.ma = f.ma.value.trim();
        await KD.api(API_GHI, KD.JSON_POST(body));
        vuaLuu = body.ma; dlg.close(); bao('ok', 'Đã thêm tài khoản ' + body.ma + ' — ' + body.ten);
      }
      await tai();
    } catch (err) {
      KD.baoLoiHopThoai(dlg, 'Chưa lưu được: ' + err.message + ' Dữ liệu vẫn còn trong hộp. (Hệ thống chưa lưu được danh mục tài khoản.)');
    } finally { nut.disabled = false; }
  });

  /* ── Ngừng dùng / dùng lại ── */
  async function doiTrangThai(t) {
    try {
      await KD.api(API_GHI + '/' + encodeURIComponent(t.ma), Object.assign(KD.JSON_POST({ dang_dung: !t.dang_dung }), { method: 'PUT' }));
      bao('ok', (t.dang_dung ? 'Đã ngừng dùng tài khoản ' : 'Đã dùng lại tài khoản ') + t.ma + (t.dang_dung ? ' — không chọn được khi lập chứng từ mới' : ''));
      vuaLuu = t.ma; await tai();
    } catch (err) { bao('err', 'Chưa đổi được trạng thái ' + t.ma + ': ' + err.message); }
  }

  /* ── Xoá (hỏi lại) ── */
  const dlgXoa = $('tk-dlg-xoa'); let xoaTk = null;
  function hoiXoa(t) {
    xoaTk = t;
    $('tk-xoa-td').textContent = 'Xoá tài khoản ' + t.ma + '?';
    $('tk-xoa-nd').textContent = t.ma + ' — ' + t.ten + ' sẽ bị xoá khỏi danh mục. Không hoàn tác được. '
      + (t.co_phat_sinh ? 'Tài khoản này ĐÃ có bút toán hoặc số dư nên máy chủ sẽ từ chối — hãy dùng "Ngừng sử dụng".' : 'Chỉ xoá được tài khoản chưa có bút toán, số dư và tài khoản con.');
    KD.moHopThoai(dlgXoa); $('tk-xoa-ok').focus();
  }
  $('tk-xoa-ok').addEventListener('click', async () => {
    const t = xoaTk; if (!t) return; const nut = $('tk-xoa-ok'); nut.disabled = true;
    try { await KD.api(API_GHI + '/' + encodeURIComponent(t.ma), { method: 'DELETE', headers: { Accept: 'application/json' } });
      dlgXoa.close(); bao('ok', 'Đã xoá tài khoản ' + t.ma); await tai(); }
    catch (err) { KD.baoLoiHopThoai(dlgXoa, err.message + ' (Hệ thống chưa lưu được danh mục tài khoản.)'); }
    finally { nut.disabled = false; }
  });

  /* ── Sự kiện bảng ── */
  const timTk = (ma) => ds.find((t) => t.ma === ma);
  $('tk-tbody').addEventListener('click', (e) => {
    const m = e.target.closest('[data-menu]'); if (!m) return;
    const t = timTk(m.dataset.menu); if (!t) return;
    const soCai = { nhan: 'Xem sổ cái', icon: 'bi-journal-text', href: '/ketoan/so-cai?tk=' + encodeURIComponent(t.ma) + '&ky=nam_nay' };
    if (!CHO_PHEP_GHI) { KD.menu(m, [soCai]); return; }
    const muc = [{ nhan: 'Sửa tài khoản', icon: 'bi-pencil', onClick: () => moHop(t) }];
    if (t.cap === 1) muc.push({ nhan: 'Thêm tài khoản chi tiết', icon: 'bi-plus-lg', onClick: () => moHop(null, t.ma) });
    muc.push(soCai);
    muc.push({ nhan: t.dang_dung ? 'Ngừng sử dụng' : 'Dùng lại', icon: t.dang_dung ? 'bi-pause-circle' : 'bi-play-circle', onClick: () => doiTrangThai(t) });
    muc.push('-', { nhan: 'Xoá tài khoản', icon: 'bi-trash', danger: true, onClick: () => hoiXoa(t) });
    KD.menu(m, muc);
  });
  KT.ganDongBang($('tk-tbody'), (tr) => {
    const t = timTk(tr.dataset.id); if (!t) return;
    if (CHO_PHEP_GHI) moHop(t); else location.href = '/ketoan/so-cai?tk=' + encodeURIComponent(t.ma) + '&ky=nam_nay';
  });

  function datLai() { Object.assign(st, MAC_DINH); $('tk-tim').value = ''; $('tk-tt').value = 'dang_dung'; $('tk-tc').value = ''; tab.chon(''); ve(); }
  $('tk-them').addEventListener('click', () => moHop(null));
  $('tk-tim').addEventListener('input', KD.debounce(() => { st.tim = $('tk-tim').value.trim(); ve(); }, 200));
  $('tk-tt').addEventListener('change', (e) => { st.tt = e.target.value; ve(); });
  $('tk-tc').addEventListener('change', (e) => { st.tc = e.target.value; ve(); });
  $('tk-dat-lai').addEventListener('click', datLai);
  $('tk-loc').addEventListener('submit', (e) => e.preventDefault());
  tai();
})();
