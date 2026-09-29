/* ═══════════════════════════════════════════════════════════════════════════
   kt-bu-tru.js — Bù trừ công nợ — ĐỢT 2, ghép API THẬT (không có endpoint
   /api/cong-no/bu-tru như README mục 4.7 mô tả — backend không có bảng nào lưu
   mã số thuế (MST) trên hồ sơ khách hàng lẫn nhà cung cấp, nên KHÔNG THỂ ghép
   theo MST như thiết kế gốc).

   Dữ liệu "có thể bù trừ" (tab 1) tự ghép từ 2 API thật, GHÉP THEO TÊN ĐỐI TÁC
   (chuẩn hoá khoảng trắng + chữ thường) thay cho mã số thuế:
     GET /api/cong-no?loai=phai_thu&trang_thai=chua_tra&limit=2000   (khách hàng còn nợ)
     GET /api/cong-no?loai=phai_tra&trang_thai=chua_tra&limit=2000  (nhà cung cấp còn nợ)
   → đối tác nào xuất hiện ở CẢ HAI (cùng tên sau chuẩn hoá) và cả hai vế đều còn dư > 0
     mới vào danh sách "có thể bù trừ". Ghép theo tên có thể sai khi hai bên đặt tên khác
     nhau cho cùng một đối tác, hoặc trùng khi hai đối tác khác nhau trùng tên — CẦN backend
     thêm trường MST thật lên hồ sơ khách/NCC rồi ghép lại theo đúng thiết kế gốc.

   Ghi sổ (tab "Lập bút toán bù trừ") dùng ĐÚNG endpoint tạo bút toán thủ công thật:
     POST /api/journal ← {ngay, mo_ta, source_type:'bu_tru_cong_no', source_id:<tên đối tác>,
                           lines:[{loai:'no',account_code:'331',so_tien}, {loai:'co',account_code:'131',so_tien}]}
   Endpoint này CÓ THẬT và hoạt động — nhưng CHỈ role admin/ceo/assistant_ceo được phép post
   bút toán thủ công (app/routers/journal.py:_ROLES_POST); nút bị khoá sẵn cho role khác qua
   cờ `co_the_lap_but_toan` do router truyền vào template (không chờ bấm rồi ăn 403).
   Máy chủ CHỈ kiểm Nợ=Có và mã TK hợp lệ — KHÔNG tự đối chiếu số tiền với công nợ còn lại
   như thiết kế gốc kỳ vọng ("máy chủ tự kiểm lại số tối đa") — kiểm tra số tối đa Ở ĐÂY là
   phòng tuyến DUY NHẤT, không phải phòng tuyến thứ hai sau máy chủ. Bút toán ghi sổ thành
   công cũng KHÔNG tự cập nhật ketoan.cong_no.da_tra/con_lai (bảng công nợ hiển thị ở màn
   Công nợ KH/NCC) — hai nơi có thể lệch nhau cho tới khi kế toán tất toán thủ công các phiếu
   liên quan ở đó, hoặc backend bổ sung đồng bộ tự động.

   Tab "Đã bù trừ" đọc GET /api/journal?source_type=bu_tru_cong_no (liệt kê đúng các bút toán
   do màn này lập, lọc theo source_type — journal.py đã hỗ trợ sẵn tham số này).
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const trang = $('kd-kt-bu-tru');
  if (!trang) return;
  const COI_QUYEN_LAP = trang.dataset.coQuyen === 'true';

  let d = null; let luot = 0;
  const bao = (loai, cau) => (window.showToast ? window.showToast(loai, cau) : console.info(cau));
  // Tab đang xem ghi lên URL (?tab=da) để F5 / gửi link mở lại đúng tab.
  const tabs = KD.ganTab($('bt-tabs'), (k) => { try { KT.url.ghi({ tab: k }, { tab: 'co' }); } catch (e) { /* khung xem */ } });
  if (KT.url.doc().tab === 'da') tabs.chon('da');

  function chuanHoaTen(s) { return (s || '').trim().toLowerCase().replace(/\s+/g, ' '); }

  /* ── Ghép "có thể bù trừ" từ 2 API công nợ thật, theo TÊN đối tác ── */
  async function ghepDoiTac() {
    const [phaiThu, phaiTra] = await Promise.all([
      KD.api('/api/cong-no?loai=phai_thu&trang_thai=chua_tra&limit=2000'),
      KD.api('/api/cong-no?loai=phai_tra&trang_thai=chua_tra&limit=2000'),
    ]);
    const gom = (rows) => {
      const map = {};
      (rows || []).forEach((r) => {
        const key = chuanHoaTen(r.doi_tac); if (!key) return;
        if (!map[key]) map[key] = { ten: (r.doi_tac || '').trim(), tong: 0 };
        map[key].tong += Number(r.con_lai) || 0;
      });
      return map;
    };
    // Bỏ dòng "thu hộ qua ĐVVC" (saleadmin_vc_phai_thu): trùng phải thu của chính đơn báo giá (vd
    // CN-2026-0057 và CN-2026-0022 cùng đơn NV26010-26-00010) — màn cũ & màn Công nợ KH đều loại.
    const mapThu = gom((phaiThu || []).filter((r) => r.ref_source !== 'saleadmin_vc_phai_thu')), mapTra = gom(phaiTra);
    const doiTac = [];
    Object.keys(mapThu).forEach((key) => {
      const tra = mapTra[key], thu = mapThu[key];
      if (!tra || thu.tong <= 0 || tra.tong <= 0) return;
      doiTac.push({
        mst: key, ten: thu.ten || tra.ten, kh: { id: key, ma: '' }, ncc: { id: key, ma: '' },
        phai_thu: thu.tong, phai_tra: tra.tong,
        co_the_bu_tru: Math.min(thu.tong, tra.tong), sau_bu_tru: thu.tong - tra.tong,
      });
    });
    doiTac.sort((a, b) => b.co_the_bu_tru - a.co_the_bu_tru);
    return doiTac;
  }

  async function ghepDaBuTru() {
    const rows = await KD.api('/api/journal?source_type=' + encodeURIComponent('bu_tru_cong_no') + '&limit=200');
    return (rows || []).map((r) => ({
      id: r.id, ngay: r.ngay, so_ct: r.ma_but_toan, doi_tac: r.source_id || '—',
      dien_giai: r.mo_ta || '', so_tien: Number(r.tong_tien) || 0, nguoi_lap: r.created_by,
    }));
  }

  function choStrip() { trang.querySelectorAll('#bt-strip [data-v]').forEach((el) => { el.innerHTML = '<span class="kd-skel kd-skel--kpi"></span>'; }); trang.querySelectorAll('#bt-strip [data-phu]').forEach((el) => { el.textContent = ''; }); }
  function veStrip(t) {
    const o = (k) => trang.querySelector('#bt-strip [data-kpi="' + k + '"]');
    o('so_doi_tac').querySelector('[data-v]').innerHTML = '<span>' + KD.soDem(t.so_doi_tac) + '</span><span class="kd-kpi__don-vi">đối tác</span>';
    o('so_doi_tac').querySelector('[data-phu]').textContent = 'Vừa mua vừa bán';
    o('co_the_bu_tru').querySelector('[data-v]').innerHTML = KD.tienGonHtml(t.co_the_bu_tru);
    o('co_the_bu_tru').querySelector('[data-phu]').textContent = t.co_the_bu_tru ? 'Giảm cả thu và trả' : 'Chưa có khoản cấn trừ';
    o('da_bu_tru_ky').querySelector('[data-v]').innerHTML = KD.tienGonHtml(t.da_bu_tru_ky);
    o('da_bu_tru_ky').querySelector('[data-phu]').textContent = KD.soDem(t.so_but_toan_ky) + ' bút toán';
  }
  const sau = (x) => x.sau_bu_tru > 0 ? 'Còn phải thu ' + KD.tien(x.sau_bu_tru) : x.sau_bu_tru < 0 ? 'Còn phải trả ' + KD.tien(-x.sau_bu_tru) : 'Hết công nợ hai chiều';
  function veCo() {
    const ds = d.doi_tac, tb = $('bt-tbody-co'), tt = $('bt-tt-co');
    trang.querySelector('[data-dem="co"]').textContent = ds.filter((x) => x.co_the_bu_tru > 0).length;
    if (!ds.length) {
      tb.innerHTML = ''; $('bt-tfoot-co').innerHTML = ''; $('bt-cuon-co').hidden = true;
      tt.innerHTML = KD.khoiRong('Chưa có đối tác hai chiều', 'Chưa đối tác nào còn nợ ở cả hai bên.');
      return;
    }
    $('bt-cuon-co').hidden = false; tt.innerHTML = '';
    tb.innerHTML = ds.map((x) => '<tr data-id="' + esc(x.mst) + '"' + (COI_QUYEN_LAP ? ' tabindex="0"' : '') + '>'
      + '<td><span class="kt-doi-tac__ten">' + esc(x.ten) + '</span></td>'
      + '<td class="num">' + KT.tienSo(x.phai_thu) + '</td><td class="num">' + KT.tienSo(x.phai_tra) + '</td>'
      + '<td class="num kt-so-bt">' + KT.tienSo(x.co_the_bu_tru) + '</td>'
      + '<td>' + (x.co_the_bu_tru ? esc(sau(x)) : '<span class="pill pill--muted">Không bù trừ được</span>') + '</td>'
      + '<td class="kd-col-act"><button type="button" class="kd-icon-btn" data-menu="' + esc(x.mst) + '" aria-haspopup="menu" aria-expanded="false" aria-label="Thao tác với ' + esc(x.ten) + '"><i class="bi bi-three-dots" aria-hidden="true"></i></button></td></tr>').join('');
    const tg = ds.reduce((a, x) => ({ thu: a.thu + x.phai_thu, tra: a.tra + x.phai_tra, bt: a.bt + x.co_the_bu_tru }), { thu: 0, tra: 0, bt: 0 });
    $('bt-tfoot-co').innerHTML = '<tr><th scope="row">Cộng (' + KD.soDem(ds.length) + ' đối tác)</th><td class="num">' + KD.tien(tg.thu) + '</td><td class="num">' + KD.tien(tg.tra) + '</td><td class="num">' + KD.tien(tg.bt) + '</td><td></td><td class="kd-col-act"></td></tr>';
  }
  function veDa() {
    const ds = d.da_bu_tru, tb = $('bt-tbody-da'), tt = $('bt-tt-da');
    trang.querySelector('[data-dem="da"]').textContent = ds.length;
    if (!ds.length) { tb.innerHTML = ''; $('bt-cuon-da').hidden = true; tt.innerHTML = KD.khoiRong('Chưa lập bút toán bù trừ nào', ''); return; }
    $('bt-cuon-da').hidden = false; tt.innerHTML = '';
    tb.innerHTML = ds.map((x) => '<tr><td>' + KD.ngay(x.ngay) + '</td>'
      // Link lọc đúng NGÀY của bút toán (trước: ky=nam_nay → bút toán năm trước không hiện trên Sổ kế toán).
      + '<td>' + KT.linkCt(x.so_ct, x.ngay) + '</td>'
      + '<td>' + esc(x.doi_tac) + '</td><td><span class="kt-cat" title="' + esc(x.dien_giai) + '">' + esc(x.dien_giai) + '</span></td>'
      + '<td class="num">' + KD.tien(x.so_tien) + '</td><td>' + esc(x.nguoi_lap || '—') + '</td></tr>').join('');
  }

  async function tai() {
    const l = ++luot; choStrip();
    $('bt-cuon-co').hidden = false; $('bt-tt-co').innerHTML = ''; $('bt-tbody-co').innerHTML = KT.hangCho(6, 4); $('bt-tfoot-co').innerHTML = '';
    $('bt-cuon-da').hidden = false; $('bt-tt-da').innerHTML = ''; $('bt-tbody-da').innerHTML = KT.hangCho(6, 4);
    try {
      const [doiTac, daBuTru] = await Promise.all([ghepDoiTac(), ghepDaBuTru()]);
      if (l !== luot) return;
      const denNgay = KD.iso(new Date());
      const thangNay = denNgay.slice(0, 7);
      const daBuTruKy = daBuTru.filter((x) => (x.ngay || '').slice(0, 7) === thangNay).reduce((a, x) => a + x.so_tien, 0);
      d = {
        den_ngay: denNgay, doi_tac: doiTac, da_bu_tru: daBuTru,
        tong: { so_doi_tac: doiTac.length, co_the_bu_tru: doiTac.reduce((a, x) => a + x.co_the_bu_tru, 0), da_bu_tru_ky: daBuTruKy, so_but_toan_ky: daBuTru.filter((x) => (x.ngay || '').slice(0, 7) === thangNay).length },
      };
      veStrip(d.tong); veCo(); veDa();
      $('bt-pham-vi').textContent = 'Số liệu đến ' + KD.ngay(d.den_ngay);
    } catch (e) {
      if (l !== luot) return;
      trang.querySelectorAll('#bt-strip [data-v]').forEach((el) => { el.innerHTML = '<span class="kd-muted">—</span>'; });
      $('bt-cuon-co').hidden = true; $('bt-cuon-da').hidden = true;
      KD.khoiLoi($('bt-tt-co'), 'Không tải được công nợ hai chiều', e, tai);
      KD.khoiLoi($('bt-tt-da'), 'Không tải được bút toán bù trừ', e, tai);
    }
  }

  /* ── Hộp lập bù trừ ── */
  const dlg = $('bt-dlg'), f = { dt: $('bt-f-dt'), tien: $('bt-f-tien'), ngay: $('bt-f-ngay'), dg: $('bt-f-dg'), bb: $('bt-f-bb') };
  const soTien = () => Math.round(Number(String(f.tien.value).replace(/[^\d]/g, '')) || 0);
  const chon = () => d && d.doi_tac.find((x) => x.mst === f.dt.value);
  function loiO(o, cau) { const p = $(o.id + '-loi'); o.setAttribute('aria-invalid', String(!!cau)); if (p) { p.textContent = cau || ''; p.hidden = !cau; } return !cau; }
  function veDk() {
    const x = chon(); const v = soTien();
    $('bt-f-so').innerHTML = x ? '<dt>Phải thu (TK 131)</dt><dd>' + KD.tienVnd(x.phai_thu) + '</dd><dt>Phải trả (TK 331)</dt><dd>' + KD.tienVnd(x.phai_tra) + '</dd><dt class="is-dam">Tối đa được bù trừ</dt><dd>' + KD.tienVnd(x.co_the_bu_tru) + '</dd>' : '';
    $('bt-f-dk').innerHTML = x ? '<tr><td><span class="kt-tk">331</span><span class="kt-dk__phu">Phải trả người bán · ' + esc(x.ten) + '</span></td><td class="num">' + KT.tienSo(v) + '</td><td class="num">' + KT.tienSo(0) + '</td></tr>'
      + '<tr><td><span class="kt-tk">131</span><span class="kt-dk__phu">Phải thu khách hàng · ' + esc(x.ten) + '</span></td><td class="num">' + KT.tienSo(0) + '</td><td class="num">' + KT.tienSo(v) + '</td></tr>'
      : '<tr><td colspan="3" class="kd-muted">Chọn đối tác để xem định khoản.</td></tr>';
  }
  function kiemTien() {
    const x = chon(), v = soTien();
    if (!x) return loiO(f.dt, 'Chọn đối tác cần bù trừ.');
    loiO(f.dt, '');
    if (!v) return loiO(f.tien, 'Nhập số tiền bù trừ lớn hơn 0.');
    // Máy chủ POST /api/journal KHÔNG tự đối chiếu số này với công nợ còn lại — đây là phòng
    // tuyến DUY NHẤT chặn bù trừ vượt mức (xem ghi chú đầu file).
    if (v > x.co_the_bu_tru) return loiO(f.tien, 'Tối đa ' + KD.tienVnd(x.co_the_bu_tru) + ' — không bù trừ quá số nhỏ hơn giữa phải thu và phải trả.');
    return loiO(f.tien, '');
  }
  function kiemNgay() { const v = f.ngay.value; if (!v) return loiO(f.ngay, 'Chọn ngày hạch toán.'); if (v > KD.iso(new Date())) return loiO(f.ngay, 'Ngày hạch toán không được sau hôm nay.'); return loiO(f.ngay, ''); }
  function kiemBb() { return loiO(f.bb, f.bb.checked ? '' : 'Cần biên bản bù trừ có xác nhận của hai bên trước khi ghi sổ — tick ô này khi đã có.'); }
  f.dt.addEventListener('change', () => { const x = chon(); if (x) f.tien.value = KD.tien(x.co_the_bu_tru); loiO(f.tien, ''); veDk(); });
  f.tien.addEventListener('input', veDk);
  f.tien.addEventListener('blur', () => { if (soTien()) f.tien.value = KD.tien(soTien()); kiemTien(); });
  f.ngay.addEventListener('blur', kiemNgay); f.bb.addEventListener('change', kiemBb);
  $('bt-f-toi-da').addEventListener('click', () => { const x = chon(); if (x) { f.tien.value = KD.tien(x.co_the_bu_tru); loiO(f.tien, ''); veDk(); } });

  function moHop(mst) {
    if (!COI_QUYEN_LAP) { bao('err', 'Chỉ CEO/Admin được lập bút toán bù trừ (bút toán thủ công) — liên hệ CEO nếu cần ghi sổ khoản này.'); return; }
    if (!d) return;
    const dsCo = d.doi_tac.filter((x) => x.co_the_bu_tru > 0);
    if (!dsCo.length) { bao('info', 'Không có đối tác nào còn cả phải thu và phải trả để bù trừ'); return; }
    f.dt.innerHTML = '<option value="">Chọn đối tác…</option>' + dsCo.map((x) => '<option value="' + esc(x.mst) + '">' + esc(x.ten + ' — tối đa ' + KD.tienVnd(x.co_the_bu_tru)) + '</option>').join('');
    f.dt.value = mst && dsCo.some((x) => x.mst === mst) ? mst : '';
    const x = chon(); f.tien.value = x ? KD.tien(x.co_the_bu_tru) : '';
    f.ngay.value = KD.iso(new Date()); f.dg.value = ''; f.bb.checked = false;
    [f.dt, f.tien, f.ngay, f.bb].forEach((o) => loiO(o, ''));
    veDk(); KD.moHopThoai(dlg); (x ? f.tien : f.dt).focus();
  }
  $('bt-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!COI_QUYEN_LAP) { KD.baoLoiHopThoai(dlg, 'Chỉ CEO/Admin được lập bút toán bù trừ.'); return; }
    const ok = [kiemTien(), kiemNgay(), kiemBb()];
    if (ok.includes(false)) { const o = [f.dt.getAttribute('aria-invalid') === 'true' ? f.dt : f.tien, f.ngay, f.bb][ok.indexOf(false)]; o.focus(); return; }
    const x = chon(); const nut = $('bt-f-luu'); nut.disabled = true;
    const soTienBt = soTien();
    try {
      const je = await KD.api('/api/journal', KD.JSON_POST({
        ngay: f.ngay.value,
        mo_ta: (f.dg.value.trim() || 'Bù trừ công nợ') + ' — ' + x.ten,
        source_type: 'bu_tru_cong_no',
        source_id: String(x.ten).slice(0, 64), // JournalEntryIn.source_id max_length=64
        lines: [
          { loai: 'no', account_code: '331', account_name: 'Phải trả người bán', so_tien: soTienBt, ghi_chu: x.ten },
          { loai: 'co', account_code: '131', account_name: 'Phải thu khách hàng', so_tien: soTienBt, ghi_chu: x.ten },
        ],
      }));
      dlg.close(); bao('ok', 'Đã ghi sổ bù trừ ' + je.ma_but_toan + ' — ' + KD.tienVnd(je.tong_tien) + ' với ' + x.ten
        + '. Lưu ý: số liệu ở màn Công nợ KH/NCC không tự giảm theo — tất toán các phiếu liên quan riêng nếu cần khớp hai nơi.');
      await tai(); tabs.chon('da');
    } catch (err) {
      KD.baoLoiHopThoai(dlg, 'Chưa ghi sổ được: ' + err.message + ' Dữ liệu vẫn còn trong hộp.');
    } finally { nut.disabled = false; }
  });

  /* ── Sự kiện bảng ── */
  $('bt-tbody-co').addEventListener('click', (e) => {
    const m = e.target.closest('[data-menu]'); if (!m) return;
    const x = d.doi_tac.find((y) => y.mst === m.dataset.menu); if (!x) return;
    KD.menu(m, [
      ...(COI_QUYEN_LAP ? [{ nhan: 'Lập bút toán bù trừ', icon: 'bi-arrow-left-right', onClick: () => moHop(x.mst) }, '-'] : []),
      { nhan: 'Xem công nợ khách hàng', icon: 'bi-person', href: '/ketoan/cong-no-kh?tim=' + encodeURIComponent(x.ten) + '&tinh_trang=tat_ca' },
      { nhan: 'Xem công nợ nhà cung cấp', icon: 'bi-truck', href: '/ketoan/cong-no-ncc?tim=' + encodeURIComponent(x.ten) + '&tinh_trang=tat_ca' },
    ]);
  });
  // Không có quyền lập (F3): nút "Lập bút toán bù trừ" không được vẽ (template) và bấm dòng không mở hộp lập — chỉ xem.
  if (COI_QUYEN_LAP) {
    KT.ganDongBang($('bt-tbody-co'), (tr) => moHop(tr.dataset.id));
    $('bt-lap').addEventListener('click', () => moHop(''));
  }
  tai();
})();
