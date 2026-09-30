/* kt-cdkt.js — Báo cáo tình hình tài chính B01-DN (khung: kt-bao-cao.js).
   API thật: GET /api/bao-cao/can-doi?thang=YYYY-MM (app/routers/bao_cao_can_doi.py — cùng API màn cũ #can-doi)
   trả {thang, tai_san:{tien_va_td:{tk_ngan_hang,tien_mat_so_quy,tong},phai_thu,hang_ton_kho,
   tscd_nguyen_gia,tscd_hao_mon_luy_ke,tscd_rong,tong_tai_san}, nguon_von:{no_phai_tra:{...},
   von_csh:{...},tong_nguon_von}, check:{lech,can_bang,warning}}.
   - API chốt số CUỐI THÁNG → ngày chọn được quy về tháng chứa ngày đó.
   - Cột "Số đầu năm" = số dư cuối tháng 12 năm trước (gọi thêm /can-doi?thang=(năm-1)-12, song song).
   - Khối "Cơ cấu tài sản / nguồn vốn" = 2 biểu đồ tròn của màn cũ (vẽ thanh xếp chồng + chú giải). */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-cdkt')) return;
  const $ = (id) => document.getElementById(id);
  const H = KT.H;

  const homNay = () => KD.iso(new Date());
  const thangCuaNgay = (den) => (/^\d{4}-\d{2}-\d{2}$/.test(den || '') ? den : homNay()).slice(0, 7);
  const cuoiThang = (thang) => { const [y, m] = thang.split('-').map(Number); return KD.iso(new Date(y, m, 0)); };
  const thangDauNam = (thang) => (+thang.slice(0, 4) - 1) + '-12';

  /* Giá trị của từng mã số từ 1 snapshot /can-doi */
  function giaTri(d0) {
    const ts = d0.tai_san, nv = d0.nguon_von, no = nv.no_phai_tra, v = nv.von_csh;
    return {
      110: ts.tien_va_td.tong, 111: ts.tien_va_td.tien_mat_so_quy, 112: ts.tien_va_td.tk_ngan_hang,
      130: ts.phai_thu, 140: ts.hang_ton_kho, 220: ts.tscd_rong, 221: ts.tscd_nguyen_gia, 222: -ts.tscd_hao_mon_luy_ke, 270: ts.tong_tai_san,
      311: no.phai_tra_ncc, 320: no.vay_ngan_han, 338: no.vay_dai_han, 315: no.phai_tra_nv, 300: no.tong,
      411: v.von_gop, 414: v.quy_dn, 421: v.ln_giu_lai, 400: v.tong, 440: nv.tong_nguon_von,
    };
  }
  const KHUNG = [
    ['', 'TÀI SẢN', 'nhom'],
    ['110', 'Tiền và các khoản tương đương tiền', 'tong'], ['111', 'Tiền mặt (sổ quỹ)', 'con'], ['112', 'Tiền gửi ngân hàng', 'con'],
    ['130', 'Các khoản phải thu ngắn hạn (gồm tạm ứng)', 'tong'], ['140', 'Hàng tồn kho', 'tong'],
    ['220', 'Tài sản cố định', 'tong'], ['221', 'Nguyên giá', 'con'], ['222', 'Giá trị hao mòn luỹ kế (*)', 'con'],
    ['270', 'TỔNG CỘNG TÀI SẢN', 'dam'],
    ['', 'NGUỒN VỐN', 'nhom'],
    ['311', 'Phải trả người bán ngắn hạn', 'muc'], ['315', 'Phải trả người lao động', 'muc'],
    ['320', 'Vay và nợ thuê tài chính ngắn hạn', 'muc'], ['338', 'Vay và nợ thuê tài chính dài hạn', 'muc'],
    ['300', 'Tổng nợ phải trả', 'tong'],
    ['411', 'Vốn góp của chủ sở hữu', 'muc'], ['414', 'Quỹ đầu tư phát triển và quỹ khác', 'muc'], ['421', 'Lợi nhuận sau thuế chưa phân phối', 'muc'],
    ['400', 'Tổng vốn chủ sở hữu', 'tong'],
    ['440', 'TỔNG CỘNG NGUỒN VỐN', 'dam'],
  ];

  /* Tiền VND là số nguyên: làm tròn từng LÁ rồi cộng lại mọi dòng tổng + chênh lệch từ chính số đã làm tròn,
     để trên bảng 110 = 111 + 112, 270 = 110 + 130 + 140 + 220, 440 = 300 + 400, chênh lệch = 270 − 440
     đúng tới từng đồng (API trả số lẻ thập phân → làm tròn riêng từng dòng từng lệch 1đ). */
  function lamTron(d0) {
    const R = Math.round, ts = d0.tai_san, td = ts.tien_va_td, nv = d0.nguon_von, no = nv.no_phai_tra, v = nv.von_csh;
    td.tk_ngan_hang = R(td.tk_ngan_hang); td.tien_mat_so_quy = R(td.tien_mat_so_quy); td.tong = td.tk_ngan_hang + td.tien_mat_so_quy;
    ts.phai_thu = R(ts.phai_thu); ts.hang_ton_kho = R(ts.hang_ton_kho);
    ts.tscd_nguyen_gia = R(ts.tscd_nguyen_gia); ts.tscd_hao_mon_luy_ke = R(ts.tscd_hao_mon_luy_ke); ts.tscd_rong = ts.tscd_nguyen_gia - ts.tscd_hao_mon_luy_ke;
    ts.tong_tai_san = td.tong + ts.phai_thu + ts.hang_ton_kho + ts.tscd_rong;
    ['phai_tra_ncc', 'vay_ngan_han', 'vay_dai_han', 'phai_tra_nv'].forEach((x) => { no[x] = R(no[x] || 0); });
    no.tong = no.phai_tra_ncc + no.vay_ngan_han + no.vay_dai_han + no.phai_tra_nv;
    ['von_gop', 'quy_dn', 'ln_giu_lai'].forEach((x) => { v[x] = R(v[x] || 0); });
    v.tong = v.von_gop + v.quy_dn + v.ln_giu_lai;
    nv.tong_nguon_von = no.tong + v.tong;
    d0.check.lech = ts.tong_tai_san - nv.tong_nguon_von; d0.check.can_bang = !d0.check.lech;
    return d0;
  }
  /* Lý do bảng chưa cân — theo đúng số API trả: thiếu nguồn vốn nào thì nói nguồn đó (không suy diễn số). */
  function lyDoLech(d0) {
    const v = d0.nguon_von.von_csh, ly = [];
    if (!v.von_gop) ly.push('chưa ghi vốn góp chủ sở hữu');
    if (!v.ln_giu_lai) ly.push('chưa chốt kỳ nên lợi nhuận chưa phân phối (421) = 0');
    if (!v.quy_dn) ly.push('các quỹ đang bằng 0');
    return ly.length ? 'Nguyên nhân: ' + ly.join('; ') + '. Cần khai số dư đầu kỳ, vốn góp và chốt kỳ.' : (d0.check.warning || 'Kiểm tra bút toán thiếu vế ở Sổ kế toán.');
  }
  function chuyen(ds, k) {
    ds.forEach((x) => x && lamTron(x));
    const [d0, dn] = ds, a = giaTri(d0), b = dn ? giaTri(dn) : {};
    const ts = d0.tai_san, nv = d0.nguon_von;
    const tsNganHan = ts.tien_va_td.tong + ts.phai_thu + ts.hang_ton_kho;
    const noNganHan = nv.no_phai_tra.phai_tra_ncc + nv.no_phai_tra.vay_ngan_han + nv.no_phai_tra.phai_tra_nv;
    const chon = k.den || homNay(), cuoi = cuoiThang(d0.thang);
    return {
      den_ngay: chon < cuoi ? chon : cuoi, thang: d0.thang, thang_dau_nam: dn ? dn.thang : null, raw: d0,
      dong: KHUNG.map(([ma, chi_tieu, cap]) => (cap === 'nhom' ? { ma, chi_tieu, cap } : { ma, chi_tieu, cap, cuoi_ky: a[ma], dau_nam: dn ? b[ma] : null }))
        .concat(Math.abs(d0.check.lech || 0) >= 1 || (dn && Math.abs(dn.check.lech || 0) >= 1)
          ? [{ ma: '', chi_tieu: 'Chênh lệch chưa cân (Tài sản − Nguồn vốn)', ghi_chu: lyDoLech(d0), cap: 'lech', cuoi_ky: d0.check.lech || 0, dau_nam: dn ? dn.check.lech || 0 : null }] : []),
      tong: { tai_san: ts.tong_tai_san, no_phai_tra: nv.no_phai_tra.tong, von_chu: nv.von_csh.tong },
      chi_so: {
        tien_tren_ts: ts.tong_tai_san ? ts.tien_va_td.tong / ts.tong_tai_san : 0,
        no_tren_von: nv.von_csh.tong ? nv.no_phai_tra.tong / nv.von_csh.tong : null,
        thanh_toan_hien_hanh: noNganHan ? tsNganHan / noNganHan : 0,
      },
      kiem: { lech: d0.check.lech, can_bang: d0.check.can_bang, canh_bao: d0.check.warning },
      // 30/09/2026 (quyết định người dùng): 311 CHỈ cộng nợ NCC thực+cần kiểm — dự kiến (chưa
      // chốt) và cần kiểm (khoản mất PO) không lộ ra ở dòng 311 nào cả, phải ghi chú riêng dưới
      // bảng để người dùng không tưởng nợ NCC chỉ có 311. Giá trị lấy thẳng từ API, KHÔNG tính lại.
      ncc_du_kien: nv.no_phai_tra.phai_tra_ncc_du_kien || 0,
      ncc_can_kiem: nv.no_phai_tra.phai_tra_ncc_can_kiem || 0,
    };
  }

  /* Cơ cấu (thay 2 biểu đồ tròn màn cũ) — chỉ lấy khoản dương như màn cũ */
  const MAU = ['var(--brand, #2563eb)', 'var(--info, #0e7490)', 'var(--warning, #b45309)', 'var(--tile-violet, #7c3aed)', 'var(--success, #15803d)', 'var(--danger, #b91c1c)'];
  function veCoCau(el, ds) {
    const cc = ds.map((x, i) => x.concat(MAU[i % MAU.length])).filter((x) => x[1] > 0), tong = cc.reduce((s, x) => s + x[1], 0);
    /* % 1 chữ số thập phân chia theo phần dư lớn nhất → các % cộng đúng 100% */
    const g = cc.map((x) => (tong ? x[1] / tong * 1000 : 0)), s0 = g.map(Math.floor);
    let du = (tong ? 1000 : 0) - s0.reduce((a, x) => a + x, 0);
    g.map((x, i) => [x - s0[i], i]).sort((a, b2) => b2[0] - a[0]).forEach(([, i]) => { if (du > 0) { s0[i] += 1; du -= 1; } });
    cc.forEach((x, i) => { x[3] = s0[i] / 10; });
    el.innerHTML = !tong ? KD.khoiRong('Không có số dư dương để vẽ cơ cấu', '') : '<div class="kt-cc__thanh" role="img" aria-label="Tỷ trọng">' + cc.map((x) => '<span style="width:' + (x[1] / tong * 100) + '%;background:' + x[2] + '" title="' + esc(x[0]) + ' ' + KD.phanTram(x[3]) + '"></span>').join('') + '</div>'
      + '<ul class="kd-legend kt-cc__chu">' + cc.map((x) => '<li><span class="kd-legend__cham" style="background:' + x[2] + '"></span><span class="kd-legend__ten">' + esc(x[0]) + '</span><span class="kd-meta">' + KD.phanTram(x[3]) + '</span><b class="num" title="' + KD.tienVnd(x[1]) + '">' + KD.tienGon(x[1]) + '</b></li>').join('') + '</ul>';
  }

  const tsT = (d) => d.tong.tai_san, noT = (d) => d.tong.no_phai_tra, vT = (d) => d.tong.von_chu;
  const bc = KT.baoCao({
    pfx: 'cd', tenFile: 'can-doi-ke-toan',
    api: (k) => { const t = thangCuaNgay(k.den); return ['/api/bao-cao/can-doi?' + KT.url.qs({ thang: t }), '/api/bao-cao/can-doi?' + KT.url.qs({ thang: thangDauNam(t) })]; },
    macDinh: { den: '' },
    inUrl: (k, d) => '/ketoan/in?' + KT.url.qs({ loai: 'bao_cao', mau: 'cdkt', den: (d && d.den_ngay) || k.den || '' }),
    cot: [{ key: 'ma' }, { key: 'cuoi_ky', num: true }, { key: 'dau_nam', num: true }],
    lien: { '111': '111', '112': '112', '130': '131', '140': '156', '221': '211', '222': '214', '311': '331', '320': '311', '338': '341', '315': '334', '411': '411', '421': '421' },
    chuyen,
    kpi: {
      ts: (d) => ({ v: KD.tienGonHtml(tsT(d)), title: KD.tienVnd(tsT(d)), phu: 'Tiền chiếm ' + KD.phanTram(d.chi_so.tien_tren_ts * 100) + ' tài sản' }),
      no: (d) => ({ v: KD.tienGonHtml(noT(d)), title: KD.tienVnd(noT(d)), phu: d.chi_so.no_tren_von == null ? 'Chưa có vốn chủ để so' : 'Bằng ' + KD.phanTram(d.chi_so.no_tren_von * 100) + ' vốn chủ' }),
      vcsh: (d) => ({ v: KD.tienGonHtml(vT(d)), title: KD.tienVnd(vT(d)), phu: 'Khả năng trả nợ ' + KD.phanTram(d.chi_so.thanh_toan_hien_hanh * 100) + KD.tip('Tài sản ngắn hạn / nợ ngắn hạn') }),
      kiem: (d) => (d.kiem.lech && Math.abs(d.kiem.lech) >= 1 ? { v: '<span class="kt-so--xau">Lệch</span>', phu: H.pill('danger', 'Lệch ' + KD.tienVnd(d.kiem.lech)) }
        : { v: '<span class="kt-so--tot">Cân</span>', phu: H.pill('success', 'Tài sản = Nguồn vốn') }),
    },
    phuDe: (d) => 'Cuối tháng ' + d.thang.slice(5) + '/' + d.thang.slice(0, 4) + (d.thang_dau_nam ? ' · đầu năm = 31/12/' + d.thang_dau_nam.slice(0, 4) : ''),
    phamVi: () => 'Số dư chốt cuối tháng chứa ngày đã chọn; tồn kho theo sổ nhập − xuất, hao mòn theo nhật ký khấu hao. Mã số theo mẫu B01-DN để tham khảo.',
    // 30/09/2026 (quyết định người dùng): 311 "Phải trả người bán" CHỈ cộng nợ NCC thực + cần
    // kiểm — dự kiến (đơn NCC chưa chốt) tách hẳn, không cộng vào 311/300/440. Ghi chú này là nơi
    // DUY NHẤT trên màn giải thích số đó đi đâu — thiếu nó người dùng tưởng nợ NCC chỉ có 311.
    // Câu lệch chỉ hiện khi ncc_du_kien > 0, vì lệch tăng thêm đúng bằng phần dự kiến bị tách ra
    // (không phải lỗi mới) — không đổi cách TÍNH lệch, chỉ giải thích thêm.
    ghiChu: (d) => {
      const phanDuKien = d.ncc_du_kien > 0
        ? 'Nợ dự kiến (chưa chốt) — không tính vào Phải trả người bán: <b class="num">' + KD.tienVnd(d.ncc_du_kien) + '</b>.'
          + (d.ncc_can_kiem > 0 ? ' Trong Phải trả người bán có <b class="num">' + KD.tienVnd(d.ncc_can_kiem) + '</b> cần kiểm (khoản gắn đơn mua đã mất).' : '')
        : '';
      const coLech = d.kiem.lech && Math.abs(d.kiem.lech) >= 1;
      const phanLech = (coLech && d.ncc_du_kien > 0)
        ? 'Đã tách nợ dự kiến khỏi Phải trả người bán (' + KD.tienVnd(d.ncc_du_kien) + ') nên lệch tăng tương ứng; nguyên nhân lệch gốc có từ trước.'
        : '';
      return [phanDuKien, phanLech].filter(Boolean).join(' ');
    },
    sauTai: (d) => {
      if (!$('cd-den-ngay').value) $('cd-den-ngay').value = d.den_ngay;
      const ts = d.raw.tai_san, nv = d.raw.nguon_von, no = nv.no_phai_tra;
      $('cc-khoi').hidden = false;
      veCoCau($('cc-ts'), [['Tiền và tương đương tiền', ts.tien_va_td.tong], ['Phải thu ngắn hạn', ts.phai_thu], ['Hàng tồn kho', ts.hang_ton_kho], ['Tài sản cố định (giá trị còn lại)', ts.tscd_rong]]);
      veCoCau($('cc-nv'), [['Phải trả người bán', no.phai_tra_ncc], ['Phải trả người lao động', no.phai_tra_nv], ['Vay và nợ thuê tài chính', no.vay_ngan_han + no.vay_dai_han], ['Vốn chủ sở hữu', nv.von_csh.tong]]);
    },
    khiLoi: () => { $('cc-khoi').hidden = true; },
    rong: ['Chưa có số dư nào để lập báo cáo', 'Nhập số dư đầu kỳ ở Danh mục tài khoản hoặc ghi sổ nghiệp vụ đầu tiên.'],
    loi: 'Không tải được báo cáo tình hình tài chính',
  });
  bc.tai();
})();
