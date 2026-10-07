/* kt-doi-chieu.js — Đối chiếu sổ cái ↔ bảng nghiệp vụ (Đợt 1, 07/10/2026).
   API: GET /api/bao-cao/doi-chieu?thang=YYYY-MM → {thang, tu_ngay, den_ngay, can_doi:[dòng], kqkd:[dòng], loi_doc_du_lieu}
        dòng = {khoa, nhan, tk[], bang, so_cai, nghiep_vu, chenh,
                dang_dung: so_cai|nghiep_vu|khop|khac (Cân đối) · nghiep_vu|so_cai|tron|cong_thuc|chua_tinh (KQKD)}
        so_cai / nghiep_vu = null khi khoản mục không có nguồn đó (vd phải trả người lao động chỉ có ở sổ cái).
        Bảng KQKD: `nghiep_vu` là đúng con số đang hiện trên Kết quả kinh doanh.
   CHỈ HIỆN chênh — không có nút nào sửa số. Bấm mã TK → Sổ cái của TK đó trong đúng kỳ để truy ngược bút toán.
   Dải cảnh báo đầu trang dùng chung với 3 báo cáo: KT.ganCanhBao (kt-bao-cao.js). */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  if (!$('kd-kt-doi-chieu')) return;

  const homNay = KD.iso(new Date()).slice(0, 7);
  const MAC_DINH = { thang: homNay };
  const st = Object.assign({}, MAC_DINH, KT.url.doc());
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(st.thang || '') || st.thang > homNay) st.thang = homNay;
  const chuThang = (t) => t.slice(5, 7) + '/' + t.slice(0, 4);

  /* Ô tháng: 24 tháng gần nhất, không có tháng tương lai (số dư/phát sinh tương lai không có nghĩa).
     Link cũ trỏ tháng xa hơn vẫn mở được — thêm đúng tháng đó vào cuối danh sách. */
  (function dungOThang() {
    const ds = [];
    let y = +homNay.slice(0, 4), m = +homNay.slice(5, 7);
    for (let i = 0; i < 24; i += 1) { ds.push(y + '-' + String(m).padStart(2, '0')); if (--m === 0) { m = 12; y -= 1; } }
    if (!ds.includes(st.thang)) ds.push(st.thang);
    $('dc-thang').innerHTML = ds.map((t) => '<option value="' + t + '">Tháng ' + chuThang(t) + '</option>').join('');
    $('dc-thang').value = st.thang;
  })();

  // Cùng bản đồ nhãn + màu với nhãn nguồn trên 3 báo cáo (kt-bao-cao.js) — một trạng thái, một chữ, một màu.
  const DUNG = KT.NGUON_DUNG;
  const LECH = 1; // VND — dưới mức này coi như sai số làm tròn
  let luot = 0;

  // null = khoản mục không có nguồn đó (khác với số 0 — số 0 hiện "—" như mọi bảng số của app).
  const so = (v) => (v == null ? '<span class="kd-muted kt-dcs__khong">không có</span>' : KT.soBc(KD.so(v)));
  const bang0 = (v) => v == null || !Math.round(KD.so(v) || 0);
  function oChenh(r) {
    if (r.chenh == null) return '<span class="kd-muted">—</span>';
    const c = KD.so(r.chenh) || 0;
    return Math.abs(c) < LECH ? KT.tienSo(0) : '<b class="kt-dcs__lech">' + KT.soBc(c) + '</b>';
  }
  function lienTk(tk, d, laSoDu) {
    // Cân đối là số dư → sổ cái từ đầu năm tới cuối tháng; KQKD là phát sinh → đúng tháng.
    const tu = laSoDu ? d.den_ngay.slice(0, 4) + '-01-01' : d.tu_ngay;
    return tk.map((x) => '<a class="kt-tk-link" href="/ketoan/so-cai?' + KT.url.qs({ tk: x, ky: 'tuy_chinh', tu, den: d.den_ngay })
      + '" title="Mở sổ cái TK ' + esc(x) + '">' + esc(x) + '</a>').join(', ');
  }
  function veBang(pfx, ds, d, laSoDu) {
    const lech = ds.filter((r) => r.chenh != null && Math.abs(KD.so(r.chenh) || 0) >= LECH).length;
    const coDu = ds.filter((r) => r.chenh != null).length;
    const trong = ds.length > 0 && ds.every((r) => bang0(r.so_cai) && bang0(r.nghiep_vu));   // [].every() = true
    // Ghi kỳ ngay trên dòng tóm tắt: khi in, ô chọn tháng bị ẩn nên đây là chỗ duy nhất cho biết kỳ nào.
    const ky = (laSoDu ? 'Cuối tháng ' : 'Tháng ') + chuThang(d.thang) + ' · ';
    $(pfx + '-tom').innerHTML = esc(ky) + (trong ? '<span class="pill pill--muted">Chưa có số liệu trong tháng</span>'
      : !coDu ? '' : lech ? '<span class="pill pill--warning">' + KD.soDem(lech) + '/' + KD.soDem(coDu) + ' khoản mục lệch</span>'
        : '<span class="pill pill--success">Mọi khoản mục so được đều khớp</span>');
    if (!ds.length) {
      $(pfx + '-cuon').hidden = true;
      $(pfx + '-tt').innerHTML = KD.khoiRong('Không có khoản mục nào để đối chiếu',
        'Máy chủ không trả khoản mục nào cho tháng này. Bấm tải lại trang; vẫn trống thì báo bộ phận IT.');
      return;
    }
    $(pfx + '-cuon').hidden = false; $(pfx + '-tt').innerHTML = '';
    $(pfx + '-tbody').innerHTML = ds.map((r) => {
      const ca0 = r.so_cai != null && r.nghiep_vu != null && bang0(r.so_cai) && bang0(r.nghiep_vu);
      if (!DUNG[r.dang_dung]) console.warn('[doi-chieu] dang_dung chưa có nhãn:', r.dang_dung);
      const dung = ca0 && laSoDu ? DUNG.ca_hai_0 : (DUNG[r.dang_dung] || ['muted', 'Chưa đặt tên']);
      const lechDong = r.chenh != null && Math.abs(KD.so(r.chenh) || 0) >= LECH;
      const tip = r.bang ? (laSoDu ? 'Nguồn nghiệp vụ: ' + r.bang : r.bang) : '';
      return '<tr' + (lechDong ? ' class="kt-dcs--lech"' : '') + '>'
        + '<th scope="row">' + esc(r.nhan) + (tip ? KD.tip(tip) : '') + '</th>'
        + '<td>' + lienTk(r.tk || [], d, laSoDu) + '</td>'
        + '<td class="num">' + so(r.so_cai) + '</td><td class="num">' + so(r.nghiep_vu) + '</td>'
        + '<td class="num">' + oChenh(r) + '</td>'
        // Dòng lệch đã tô nền vàng nhạt → pill thêm viền (pill--vien) để không chìm vào nền dòng.
        + '<td><span class="pill pill--' + dung[0] + (lechDong ? ' pill--vien' : '') + '">' + esc(dung[1]) + '</span></td></tr>';
    }).join('');
  }

  async function tai() {
    const l = ++luot;
    KT.url.ghi(st, MAC_DINH);
    ['dc-cd', 'dc-kq'].forEach((p) => { $(p + '-cuon').hidden = false; $(p + '-tt').innerHTML = ''; $(p + '-tom').innerHTML = ''; $(p + '-tbody').innerHTML = KT.hangCho(6, 6); });
    // Xoá cả dataset.thang: canhBao() bỏ phản hồi đến muộn bằng cách so tháng này — để nguyên thì cảnh báo
    // của tháng cũ (đang bay về) vẫn khớp và hiện dưới ô tháng mới.
    const cb = $('dc-canh-bao'); cb.hidden = true; cb.innerHTML = ''; delete cb.dataset.thang;
    try {
      const d = await KD.api('/api/bao-cao/doi-chieu?' + KT.url.qs({ thang: st.thang }));
      if (l !== luot) return;
      $('dc-kq-cuon').closest('section').hidden = false;
      veBang('dc-cd', d.can_doi || [], d, true);
      veBang('dc-kq', d.kqkd || [], d, false);
      KT.ganCanhBao(cb, d.thang, 'doi_chieu', d);
    } catch (e) {
      if (l !== luot) return;
      // Một API cho cả hai bảng → một khối lỗi (ở thẻ đầu) + ẩn thẻ thứ hai, không để thẻ rỗng treo đó.
      ['dc-cd', 'dc-kq'].forEach((p) => { $(p + '-cuon').hidden = true; $(p + '-tt').innerHTML = ''; });
      $('dc-kq-cuon').closest('section').hidden = true;
      KD.khoiLoi($('dc-cd-tt'), 'Không tải được số đối chiếu', e, tai);
    }
  }

  $('dc-thang').addEventListener('change', (e) => { st.thang = e.target.value; tai(); });
  tai();
})();
