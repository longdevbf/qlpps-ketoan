/* kt-so-quy.js (dot3b) — Sổ quỹ tiền mặt, nối API THẬT của app ketoan.
   ─────────────────────────────────────────────────────────────────────────
   GAP THẬT so với bản thiết kế / README mục 4.11 (ghi rõ để không ai tưởng nhầm là số giả):
   - KHÔNG có endpoint `/api/so-quy` kiểu tổng hợp sẵn (tồn đầu/cuối, tồn luỹ kế mỗi dòng,
     số phiếu thu/chi tách cột, phân trang server). API thật chỉ có:
       GET /api/so-quy?tu_ngay&den_ngay&loai&tai_khoan&limit&offset  → MẢNG phẳng SoQuy
       GET /api/so-quy/summary?tu_ngay&den_ngay (hoặc ?thang=) → tồn đầu/cuối THEO TỪNG TÀI KHOẢN
     → file này tự: lọc theo "tiền mặt" (TaiKhoanNH.loai='tien_mat'), tự cộng dồn "Tồn quỹ"
       theo dòng, tự tìm-kiếm/phân trang ở trình duyệt (tồn đầu kỳ lấy từ summary theo
       đúng khoảng ngày, xem dongBoTon).
   - SoQuy không có số phiếu (so_phieu_thu/so_phieu_chi) hay TK đối ứng thật — cột "Số phiếu"
     dùng mã nội bộ SQ-<id>; cột "TK đối ứng" đổi thành "Nguồn" (lien_quan: doanh_thu/chi_phí/
     công nợ/chuyển nội bộ/nhập tay) vì đó là dữ liệu thật gần nhất có ý nghĩa tương đương.
   - Không có "kiểm kê quỹ" (đối chiếu tiền mặt thực tế) trong DB — bỏ khối này khỏi phạm vi.
   - Panel không gọi thêm API phụ (SoQuy không link sang một bút toán sổ cái riêng) — hiện
     thẳng dữ liệu của dòng sổ quỹ.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-so-quy')) return;
  const H = KT.H;
  // Giải thích phạm vi số liệu: ⓘ cạnh tiêu đề (không in đoạn chữ dưới hàng thẻ số).
  document.querySelector('#kd-kt-so-quy .kd-h1').insertAdjacentHTML('beforeend',
    KD.tip('Chỉ tài khoản tiền mặt (ngân hàng xem ở màn Ngân hàng). Tồn đầu kỳ là số dư ngay trước ngày đầu kỳ; cột Tồn quỹ cộng dồn các giao dịch trong kỳ.'));
  document.getElementById('sq-pham-vi').hidden = true;

  /* Nhãn nguồn (so_quy.lien_quan) + phân loại dòng tiền (phan_loai_cf) — dùng chung với màn cũ
     /app#so-quy (badge CF). Giá trị lạ (vd 'vay_8' = khoản vay #8) vẫn hiện có nghĩa. */
  const NGUON = {
    doanh_thu: 'Tự động — Doanh thu', chi_phi: 'Tự động — Chi phí',
    cong_no: 'Tự động — Công nợ', chuyen_noi_bo: 'Chuyển nội bộ', denghitt: 'Đề nghị thanh toán', tam_ung: 'Tạm ứng',
  };
  const nhanNguon = (v) => NGUON[v] || (/^vay_\d+$/.test(v || '') ? 'Khoản vay #' + v.slice(4) : v ? esc(v) : 'Nhập tay');
  const CF = { thu_kh: ['success', 'Thu KH'], tra_ncc: ['danger', 'Trả NCC'], nap_ads: ['warning', 'Ads'], tra_luong: ['info', 'Lương'],
    mua_ccdc: ['info', 'CCDC'], sua_chua_lon: ['warning', 'Sửa chữa'], vay_nh: ['info', 'Vay NH'], tra_nh: ['info', 'Trả NH'], khac: ['muted', 'Khác'] };
  const cfPill = (cf) => (CF[cf] ? ' ' + H.pill(CF[cf][0], CF[cf][1]) : '');

  /* ── Tài khoản tiền mặt thật (TaiKhoanNH.loai='tien_mat') — cache 1 lần ── */
  let tkTienMat = null;
  async function layTkTienMat() {
    if (tkTienMat) return tkTienMat;
    try {
      const ds2 = await KD.api('/api/tai-khoan?loai=tien_mat&active_only=true');
      tkTienMat = (ds2 || []).map((t) => t.ten_tk);
    } catch (e) { tkTienMat = []; }
    return tkTienMat;
  }

  /* ── Tồn đầu kỳ THẬT tại đúng ngày `ky.tu` ──────────────────────────────
     GET /api/so-quy/summary?tu_ngay&den_ngay (2026-09-25) trả số dư NGAY TRƯỚC `tu_ngay`
     theo từng tài khoản, cùng thuật toán neo SoDuDauKy với màn Ngân hàng
     (so_quy_auto.so_du_truoc_ngay) — không còn phải tự cộng phần lệch đầu tháng ở đây.
     Thu/Chi/Tồn cuối vẫn tính trực tiếp trên đúng danh sách đang lọc [tu, den]. */
  let tonState = { key: null, ready: false, tonDau: 0 };
  async function dongBoTon(ky) {
    const key = ky.tu + '|' + ky.den;
    if (tonState.key === key && tonState.ready) return false;
    if (!ky.tu || !ky.den) { tonState = { key, ready: true, tonDau: 0 }; return true; }
    const tks = await layTkTienMat();
    let tonDau = 0;
    try {
      const d = await KD.api('/api/so-quy/summary?' + KT.url.qs({ tu_ngay: ky.tu, den_ngay: ky.den }));
      tonDau = (d.items || []).filter((it) => tks.indexOf(it.ten_tk) !== -1).reduce((s, x) => s + Number(x.so_du_dau_thang || 0), 0);
    } catch (e) { /* fail-soft — giữ tonDau = 0 */ }
    tonState = { key, ready: true, tonDau };
    return true;
  }

  const ds = KT.danhSach({
    pfx: 'sq', donVi: 'giao dịch',
    // Không gửi `loai` lên API: lọc Thu/Chi ở trình duyệt SAU khi cộng dồn tồn quỹ, để cột "Tồn quỹ"
    // và KPI Tồn cuối vẫn đúng khi chỉ xem phiếu thu hoặc phiếu chi.
    api: (q) => '/api/so-quy?' + KT.url.qs({ tu_ngay: q.tu, den_ngay: q.den, limit: 2000 }),
    macDinh: { ky: 'thang_nay', tu: '', den: '', tim: '', loai: '', page: 1, size: 20, sort: '' },
    dong: { id: (r) => r.id },
    chuyen: (raw, q) => {
      const tks = tkTienMat || [];
      // Chỉ tính sổ quỹ TIỀN MẶT (tài khoản loai='tien_mat') — bỏ dòng của TK ngân hàng
      // nếu cùng bảng so_quy có lẫn (module khác có thể ghi cả 2 loại vào chung bảng).
      const list = (raw || []).filter((r) => !tks.length || !r.tai_khoan || tks.indexOf(r.tai_khoan) !== -1);
      list.sort((a, b) => (a.ngay < b.ngay ? -1 : a.ngay > b.ngay ? 1 : a.id - b.id));
      let running = tonState.ready ? tonState.tonDau : 0;
      const withTon = list.map((r) => {
        running += r.loai === 'thu' ? Number(r.so_tien || 0) : -Number(r.so_tien || 0);
        return Object.assign({}, r, { ton: running });
      });
      withTon.reverse(); // mới nhất trước, khớp bố cục thiết kế
      const t = (q.tim || '').trim();
      const theoLoai = q.loai ? withTon.filter((r) => r.loai === q.loai) : withTon;
      const filtered = t ? theoLoai.filter((r) => KT.khopTim([r.noi_dung, r.mo_ta, r.ghi_chu, r.tai_khoan, r.nhan_vien_ten, r.ma_don], t)) : theoLoai;
      const size = +q.size || 20, page = Math.max(1, +q.page || 1);
      const tong_dong = filtered.length, so_trang = Math.max(1, Math.ceil(tong_dong / size)), trang = Math.min(page, so_trang);
      // Thu/Chi luôn tính trực tiếp từ đúng danh sách đã lọc theo kỳ [tu, den] —
      // khớp 1-1 với các dòng đang hiển thị (không lấy tổng theo tháng nữa).
      const tongThu = list.reduce((s, r) => s + (r.loai === 'thu' ? Number(r.so_tien || 0) : 0), 0);
      const tongChi = list.reduce((s, r) => s + (r.loai === 'chi' ? Number(r.so_tien || 0) : 0), 0);
      const tonDau = tonState.ready ? tonState.tonDau : null;
      const tonCuoi = tonDau == null ? null : tonDau + tongThu - tongChi;
      return {
        ky: { tu: q.tu, den: q.den },
        ton_dau: tonDau,
        tong_thu: tongThu,
        tong_chi: tongChi,
        ton_cuoi: tonCuoi,
        so_phieu_thu: list.filter((r) => r.loai === 'thu').length,
        so_phieu_chi: list.filter((r) => r.loai === 'chi').length,
        // Đang lọc loại/tìm → dòng Cộng cộng đúng các dòng đang hiện (nhãn ghi rõ "đang lọc"),
        // còn thẻ KPI vẫn là cả kỳ — hai đại lượng khác nhau, nhãn khác nhau.
        co_loc: filtered.length !== list.length,
        thu_loc: filtered.reduce((s, r) => s + (r.loai === 'thu' ? Number(r.so_tien || 0) : 0), 0),
        chi_loc: filtered.reduce((s, r) => s + (r.loai === 'chi' ? Number(r.so_tien || 0) : 0), 0),
        trang, so_trang, tong_dong,
        dong: filtered.slice((trang - 1) * size, trang * size),
      };
    },
    cot: [
      { key: 'ngay', nhan: 'Ngày', ve: (r) => KD.ngay(r.ngay) },
      // Gộp 2 cột "Số phiếu thu" / "Số phiếu chi" thành một — loại phiếu đã rõ qua cột Thu / Chi.
      { key: 'sp', nhan: 'Số phiếu', ve: (r) => H.ma('SQ-' + r.id) + '<span class="kt-khach__ma kt-sq-loai">' + (r.loai === 'thu' ? 'Phiếu thu' : 'Phiếu chi') + '</span>' },
      { key: 'dg', nhan: 'Diễn giải', ve: (r) => '<span class="kt-sq-dg" title="' + esc(r.noi_dung || r.mo_ta || '') + '">' + esc(r.noi_dung || r.mo_ta || '—') + '</span>' + (r.nhan_vien_ten ? '<span class="kt-khach__ma">' + esc(r.nhan_vien_ten) + '</span>' : r.ma_don ? '<span class="kt-khach__ma">Đơn ' + esc(r.ma_don) + '</span>' : '') },
      { key: 'nguon', nhan: 'Nguồn', ve: (r) => '<span class="kt-tk">' + nhanNguon(r.lien_quan) + '</span>' + cfPill(r.phan_loai_cf) },
      { key: 'thu', nhan: 'Thu (VND)', num: true, ve: (r) => (r.loai === 'thu' ? '<span class="kt-vao">+' + KD.tien(r.so_tien) + '</span>' : KT.tienSo(0)) },
      { key: 'chi', nhan: 'Chi (VND)', num: true, ve: (r) => (r.loai === 'chi' ? '−' + KD.tien(r.so_tien) : KT.tienSo(0)) },
      { key: 'ton', nhan: 'Tồn quỹ (VND)', num: true, cls: 'kd-strong', ve: (r) => KD.tien(r.ton) },
    ],
    kpi: {
      ton_dau: (d) => ({ v: d.ton_dau == null ? null : H.tienKpi(d.ton_dau), title: d.ton_dau == null ? '' : KD.tienVnd(d.ton_dau), phu: 'Ngày ' + KD.ngay(d.ky.tu) }),
      thu: (d) => ({ v: H.tienKpi(d.tong_thu), title: KD.tienVnd(d.tong_thu), phu: KD.soDem(d.so_phieu_thu) + ' phiếu thu' }),
      chi: (d) => ({ v: H.tienKpi(d.tong_chi), title: KD.tienVnd(d.tong_chi), phu: KD.soDem(d.so_phieu_chi) + ' phiếu chi' }),
      ton_cuoi: (d) => ({ v: d.ton_cuoi == null ? null : H.tienKpi(d.ton_cuoi), title: d.ton_cuoi == null ? '' : KD.tienVnd(d.ton_cuoi), phu: d.ton_cuoi != null && d.ton_cuoi < 0 ? H.pill('danger', 'Quỹ âm — kiểm tra lại phiếu chi') : 'Ngày ' + KD.ngay(d.ky.den) }),
    },
    cong: (d) => (d.co_loc
      ? [{ html: 'Cộng ' + KD.soDem(d.tong_dong) + ' giao dịch đang lọc' + KD.tip('Cả kỳ có ' + KD.soDem(d.so_phieu_thu + d.so_phieu_chi) + ' giao dịch — xem thẻ số phía trên.'), span: 4 }, { html: KD.tien(d.thu_loc), num: true }, { html: KD.tien(d.chi_loc), num: true }, { html: '—', num: true }]
      : [{ html: 'Cộng ' + KD.soDem(d.so_phieu_thu + d.so_phieu_chi) + ' giao dịch trong kỳ', span: 4 }, { html: KD.tien(d.tong_thu), num: true }, { html: KD.tien(d.tong_chi), num: true }, { html: d.ton_cuoi == null ? '' : KD.tien(d.ton_cuoi), num: true }]),
    rong: (d, coLoc) => (coLoc ? ['Không có giao dịch nào khớp bộ lọc', 'Thử bỏ bớt điều kiện lọc hoặc đổi kỳ.'] : ['Kỳ này chưa có phiếu thu, chi tiền mặt', 'Sổ quỹ tự sinh khi ghi Doanh thu/Chi phí bằng tiền mặt.']),
    loi: 'Không tải được sổ quỹ',
    // Tồn đầu kỳ nạp TRƯỚC khi gọi sổ (bản trước tải sổ → nạp tồn → tải sổ lần 2: mỗi lần đổi kỳ gọi /api/so-quy 2 lần).
    truocTai: (q) => dongBoTon({ tu: q.tu, den: q.den }),
    panel: {
      ve: (r) => H.dauPanel(r.loai === 'thu' ? 'bi-box-arrow-in-down' : 'bi-box-arrow-up', r.loai === 'thu' ? 'success' : 'danger',
        'SQ-' + r.id, KD.ngay(r.ngay) + (r.tai_khoan ? ' · ' + esc(r.tai_khoan) : ''), '')
        + '<p>' + esc(r.noi_dung || r.mo_ta || '(không có diễn giải)') + '</p>'
        + H.kv([
          [r.loai === 'thu' ? 'Số tiền thu' : 'Số tiền chi', KD.tienVnd(r.so_tien), true],
          ['Tồn quỹ luỹ kế sau dòng này', KD.tienVnd(r.ton)],
          ['Nguồn', nhanNguon(r.lien_quan) + cfPill(r.phan_loai_cf)],
          r.ref_id ? ['Mã tham chiếu', esc(r.ref_id)] : null,
          r.nhan_vien_ten ? ['Nhân viên', esc(r.nhan_vien_ten)] : null,
          r.ma_don ? ['Mã đơn liên quan', esc(r.ma_don)] : null,
          r.ghi_chu ? ['Ghi chú', esc(r.ghi_chu)] : null,
          ['Người tạo', esc(r.created_by || '—')],
        ]),
      nut: () => '',
    },
  });

  /* ── Lập phiếu thu / phiếu chi — ĐÚNG cơ chế màn cũ /app#so-quy (modal-sq · submitSoQuy):
     POST /api/so-quy {ngay, loai, tai_khoan, so_tien, noi_dung, lien_quan, ghi_chu, phan_loai_cf,
     nhan_vien_id, nhan_vien_ten, ma_don} → ghi 1 dòng ketoan.so_quy (router so_quy.create_so_quy:
     chặn chi làm âm số dư qua assert_du_chi, tự tra tên NV nếu thiếu, ghi audit). Cơ chế cũ KHÔNG sinh
     doanh thu / chi phí / công nợ / bút toán kèm theo — màn này cũng không. (Anh Quang 2026-09-25: thay
     việc chuyển sang màn Chứng từ, vốn chỉ ghi sổ nhật ký và không hiện trên Sổ quỹ.) ── */
  const $ = (id) => document.getElementById(id);
  const dlg = $('sq-dlg');
  const docSo = (v) => Number(String(v || '').replace(/[^\d]/g, '')) || 0;
  let napDm = null;
  function napDanhMuc() {
    napDm = napDm || Promise.all([
      KD.api('/api/tai-khoan?active_only=true').catch(() => []),
      KD.api('/api/external/employees?active=true').then((r) => (r && r.data) || []).catch(() => []),
    ]).then(([tks, nvs]) => {
      $('sq-f-tk').innerHTML = (tks || []).map((t) => '<option value="' + esc(t.ten_tk) + '">' + esc(t.ten_tk) + (t.loai === 'tien_mat' ? ' (tiền mặt)' : '') + '</option>').join('');
      $('sq-f-nv').innerHTML = '<option value="">— Không gắn nhân viên —</option>' + (nvs || []).filter((n) => n.id).map((n) => '<option value="' + n.id + '" data-ten="' + esc(n.ho_ten || '') + '">'
        + esc(n.ho_ten || '') + (n.phong_ban ? ' — ' + esc(n.phong_ban) : '') + (n.chuc_vu ? ' (' + esc(n.chuc_vu) + ')' : '') + '</option>').join('');
      return tks || [];
    });
    return napDm;
  }
  function datTieuDe() { $('sq-dlg-td').textContent = $('sq-f-loai').value === 'thu' ? 'Lập phiếu thu' : 'Lập phiếu chi'; }
  async function moPhieu(loai) {
    ['sq-f-tien', 'sq-f-nd', 'sq-f-lq', 'sq-f-madon', 'sq-f-gc'].forEach((id) => { $(id).value = ''; });
    $('sq-f-loai').value = loai; $('sq-f-cf').value = ''; $('sq-f-nv').value = ''; datTieuDe();
    const k = ds.khoang(), hom = KD.iso(new Date());
    $('sq-f-ngay').value = k.den && k.den < hom ? k.den : hom;
    KD.moHopThoai(dlg);
    const tks = await napDanhMuc();
    const tm = tks.find((t) => t.loai === 'tien_mat');
    if (tm && !$('sq-f-tk').dataset.daChon) $('sq-f-tk').value = tm.ten_tk;   // Sổ quỹ tiền mặt → mặc định quỹ tiền mặt
    $('sq-f-tien').focus();
  }
  document.querySelectorAll('#kd-kt-so-quy [data-lap]').forEach((b) => b.addEventListener('click', () => moPhieu(b.dataset.lap)));
  $('sq-f-loai').addEventListener('change', datTieuDe);
  $('sq-f-tk').addEventListener('change', () => { $('sq-f-tk').dataset.daChon = '1'; });
  $('sq-f-tien').addEventListener('input', (e) => { const n = docSo(e.target.value); e.target.value = n ? KD.tien(n) : ''; });
  $('sq-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const v = (id) => $(id).value.trim() || null, nv = $('sq-f-nv').selectedOptions[0];
    const body = { ngay: $('sq-f-ngay').value, loai: $('sq-f-loai').value, tai_khoan: $('sq-f-tk').value, so_tien: docSo($('sq-f-tien').value),
      noi_dung: v('sq-f-nd'), lien_quan: v('sq-f-lq'), ghi_chu: v('sq-f-gc'), phan_loai_cf: $('sq-f-cf').value || null,
      nhan_vien_id: +$('sq-f-nv').value || null, nhan_vien_ten: (nv && nv.dataset.ten) || null, ma_don: v('sq-f-madon') };
    if (!body.ngay) { $('sq-f-ngay').focus(); return KD.baoLoiHopThoai(dlg, 'Chọn ngày.'); }
    if (!body.tai_khoan) { $('sq-f-tk').focus(); return KD.baoLoiHopThoai(dlg, 'Chọn tài khoản / quỹ.'); }
    if (!body.so_tien) { $('sq-f-tien').focus(); return KD.baoLoiHopThoai(dlg, 'Nhập số tiền lớn hơn 0.'); }
    if (!body.noi_dung) { $('sq-f-nd').focus(); return KD.baoLoiHopThoai(dlg, 'Nhập nội dung giao dịch.'); }
    const nut = $('sq-f-luu'); nut.disabled = true;
    try {
      const r = await KD.api('/api/so-quy', KD.JSON_POST(body));
      dlg.close();
      window.showToast && window.showToast('ok', 'Đã ghi ' + (body.loai === 'thu' ? 'phiếu thu' : 'phiếu chi') + ' SQ-' + r.id + ' — ' + KD.tienVnd(body.so_tien));
      tonState.key = null;   // phiếu lùi ngày trước kỳ làm đổi tồn đầu kỳ
      ds.tai();
    } catch (err) { KD.baoLoiHopThoai(dlg, 'Chưa ghi được: ' + err.message); } finally { nut.disabled = false; }
  });
  // Mở thẳng hộp thoại khi tới từ nút "Lập phiếu thu/chi" ở màn khác: /ketoan/so-quy?lap=thu|chi
  const lap = new URLSearchParams(location.search).get('lap');
  if (lap === 'thu' || lap === 'chi') {
    const u = new URL(location.href); u.searchParams.delete('lap'); history.replaceState(null, '', u); delete ds.st.lap;
    moPhieu(lap);
  }

  ds.tai();
})();
