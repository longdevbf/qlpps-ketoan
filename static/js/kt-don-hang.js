/* kt-don-hang.js (dot3b) — Đơn hàng — tài chính, bản đợt 3, nối API THẬT external.py.
   ─────────────────────────────────────────────────────────────────────────
   Đây là màn có sẵn ÍT khoảng cách nhất với API thật trong cả 5 màn đợt 3b: bản thiết kế
   này vốn đã "chuyển từ code thật index.html + external.py" (README mục 1) nên hầu hết tên
   trường (tong_don, deposit, thu_thuc_te, thu_dat_coc, thu_thanh_toan, cn_phai_tra, cn_da_tra,
   chi_phi_vc, sa_ban_giao, delivery_cod_received, gia_cong_thuc, gia_ban_matched, vc_status,
   ketoan_approved_at, ma_vh, po_status…) KHỚP ĐÚNG cột SQL thật của `/api/external/orders-overview`
   và `/orders-optimization` — xem app/routers/external.py (đã đọc toàn bộ 2 hàm trước khi viết file này).

   GAP THẬT vẫn còn (đã xử lý trong file này, không bịa API mới):
   - `/api/external/orders-overview` trả `{filter, limit, data:[...]}` — KHÔNG có "tong" tổng hợp sẵn,
     KHÔNG phân trang. Kỳ (date_basis + tu_ngay/den_ngay) lọc NGAY TRONG SQL (QA 25/09: trước đó
     màn này không lọc kỳ, "Tháng này" hiện cả 200 đơn mới nhất); không lọc kỳ ("Tất cả") thì API
     vẫn giới hạn 200 đơn mới nhất như màn cũ. Từ khoá `tim` cũng lọc trong SQL và tìm MỌI kỳ (07/10/2026:
     lọc ở trình duyệt trên tập đã lọc kỳ làm link ?tim=<mã> từ Công nợ ra bảng rỗng). `chuanHoaDon()` tự
     tính con_thu/con_phai_tra, lọc thue, sắp xếp, phân trang, gộp "tong".
   - `/api/external/orders-optimization` GẦN NHƯ khớp 100% (đã kiểm field-by-field); chỉ thiếu 2
     trường tuỳ chọn `max_ck_go_tram` / `max_ck_go_tram_ap_tu` mà UI đã tự bỏ qua an toàn (không
     sửa gì thêm).
   - `co_tin_moi` (chấm tin nhắn mới): API không trả — dùng lại đúng cơ chế màn cũ (mốc đã xem
     lưu localStorage theo trình duyệt), y như README mô tả, không bịa endpoint mới.
   - Không có `/api/external/orders-overview/xuat` hay `/orders-optimization/xuat` — nút Xuất
     Excel khoá hẳn (không giả 404 bằng cách vẫn cho bấm).
   - `POST vanchuyen/<ma_vh>/hoan-thanh` trả `revenue:{created,id,so_tien,con_lai_bao_gia,...}`
     và `journal:{created,entries}` (không phải `so_ghi_nhan/con_thieu/doanh_thu/thu_tien` như
     suy đoán ban đầu) — đọc field thật, có fallback an toàn nếu thiếu.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-don-hang')) return;
  const H = KT.H, $ = (id) => document.getElementById(id);
  const u0 = Object.assign({ tab: 'doi_chieu', pt: '' }, KT.url.doc());
  let tab = ['doi_chieu', 'ban_giao', 'toi_uu'].includes(u0.tab) ? u0.tab : 'doi_chieu';
  const VC = { cho_lay: ['info', 'Chờ lấy hàng'], da_lay: ['info', 'Đã lấy hàng'], dang_giao: ['info', 'Đang giao'], da_giao: ['warning', 'Đã giao'], hoan_thanh: ['success', 'Hoàn thành'], hoan: ['danger', 'Hoàn hàng'] };
  const pillVC = (k) => { if (!k) return H.pill('muted', 'Chưa giao'); const x = VC[k]; if (!x) console.warn('[Đơn hàng] trạng thái vận chuyển chưa có nhãn:', k); return H.pill(x ? x[0] : 'muted', x ? x[1] : 'Chưa đặt tên'); };
  const NGAY_THEO = { duyet: 'Ngày duyệt', created: 'Ngày tạo', ketoan: 'Ngày KT hoàn thành' };
  const tienSo = (v) => KT.tienSo(v);
  const POST = { method: 'POST', headers: { Accept: 'application/json' } };
  let TK = null;
  const layTk = async () => { if (TK) return TK; try { const m = await KD.api('/api/meta'); const ten = (m.tai_khoan_nh || []).map((t) => (t && (t.ten_tk || t.ten)) || (typeof t === 'string' ? t : '')).filter(Boolean);
    TK = ['Tiền Mặt'].concat(ten.filter((n, i) => n.toLowerCase() !== 'tiền mặt' && ten.indexOf(n) === i)); } catch (e) { TK = ['Tiền Mặt']; } return TK; };
  const napTk = (sel, chon) => { sel.innerHTML = (TK || ['Tiền Mặt']).map((n) => '<option' + (n === chon ? ' selected' : '') + '>' + esc(n) + '</option>').join(''); };
  const codSA = (r) => { const raw = +r.delivery_cod_received || 0, con = Math.max(0, r.tong_don - r.thu_dat_coc); return r.thu_dat_coc > 0 && raw > con ? con : raw; };
  const conThuThat = (r) => Math.max(0, r.tong_don - r.thu_dat_coc - r.thu_thanh_toan);
  const docSo = (v) => Number(String(v || '').replace(/[^\d]/g, '')) || 0;
  /* Ghi chú của thẻ số → nút ⓘ cạnh nhãn (không in thành chữ dưới số). */
  function datTip(pfx, k, text, trai) {
    const el = document.querySelector('#' + pfx + '-kpi [data-kpi="' + k + '"] .kd-kpi__label'); if (!el) return;
    let b = el.querySelector('.kd-tip'); if (!text) { if (b) b.remove(); return; }
    if (!b) { el.insertAdjacentHTML('beforeend', ' ' + KD.tip(text, trai ? 'kd-tip--trai' : '')); b = el.querySelector('.kd-tip'); }
    b.dataset.tip = text; b.setAttribute('aria-label', text);
  }

  /* ── "Tin mới": mốc đã xem lưu ở localStorage theo trình duyệt (giống màn cũ) ── */
  const KEY_XEM = 'kt_dh_xem_v1';
  function docMocXem() { try { return JSON.parse(localStorage.getItem(KEY_XEM) || '{}'); } catch (e) { return {}; } }
  function ghiMocXem(maBg, luc) { try { const m = docMocXem(); m[maBg] = luc; localStorage.setItem(KEY_XEM, JSON.stringify(m)); } catch (e) { /* private mode — bỏ qua */ } }
  function coTinMoi(r) { if (!r.comment_count || !r.last_comment_at) return false; const m = docMocXem(); return !m[r.ma_bg] || m[r.ma_bg] < r.last_comment_at; }

  /* ── Chuẩn hoá /api/external/orders-overview (mảng phẳng; máy chủ lọc kỳ + tim, không lọc thue/page/
     size/sort) thành dạng khung kt-danh-sach.js cần ── */
  /* Còn thu (đúng công thức màn cũ, anh Quang 28/07): Tổng − Đã thu thực (đã gồm cọc đã ghi
     doanh thu) − phần cọc HỢP ĐỒNG chưa ghi doanh thu. Không trừ cọc 2 lần. Âm = thu thừa. */
  const conThuDoiChieu = (r) => Number(r.tong_don || 0) - Number(r.thu_thuc_te || 0) - Math.max(0, Number(r.deposit || 0) - Number(r.thu_dat_coc || 0));
  // Từ khoá tìm đã bỏ khoảng trắng hai đầu — "?tim=%20%20" trên URL không phải đang tìm (máy chủ cũng strip).
  const timGon = (q) => String(q.tim || '').trim();
  function chuanHoaDon(raw, q) {
    const rawData = raw.data;
    const dateBasis = q.date_basis || 'duyet';
    const NGAY_TRUONG = { duyet: 'ngay_duyet', created: 'ngay_tao', ketoan: 'ketoan_approved_at' };
    // Tiền VND nguyên: tong_don báo giá có lẻ (vd 29.999.999,81) → làm tròn TỪNG dòng trước khi
    // cộng, để dòng Cộng/thẻ = đúng tổng các số đang hiện trên bảng (QA nhất quán 25/09: lệch 1đ).
    const TIEN = ['tong_don', 'tien_thue', 'deposit', 'thu_thuc_te', 'thu_dat_coc', 'thu_thanh_toan', 'cn_phai_tra', 'cn_da_tra', 'chi_phi_vc', 'da_tra_dvvc', 'gia_cong_thuc', 'gia_ban_matched', 'tien_thu_ho', 'delivery_cod_received'];
    let list = (rawData || []).map((r0) => { const r = Object.assign({}, r0); TIEN.forEach((k) => { if (r[k] != null) r[k] = Math.round(Number(r[k]) || 0); }); return r; }).map((r) => Object.assign({}, r, {
      ngay: r[NGAY_TRUONG[dateBasis] || 'ngay_duyet'],
      con_thu: conThuDoiChieu(r),
      con_phai_tra: Math.max(0, (Number(r.cn_phai_tra || 0) - Number(r.cn_da_tra || 0)) + (Number(r.chi_phi_vc || 0) - Number(r.da_tra_dvvc || 0))),
      co_tin_moi: coTinMoi(r),
    }));
    // Không lọc lại q.tim ở đây: máy chủ đã lọc trên MỌI kỳ (cùng quy tắc bỏ dấu với KT.khopTim).
    if (q.thue === 'co_thue') list = list.filter((r) => Number(r.tien_thue || 0) > 0);
    else if (q.thue === 'khong_thue') list = list.filter((r) => !(Number(r.tien_thue || 0) > 0));
    const [cotSort, chieu] = (q.sort || 'ngay_desc').split('_');
    const dau = chieu === 'asc' ? 1 : -1;
    list.sort((a, b) => { const va = a[cotSort], vb = b[cotSort]; if (va == null && vb == null) return 0; if (va == null) return 1; if (vb == null) return -1;
      return va < vb ? -1 * dau : va > vb ? 1 * dau : 0; });
    const S = (f) => list.reduce((s, r) => s + f(r), 0);
    const tong = {
      so_don: list.length, tong_don: S((r) => Number(r.tong_don || 0)), tien_vat: S((r) => Number(r.tien_thue || 0)),
      dat_coc: S((r) => Number(r.deposit || 0)), da_thu: S((r) => Number(r.thu_thuc_te || 0)), con_thu: S((r) => Math.max(0, r.con_thu)),
      coc_chua_ghi: S((r) => Math.max(0, Number(r.deposit || 0) - Number(r.thu_dat_coc || 0))), thu_thua: S((r) => Math.max(0, -r.con_thu)), so_thu_thua: list.filter((r) => r.con_thu < 0).length,
      cn_phai_tra: S((r) => Number(r.cn_phai_tra || 0)), cn_da_tra: S((r) => Number(r.cn_da_tra || 0)),
      phi_vc: S((r) => Number(r.chi_phi_vc || 0)), tong_phai_tra: S((r) => r.con_phai_tra),
      gia_cong_thuc: S((r) => Number(r.gia_cong_thuc || 0)), gia_ban_matched: S((r) => Number(r.gia_ban_matched || 0)),
    };
    const size = +q.size || 20, page = Math.max(1, +q.page || 1);
    const tong_dong = list.length, so_trang = Math.max(1, Math.ceil(tong_dong / size)), trang = Math.min(page, so_trang);
    // _tim: có từ khoá thì máy chủ bỏ lọc kỳ (tìm mọi thời gian) — thẻ số / ghi chú phải nói đúng phạm vi đó.
    return { date_basis: dateBasis, tong, trang, so_trang, tong_dong, dong: list.slice((trang - 1) * size, trang * size), _day_du: (rawData || []).length < (raw.limit || 200),
      _gioi_han: raw.limit || 200, _tim: timGon(q), _co_ky: !!q.tu && !timGon(q) };
  }

  /* ═════════ Tab 1 — Đối chiếu kế toán ═════════ */
  const ptBat = () => $('dh-pt').checked;
  function datPt(bat) {
    $('dh-pt').checked = bat; $('dh-bang').classList.toggle('kt-an-pt', !bat); $('dh-pt-khoi').hidden = !bat;
  }
  // Ô "Giá công thức" (cột riêng như màn cũ): giá CT + dòng chênh (bán − CT).
  const giaCT = (ct, ban, lech) => { if (!(ct > 0)) return '<span class="kd-muted" title="Đơn chưa có dòng giá công thức">—</span>'; const ch = ban - ct, tt = 'Giá công thức ' + KD.tienVnd(ct) + ' · giá bán ' + KD.tienVnd(ban) + (lech || '');
    return KD.tien(ct) + (ch > 0.5 ? '<span class="kt-dh-lech kt-so--tot" title="Bán cao hơn công thức — ' + tt + '">▲ +' + KD.tien(ch) + '</span>'
      : ch < -0.5 ? '<span class="kt-dh-lech kt-so--xau" title="Bán THẤP hơn công thức, cần soát lại — ' + tt + '">▼ −' + KD.tien(-ch) + '</span>' : '<span class="kt-dh-lech kd-muted" title="Đúng giá công thức — ' + tt + '">đúng giá</span>'); };
  function xuLy(r) {
    if (r.vc_status === 'da_giao') return '<div class="kt-dh-xl">' + (r.sla_hoan ? H.pill('muted', 'Đang hoãn') : '')
      + (r.sa_ban_giao ? '<button type="button" class="kd-btn kd-btn--sm" data-xl="nhan" data-id="' + esc(r.ma_bg) + '" title="Nhận số Sale Admin đã báo: ' + KD.tienVnd(codSA(r)) + '">Nhận thực</button>'
        : '<span class="kd-muted" title="Chờ Sale Admin báo số thực thu — hoặc thu trực tiếp ở tab Bàn giao trong ngày">Chờ SA bàn giao</span>') + '</div>';
    if (r.vc_status === 'hoan_thanh' && !r.ketoan_approved_at) return '<button type="button" class="kd-btn kd-btn--sm" data-xl="duyet" data-id="' + esc(r.ma_bg) + '">Duyệt KT</button>';
    if (r.vc_status === 'hoan_thanh') return '<span title="Kế toán duyệt: ' + esc(r.ketoan_approved_by || '') + ' · ' + KD.ngay(r.ketoan_approved_at) + '">' + H.pill('success', 'Đã xong') + '</span>';
    return '';
  }
  // Danh sách NV KD lấy từ /orders-salespeople (mọi đơn đã duyệt, gộp biến thể tên — như màn cũ),
  // không lấy từ các dòng đang tải (kỳ ngắn sẽ thiếu NV).
  let nvDaNap = false;
  function napNvDoiChieu() {
    if (nvDaNap) return; nvDaNap = true;
    KD.api('/api/external/orders-salespeople').then((r) => H.napChon($('dh-salesperson'), (r.data || []).map((x) => [x.name, x.name + ' (' + KD.soDem(x.so_don) + ')']), 'Tất cả', ds.st.salesperson)).catch(() => { nvDaNap = false; });
  }
  const PT = 'kt-cot-pt';
  const ds = KT.danhSach({
    // tim gửi lên máy chủ (ô tìm đã debounce 350ms trong kt-danh-sach.js); có tim thì máy chủ bỏ qua tu_ngay/den_ngay.
    pfx: 'dh', api: (q) => '/api/external/orders-overview?' + KT.url.qs({ filter: q.date_basis === 'ketoan' ? 'done' : q.filter, salesperson: q.salesperson || undefined, date_basis: q.date_basis || 'duyet', tu_ngay: q.tu || undefined, den_ngay: q.den || undefined, tim: timGon(q) || undefined }), donVi: 'đơn', kyThem: ['hom_nay', '7_ngay', 'tat_ca'],
    dangHien: () => tab === 'doi_chieu',
    // Tab Tối ưu dùng chung ô kỳ: tải lại khi khoảng đổi (sau debounce của ô ngày), luôn ghi URL (bảng đối chiếu đang ẩn thì không tự ghi).
    sauDoiKy: (doiKhoang) => { ghiUrl(); if (doiKhoang && tab === 'toi_uu') taiToiUu(); },
    macDinh: { tim: '', filter: 'all', salesperson: '', date_basis: 'duyet', thue: '', page: 1, size: 20, sort: 'ngay_desc' },
    dong: { id: (r) => r.ma_bg },
    chuyen: (raw, q) => chuanHoaDon(raw, q),
    cot: [
      { key: 'ma', nhan: 'Mã báo giá', ve: (r) => H.ma(r.ma_bg) + (r.comment_count ? '<span class="kt-dh-tin' + (r.co_tin_moi ? ' is-moi' : '') + '" title="' + KD.soDem(r.comment_count) + ' tin nhắn trao đổi' + (r.co_tin_moi ? ' — có tin mới' : '') + '"><i class="bi bi-chat-dots" aria-hidden="true"></i>' + KD.soDem(r.comment_count) + (r.co_tin_moi ? ' mới' : '') + '</span>' : '') + '<span class="kt-khach__ma">' + esc(r.salesperson || '—') + '</span>' },
      { key: 'kh', nhan: 'Khách', ve: (r) => '<span class="kt-khach__ten kt-dh-kh">' + esc(r.customer_name || '—') + '</span>' },
      { key: 'ngay', nhan: 'Ngày', sort: 'so', ve: (r) => (r.ngay ? KD.ngay(r.ngay) : '—') },
      { key: 'tong_don', nhan: 'Tổng đơn', num: true, sort: 'so', ve: (r) => '<b>' + KD.tien(r.tong_don) + '</b>' + (+r.tien_thue ? '<span class="kt-dh-lech kd-muted">VAT ' + KD.tien(r.tien_thue) + '</span>' : '') },
      { key: 'gia_ct', nhan: 'Giá công thức', num: true, lop: PT, title: 'Giá theo công thức bảng giá (bắt lúc lên đơn), trước chiết khấu/VAT. Dòng nhỏ: chênh giá NV bán so với công thức', ve: (r) => giaCT(+r.gia_cong_thuc || 0, +r.gia_ban_matched || 0, r.gia_ct_items ? ' — ' + KD.soDem(r.gia_ct_items) + ' sản phẩm sửa giá tay' : '') },
      { key: 'coc', nhan: 'Đã cọc', num: true, lop: PT, title: 'Cọc theo hợp đồng', ve: (r) => tienSo(r.deposit) },
      { key: 'da_thu', nhan: 'Đã thu', num: true, ve: (r) => KD.tien(r.thu_thuc_te) },
      { key: 'con_thu', nhan: 'Còn thu', num: true, sort: 'so', title: 'Tổng đơn − đã thu − phần cọc hợp đồng chưa ghi doanh thu', ve: (r) => '<span class="' + (r.con_thu <= 0 ? 'kt-so--tot' : !r.thu_thuc_te && !r.deposit ? 'kt-so--xau kd-strong' : 'kd-strong') + '">' + (r.con_thu < 0 ? '−' + KD.tien(-r.con_thu) + '<span class="kt-dh-lech">thu thừa</span>' : KD.tien(r.con_thu)) + '</span>' },
      { key: 'cn_pt', nhan: 'Phải trả NCC', num: true, lop: PT, ve: (r) => tienSo(r.cn_phai_tra) },
      { key: 'cn_dt', nhan: 'Đã trả NCC', num: true, lop: PT, ve: (r) => tienSo(r.cn_da_tra) },
      { key: 'vc', nhan: 'Phí VC', num: true, lop: PT, ve: (r) => tienSo(r.chi_phi_vc) },
      { key: 'con_pt', nhan: 'Còn phải trả', num: true, lop: PT, ve: (r) => '<span class="' + (r.con_phai_tra > 0 ? 'kt-so--xau kd-strong' : 'kt-so--tot') + '">' + KD.tien(Math.max(0, r.con_phai_tra)) + '</span>' },
      { key: 'vc_tt', nhan: 'Tiến trình', ve: (r) => '<div class="kt-dh-vc">' + pillVC(r.vc_status) + (r.ngay_giao ? '<span class="kt-khach__ma">Giao ' + KD.ngay(r.ngay_giao) + '</span>' : '')
        + (r.bg_status && r.bg_status !== 'approved' ? H.pill('muted', 'Báo giá nháp') : '') + xuLy(r) + '</div>' },
      { key: 'act', nhan: 'Thao tác', act: true, nhanDong: (r) => r.ma_bg },
    ],
    kpi: {
      tong_don: (d) => ({ v: H.tienKpi(d.tong.tong_don), title: KD.tienVnd(d.tong.tong_don), phu: KD.soDem(d.tong.so_don) + ' đơn' + (d._day_du ? '' : ' · ' + KD.soDem(d._gioi_han) + (d._tim ? ' đơn khớp gần nhất' : ' đơn gần nhất')) }),
      vat: (d) => ({ v: H.tienKpi(d.tong.tien_vat), title: KD.tienVnd(d.tong.tien_vat), phu: '' }),
      dat_coc: (d) => ({ v: H.tienKpi(d.tong.dat_coc), title: KD.tienVnd(d.tong.dat_coc), phu: '' }),
      da_thu: (d) => ({ v: H.tienKpi(d.tong.da_thu), title: KD.tienVnd(d.tong.da_thu), phu: d.tong.tong_don ? KD.phanTram(d.tong.da_thu / d.tong.tong_don * 100) + ' tổng đơn' : '' }),
      // Còn phải thu = Tổng − Đã thu − cọc HĐ chưa ghi thu + phần thu thừa (đơn âm không trừ vào tổng — như màn cũ).
      con_thu: (d) => ({ v: H.tienKpi(d.tong.con_thu), title: KD.tienVnd(d.tong.con_thu), phu: d.tong.thu_thua ? 'Thu thừa ' + KD.tienGon(d.tong.thu_thua) + ' (' + KD.soDem(d.tong.so_thu_thua) + ' đơn)' : '' }),
    },
    // Ô Thời gian vẫn hiện "Tháng này" khi đang tìm → nói rõ kết quả là của mọi thời gian (textContent, không cần esc).
    phamVi: (d) => [d._tim ? 'Đang tìm “' + d._tim + '” trong mọi thời gian — ô Thời gian không áp dụng khi tìm.' : '', d.date_basis === 'ketoan' ? 'Chỉ gồm đơn kế toán đã duyệt.' : ''].filter(Boolean).join(' '),
    cong: (d) => { const t = d.tong;
      return [{ html: 'Cộng ' + KD.soDem(t.so_don) + ' đơn', span: 3 }, { html: KD.tien(t.tong_don) + '<span class="kt-dh-lech kd-muted">VAT ' + KD.tien(t.tien_vat) + '</span>', num: true }, { html: giaCT(t.gia_cong_thuc, t.gia_ban_matched), num: true, lop: PT },
        { html: KD.tien(t.dat_coc), num: true, lop: PT }, { html: KD.tien(t.da_thu), num: true }, { html: KD.tien(t.con_thu) + (t.thu_thua ? '<span class="kt-dh-lech kd-muted" title="Tổng các dòng âm (thu thừa) — không trừ vào Còn thu">thu thừa −' + KD.tien(t.thu_thua) + '</span>' : ''), num: true },
        { html: KD.tien(t.cn_phai_tra), num: true, lop: PT }, { html: KD.tien(t.cn_da_tra), num: true, lop: PT }, { html: KD.tien(t.phi_vc), num: true, lop: PT }, { html: KD.tien(t.tong_phai_tra), num: true, lop: PT },
        { html: '' }, { html: '' }]; },
    rong: (d, coLoc) => (d._tim ? ['Không tìm thấy đơn nào khớp “' + d._tim + '”', 'Đã tìm trong mọi thời gian. Kiểm tra lại mã báo giá, tên khách hoặc số điện thoại, hoặc bỏ bớt bộ lọc khác.']
      : coLoc ? ['Không có đơn nào khớp bộ lọc', 'Thử bỏ bớt điều kiện lọc hoặc đổi Thời gian.'] : ['Chưa có đơn đã duyệt trong thời gian này', 'Đơn hiện ở đây sau khi báo giá được duyệt bên app Báo giá.']),
    loi: 'Không tải được bảng đối chiếu đơn hàng',
    sauTai: (d) => {
      const th = document.querySelector('#dh-thead [data-sort="ngay"]'); if (th) th.firstChild.textContent = (NGAY_THEO[d.date_basis] || 'Ngày') + ' ';
      $('dh-filter').disabled = d.date_basis === 'ketoan';
      napNvDoiChieu();
      const ch = d.tong.gia_ban_matched - d.tong.gia_cong_thuc;
      datTip('dh', 'tong_don', (d._tim ? 'Kết quả tìm trong mọi thời gian, tối đa ' + KD.soDem(d._gioi_han) + ' đơn tạo gần nhất.' : 'Lọc theo ' + NGAY_THEO[d.date_basis || 'duyet'].toLowerCase() + '.') + (d.tong.gia_cong_thuc > 0 ? ' Giá công thức ' + KD.tienVnd(d.tong.gia_cong_thuc) + (Math.abs(ch) > 0.5 ? ' (bán ' + (ch > 0 ? 'cao' : 'thấp') + ' hơn ' + KD.tienVnd(Math.abs(ch)) + ')' : '') + '.' : '') + (d._co_ky || d._tim ? '' : ' Thời gian "Tất cả" chỉ tải 200 đơn tạo gần nhất.'));
      datTip('dh', 'vat', 'Thuế GTGT nằm trong tổng đơn.');
      datTip('dh', 'dat_coc', 'Cọc ghi trên hợp đồng.');
      datTip('dh', 'con_thu', 'Tổng đơn − đã thu − cọc hợp đồng chưa ghi thu.' + (d.tong.thu_thua ? ' Chưa trừ ' + KD.tienVnd(d.tong.thu_thua) + ' thu thừa của ' + KD.soDem(d.tong.so_thu_thua) + ' đơn.' : ''), true);
      const t = d.tong, dat = (k, v, phu) => { const el = document.querySelector('#dp-kpi [data-kpi="' + k + '"]'); el.querySelector('[data-v]').innerHTML = H.tienKpi(v); el.querySelector('[data-v]').title = KD.tienVnd(v); el.querySelector('[data-phu]').innerHTML = phu; };
      dat('cn_phai_tra', t.cn_phai_tra, 'Theo đơn mua hàng'); dat('cn_da_tra', t.cn_da_tra, t.cn_phai_tra ? KD.phanTram(t.cn_da_tra / t.cn_phai_tra * 100) + ' đã trả' : ''); dat('phi_vc', t.phi_vc, 'Đơn vị vận chuyển'); dat('tong_phai_tra', t.tong_phai_tra, 'Nhà cung cấp + vận chuyển');
      ghiUrl();
    },
    khiLoi: () => { document.querySelectorAll('#dp-kpi [data-v]').forEach((x) => { x.innerHTML = '<span class="kd-muted">—</span>'; }); },
    panel: {
      tai: (r) => '/api/external/order-detail/' + encodeURIComponent(r.ma_bg),
      ve: (d, r) => { if (r.last_comment_at) ghiMocXem(r.ma_bg, r.last_comment_at); return veChiTiet(d, r); },
      nut: (d, r) => (r.vc_status === 'da_giao' && r.sa_ban_giao ? '<button type="button" class="kd-btn kd-btn--grow" data-xl="nhan" data-id="' + esc(r.ma_bg) + '"><i class="bi bi-cash-coin" aria-hidden="true"></i>Nhận thực</button>' : '')
        + (r.vc_status === 'hoan_thanh' && !r.ketoan_approved_at ? '<button type="button" class="kd-btn kd-btn--grow" data-xl="duyet" data-id="' + esc(r.ma_bg) + '"><i class="bi bi-check2" aria-hidden="true"></i>Duyệt KT</button>' : '')
        + '<a class="kd-btn kd-btn--grow" href="/kd/bao-gia?tim=' + encodeURIComponent(r.ma_bg) + '"><i class="bi bi-box-arrow-up-right" aria-hidden="true"></i>Mở báo giá</a>',
    },
    menu: (r) => [
      r.vc_status === 'da_giao' ? (r.sla_hoan ? { nhan: 'Bỏ hoãn — tính SLA lại', icon: 'bi-play', onClick: () => moHoan(r, 'bo') } : { nhan: 'Hoãn (đã giao, chưa thu tiền)', icon: 'bi-pause', onClick: () => moHoan(r, 'hoan') }) : null,
      r.vc_status === 'da_giao' ? { nhan: 'Thu và hoàn thành ở tab Bàn giao', icon: 'bi-box-seam', onClick: () => tabs.chon('ban_giao') } : null,
      { nhan: 'Mở báo giá bên app Báo giá', icon: 'bi-box-arrow-up-right', href: '/kd/bao-gia?tim=' + encodeURIComponent(r.ma_bg) },
    ].filter(Boolean),
  });

  /* ── Panel chi tiết đơn: mỗi khối một hàm, tự phòng dữ liệu thiếu và tự bắt lỗi của riêng nó ──
     Trước 07/10/2026 cả panel là MỘT biểu thức: một trường lồng nhau lạ ném lỗi là mất trắng panel, chỉ còn câu
     "Không tải được chi tiết" (kt-danh-sach.js bắt chung với lỗi API). Nay khối nào hỏng chỉ mất khối đó. */
  // Dữ liệu gom từ nhiều app (baogia, muahang, saleadmin, marketing…) — không tin hình dạng: không phải mảng → [],
  // phần tử null/sai kiểu bị bỏ nhưng luôn console.warn để không âm thầm thiếu dòng.
  const mang = (v, ten) => { const ds = Array.isArray(v) ? v.filter((x) => x && typeof x === 'object') : [];
    if ((Array.isArray(v) ? v.length : v == null ? 0 : 1) !== ds.length) console.warn('[Đơn hàng] Bỏ dữ liệu sai dạng ở "' + ten + '":', v); return ds; };
  const doiTuong = (v) => (v && typeof v === 'object' && !Array.isArray(v) ? v : null);
  const bangNho = (dau, dong, rong) => (dong.length ? '<table class="kt-bang-nho"><thead><tr>' + dau.map(([t, n]) => '<th scope="col"' + (n ? ' class="num"' : '') + '>' + t + '</th>').join('') + '</tr></thead><tbody>' + dong.join('') + '</tbody></table>' : KD.khoiRong(rong, ''));
  // Key trạng thái không bao giờ in thô (luật frontend-ui 2): thiếu nhãn → "Chưa đặt tên" + console.warn.
  const nhan = (bang, k, loai) => { if (Object.prototype.hasOwnProperty.call(bang, k)) return bang[k]; console.warn('[Đơn hàng] ' + loai + ' chưa có nhãn:', k); return 'Chưa đặt tên'; };
  const DUYET_BG = { approved: 'Đã duyệt', kt_pending: 'Chờ kế toán xác nhận cọc' };
  function veKhoiAnToan(ten, icon, ve, buocTiep) {
    try { return ve(); } catch (e) {
      console.error('[Đơn hàng] Không vẽ được khối "' + ten + '" của panel chi tiết:', e);
      return H.khoi(icon, ten, '<p class="kd-note kd-note--danger" role="alert">Không hiển thị được khối ' + esc(ten) + ' vì dữ liệu có dạng lạ — '
        + esc(buocTiep) + '. Các khối khác của đơn vẫn xem được.</p>');
    }
  }
  function veKhoiThongTin(d, r) {
    const q = doiTuong(d.quote) || {};
    const duyet = q.duyet_boi ? 'Đã duyệt bởi ' + esc(q.duyet_boi) : q.duyet_status ? esc(nhan(DUYET_BG, q.duyet_status, 'trạng thái duyệt báo giá')) : '—';
    return H.dauPanel('bi-receipt', r.con_thu > 0 ? 'warning' : 'success', r.ma_bg, esc(q.customer_name || r.customer_name || ''), pillVC(r.vc_status))
      + H.kv([['Khách', esc(q.customer_name || r.customer_name || '—') + (q.customer_phone ? ' · ' + esc(q.customer_phone) : '')], ['Địa chỉ', esc(q.customer_address && q.customer_address !== 'None' ? q.customer_address : '—')], ['NV kinh doanh', esc(q.salesperson || r.salesperson || '—')], ['Ngày tạo', KD.ngay(q.created_at)], ['Duyệt', duyet], ['Tiến trình', esc(q.tien_trinh_mh || '—')]]);
  }
  function veKhoiTien(d, r) {
    // Tổng đơn / thuế / cọc lấy từ DÒNG BẢNG (r — đã làm tròn đồng ở chuanHoaDon), không từ báo giá thô (q, có lẻ
    // ,81): cùng con số với bảng và thẻ số, và "Còn phải thu" (tính từ r) khớp các số ngay phía trên nó.
    const q = doiTuong(d.quote), ct = +r.gia_cong_thuc || 0, ban = +r.gia_ban_matched || 0, thu = +r.thu_dat_coc || 0, tt = +r.thu_thanh_toan || 0;
    const tien = (v) => (v == null ? '—' : KD.tienVnd(v));
    return H.khoi('bi-cash-stack', 'Tiền', H.kv([['Tổng đơn', tien(r.tong_don)], ['Giảm giá', q ? KD.tienVnd(q.discount_amount || 0) : '—'], ['Thuế GTGT', tien(r.tien_thue)], ['Giá công thức', ct > 0 ? KD.tienVnd(ct) + (Math.abs(ban - ct) > 0.5 ? ' · bán ' + (ban > ct ? 'cao' : 'thấp') + ' hơn ' + KD.tienVnd(Math.abs(ban - ct)) : ' · đúng giá') : '—'],
      ['Cọc hợp đồng', tien(r.deposit)], ['Đã thu', KD.tienVnd(r.thu_thuc_te || 0) + (thu || tt ? '<span class="kt-khach__ma">' + [thu ? 'Cọc ' + KD.tienVnd(thu) : '', tt ? 'Thanh toán ' + KD.tienVnd(tt) : ''].filter(Boolean).join(' · ') + '</span>' : '')], ['Còn phải thu', KD.tienVnd(Math.max(0, +r.con_thu || 0)), true]])
      // Báo giá không đọc được: nói ra, không để các ô hiện "0 VND" như số thật.
      + (q ? '' : '<p class="kt-dh-canh">Không đọc được chi tiết báo giá của đơn này — số tiền lấy từ bảng đối chiếu, giảm giá chưa có. Bấm "Mở báo giá" để xem bản gốc.</p>'));
  }
  function veKhoiSanPham(d) {
    const ds = mang(d.items, 'items');
    return H.khoi('bi-box', 'Sản phẩm (' + KD.soDem(ds.length) + ')', bangNho([['Sản phẩm'], ['SL', 1], ['Đơn giá', 1], ['Thành tiền', 1]], ds.map((x) => '<tr><td>' + esc(x.ten_sp || '—') + '<span class="kt-khach__ma">' + esc([x.ma_don, x.kich_thuoc, x.mau_go, x.mau_vai, x.mau_da, x.loai_son].filter(Boolean).join(' · ')) + '</span></td><td class="num">' + KD.soDem(x.so_luong) + ' ' + esc(x.dvt || '') + '</td><td class="num">' + KD.tien(x.don_gia || 0) + '</td><td class="num">' + KD.tien(x.thanh_tien) + '</td></tr>'), 'Không có sản phẩm'));
  }
  function veKhoiMuaHang(d) {
    const ds = mang(d.pos, 'pos');
    return H.khoi('bi-truck', 'Đơn mua nhà cung cấp (' + KD.soDem(ds.length) + ')', bangNho([['Mã PO'], ['Nhà cung cấp'], ['Chiết khấu', 1], ['Trạng thái']], ds.map((p) => '<tr><td>' + esc(p.po_id == null ? '—' : p.po_id) + '<span class="kt-khach__ma">' + (p.created_at ? 'Tạo ' + KD.ngay(p.created_at) : '') + '</span></td><td>' + esc(p.ncc_name || '—') + '</td><td class="num">' + KD.tien(p.discount || 0) + '</td><td>' + esc(p.status || '—') + '</td></tr>'), 'Chưa có PO'));
  }
  function veKhoiSoQuy(d) {
    const ds = mang(d.so_quy, 'so_quy');
    return H.khoi('bi-journal-text', 'Sổ quỹ liên quan (' + KD.soDem(ds.length) + ')', bangNho([['Ngày'], ['Nội dung'], ['Số tiền', 1]], ds.map((s) => '<tr><td>' + KD.ngay(s.ngay) + '</td><td>' + (s.loai === 'thu' ? 'Thu' : 'Chi') + ' · ' + esc(s.tai_khoan || '—') + '<span class="kt-khach__ma">' + esc(s.noi_dung || '') + '</span></td><td class="num ' + (s.loai === 'thu' ? 'kt-so--tot' : 'kt-so--xau') + '">' + KD.tien(s.so_tien) + '</td></tr>'), 'Chưa có giao dịch sổ quỹ'));
  }
  // Tiền VND nguyên — cùng cách làm tròn với dòng bảng (chuanHoaDon) để khối Công nợ khớp khối Tiền ngay trên.
  const tronDong = (v) => Math.round(Number(v) || 0);
  function veKhoiCongNo(d) {
    // trang_thai chỉ có chua_tra/da_tra cho cả hai chiều → đọc theo loai: phải thu là "thu", phải trả là "trả".
    const ttCn = (c) => { const thu = c.loai === 'phai_thu'; return c.trang_thai === 'da_tra' ? (thu ? 'Đã thu đủ' : 'Đã trả đủ') : c.trang_thai === 'chua_tra' ? (thu ? 'Chưa thu đủ' : 'Chưa trả đủ') : nhan({}, c.trang_thai, 'trạng thái công nợ'); };
    return H.khoi('bi-people', 'Công nợ', bangNho([['Loại'], ['Đối tác'], ['Còn lại', 1]], mang(d.cong_no, 'cong_no').map((c) => '<tr><td>' + (c.loai === 'phai_thu' ? 'Phải thu' : 'Phải trả') + (c.ngay ? '<span class="kt-khach__ma">' + KD.ngay(c.ngay) + '</span>' : '') + '</td><td>' + esc(c.doi_tac || '—') + '<span class="kt-khach__ma">' + KD.tien(tronDong(c.so_tien)) + ' · đã ' + KD.tien(tronDong(c.da_tra)) + (c.trang_thai ? ' · ' + esc(ttCn(c)) : '') + '</span></td><td class="num">' + KD.tien(tronDong(c.con_lai)) + '</td></tr>'), 'Chưa có công nợ'));
  }
  function veKhoiVanChuyen(d) {
    const vc = doiTuong(d.vanchuyen);
    return H.khoi('bi-signpost', 'Vận chuyển', vc ? H.kv([['Mã vận chuyển', esc(vc.ma_vh || '—')], ['Ngày giao', KD.ngay(vc.ngay_giao)], ['Đơn vị vận chuyển', esc(vc.don_vi_vc || '—')], ['Phí vận chuyển', KD.tienVnd(vc.chi_phi_vc || 0) + ' · đã trả ' + KD.tienVnd(vc.da_tra_dvvc || 0)], ['Tiền thu hộ', KD.tienVnd(vc.tien_thu_ho || 0)], ['Sale Admin báo đã thu', KD.tienVnd(vc.dvvc_da_thu || 0)]]) : KD.khoiRong('Chưa có vận chuyển', ''));
  }
  function veKhoiTraoDoi(d) {
    const ds = mang(d.comments, 'comments');
    // Ảnh do app khác ghi: chỉ nhận đường dẫn nội bộ "/…" hoặc http(s) (KD.urlAnToan) — chặn href="javascript:…".
    return H.khoi('bi-chat-dots', 'Trao đổi đơn hàng (' + KD.soDem(ds.length) + ')', ds.length ? '<ul class="kt-dh-tn">' + ds.map((c) => { const anh = KD.urlAnToan(c.hinh_anh);
      return '<li><p class="kd-meta"><b>' + esc(c.nguoi_gui_name || c.nguoi_gui || '—') + '</b>' + (KD.nhanPhongBan(c.phong_ban) ? ' · ' + esc(KD.nhanPhongBan(c.phong_ban)) : '') + ' · ' + KD.ngay(c.thoi_gian) + '</p><p>' + esc(c.noi_dung || '') + '</p>' + (anh ? '<a href="' + esc(anh) + '" target="_blank" rel="noopener"><img class="kt-dh-tn__anh" src="' + esc(anh) + '" alt="Ảnh đính kèm tin nhắn" loading="lazy" onerror="this.parentNode.hidden=true"></a>' : '') + '</li>'; }).join('') + '</ul>' : KD.khoiRong('Chưa có trao đổi nào về đơn này', ''));
  }
  function veChiTiet(d, r) {
    const dl = doiTuong(d) || {};
    const BG = 'bấm "Mở báo giá" bên dưới để xem phần này';
    // [tên khối, icon, hàm vẽ, bước tiếp theo khi khối lỗi — chỉ đúng nơi dữ liệu đó thật sự nằm]
    return [['Thông tin đơn', 'bi-receipt', () => veKhoiThongTin(dl, r), BG], ['Tiền', 'bi-cash-stack', () => veKhoiTien(dl, r), BG],
      ['Sản phẩm', 'bi-box', () => veKhoiSanPham(dl), BG], ['Đơn mua nhà cung cấp', 'bi-truck', () => veKhoiMuaHang(dl), 'xem đơn mua ở app Mua hàng'],
      ['Sổ quỹ liên quan', 'bi-journal-text', () => veKhoiSoQuy(dl), 'tìm mã đơn ở màn Sổ quỹ'], ['Công nợ', 'bi-people', () => veKhoiCongNo(dl), 'tìm mã đơn ở màn Công nợ'],
      ['Vận chuyển', 'bi-signpost', () => veKhoiVanChuyen(dl), 'xem lệnh vận chuyển ở app Sale Admin'], ['Trao đổi đơn hàng', 'bi-chat-dots', () => veKhoiTraoDoi(dl), BG]]
      .map(([ten, icon, ve, buoc]) => veKhoiAnToan(ten, icon, ve, buoc)).join('');
  }


  /* ═════════ Tab 2 — Bàn giao trong ngày ═════════ */
  let bgDs = [], bgLuot = 0;
  const THU = ['Chủ nhật', 'Thứ hai', 'Thứ ba', 'Thứ tư', 'Thứ năm', 'Thứ sáu', 'Thứ bảy'];
  async function taiBanGiao() {
    const l = ++bgLuot, el = $('bg-noi-dung'); el.innerHTML = KD.KHUNG_TAI;
    try {
      await layTk();
      const raw = await KD.api('/api/external/orders-overview?' + KT.url.qs({ filter: 'pending' }));
      if (l !== bgLuot) return;
      const ngayGiao = $('bg-ngay').value;
      bgDs = (raw.data || []).filter((r) => r.vc_status === 'da_giao' && (!ngayGiao || r.ngay_giao === ngayGiao));
      if (!ngayGiao) $('dh-dem-bg').textContent = bgDs.length ? '(' + KD.soDem(bgDs.length) + ')' : '';
      if (!bgDs.length) { el.innerHTML = KD.khoiRong(ngayGiao ? 'Không có đơn đã giao chờ thu ngày ' + KD.ngay(ngayGiao) : 'Không còn đơn đã giao chờ thu tiền', 'Đơn hiện ở đây khi vận chuyển báo "Đã giao". Đơn đã hoàn thành chuyển sang tab Đối chiếu kế toán.'); return; }
      const nhom = {}; bgDs.forEach((r) => { const k = r.ngay_giao || ''; (nhom[k] = nhom[k] || []).push(r); });
      el.innerHTML = '<div class="kd-table-scroll kd-table-scroll--thanh"><table class="kd-table kt-bang kt-bg-bang"><caption class="visually-hidden">Đơn đã giao chờ thu tiền, nhóm theo ngày giao</caption>'
        + '<thead><tr><th scope="col">Mã báo giá · NV KD</th><th scope="col">Khách</th><th scope="col" class="num">Cần thu (VND)</th><th scope="col" class="num">SA báo (VND)</th><th scope="col">Thực thu (VND)</th><th scope="col">Nhận vào</th><th scope="col">Xử lý</th></tr></thead>'
        + Object.keys(nhom).sort().reverse().map((k) => { const rs = nhom[k], sa = rs.reduce((a2, r) => a2 + (r.sa_ban_giao ? codSA(r) : 0), 0), can = rs.reduce((a2, r) => a2 + (+r.tien_thu_ho || 0), 0);
          const td = k ? THU[new Date(k + 'T00:00:00').getDay()] + ', ' + KD.ngay(k) : 'Chưa có ngày giao';
          return '<tbody><tr class="kt-bg-nhom"><th scope="rowgroup" colspan="7"><span class="kt-bg-ngay__td">' + td + ' · ' + KD.soDem(rs.length) + ' đơn</span><span class="kt-bg-ngay__so">Cần thu <b class="num">' + KD.tienVnd(can) + '</b> · Sale Admin đã báo <b class="num">' + KD.tienVnd(sa) + '</b></span></th></tr>'
            + rs.map((r) => { const macDinh = r.sa_ban_giao && codSA(r) > 0 ? codSA(r) : conThuThat(r);
              return '<tr data-vh="' + esc(r.ma_vh) + '"><td>' + H.ma(r.ma_bg) + '<span class="kt-khach__ma">' + esc(r.salesperson || '—') + '</span>' + (r.sla_hoan ? '<span class="kt-khach__ma">' + H.pill('muted', 'Đang hoãn') + '</span>' : '') + '</td>'
                + '<td><span class="kt-khach__ten kt-dh-kh">' + esc(r.customer_name || '—') + '</span><span class="kt-khach__ma">' + esc(r.customer_phone || '') + '</span></td>'
                + '<td class="num">' + KD.tien(r.tien_thu_ho || 0) + '</td><td class="num">' + (r.sa_ban_giao ? '<b>' + KD.tien(codSA(r)) + '</b>' : '<span class="kd-muted" title="Sale Admin chưa báo">—</span>') + '</td>'
                + '<td><input class="kd-input kt-bg-tien" data-tien inputmode="numeric" value="' + KD.tien(macDinh) + '" aria-label="Số tiền thực thu đơn ' + esc(r.ma_bg) + '"></td>'
                + '<td><select class="kd-input kt-bg-tk" data-tk aria-label="Nhận tiền vào — đơn ' + esc(r.ma_bg) + '">' + (TK || ['Tiền Mặt']).map((n) => '<option>' + esc(n) + '</option>').join('') + '</select></td>'
                + '<td><div class="kt-dh-xl kt-bg-xl"><button type="button" class="kd-btn kd-btn--sm" data-bg="thu">Hoàn thành và thu</button><button type="button" class="kd-icon-btn" data-bg="hoan" aria-label="' + (r.sla_hoan ? 'Bỏ hoãn' : 'Hoãn') + ' đơn ' + esc(r.ma_bg) + '" title="' + (r.sla_hoan ? 'Bỏ hoãn — tính SLA lại' : 'Hoãn: đã giao nhưng chưa thu tiền') + '"><i class="bi ' + (r.sla_hoan ? 'bi-play' : 'bi-pause') + '" aria-hidden="true"></i></button></div></td></tr>'; }).join('') + '</tbody>'; }).join('')
        + '</table></div>';
    } catch (e) { if (l !== bgLuot) return; KD.khoiLoi(el, 'Không tải được đơn chờ bàn giao', e, taiBanGiao); }
  }
  $('bg-noi-dung').addEventListener('input', (e) => { const i = e.target.closest('[data-tien]'); if (!i) return; const n = docSo(i.value); i.value = n ? KD.tien(n) : ''; });
  $('bg-noi-dung').addEventListener('click', (e) => { const b = e.target.closest('[data-bg]'); if (!b) return; const tr = b.closest('tr'), r = bgDs.find((x) => x.ma_vh === tr.dataset.vh); if (!r) return;
    if (b.dataset.bg === 'hoan') return moHoan(r, r.sla_hoan ? 'bo' : 'hoan');
    moThu(r, 'kt', docSo(tr.querySelector('[data-tien]').value), tr.querySelector('[data-tk]').value); });
  $('bg-ngay').addEventListener('change', () => { taiBanGiao(); }); $('bg-tat-ca').addEventListener('click', () => { $('bg-ngay').value = ''; taiBanGiao(); });

  /* ── Hộp thu tiền + hoàn thành (dùng chung 2 tab) ── */
  const dlgThu = $('dh-dlg-thu'); let dangThu = null;
  function veGoiY() {
    if (!dangThu) return; const r = dangThu.r, n = docSo($('dh-thu-tien').value), con = conThuThat(r), ghi = Math.min(n, con), tk = $('dh-thu-tk').value;
    $('dh-thu-tien-gy').textContent = 'Còn phải thu ' + KD.tienVnd(con) + (n > con ? ' — hệ thống chỉ ghi tối đa ' + KD.tienVnd(con) : n < con ? ' — thiếu ' + KD.tienVnd(con - n) + ' nằm lại ở "Còn thu"' : '');
    // Đúng như external.py mark_vanchuyen_completed: bút toán doanh thu Nợ 131 / Có 511 theo số thực thu (không tách 3331);
    // tiền thu chỉ vào Sổ quỹ của tài khoản đã chọn (máy chủ chưa ghi bút toán Nợ 111/112).
    $('dh-thu-gy').innerHTML = '<i class="bi bi-journal-text" aria-hidden="true"></i> Sẽ ghi: ' + (ghi ? 'doanh thu Nợ 131 / Có 511 ' + KD.tienVnd(ghi) + ' · thu ' + KD.tienVnd(ghi) + ' vào "' + esc(tk) + '" (Sổ quỹ)' : 'không ghi doanh thu, không thu tiền') + ' · không trừ kho (Mua hàng ghi phiếu xuất), chưa tự ghi giá vốn · chuyển đơn sang Hoàn thành.';
  }
  function moThu(r, cheDo, soTien, tk) {
    dangThu = { r, cheDo }; $('dh-thu-kq').hidden = true; $('dh-thu-than').hidden = false; $('dh-thu-chan').hidden = false; $('dh-thu-chan2').hidden = true;
    $('dh-thu-td').textContent = (cheDo === 'sa' ? 'Nhận thực — ' : 'Hoàn thành và thu — ') + r.ma_bg;
    $('dh-thu-tt').innerHTML = '<dt>Khách</dt><dd>' + esc(r.customer_name || '—') + '</dd><dt>Tổng đơn</dt><dd>' + KD.tienVnd(r.tong_don) + '</dd><dt>Đã thu</dt><dd>' + KD.tienVnd(r.thu_dat_coc + r.thu_thanh_toan) + '</dd>'
      + (r.sa_ban_giao ? '<dt>Sale Admin báo đã thu</dt><dd>' + KD.tienVnd(codSA(r)) + '</dd>' : '');
    $('dh-thu-tien').value = KD.tien(cheDo === 'sa' ? codSA(r) : soTien); $('dh-thu-tien').readOnly = cheDo === 'sa';
    $('dh-thu-tien').title = cheDo === 'sa' ? 'Nhận thực lấy đúng số Sale Admin báo — muốn sửa số, thu ở tab Bàn giao trong ngày' : '';
    napTk($('dh-thu-tk'), tk || 'Tiền Mặt'); $('dh-thu-ok').innerHTML = '<i class="bi bi-check2-circle" aria-hidden="true"></i>' + (cheDo === 'sa' ? 'Nhận thực' : 'Hoàn thành và thu');
    veGoiY(); KD.moHopThoai(dlgThu); (cheDo === 'sa' ? $('dh-thu-tk') : $('dh-thu-tien')).focus();
  }
  $('dh-thu-tien').addEventListener('input', (e) => { const n = docSo(e.target.value); e.target.value = n ? KD.tien(n) : ''; veGoiY(); });
  $('dh-thu-tk').addEventListener('change', veGoiY);
  $('dh-form-thu').addEventListener('submit', async (e) => {
    e.preventDefault(); if (!dangThu) return; const { r, cheDo } = dangThu, n = docSo($('dh-thu-tien').value), tk = $('dh-thu-tk').value;
    // Đơn đã thu đủ (cọc + cọc bổ sung + thanh toán ≥ tổng đơn, lệch < 1 đ) → cho hoàn thành với 0 đ, KHÔNG ghi thêm
    // tiền (như /app#don-hang markVCDoneKT). Đơn còn nợ vẫn bắt nhập > 0. Trước 28/09/2026 màn này chặn mọi số 0
    // → đơn đã thu đủ cọc không hoàn thành được (không ra giá vốn, không trừ kho, không lên "Đã xong").
    const daThuDu = conThuThat(r) < 1;
    if (cheDo === 'kt' && (n < 0 || (n === 0 && !daThuDu))) { $('dh-thu-tien').focus(); return KD.baoLoiHopThoai(dlgThu, 'Nhập số tiền thực thu lớn hơn 0.'); }
    const nut = $('dh-thu-ok'); nut.disabled = true;
    try {
      const q = { tai_khoan: tk, note: cheDo === 'sa' ? 'KT nhận thực — SA báo ' + KD.tien(n) + 'đ' : n === 0 ? 'KT hoàn thành — đơn đã thu đủ, không ghi thêm tiền' : 'KT thu + hoàn thành — ' + KD.tien(n) + 'đ' };
      if (cheDo === 'kt') q.so_tien_thuc_nhan = n;
      const kq = await KD.api('/api/external/vanchuyen/' + encodeURIComponent(r.ma_vh) + '/hoan-thanh?' + KT.url.qs(q), POST);
      // Field thật: revenue={created,id,so_tien,con_lai_bao_gia,...}; journal={created,entries}.
      const rev = kq.revenue || {}, jour = kq.journal || {}, inv = kq.inventory || {}, dd = inv.deducted || [], cb = inv.warnings || [];
      $('dh-thu-kq').innerHTML = '<p>' + H.pill('success', 'Đã hoàn thành') + ' Đơn ' + esc(r.ma_bg) + ' đã chuyển sang Hoàn thành' + (rev.created ? ', ghi thu ' + KD.tienVnd(rev.so_tien) + (rev.con_lai_bao_gia > 0 ? ' (còn thiếu ' + KD.tienVnd(rev.con_lai_bao_gia) + ')' : '') : '') + '.</p>'
        + (jour.created ? '<p class="kd-meta">Đã ghi ' + KD.soDem((jour.entries || []).length) + ' bút toán.</p>' : '')
        + (dd.length ? H.khoi('bi-box-seam', 'Đã trừ tồn kho (FIFO)', '<table class="kt-bang-nho"><thead><tr><th scope="col">Sản phẩm · lô nhập</th><th scope="col" class="num">Trừ</th><th scope="col" class="num">Còn</th></tr></thead><tbody>'
          + dd.map((x) => (x.lots || []).map((l, i) => '<tr><td>' + (i ? '' : '<b>' + esc(x.product_name) + '</b> · ') + 'lô nhập ' + KD.ngay(l.ngay_nhap) + '</td><td class="num">' + KD.soDem(l.deducted) + '</td><td class="num">' + KD.soDem(l.remaining) + '</td></tr>').join('')).join('') + '</tbody></table>') : '')
        + (cb.length ? '<p class="kd-note"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i> ' + cb.map(esc).join('<br>') + '</p>' : '');
      $('dh-thu-than').hidden = true; $('dh-thu-kq').hidden = false; $('dh-thu-chan').hidden = true; $('dh-thu-chan2').hidden = false; $('dh-thu-chan2').querySelector('button').focus();
      window.showToast && window.showToast('ok', 'Đã hoàn thành ' + r.ma_bg); ds.dongPanel(); lamMoi();
    } catch (err) { KD.baoLoiHopThoai(dlgThu, 'Chưa hoàn thành được: ' + err.message); } finally { nut.disabled = false; }
  });

  /* ── Duyệt KT · Hoãn SLA ── */
  const dlgDuyet = $('dh-dlg-duyet'), dlgHoan = $('dh-dlg-hoan'); let dangDuyet = null, dangHoan = null;
  function moDuyet(r) { dangDuyet = r; $('dh-duyet-td').textContent = 'Duyệt kế toán đơn ' + r.ma_bg + '?'; $('dh-duyet-nd').textContent = 'Đơn đã giao xong, kế toán chốt đối chiếu thu – chi. Sau khi duyệt, đơn chuyển "Đã xong" và tính doanh số theo ngày kế toán hoàn thành.'; KD.moHopThoai(dlgDuyet); $('dh-duyet-ok').focus(); }
  $('dh-duyet-ok').addEventListener('click', async () => { const nut = $('dh-duyet-ok'); nut.disabled = true;
    try { const kq = await KD.api('/api/external/vanchuyen/' + encodeURIComponent(dangDuyet.ma_vh) + '/ketoan-approve', POST); dlgDuyet.close(); ds.dongPanel();
      window.showToast && window.showToast('ok', kq.already_approved ? 'Đơn đã được duyệt trước đó' : 'Đã duyệt ' + dangDuyet.ma_bg + ' — chuyển "Đã xong"'); ds.tai(); }
    catch (e) { KD.baoLoiHopThoai(dlgDuyet, 'Chưa duyệt được: ' + e.message); } finally { nut.disabled = false; } });
  function moHoan(r, action) { dangHoan = { r, action }; $('dh-hoan-td').textContent = action === 'bo' ? 'Bỏ hoãn đơn ' + r.ma_bg + '?' : 'Hoãn đơn ' + r.ma_bg + ' khỏi tính SLA?';
    $('dh-hoan-nd').textContent = action === 'bo' ? 'Đơn sẽ được tính trễ hạn (SLA) trở lại.' : 'Dùng khi đã giao nhưng khách chưa trả tiền: đơn tạm ra khỏi tính trễ hạn, vẫn nằm trong danh sách chờ thu.';
    $('dh-hoan-ly-o').hidden = action === 'bo'; $('dh-hoan-ok').textContent = action === 'bo' ? 'Bỏ hoãn' : 'Hoãn'; KD.moHopThoai(dlgHoan); (action === 'bo' ? $('dh-hoan-ok') : $('dh-hoan-ly')).focus(); }
  $('dh-form-hoan').addEventListener('submit', async (e) => { e.preventDefault(); const { r, action } = dangHoan, ly = $('dh-hoan-ly').value.trim();
    if (action === 'hoan' && !ly) return KD.baoLoiHopThoai(dlgHoan, 'Nhập lý do hoãn.');
    const nut = $('dh-hoan-ok'); nut.disabled = true;
    try { await KD.api('/api/external/vanchuyen/' + encodeURIComponent(r.ma_vh) + '/hoan-sla?' + KT.url.qs({ action, ly_do: action === 'hoan' ? ly : '' }), POST);
      dlgHoan.close(); window.showToast && window.showToast('ok', action === 'hoan' ? 'Đã hoãn — đơn tạm ra khỏi tính SLA' : 'Đã bỏ hoãn — tính SLA lại'); lamMoi(); }
    catch (err) { KD.baoLoiHopThoai(dlgHoan, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; } });
  document.addEventListener('click', (e) => { const b = e.target.closest('#dh-tbody [data-xl], #dh-p-nut [data-xl]'); if (!b) return; e.stopPropagation();
    const r = ds.dsHien().find((x) => x.ma_bg === b.dataset.id); if (!r) return; layTk().then(() => (b.dataset.xl === 'nhan' ? moThu(r, 'sa') : moDuyet(r))); }, true);

  /* ═════════ Tab 3 — Tối ưu chiết khấu (đã khớp API thật ~100%, không cần chuyen) ═════════ */
  let tuDl = null, tuLuot = 0;
  const pct = (v) => KD.phanTram(v);
  const tienAm = (v) => (v < 0 ? '<span class="kt-tu-am">−' + KD.tien(-v) + '</span>' : KD.tien(v));
  const loaiTu = (o) => (o.is_papasan ? H.pill('muted', 'Ghế Papasan · miễn CK') : o.is_papasan_mix ? '<span title="Đã trừ ghế Papasan ' + KD.tienVnd(o.papasan_base) + ' khỏi tạm tính">' + H.pill('success', 'Mây · trừ Papasan') + '</span>'
    : o.loai_don === 'Đồ Mây' ? H.pill('success', 'Đồ Mây') : o.loai_don === 'Đồ Gỗ' ? H.pill('warning', 'Đồ Gỗ') + (o.phan_khuc_duyet && !['Bản Tiêu Chuẩn', 'Bản Plus'].includes(o.phan_khuc_duyet) ? '<span class="kt-khach__ma">' + esc(o.phan_khuc_duyet) + '</span>' : '') : H.pill('muted', 'Chưa phân loại'));
  const tuDat = (k, v, phu, khoi) => { const el = document.querySelector('#' + (khoi || 'tu') + '-kpi [data-kpi="' + k + '"]'); el.querySelector('[data-v]').innerHTML = v; el.querySelector('[data-phu]').innerHTML = phu || ''; };
  function tuKpi2(d) {
    const K = ['so_don', 'tam_tinh', 'sau_ck', 'ck_tb', 'toi_uu'];
    if (!d) return K.forEach((k) => tuDat(k, '<span class="kd-muted">—</span>', '', 'tu2'));
    const t = d.totals || {};
    tuDat('so_don', KD.soDem(t.so_don), 'Đơn đã duyệt', 'tu2');
    tuDat('tam_tinh', H.tienKpi(t.tam_tinh), 'Tạm tính, chưa thuế', 'tu2');
    tuDat('sau_ck', H.tienKpi(t.sau_ck), 'Đã giảm ' + KD.tienGon((t.tam_tinh || 0) - (t.sau_ck || 0)), 'tu2');
    tuDat('ck_tb', pct(t.ck_tb_pct), '', 'tu2'); datTip('tu2', 'ck_tb', 'Đã giảm ÷ tạm tính.');
    tuDat('toi_uu', t.toi_uu < 0 ? '<span class="kt-tu-am">−' + H.tienKpi(-t.toi_uu) + '</span>' : H.tienKpi(t.toi_uu), '', 'tu2'); datTip('tu2', 'toi_uu', 'Cộng cả số âm của đơn vượt trần.', true);
  }
  function tuKpi(d) {
    tuKpi2(d);
    if (!d) return ['may', 'go', 'tong'].forEach((k) => tuDat(k, '<span class="kd-muted">—</span>'));
    const g = (k) => d.by_loai.find((x) => x.loai_don === k) || { so_don: 0, toi_uu_hcns: 0 };
    tuDat('may', H.tienKpi(g('Đồ Mây').toi_uu_hcns), KD.soDem(g('Đồ Mây').so_don) + ' đơn · trần ' + pct(d.max_ck_may));
    tuDat('go', H.tienKpi(g('Đồ Gỗ').toi_uu_hcns), KD.soDem(g('Đồ Gỗ').so_don) + ' đơn · trần ' + pct(d.max_ck_go));
    datTip('tu', 'go', d.max_ck_go_tram != null ? 'Gỗ phân khúc khác Bản Tiêu Chuẩn / Bản Plus: trần ' + pct(d.max_ck_go_tram) + '.' : '');
    const pap = d.by_loai.find((x) => x.loai_don === 'Ghế Papasan'), chua = d.by_loai.find((x) => x.loai_don === 'Chưa phân loại');
    tuDat('tong', H.tienKpi(d.totals.toi_uu_hcns), 'Khớp HCNS');
    datTip('tu', 'tong', ['Mây + Gỗ + chưa phân loại, chỉ cộng đơn còn dư trần', pap ? KD.soDem(pap.so_don) + ' đơn Ghế Papasan miễn CK' : '', chua ? KD.soDem(chua.so_don) + ' đơn chưa phân loại (áp trần Gỗ) ' + KD.tienGon(chua.toi_uu_hcns) : ''].filter(Boolean).join(' · ') + '.', true);
  }
  function tuChinhSach(d) {
    $('tu-chinh-sach').innerHTML = KD.tip('Lọc theo ngày duyệt đơn (ô Thời gian). Trần chiết khấu (HCNS, áp theo tháng): Đồ Gỗ ' + pct(d ? d.max_ck_go : 20)
      + (d && d.max_ck_go_tram != null ? ' (phân khúc khác Bản Tiêu Chuẩn / Bản Plus ' + pct(d.max_ck_go_tram) + ' từ tháng ' + (d.max_ck_go_tram_ap_tu || '').split('-').reverse().join('/') + ')' : '')
      + ', Đồ Mây ' + pct(d ? d.max_ck_may : 15) + '. Tối ưu = trần × tạm tính − đã giảm; âm là vượt trần. Ghế Papasan miễn chính sách.');
  }
  function tuVe() {
    const d = tuDl; if (!d) return; const t = ($('tu-tim').value || '').trim(), vuot = $('tu-vuot').checked;
    const rows = d.data.filter((o) => (!vuot || o.vuot_chinh_sach) && KT.khopTim([o.ma_bg, o.customer_name, o.salesperson], t));
    if (!rows.length) { $('tu-cuon').hidden = true; $('tu-tfoot').innerHTML = ''; $('tu-tt').innerHTML = KD.khoiRong(t || vuot ? 'Không có đơn nào khớp bộ lọc' : 'Không có đơn đã duyệt trong thời gian này', t || vuot ? 'Thử bỏ bớt điều kiện lọc.' : 'Chọn thời gian khác ở ô Thời gian phía trên.'); return; }
    $('tu-cuon').hidden = false; $('tu-tt').innerHTML = '';
    $('tu-tbody').innerHTML = rows.map((o) => '<tr><td>' + H.ma(o.ma_bg) + '<span class="kt-khach__ma">' + esc(o.salesperson) + '</span></td><td><span class="kt-dh-kh">' + esc(o.customer_name || '—') + '</span></td><td>' + KD.ngay(o.ngay_duyet || o.ngay_tao) + '</td><td>' + loaiTu(o) + '<span class="kt-khach__ma">' + (o.is_papasan ? 'Miễn chính sách' : 'Trần ' + pct(o.max_ck_ap_dung)) + '</span></td><td class="num">' + KD.tien(o.tam_tinh) + '</td><td class="num">' + KD.tien(o.tong_giam) + '</td><td class="num">' + pct(o.ck_pct) + (o.is_papasan ? '' : '<span class="kt-dh-lech ' + (o.toi_uu_pct < 0 ? 'kt-tu-am' : 'kd-muted') + '">' + (o.toi_uu_pct < 0 ? 'vượt ' + pct(-o.toi_uu_pct) : 'dư ' + pct(o.toi_uu_pct)) + '</span>') + '</td>'
      + '<td class="num">' + (o.is_papasan ? '—' : o.vuot_chinh_sach ? '<span title="Vượt trần chiết khấu">' + tienAm(o.so_tien_toi_uu) + '<span class="kt-dh-lech kt-tu-am">Vượt trần</span></span>' : '<b>' + KD.tien(o.so_tien_toi_uu) + '</b>') + '</td></tr>').join('');
    const S = (k) => rows.reduce((a, o) => a + o[k], 0), tt = S('tam_tinh'), gi = S('tong_giam');
    $('tu-tfoot').innerHTML = '<tr><th scope="row" colspan="4">Cộng ' + KD.soDem(rows.length) + ' đơn · sau chiết khấu ' + KD.tien(tt - gi) + '</th><td class="num">' + KD.tien(tt) + '</td><td class="num">' + KD.tien(gi) + '</td><td class="num">' + pct(tt ? gi / tt * 100 : 0) + '</td><td class="num">' + tienAm(S('so_tien_toi_uu')) + '</td></tr>';
  }
  function tuVeNv() {
    const d = tuDl; if (!d) return;
    if (!d.by_sp.length) { $('tu-nv-cuon').hidden = true; $('tu-nv-tfoot').innerHTML = ''; $('tu-nv-tt').innerHTML = KD.khoiRong('Chưa có số liệu theo nhân viên', 'Chọn thời gian khác ở ô Thời gian phía trên.'); return; }
    $('tu-nv-cuon').hidden = false; $('tu-nv-tt').innerHTML = '';
    const them = {}; d.data.forEach((o) => { const a = them[o.salesperson] = them[o.salesperson] || { vuot: 0, duong: 0 }; if (o.vuot_chinh_sach) a.vuot++; if (o.so_tien_toi_uu > 0) a.duong += o.so_tien_toi_uu; });
    $('tu-nv-tbody').innerHTML = d.by_sp.map((s) => { const a = them[s.salesperson] || { vuot: 0, duong: 0 };
      return '<tr><th scope="row">' + esc(s.salesperson) + '</th><td class="num">' + KD.soDem(s.so_don) + '</td><td class="num">' + (a.vuot ? '<span class="kt-tu-am">' + KD.soDem(a.vuot) + '</span>' : '0') + '</td><td class="num">' + KD.tien(s.tam_tinh) + '</td><td class="num">' + pct(s.ck_tb_pct) + '</td>'
        + '<td class="num"><b>' + KD.tien(a.duong) + '</b></td><td class="num">' + tienAm(s.toi_uu) + '</td></tr>'; }).join('');
    $('tu-nv-tfoot').innerHTML = '<tr><th scope="row">Cộng</th><td class="num">' + KD.soDem(d.totals.so_don) + '</td><td class="num">' + KD.soDem(d.data.filter((o) => o.vuot_chinh_sach).length) + '</td><td class="num">' + KD.tien(d.totals.tam_tinh) + '</td><td class="num">' + pct(d.totals.ck_tb_pct) + '</td><td class="num">' + KD.tien(Object.values(them).reduce((a, x) => a + x.duong, 0)) + '</td><td class="num">' + tienAm(d.totals.toi_uu) + '</td></tr>';
      }
  /* API cộng số lẻ rồi mới làm tròn từng nhóm (tổng / theo NV / theo loại) → lệch 1đ với tổng các dòng
     đang hiện (QA nhất quán 25/09: T8 NV 65.324.680 vs Cộng 65.324.679; T9 Đã giảm thẻ 65.089.930 vs
     bảng 65.089.929). Làm tròn từng đơn rồi cộng lại mọi tổng từ chính các dòng. */
  function chuanToiUu(d) {
    const R = (v) => Math.round(Number(v) || 0);
    d.data.forEach((o) => { o.tam_tinh = R(o.tam_tinh); o.tong_giam = R(o.tong_giam); o.so_tien_toi_uu = R(o.so_tien_toi_uu); });
    const cong = (ds2) => { const tt = ds2.reduce((a, o) => a + o.tam_tinh, 0), gi = ds2.reduce((a, o) => a + o.tong_giam, 0);
      return { so_don: ds2.length, tam_tinh: tt, tong_giam: gi, sau_ck: tt - gi, ck_tb_pct: tt ? Math.round(gi / tt * 10000) / 100 : 0,
        toi_uu: ds2.reduce((a, o) => a + (o.is_papasan ? 0 : o.so_tien_toi_uu), 0), toi_uu_hcns: ds2.reduce((a, o) => a + (!o.is_papasan && o.so_tien_toi_uu > 0 ? o.so_tien_toi_uu : 0), 0) }; };
    d.totals = Object.assign({}, d.totals, cong(d.data));
    d.by_sp = d.by_sp.map((s) => Object.assign({}, s, cong(d.data.filter((o) => o.salesperson === s.salesperson))));
    d.by_loai = d.by_loai.map((g) => Object.assign({}, g, cong(d.data.filter((o) => (o.is_papasan ? 'Ghế Papasan' : o.loai_don || 'Chưa phân loại') === g.loai_don))));
    return d;
  }
  async function taiToiUu() {
    const l = ++tuLuot; tuDl = null; document.querySelectorAll('#tu-kpi [data-v], #tu2-kpi [data-v]').forEach((x) => { x.innerHTML = '<span class="kd-skel kd-skel--kpi"></span>'; }); document.querySelectorAll('#tu-kpi [data-phu], #tu2-kpi [data-phu]').forEach((x) => { x.innerHTML = ''; });
    $('tu-pham-vi').textContent = ''; $('tu-cuon').hidden = false; $('tu-tt').innerHTML = ''; $('tu-tfoot').innerHTML = ''; $('tu-tbody').innerHTML = KT.hangCho(8, 6);
    $('tu-nv-cuon').hidden = false; $('tu-nv-tt').innerHTML = ''; $('tu-nv-tfoot').innerHTML = ''; $('tu-nv-tbody').innerHTML = KT.hangCho(7, 3);
    const k = ds.khoang();
    try {
      const d = await KD.api('/api/external/orders-optimization?' + KT.url.qs({ tu_ngay: k.tu, den_ngay: k.den, salesperson: $('tu-nv').value }));
      if (l !== tuLuot) return; tuDl = chuanToiUu(d); tuChinhSach(d); tuKpi(d); tuVe(); tuVeNv();
      $('tu-pham-vi').textContent = '';
      if ($('tu-nv').options.length <= 1) { const nv = await KD.api('/api/external/orders-kd-list'); H.napChon($('tu-nv'), (nv.data || []).map((x) => [x.name, x.name + ' (' + KD.soDem(x.so_don) + ' đơn)']), 'Tất cả', $('tu-nv').value); }
    } catch (e) { if (l !== tuLuot) return; tuKpi(null); $('tu-cuon').hidden = true; $('tu-nv-cuon').hidden = true; $('tu-nv-tbody').innerHTML = ''; KD.khoiLoi($('tu-tt'), 'Không tải được số liệu tối ưu chiết khấu', e, taiToiUu); }
  }
  $('tu-tim').addEventListener('input', KD.debounce(tuVe, 250)); $('tu-vuot').addEventListener('change', tuVe); $('tu-nv').addEventListener('change', () => { taiToiUu(); });
  $('tu-loc').addEventListener('submit', (e) => e.preventDefault());
  tuChinhSach(null);

  /* ═════════ Tab · URL · làm mới (Xuất Excel khoá — không có API thật) ═════════ */
  const daTai = { ban_giao: false };
  const MAC_URL = { tab: 'doi_chieu', pt: '', tim: '', filter: 'all', salesperson: '', date_basis: 'duyet', thue: '', page: 1, size: 20, sort: 'ngay_desc', ky: 'thang_nay' };
  function ghiUrl() { try { KT.url.ghi(Object.assign({}, ds.st, { tab, pt: ptBat() ? '1' : '' }), MAC_URL); } catch (e) { /* khung xem trước */ } }
  const demBanGiao = () => KD.api('/api/external/orders-overview?' + KT.url.qs({ filter: 'pending' })).then((d) => { const n = (d.data || []).filter((r) => r.vc_status === 'da_giao').length; $('dh-dem-bg').textContent = n ? '(' + KD.soDem(n) + ')' : ''; }).catch(() => {});
  function lamMoi() { ds.tai(); if (tab === 'ban_giao' || daTai.ban_giao) taiBanGiao(); else demBanGiao(); }
  const tabs = KD.ganTab($('dh-tabs'), (k) => {
    tab = k; $('dh-ky-o').hidden = k === 'ban_giao'; $('dh-nut-loc').hidden = k !== 'doi_chieu'; ghiUrl();
    if (k === 'doi_chieu') ds.taiNeuCan(); else if (k === 'ban_giao') { daTai.ban_giao = true; taiBanGiao(); } else taiToiUu();
  });
  $('dh-pt').addEventListener('change', (e) => { datPt(e.target.checked); ghiUrl(); });
  $('dh-xuat').addEventListener('click', (e) => { e.preventDefault(); window.showToast && window.showToast('info', 'App ketoan chưa có API xuất Excel cho đơn hàng.'); });
  datPt(u0.pt === '1');
  layTk();
  if (tab !== 'ban_giao') demBanGiao();
  tabs.chon(tab);
})();
