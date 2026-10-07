/* kt-doi-chieu.js — Đối chiếu sổ cái ↔ bảng nghiệp vụ (Đợt 1, 07/10/2026).
   API: GET /api/bao-cao/doi-chieu?thang=YYYY-MM → {thang, tu_ngay, den_ngay, can_doi:[dòng], kqkd:[dòng], loi_doc_du_lieu}
        dòng = {khoa, nhan, tk[], bang, so_cai, nghiep_vu, chenh, dang_dung: so_cai|nghiep_vu|khop|khac}
        so_cai / nghiep_vu = null khi khoản mục không có nguồn đó (vd phải trả người lao động chỉ có ở sổ cái).
   CHỈ HIỆN chênh — không có nút nào sửa số. Bấm mã TK → Sổ cái của TK đó trong đúng kỳ để truy ngược bút toán.
   Dải cảnh báo đầu trang dùng chung với 3 báo cáo: KT.ganCanhBao (kt-bao-cao.js). */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  if (!$('kd-kt-doi-chieu')) return;

  const MAC_DINH = { thang: KD.iso(new Date()).slice(0, 7) };
  const st = Object.assign({}, MAC_DINH, KT.url.doc());
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(st.thang || '')) st.thang = MAC_DINH.thang;
  $('dc-thang').value = st.thang;

  const DUNG = {
    so_cai: ['info', 'Sổ cái'], nghiep_vu: ['warning', 'Bảng nghiệp vụ'],
    khop: ['success', 'Khớp — hai nguồn bằng nhau'], khac: ['danger', 'Không khớp nguồn nào'],
  };
  const LECH = 1; // VND — dưới mức này coi như sai số làm tròn
  let luot = 0;

  // null = khoản mục không có nguồn đó (khác với số 0 — số 0 hiện "—" như mọi bảng số của app).
  const so = (v) => (v == null ? '<span class="kd-muted kt-dcs__khong">không có</span>' : KT.soBc(KD.so(v)));
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
    $(pfx + '-tom').innerHTML = coDu ? (lech ? '<span class="pill pill--warning">' + KD.soDem(lech) + '/' + KD.soDem(coDu) + ' khoản mục lệch</span>'
      : '<span class="pill pill--success">Mọi khoản mục so được đều khớp</span>') : '';
    if (!ds.length) { $(pfx + '-cuon').hidden = true; $(pfx + '-tt').innerHTML = KD.khoiRong('Không có khoản mục nào để đối chiếu', ''); return; }
    $(pfx + '-cuon').hidden = false; $(pfx + '-tt').innerHTML = '';
    $(pfx + '-tbody').innerHTML = ds.map((r) => {
      const ca0 = r.so_cai != null && r.nghiep_vu != null && !Math.round(KD.so(r.so_cai) || 0) && !Math.round(KD.so(r.nghiep_vu) || 0);
      const dung = ca0 ? ['muted', 'Cả hai bằng 0'] : (DUNG[r.dang_dung] || ['muted', 'Chưa đặt tên']);
      if (!DUNG[r.dang_dung]) console.warn('[doi-chieu] dang_dung chưa có nhãn:', r.dang_dung);
      const lechDong = r.chenh != null && Math.abs(KD.so(r.chenh) || 0) >= LECH;
      return '<tr' + (lechDong ? ' class="kt-dcs--lech"' : '') + '>'
        + '<th scope="row">' + esc(r.nhan) + (r.bang ? KD.tip('Bảng nghiệp vụ: ' + r.bang) : '') + '</th>'
        + '<td>' + lienTk(r.tk || [], d, laSoDu) + '</td>'
        + '<td class="num">' + so(r.so_cai) + '</td><td class="num">' + so(r.nghiep_vu) + '</td>'
        + '<td class="num">' + oChenh(r) + '</td>'
        + '<td><span class="pill pill--' + dung[0] + '">' + esc(dung[1]) + '</span></td></tr>';
    }).join('');
  }

  async function tai() {
    const l = ++luot;
    KT.url.ghi(st, MAC_DINH);
    ['dc-cd', 'dc-kq'].forEach((p) => { $(p + '-cuon').hidden = false; $(p + '-tt').innerHTML = ''; $(p + '-tom').innerHTML = ''; $(p + '-tbody').innerHTML = KT.hangCho(6, 6); });
    const cb = $('dc-canh-bao'); cb.hidden = true; cb.innerHTML = '';
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

  $('dc-thang').addEventListener('change', (e) => {
    if (!/^\d{4}-\d{2}$/.test(e.target.value)) return;
    st.thang = e.target.value; tai();
  });
  tai();
})();
