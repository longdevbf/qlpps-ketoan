/* kt-tscd.js — Tài sản cố định + khấu hao (khung: kt-danh-sach.js).
   API thật: app/routers/tai_san.py — GET /api/tai-san (mảng phẳng, KHÔNG phân trang) · GET /api/tai-san/{id}
   (khau_hao_logs thật) · GET /api/tai-san/khau-hao/{thang} (bút toán khấu hao của 1 tháng — tab "Lịch khấu hao"
   của màn cũ) · POST /api/tai-san/khau-hao/{thang} (idempotent — máy chủ tự bỏ qua tài sản đã trích tháng đó)
   · DELETE /api/tai-san/{id} (chỉ khi chưa khấu hao).
   Ghi chú:
   - Lấy TOÀN BỘ danh sách rồi lọc ở trình duyệt → thẻ số luôn = /api/tai-san/summary (mọi TSCĐ đang sử dụng),
     không đổi theo bộ lọc, giống màn cũ.
   - "Nhóm tài sản" là chữ tự do ở CSDL → ô lọc nạp từ chính các nhóm đang có.
   - "Đã khấu hao hết" không phải trạng thái thật, suy ra ở trình duyệt (so_thang_da_kh >= so_thang_kh).
   - "Lịch khấu hao" ở panel: các tháng ĐÃ trích lấy đúng số tiền thật từ khau_hao_logs; các tháng
     CHƯA tới là dự kiến theo đường thẳng (nguyên giá / so_thang_kh) — chưa phải số đã ghi sổ. */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-tscd')) return;
  // Quyền (F3 28/09): xoá TSCĐ = DELETE /api/tai-san/{id} chỉ admin/ceo (tai_san.py delete_tscd — hẹp hơn KD.coQuyen('ceo'), không gồm
  // trợ lý CEO). Thêm / sửa / thanh lý / trích khấu hao mở cho Kế toán (manager/kt) như API.
  const XOA_DUOC = ['admin', 'ceo'].includes(document.getElementById('kd-kt-tscd').dataset.vaiTroGoc);
  const H = KT.H, $ = (id) => document.getElementById(id);
  const TT = { dang_khau_hao: ['success', 'Đang khấu hao'], het_khau_hao: ['info', 'Đã khấu hao hết'], hong: ['danger', 'Hỏng / ngừng dùng'], da_thanh_ly: ['muted', 'Đã thanh lý'] };
  const pillTT = (k) => { const x = TT[k]; if (!x) console.warn('[TSCĐ] trạng thái chưa có nhãn:', k); return H.pill(x ? x[0] : 'muted', x ? x[1] : 'Chưa đặt tên'); };
  const nhanNhom = (v) => v || 'Chưa phân loại';
  const LOAI = { huu_hinh: 'Hữu hình', vo_hinh: 'Vô hình' };
  const BO_PHAN = { ban_hang: 'Bán hàng', quan_ly: 'Quản lý', tai_chinh: 'Tài chính', khac: 'Khác' };
  const BO_PHAN_TK = { ban_hang: '641', quan_ly: '642', tai_chinh: '635', khac: '811' };
  const thangChu = (m) => m.slice(5, 7) + '/' + m.slice(0, 4);
  const thangHomNay = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0'); };
  const congThangIso = (iso, n) => { const d = new Date(iso + 'T00:00:00'); const m = d.getMonth() + n; d.setMonth(m); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0'); };
  let khThang = null;

  /* Trạng thái hiển thị suy ra từ dữ liệu thật (API không trả "dang_khau_hao|het_khau_hao"). */
  function trangThaiHien(t) {
    if (t.trang_thai === 'da_thanh_ly') return 'da_thanh_ly';
    if (t.trang_thai === 'hong') return 'hong';
    return t.so_thang_da_kh >= t.so_thang_kh ? 'het_khau_hao' : 'dang_khau_hao';
  }

  /* Nạp ô "Nhóm tài sản" từ dữ liệu thật, giữ giá trị đang lọc (kể cả nhóm trên URL không còn trong dữ liệu —
     để ô lọc không hiện "Tất cả" trong khi bảng vẫn đang lọc theo nhóm đó). */
  function napNhom(tatCa, dangChon) {
    const nhom = [...new Set(tatCa.map((r) => r.nhom || '').concat(dangChon && dangChon !== '__trong' ? [dangChon] : []))].sort((a, b) => a.localeCompare(b, 'vi'));
    H.napChon($('ts-nhom'), nhom.map((v) => [v || '__trong', nhanNhom(v)]), 'Tất cả', dangChon);
  }

  // Tiền VND nguyên: CSDL lưu hao mòn/KH tháng có 2 số lẻ → làm tròn TỪNG tài sản và lấy Còn lại =
  // Nguyên giá − Hao mòn (đã tròn), để dòng Cộng/thẻ = tổng các số đang hiện (QA nhất quán 25/09: lệch 1đ).
  const R = (v) => Math.round(Number(v) || 0);
  function chuyen(mang, q) {
    const tatCa = mang.map((t) => ({
      id: t.id, ma: t.ma_tscd, ten: t.ten_tscd, ncc: t.ncc, bo_phan: t.bo_phan, nhom: t.nhom, loai: t.loai,
      ngay_mua: t.ngay_mua, ngay_dung: t.ngay_su_dung, nguyen_gia: R(t.nguyen_gia), so_thang: t.so_thang_kh, so_thang_da: t.so_thang_da_kh,
      kh_thang: R(t.so_tien_kh_thang), hao_mon: R(t.hao_mon_luy_ke), con_lai: R(t.nguyen_gia) - R(t.hao_mon_luy_ke),
      tk_cp: BO_PHAN_TK[t.bo_phan] || '642', trang_thai_goc: t.trang_thai,
      trang_thai: trangThaiHien(t), thanh_ly: t.ngay_thanh_ly,
    }));
    napNhom(tatCa, q.nhom);
    const tim = q.tim || '';
    const dong = tatCa.filter((r) => (!q.loai || r.loai === q.loai)
      && (!q.nhom || (q.nhom === '__trong' ? !r.nhom : r.nhom === q.nhom))
      && (!q.bo_phan || r.bo_phan === q.bo_phan)
      // "Đang sử dụng" (như màn cũ) = trạng thái lưu CSDL, gồm cả đang khấu hao lẫn đã khấu hao hết.
      && (!q.trang_thai || (q.trang_thai === 'dang_su_dung' ? r.trang_thai_goc === 'dang_su_dung' : r.trang_thai === q.trang_thai))
      && KT.khopTim([r.ma, r.ten, r.ncc], tim));
    const dangDung = tatCa.filter((r) => r.trang_thai_goc === 'dang_su_dung');
    const cong = (ds, k) => ds.reduce((s, r) => s + r[k], 0);
    const tong = {
      nguyen_gia: cong(dangDung, 'nguyen_gia'), hao_mon: cong(dangDung, 'hao_mon'), con_lai: cong(dangDung, 'con_lai'),
      kh_thang: cong(dangDung.filter((r) => r.trang_thai === 'dang_khau_hao'), 'kh_thang'),
      so_ts: dangDung.length, so_thanh_ly: tatCa.filter((r) => r.trang_thai_goc === 'da_thanh_ly').length, so_hong: tatCa.filter((r) => r.trang_thai_goc === 'hong').length,
      dang_kh: dangDung.filter((r) => r.trang_thai === 'dang_khau_hao'),
      hien: { nguyen_gia: cong(dong, 'nguyen_gia'), kh_thang: cong(dong, 'kh_thang'), hao_mon: cong(dong, 'hao_mon'), con_lai: cong(dong, 'con_lai') },
    };
    return { dong, tong };
  }

  /* Bút toán khấu hao theo tháng — nhớ theo tháng: đổi bộ lọc danh sách (lọc ở trình duyệt) không gọi lại; xoá nhớ khi
     trích / xoá tài sản. Bản trước mỗi lần đổi 1 ô lọc gọi /khau-hao/<tháng này> thêm 1 lần, lúc mở màn gọi 2 lần. */
  let khNho = {};
  const layKh = (thang, moi) => {
    if (moi || !khNho[thang]) khNho[thang] = KD.api('/api/tai-san/khau-hao/' + thang).catch((e) => { delete khNho[thang]; throw e; });
    return khNho[thang];
  };
  /* Tháng đã trích chưa: so tài sản đang khấu hao với log của tháng đó. */
  async function daTrichThang(thang, dangKh, moi) {
    const r = await layKh(thang, moi);
    const daCo = new Set((r.items || []).map((x) => x.tscd_id));
    return { thang, con: dangKh.filter((t) => !daCo.has(t.id)), n_da: daCo.size };
  }

  const MAC_DINH = { tim: '', loai: '', nhom: '', bo_phan: '', trang_thai: '', page: 1, size: 20, sort: '' };
  const ds = KT.danhSach({
    pfx: 'ts', api: () => '/api/tai-san', donVi: 'tài sản', khongTrang: true, chuyen,
    macDinh: MAC_DINH,
    cot: [
      // Gọn cột (đợt 4): mã · nhóm thành dòng phụ dưới tên; loại, bộ phận, NCC xem ở panel chi tiết; "đã trích x/y tháng" dưới KH/tháng.
      { key: 'ten', nhan: 'Tài sản', ve: (r) => H.ten(r.ten, [r.ma, nhanNhom(r.nhom)].join(' · ')) },
      { key: 'ngay_dung', nhan: 'Ngày dùng', ve: (r) => KD.ngay(r.ngay_dung) + (r.ngay_mua && r.ngay_mua !== r.ngay_dung ? '<span class="kt-khach__ma">Mua ' + KD.ngay(r.ngay_mua) + '</span>' : '') },
      { key: 'nguyen_gia', nhan: 'Nguyên giá', num: true, ve: (r) => KD.tien(r.nguyen_gia) },
      { key: 'kh_thang', nhan: 'Khấu hao/tháng', num: true, ve: (r) => H.tien(r.kh_thang) + '<span class="kt-khach__ma">Đã trích ' + KD.soDem(r.so_thang_da) + '/' + KD.soDem(r.so_thang) + ' tháng</span>' },
      { key: 'hao_mon', nhan: 'Hao mòn luỹ kế', num: true, ve: (r) => KD.tien(r.hao_mon) },
      { key: 'con_lai', nhan: 'Còn lại', num: true, cls: 'kt-so--con', ve: (r) => H.tien(r.con_lai) },
      { key: 'tt', nhan: 'Trạng thái', ve: (r) => pillTT(r.trang_thai) },
      { key: 'act', nhan: 'Thao tác', act: true, nhanDong: (r) => r.ma },
    ],
    kpi: {
      nguyen_gia: (d) => ({ v: H.tienKpi(d.tong.nguyen_gia), title: KD.tienVnd(d.tong.nguyen_gia), phu: KD.soDem(d.tong.so_ts) + ' đang dùng' + KD.tip(KD.soDem(d.tong.so_thanh_ly) + ' đã thanh lý · ' + KD.soDem(d.tong.so_hong) + ' hỏng. Thẻ số tính trên mọi tài sản đang dùng, không theo bộ lọc.') }),
      hao_mon: (d) => ({ v: H.tienKpi(d.tong.hao_mon), title: KD.tienVnd(d.tong.hao_mon), phu: d.tong.nguyen_gia ? KD.phanTram(d.tong.hao_mon / d.tong.nguyen_gia * 100) + ' nguyên giá' : '' }),
      con_lai: (d) => ({ v: H.tienKpi(d.tong.con_lai), title: KD.tienVnd(d.tong.con_lai), phu: 'Nguyên giá − hao mòn' }),
      kh_thang: (d) => ({ v: H.tienKpi(d.tong.kh_thang), title: KD.tienVnd(d.tong.kh_thang),
        phu: khThang ? (khThang.da_trich ? H.pill('success', 'Đã trích ' + thangChu(khThang.thang)) : H.pill('warning', 'Chưa trích ' + thangChu(khThang.thang))) : '' }),
    },
    cong: (d) => [{ html: 'Cộng (' + KD.soDem(d.dong.length) + ' tài sản)', span: 2 }, { html: KD.tien(d.tong.hien.nguyen_gia), num: true }, { html: KD.tien(d.tong.hien.kh_thang), num: true }, { html: KD.tien(d.tong.hien.hao_mon), num: true }, { html: KD.tien(d.tong.hien.con_lai), num: true }, { html: '' }, { html: '' }],
    rong: (d, coLoc) => (coLoc ? ['Không có tài sản nào khớp bộ lọc', 'Thử bỏ bớt điều kiện lọc.'] : ['Chưa có tài sản cố định nào', 'Bấm "Thêm tài sản" để ghi tăng tài sản đầu tiên — hệ thống sẽ tự tính khấu hao hằng tháng.']),
    loi: 'Không tải được danh sách tài sản',
    sauTai: (d) => {
      const thang = thangHomNay(), dangKh = d.tong.dang_kh;
      const b = $('ts-trich'), chu = $('ts-trich-chu');
      khThang = { thang, da_trich: dangKh.length === 0 };
      chu.textContent = 'Trích khấu hao'; b.disabled = dangKh.length === 0;
      daTrichThang(thang, dangKh).then((r) => {
        khThang = { thang, da_trich: r.con.length === 0 && dangKh.length > 0 };
        const el = document.querySelector('#ts-kpi [data-kpi="kh_thang"] [data-phu]');
        if (el) el.innerHTML = khThang.da_trich ? H.pill('success', 'Đã trích ' + thangChu(thang)) : H.pill('warning', 'Chưa trích ' + thangChu(thang));
      }).catch(() => { /* không chặn màn — thẻ số chỉ thiếu nhãn tình trạng tháng */ });
    },
    khiLoi: () => { $('ts-trich').disabled = true; },
    panel: {
      tai: (r) => '/api/tai-san/' + encodeURIComponent(r.id),
      ve: (t) => {
        const nguyenGia = +t.nguyen_gia, soThoiGian = t.so_thang_kh, khThangSo = +t.so_tien_kh_thang;
        const logs = (t.khau_hao_logs || []).slice().sort((a, b) => (a.thang < b.thang ? -1 : 1));
        const lich = []; let luyKe = 0;
        for (let i = 0; i < soThoiGian; i++) {
          const daGhi = i < logs.length;
          const soTien = daGhi ? +logs[i].so_tien : Math.min(khThangSo, Math.max(0, nguyenGia - luyKe));
          luyKe = daGhi ? +logs[i].hao_mon_luy_ke_sau : Math.min(nguyenGia, luyKe + soTien);
          lich.push({ thang: daGhi ? logs[i].thang : congThangIso(t.ngay_su_dung, i), khau_hao: soTien, luy_ke: luyKe, con_lai: nguyenGia - luyKe, da_trich: daGhi });
        }
        // Làm tròn theo luỹ kế (như trang chi tiết): khấu hao tháng = luỹ kế tròn − luỹ kế tròn tháng trước → cột tự cộng khớp.
        let lkTruoc = 0; lich.forEach((x) => { const lk = Math.round(x.luy_ke); x.khau_hao = lk - lkTruoc; x.luy_ke = lk; x.con_lai = Math.round(nguyenGia) - lk; lkTruoc = lk; });
        const hienTai = lich.findIndex((x) => !x.da_trich);
        const tu = Math.max(0, (hienTai < 0 ? lich.length : hienTai) - 3), doanLich = lich.slice(tu, tu + 7);
        const trangThaiHT = trangThaiHien({ trang_thai: t.trang_thai, so_thang_da_kh: logs.length, so_thang_kh: soThoiGian });
        return H.dauPanel('bi-building', trangThaiHT === 'dang_khau_hao' ? 'success' : 'info', t.ma_tscd, esc(t.ten_tscd), pillTT(trangThaiHT))
          + H.kv([['Nhóm', esc(nhanNhom(t.nhom))], ['Loại', esc(LOAI[t.loai] || t.loai)], ['Bộ phận sử dụng', esc(BO_PHAN[t.bo_phan] || t.bo_phan)], t.ncc ? ['Nhà cung cấp', esc(t.ncc)] : null,
            ['Ngày mua', KD.ngay(t.ngay_mua)], ['Ngày đưa vào dùng', KD.ngay(t.ngay_su_dung)], ['Thời gian khấu hao', KD.soDem(soThoiGian) + ' tháng (đường thẳng)'], ['TK chi phí', esc(BO_PHAN_TK[t.bo_phan] || '642')],
            t.ngay_thanh_ly ? ['Ngày thanh lý', KD.ngay(t.ngay_thanh_ly)] : null])
          + H.khoi('bi-cash-stack', 'Giá trị', H.kv([['Nguyên giá', KD.tienVnd(nguyenGia)], +t.chi_phi_lap_dat ? ['Trong đó lắp đặt', KD.tienVnd(t.chi_phi_lap_dat)] : null, ['Hao mòn luỹ kế', KD.tienVnd(t.hao_mon_luy_ke)], ['Giá trị còn lại', KD.tienVnd(t.gia_tri_con_lai), true], ['Khấu hao mỗi tháng', KD.tienVnd(khThangSo)]]))
          + H.khoi('bi-calendar3', 'Lịch khấu hao', (doanLich.length ? '<p class="kd-meta">Dòng tô xanh là kỳ tới; tháng sau đó là dự kiến</p>' : '') + (doanLich.length ? '<div class="kd-table-scroll"><table class="kt-bang-nho"><thead><tr><th scope="col">Tháng</th><th scope="col" class="num">Khấu hao</th><th scope="col" class="num">Luỹ kế</th><th scope="col" class="num">Còn lại</th></tr></thead><tbody>'
            + doanLich.map((x, i) => '<tr class="' + (x.da_trich ? '' : 'is-cho') + (tu + i === hienTai ? ' is-nay' : '') + '"><td' + (tu + i === hienTai ? ' title="Kỳ tới"' : '') + '>' + thangChu(x.thang) + '</td><td class="num">' + KD.tien(x.khau_hao) + '</td><td class="num">' + KD.tien(x.luy_ke) + '</td><td class="num">' + KD.tien(x.con_lai) + '</td></tr>').join('') + '</tbody></table></div>' : KD.khoiRong('Không có lịch khấu hao', '')));
      },
      nut: (t) => '<a class="kd-btn kd-btn--grow" href="/ketoan/tscd/chi-tiet?id=' + t.id + '"><i class="bi bi-box-arrow-up-right" aria-hidden="true"></i>Mở trang chi tiết</a>',
    },
    chiTiet: (r) => '/ketoan/tscd/chi-tiet?id=' + r.id,
    menu: (r) => [
      // Xem chi tiết = popup giữa màn như bấm dòng (anh Quang 28/09/2026); trang chi tiết đầy đủ vẫn mở được ở mục kế.
      { nhan: 'Xem chi tiết', icon: 'bi-eye', onClick: () => { const tr = document.querySelector('#ts-tbody tr[data-id="' + CSS.escape(String(r.id)) + '"]'); if (tr) tr.click(); } },
      { nhan: 'Mở trang chi tiết', icon: 'bi-box-arrow-up-right', href: '/ketoan/tscd/chi-tiet?id=' + r.id },
      { nhan: 'Sửa thông tin tài sản', icon: 'bi-pencil', href: '/ketoan/tscd/phieu?id=' + r.id },
      { nhan: 'Xem sổ cái TK 211', icon: 'bi-journal-text', href: '/ketoan/so-cai?tk=211&ky=nam_nay' },
      '-',
      r.trang_thai_goc === 'dang_su_dung' ? { nhan: 'Ghi giảm / thanh lý', icon: 'bi-box-arrow-right', href: '/ketoan/tscd/phieu?id=' + r.id + '&che_do=thanh_ly', danger: true }
        : r.thanh_ly ? { nhan: 'Đã thanh lý ' + KD.ngay(r.thanh_ly), icon: 'bi-info-circle' } : null,
      XOA_DUOC ? { nhan: 'Xoá tài sản', icon: 'bi-trash', danger: true, onClick: () => moXoa(r) } : null,
    ].filter(Boolean),
  });

  /* ── Xoá (chỉ khi chưa khấu hao — máy chủ tự chặn) ── */
  const dXoa = $('ts-dlg-xoa'); let xoaDang = null;
  function moXoa(r) {
    xoaDang = r;
    $('ts-xoa-td').textContent = 'Xoá tài sản ' + r.ma + '?';
    $('ts-xoa-nd').textContent = r.so_thang_da > 0
      ? 'Tài sản đã trích khấu hao ' + KD.soDem(r.so_thang_da) + ' tháng — máy chủ sẽ không cho xoá. Dùng "Ghi giảm / thanh lý" thay thế.'
      : 'Xoá hẳn "' + r.ten + '" khỏi danh sách. Chỉ xoá được khi tài sản chưa trích khấu hao tháng nào.';
    $('ts-xoa-ok').disabled = r.so_thang_da > 0;
    KD.moHopThoai(dXoa);
  }
  $('ts-xoa-ok').addEventListener('click', async () => {
    if (!xoaDang) return; const nut = $('ts-xoa-ok'); nut.disabled = true;
    try {
      await KD.api('/api/tai-san/' + xoaDang.id, { method: 'DELETE', headers: { Accept: 'application/json' } });
      dXoa.close(); window.showToast && window.showToast('ok', 'Đã xoá ' + xoaDang.ma); ds.dongPanel(); khNho = {}; ds.tai(); taiKh();
    } catch (e) { KD.baoLoiHopThoai(dXoa, 'Chưa xoá được: ' + e.message); } finally { nut.disabled = false; }
  });

  /* ── Trích khấu hao theo tháng chọn (POST /api/tai-san/khau-hao/{thang}, idempotent) ── */
  const dlg = $('ts-dlg'); let trichDang = null;
  async function veTrich() {
    const d = ds.duLieu(); const thang = $('ts-dlg-thang').value; const ok = $('ts-dlg-ok');
    ok.disabled = true; trichDang = null;
    if (!d || !thang) return;
    $('ts-dlg-td').textContent = 'Trích khấu hao tháng ' + thangChu(thang) + '?';
    $('ts-dlg-nd').textContent = 'Đang kiểm tra tháng ' + thangChu(thang) + '…'; $('ts-dlg-dk').innerHTML = '';
    try {
      // Tài sản đưa vào dùng sau tháng này thì chưa trích (máy chủ cũng bỏ qua).
      const r = await daTrichThang(thang, d.tong.dang_kh.filter((t) => (t.ngay_dung || '').slice(0, 7) <= thang), true);
      if ($('ts-dlg-thang').value !== thang) return;
      const tong = r.con.reduce((s, t) => s + t.kh_thang, 0);
      if (!r.con.length) { $('ts-dlg-nd').textContent = 'Tháng ' + thangChu(thang) + ' không còn tài sản nào cần trích' + (r.n_da ? ' — đã trích ' + KD.soDem(r.n_da) + ' tài sản.' : '.'); return; }
      const theoTk = {}; r.con.forEach((t) => { theoTk[t.tk_cp] = (theoTk[t.tk_cp] || 0) + t.kh_thang; });
      $('ts-dlg-nd').textContent = 'Ghi sổ khoảng ' + KD.tienVnd(Math.round(tong)) + ' khấu hao cho ' + KD.soDem(r.con.length) + ' tài sản' + (r.n_da ? ' (bỏ qua ' + KD.soDem(r.n_da) + ' tài sản đã trích tháng này)' : '') + '.';
      $('ts-dlg-dk').innerHTML = Object.keys(theoTk).map((tk) => '<tr><td><span class="kt-tk">' + tk + '</span></td><td class="num">' + KD.tien(theoTk[tk]) + '</td><td class="num">' + KT.tienSo(0) + '</td></tr>').join('')
        + '<tr><td><span class="kt-tk">214</span><span class="kt-dk__phu">Hao mòn tài sản cố định</span></td><td class="num">' + KT.tienSo(0) + '</td><td class="num">' + KD.tien(tong) + '</td></tr>';
      trichDang = thang; ok.disabled = false;
    } catch (e) { $('ts-dlg-nd').textContent = 'Không kiểm tra được tháng này: ' + e.message; }
  }
  $('ts-trich').addEventListener('click', () => {
    if (!ds.duLieu()) return;
    $('ts-dlg-thang').value = thangHomNay(); KD.moHopThoai(dlg); veTrich();
  });
  $('ts-dlg-thang').addEventListener('change', veTrich);
  $('ts-dlg-ok').addEventListener('click', async () => {
    if (!trichDang) return; const nut = $('ts-dlg-ok'); nut.disabled = true; const thang = trichDang;
    try {
      const r = await KD.api('/api/tai-san/khau-hao/' + thang, KD.JSON_POST({}));
      dlg.close();
      const boQua = (r.skipped || []).length;
      window.showToast && window.showToast('ok', 'Khấu hao ' + thangChu(thang) + ': ghi sổ ' + r.da_xu_ly + ' tài sản — tổng ' + KD.tienVnd(r.tong_kh) + (boQua ? ' · bỏ qua ' + boQua : ''));
      khNho = {}; ds.tai(); $('ts-kh-thang').value = thang; taiKh();
    } catch (e) { KD.baoLoiHopThoai(dlg, 'Chưa ghi sổ được: ' + e.message); nut.disabled = false; }
  });

  /* ── Khấu hao theo tháng (tab "Lịch khấu hao" của màn cũ) — GET /api/tai-san/khau-hao/{thang} ── */
  /* Tháng đang xem giữ trên URL (?thang_kh=YYYY-MM, bỏ khi là tháng này) — F5 / gửi link mở đúng tháng.
     Ghi chung vào ds.st để lần tải danh sách sau không xoá mất khoá này khỏi URL. */
  let luotKh = 0;
  const THANG_RE = /^\d{4}-(0[1-9]|1[0-2])$/;
  function ghiThangKh(thang) {
    ds.st.thang_kh = thang !== thangHomNay() ? thang : '';
    KT.url.ghi(ds.st, Object.assign({}, MAC_DINH, { ky: 'thang_nay' }));
  }
  async function taiKh() {
    const thang = $('ts-kh-thang').value || thangHomNay(), l = ++luotKh;
    ghiThangKh(thang);
    $('ts-kh-tbody').innerHTML = KT.hangCho(4, 2); $('ts-kh-tfoot').innerHTML = ''; $('ts-kh-tt').innerHTML = ''; $('ts-kh-cuon').hidden = false; $('ts-kh-tong').textContent = '';
    try {
      const d = await layKh(thang); if (l !== luotKh) return;
      const items = d.items || [];
      $('ts-kh-tong').textContent = items.length ? 'Tháng ' + thangChu(thang) + ': ' + KD.soDem(items.length) + ' tài sản · tổng ' + KD.tienVnd(d.tong_kh) : '';
      if (!items.length) { $('ts-kh-cuon').hidden = true; $('ts-kh-tt').innerHTML = KD.khoiRong('Tháng ' + thangChu(thang) + ' chưa trích khấu hao', 'Bấm "Trích khấu hao" ở đầu trang để ghi sổ tháng này.'); return; }
      $('ts-kh-tbody').innerHTML = items.map((x) => '<tr><td>' + H.ten(x.ten_tscd || '', [x.ma_tscd, nhanNhom(x.nhom), BO_PHAN[x.bo_phan] || x.bo_phan].filter(Boolean).join(' · ')) + '</td>'
        + '<td class="num">' + KD.tien(x.so_tien) + '</td><td class="num">' + KD.tien(x.hao_mon_luy_ke_sau) + '</td><td>' + (x.journal_id ? '#' + x.journal_id : '—') + (x.created_at ? '<span class="kt-khach__ma">Ghi ' + KD.ngay(String(x.created_at).slice(0, 10)) + '</span>' : '') + '</td></tr>').join('');
      $('ts-kh-tfoot').innerHTML = '<tr><th scope="row">Cộng tháng ' + thangChu(thang) + '</th><td class="num">' + KD.tien(d.tong_kh) + '</td><td colspan="2"></td></tr>';
    } catch (e) { if (l !== luotKh) return; $('ts-kh-cuon').hidden = true; KD.khoiLoi($('ts-kh-tt'), 'Không tải được khấu hao tháng', e, taiKh); }
  }
  $('ts-kh-thang').value = THANG_RE.test(ds.st.thang_kh || '') ? ds.st.thang_kh : thangHomNay();
  $('ts-kh-thang').addEventListener('change', taiKh);
  ds.tai(); taiKh();
})();
