/* ═══════════════════════════════════════════════════════════════════════════
   kt-chung-tu.js — trang Chứng từ kế toán (L4): lập phiếu thu / phiếu chi / bút toán khác, xem, đảo.
   API THẬT: app/routers/journal.py, prefix /api/journal (model generic double-entry — KHÁC
   README mục 4.19, không có /api/chung-tu/so-moi hay /api/journal/dao).

   MISMATCH so với thiết kế gốc (đọc kỹ trước khi sửa tiếp):
   - Không có GET /api/chung-tu/so-moi (số CT dự kiến, tồn quỹ, kỳ khoá sổ) — `ct-so` do
     máy chủ tự sinh `ma_but_toan` khi ghi sổ (không hiện trước được), ô này khoá readonly.
   - Không có nháp (`trang_thai`, `id_nhap`) — JournalEntryIn không nhận trạng thái, mọi lần
     "Ghi sổ" là ghi thẳng, không có "Lưu nháp" (đã ẩn nút).
   - Không có GET /api/doi-tuong (danh sách KH/NCC/NV) — khối "Đối tượng" (đầu phiếu + từng
     dòng định khoản) khoá hẳn, không chọn được; người lập ghi tên đối tượng vào diễn giải.
   - `POST /api/journal` chỉ nhận {ngay, mo_ta, source_type, source_id, lines:[{loai:'no'|'co',
     account_code, so_tien, ghi_chu}]} — không có so_ct/ngay_ct (chỉ 1 ngày)/nguoi_nop/kem_theo
     riêng; "Người nộp/nhận tiền" được gộp vào cuối diễn giải vì không có field riêng.
   - `POST /api/journal/<id>/void` (đảo) không nhận ngày/lý do — luôn đảo bằng NGÀY HỆ THỐNG
     HÔM NAY, không lưu lý do; 2 ô đó trong hộp thoại chỉ để đối chiếu nội bộ trước khi bấm.
   - **Quan trọng — quyền:** `POST /api/journal` và `.../void` chỉ cho role admin/ceo/
     assistant_ceo (app/routers/journal.py:_ROLES_POST) — nhân viên kế toán thường (role
     `kt`/`manager`, vẫn vào được app qua require_ketoan_user) xem được chứng từ nhưng KHÔNG
     lập/đảo được qua API thật. Cần chủ dự án quyết có nới quyền hay không.
   - Không kiểm được "kỳ đã khoá sổ" hay "tồn quỹ đủ chi" (không có API tương ứng) — 2 mục đó
     bị bỏ khỏi danh sách kiểm tra; chỉ còn kiểm được: có diễn giải, mỗi dòng có TK + tiền,
     tổng Nợ = tổng Có, đủ tối thiểu 2 dòng (đúng yêu cầu thật của post_journal).
   - Ô chọn tài khoản (KT.oTk, dùng ở quỹ tiền mặt + từng dòng định khoản): từ 2026-09-25 kt-chung.js
     nạp danh mục từ GET /api/journal/accounts ({code,name} — cùng danh mục post_journal kiểm tra),
     không còn gọi nhầm /api/tai-khoan (tài khoản ngân hàng) nên gợi ý tài khoản đã có dữ liệu.
*/
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-chung-tu')) return;
  const $ = (id) => document.getElementById(id);
  const pill = (mau, nhan) => '<span class="pill pill--' + mau + '">' + esc(nhan) + '</span>';
  const LOAI = {
    phieu_thu: { h1: 'Lập phiếu thu', ten: 'Phiếu thu', ico: 'bi-box-arrow-in-down', mau: 'success', tien: 'no', nguoi: 'Người nộp tiền', dg: 'Lý do thu', ve: ['/ketoan/so-quy', 'Sổ quỹ'] },
    phieu_chi: { h1: 'Lập phiếu chi', ten: 'Phiếu chi', ico: 'bi-box-arrow-up', mau: 'warning', tien: 'co', nguoi: 'Người nhận tiền', dg: 'Lý do chi', ve: ['/ketoan/so-quy', 'Sổ quỹ'] },
    khac: { h1: 'Tạo bút toán', ten: 'Bút toán khác', ico: 'bi-journal-plus', mau: '', tien: null, nguoi: '', dg: 'Diễn giải', ve: ['/ketoan/so-cai', 'Sổ kế toán'] },
  };
  const u = KT.url.doc();
  let loai = LOAI[u.loai] ? u.loai : 'khac', cheDo = u.id ? 'xem' : 'moi', ct = null;
  let dong = [], soDong = 0;
  const docSo = (v) => Number(String(v || '').replace(/[^\d]/g, '')) || 0;
  const homNay = () => KD.iso(new Date());
  const TK_QUY = '111';   // TK cấp 1 tiền mặt: ô quỹ lọc theo tiền tố này (gồm cả TK con, vd 1111)

  /* ── Khởi động ── */
  async function tai() {
    $('ct-tt').innerHTML = KD.KHUNG_TAI; $('ct-than').hidden = true; $('ct-thanh').hidden = true;
    try {
      if (cheDo === 'xem') { ct = await KD.api('/api/journal/' + encodeURIComponent(u.id)); loai = LOAI[ct.source_type] ? ct.source_type : 'khac'; }
      $('ct-tt').innerHTML = ''; $('ct-than').hidden = false; $('ct-thanh').hidden = false;
      dung();
    } catch (e) {
      $('ct-ma').textContent = '—';
      KD.khoiLoi($('ct-tt'), cheDo === 'xem' ? 'Không tải được chứng từ' : 'Không mở được mẫu chứng từ', e, tai);
    }
  }

  /* ── Dựng trang theo loại + chế độ ── */
  const oQuy = KT.oTk($('ct-quy'), { loc: (t) => (t.ma || '').indexOf(TK_QUY) === 0, khiChon: () => { if (dong[0] && dong[0].khoaTien) { dong[0].tk = oQuy.lay(); tinh(); } } });
  function dung() {
    const L = LOAI[loai], xem = cheDo === 'xem';
    document.title = (xem ? ct.ma_but_toan : L.h1) + ' — Kế toán';
    $('ct-ico').className = 'ico-tile ico-tile--lg' + (L.mau ? ' ico-tile--' + L.mau : ''); $('ct-ico').innerHTML = '<i class="bi ' + L.ico + '"></i>';
    $('ct-h1').textContent = xem ? 'Chi tiết ' + (L.ten || 'chứng từ').toLowerCase() : L.h1;
    $('ct-crumb').textContent = xem ? ct.ma_but_toan : L.h1;
    $('ct-ve').innerHTML = '<i class="bi bi-arrow-left" aria-hidden="true"></i>' + L.ve[1]; $('ct-ve').href = L.ve[0]; $('ct-quay-lai').href = L.ve[0];
    $('ct-loai').hidden = xem;
    $('ct-loai').querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.loai === loai)));
    document.querySelectorAll('#ct-form [data-chi]').forEach((el) => { el.hidden = el.dataset.chi.split(' ').indexOf(loai) < 0; });
    $('ct-nguoi-nhan').textContent = L.nguoi; $('ct-dg-nhan').innerHTML = esc(L.dg) + ' <span class="kd-field__req" aria-hidden="true">*</span>';

    // Một nút chính: Ghi sổ khi lập · In khi xem. Không có nháp/đảo-có-lý-do ở backend thật.
    $('ct-ghi').hidden = xem; $('ct-them-dong').hidden = xem;
    $('ct-dao').hidden = !xem || ct.trang_thai !== 'da_post'; $('ct-sao').hidden = !xem;
    $('ct-in').hidden = !xem; $('ct-in').classList.toggle('kd-btn--primary', xem);
    $('ct-form').hidden = xem; $('ct-tt-xem').hidden = !xem; $('ct-than').classList.toggle('kt-ct-nhap', !xem);
    $('ct-h-kiem').textContent = xem ? 'Trạng thái chứng từ' : 'Kiểm tra trước khi ghi sổ';

    if (xem) napTuCt(); else napMoi();
    veMeta(); veLienQuan(); veQuyen(xem);
  }

  /* ── Quyền ghi (F3 28/09): POST /api/journal và /void chỉ cho admin/ceo/assistant_ceo (journal.py _ROLES_POST) = KD.coQuyen('ceo').
     Nút Ghi sổ / Thêm dòng / Đảo / Sao chép mang data-quyen="ceo" (CSS tự ẩn); ở đây chỉ báo rõ "chỉ xem" + khoá ô nhập của mẫu lập mới. ── */
  const GHI_DUOC = KD.coQuyen('ceo');
  function veQuyen(xem) {
    const note = $('ct-chi-xem');
    note.hidden = GHI_DUOC;
    if (GHI_DUOC) return;
    note.innerHTML = '<i class="bi bi-lock" aria-hidden="true"></i> <b>Chỉ xem — cần quyền CEO để ghi.</b> '
      + (xem ? 'Lập bút toán đảo hoặc sao chép chứng từ chỉ CEO / Admin / Trợ lý CEO làm được.'
        : 'Phiếu thu, phiếu chi, bút toán tay ở màn này chỉ CEO / Admin / Trợ lý CEO ghi sổ được. Kế toán lập phiếu thu / chi ở <a class="kd-link" href="/ketoan/so-quy">Sổ quỹ</a>.');
    if (!xem) $('ct-than').querySelectorAll('input, select, textarea, #ct-dong button').forEach((el) => { el.disabled = true; });
  }

  function napMoi() {
    $('ct-so').value = 'Tự sinh khi ghi sổ'; $('ct-ngay-ct').value = homNay(); $('ct-ngay-ht').value = homNay();
    $('ct-nguoi').value = ''; $('ct-dg').value = '';
    $('ct-mau-box').hidden = true;
    dong = [];
    // Quỹ mặc định lấy từ danh mục thật (/api/journal/accounts — mã nào post_journal nhận): xem datQuyMacDinh.
    // (Trước 2026-09-25 gắn cứng '1111' khi danh mục chưa có mã đó → MỌI phiếu thu/chi bị post_journal từ chối.)
    if (LOAI[loai].tien) { dong.push({ tk: TK_QUY, khoaTien: true }); dong.push({}); datQuyMacDinh(); }
    else { dong.push({}); dong.push({}); }
    veDong();
  }
  /* Từ 28/09/2026 mỗi tài khoản tiền có TK con: mặc định chọn TK con ĐẦU TIÊN của 111 trong danh mục
     (mã lấy từ API, không gắn cứng); danh mục chưa có TK con thì dùng chính 111. Chỉ đặt khi dòng quỹ còn
     là giá trị khởi tạo (người dùng chưa kịp chọn quỹ khác). */
  async function datQuyMacDinh() {
    let ma = TK_QUY;
    try { const con = (await KT.dmTk()).find((t) => t.cha === TK_QUY); if (con) ma = con.ma; } catch (e) { /* ô quỹ tự báo lỗi tải danh mục khi mở */ }
    if (cheDo === 'moi' && dong[0] && dong[0].khoaTien && dong[0].tk === TK_QUY) oQuy.dat(ma);
  }
  function napTuCt() {
    $('ct-so').value = ct.ma_but_toan; $('ct-ngay-ct').value = ct.ngay; $('ct-ngay-ht').value = ct.ngay;
    $('ct-nguoi').value = ''; $('ct-dg').value = ct.mo_ta || ''; $('ct-mau-box').hidden = true;
    const tien = LOAI[loai].tien;
    dong = (ct.lines || []).map((l) => ({ tk: l.account_code, ten_tk: l.account_name || '', dg: l.ghi_chu || '', dtTen: '', dtMa: '', no: l.loai === 'no' ? +l.so_tien : 0, co: l.loai === 'co' ? +l.so_tien : 0 }));
    if (tien) { const i = dong.findIndex((l) => (l.tk || '').indexOf(TK_QUY) === 0 && l[tien] > 0); if (i >= 0) { const q = dong.splice(i, 1)[0]; q.khoaTien = true; dong.unshift(q); oQuy.dat(q.tk); } }
    if (cheDo === 'xem') {
      const o = [['Ngày hạch toán', KD.ngay(ct.ngay)], ['Số chứng từ', esc(ct.ma_but_toan)]];
      if (tien) o.push(['Quỹ', esc(dong[0] ? dong[0].tk + ' — ' + (dong[0].ten_tk || '') : '—')]);
      o.push([LOAI[loai].dg, esc(ct.mo_ta || '—'), true]);
      $('ct-tt-xem').innerHTML = o.map((x) => '<div' + (x[2] ? ' class="kt-ct-rong"' : '') + '><dt>' + esc(x[0]) + '</dt><dd>' + x[1] + '</dd></div>').join('');
    }
    veDong();
  }

  /* ── Bảng định khoản ── */
  function veDong() {
    const xem = cheDo === 'xem', tien = LOAI[loai].tien;
    // Hướng dẫn định khoản: ⓘ cạnh tiêu đề thẻ thay cho dòng chữ dài.
    $('ct-dk-gy').innerHTML = xem ? '' : KD.tip(tien === 'no' ? 'Dòng đầu là quỹ nhận tiền (Nợ, tự tính). Các dòng dưới ghi Có — thường là 131 phải thu khách, 711 thu nhập khác…'
      : tien === 'co' ? 'Dòng đầu là quỹ chi tiền (Có, tự tính). Các dòng dưới ghi Nợ — thường là 331 trả nhà cung cấp, 642 chi phí, 141 tạm ứng…'
      : 'Mỗi dòng ghi một bên Nợ hoặc Có. Tổng Nợ phải bằng tổng Có mới ghi sổ được.');
    $('ct-dong').closest('table').classList.toggle('is-xem', xem);
    if (xem) {
      $('ct-dong').innerHTML = dong.map((r, i) => '<tr><td class="kt-ct-stt">' + (i + 1) + '</td><td><span class="kt-tk">' + esc(r.tk) + '</span><span class="kt-khach__ma">' + esc(r.ten_tk || '') + '</span></td>'
        + '<td>' + esc(r.dg || '—') + '</td>'
        + '<td class="num">' + KT.tienSo(r.no) + '</td><td class="num">' + KT.tienSo(r.co) + '</td><td class="kd-col-act"></td></tr>').join('');
      tinh(); return;
    }
    soDong++;
    $('ct-dong').innerHTML = dong.map((r, i) => {
      const khoa = r.khoaTien, noKhoa = khoa || tien === 'no', coKhoa = khoa || tien === 'co';
      const o = (ben, bi) => '<td class="num kt-ct-o-so"><input class="kd-input num" id="ct-' + ben + '-' + i + '" data-i="' + i + '" data-ben="' + ben + '" inputmode="numeric" autocomplete="off" aria-label="' + (ben === 'no' ? 'Nợ' : 'Có') + ' dòng ' + (i + 1) + '"'
        + (bi ? ' readonly tabindex="-1" placeholder="—"' : ' placeholder="0"') + ' value="' + (r[ben] ? KD.tien(r[ben]) : '') + '">' + (khoa && ((ben === 'no') === (tien === 'no')) ? '<span class="kt-ct-khoa">Tự tính</span>' : '') + '</td>';
      return '<tr class="' + (khoa ? 'is-khoa' : '') + '"><td class="kt-ct-stt">' + (i + 1) + '</td>'
        + '<td class="kt-ct-o-tk">' + (khoa ? '<input class="kd-input" id="ct-tk-' + i + '" readonly tabindex="-1" value="' + esc(r.tk) + '" aria-label="Tài khoản quỹ dòng 1"><span class="kt-ct-khoa">Chọn quỹ ở phần trên</span>'
          : '<div class="kt-o-tk"><input class="kd-input" type="search" id="ct-tk-' + i + '" data-i="' + i + '" placeholder="Gõ mã hoặc tên TK" aria-label="Tài khoản dòng ' + (i + 1) + '"></div>') + '</td>'
        + '<td class="kt-ct-o-dg"><input class="kd-input" id="ct-dg-' + i + '" data-i="' + i + '" data-truong="dg" maxlength="200" autocomplete="off" aria-label="Diễn giải dòng ' + (i + 1) + '" value="' + esc(r.dg || '') + '" placeholder="Theo diễn giải chung"></td>'
        + o('no', noKhoa) + o('co', coKhoa)
        + '<td class="kd-col-act">' + (khoa ? '' : '<button type="button" class="kd-icon-btn" data-xoa="' + i + '" aria-label="Xoá dòng ' + (i + 1) + '"><i class="bi bi-trash" aria-hidden="true"></i></button>') + '</td></tr>';
    }).join('');
    dong.forEach((r, i) => {
      if (r.khoaTien) return;
      const ot = KT.oTk($('ct-tk-' + i), { khiChon: (t) => { r.tk = t ? t.ma : ''; tinh(); } });
      if (r.tk) ot.dat(r.tk); r.ot = ot;
    });
    tinh();
  }
  $('ct-dong').addEventListener('input', (e) => {
    const el = e.target, i = +el.dataset.i, r = dong[i]; if (!r) return;
    if (el.dataset.ben) { const n = docSo(el.value); el.value = n ? KD.tien(n) : ''; r[el.dataset.ben] = n;
      if (n && loai === 'khac') { const kia = el.dataset.ben === 'no' ? 'co' : 'no'; r[kia] = 0; $('ct-' + kia + '-' + i).value = ''; }
      tinh(); }
    else if (el.dataset.truong === 'dg') r.dg = el.value;
  });
  $('ct-dong').addEventListener('click', (e) => { const b = e.target.closest('[data-xoa]'); if (!b) return; dong.splice(+b.dataset.xoa, 1); if (!dong.some((r) => !r.khoaTien)) dong.push({}); veDong(); });
  $('ct-them-dong').addEventListener('click', () => { dong.push({}); veDong(); const i = dong.length - 1; $('ct-tk-' + i).focus(); });

  /* ── Tính tổng + kiểm tra ── */
  function tinh() {
    const tien = LOAI[loai].tien, xem = cheDo === 'xem';
    if (tien && !xem) { const q = dong[0]; const t = dong.slice(1).reduce((s, r) => s + (r[tien === 'no' ? 'co' : 'no'] || 0), 0); q[tien] = t; q[tien === 'no' ? 'co' : 'no'] = 0;
      const el = $('ct-' + tien + '-0'); if (el) el.value = t ? KD.tien(t) : ''; const tk = $('ct-tk-0'); if (tk) tk.value = q.tk + ' — Quỹ tiền mặt'; }
    const no = dong.reduce((s, r) => s + (r.no || 0), 0), co = dong.reduce((s, r) => s + (r.co || 0), 0), l = no - co;
    $('ct-cong').innerHTML = '<tr><th scope="row" colspan="3">Cộng</th><td class="num">' + KD.tien(no) + '</td><td class="num">' + KD.tien(co) + '</td><td class="kd-col-act"></td></tr>';
    $('ct-tong').innerHTML = '<div><dt>Tổng phát sinh Nợ</dt><dd>' + KD.tien(no) + '</dd></div><div><dt>Tổng phát sinh Có</dt><dd>' + KD.tien(co) + '</dd></div>'
      + '<div class="is-dam"><dt>Chênh lệch Nợ − Có</dt><dd>' + (l ? '<span class="kt-so--xau">' + (l > 0 ? '+' : '−') + KD.tien(Math.abs(l)) + '</span>' : '<span class="kt-so--tot">0 — cân</span>') + '</dd></div>';
    const so = tien ? (dong[0] ? dong[0][tien] || 0 : 0) : Math.max(no, co);
    $('ct-grand-nhan').textContent = tien === 'no' ? 'Số tiền thu' : tien === 'co' ? 'Số tiền chi' : 'Giá trị bút toán';
    $('ct-grand-so').textContent = KD.tienVnd(so); $('ct-grand-chu').textContent = 'Bằng chữ: ' + KT.bangChu(so);
    if (!xem) veKiem();
    else $('ct-kiem').innerHTML = dongKiem(ct.trang_thai === 'da_huy' ? 'loi' : 'ok', ct.trang_thai === 'da_huy' ? 'Đã bị đảo (huỷ hiệu lực)' : 'Đã ghi sổ ' + KD.ngayGio(ct.created_at), ct.trang_thai === 'da_huy' ? 'Bút toán đảo đã được lập — số liệu này không còn hiệu lực trên sổ.' : 'Không sửa trực tiếp bút toán đã ghi sổ — dùng "Lập bút toán đảo".');
    return { no, co, so };
  }
  const dongKiem = (tt, cau, phu) => '<li class="is-' + tt + '"><i class="bi ' + (tt === 'ok' ? 'bi-check-circle-fill' : tt === 'loi' ? 'bi-x-circle-fill' : 'bi-circle') + '" aria-hidden="true"></i><span><span class="visually-hidden">' + (tt === 'ok' ? 'Đạt: ' : tt === 'loi' ? 'Chưa đạt: ' : 'Chưa kiểm: ') + '</span>' + esc(cau) + '</span>' + (phu ? '<small>' + esc(phu) + '</small>' : '') + '</li>';
  function kiem() {
    const loi = [];
    const co = dong.filter((r) => !r.khoaTien), coSo = dong.filter((r) => r.no || r.co);
    const no = dong.reduce((s, r) => s + (r.no || 0), 0), cO = dong.reduce((s, r) => s + (r.co || 0), 0);
    const k = [
      ['dg', !!$('ct-dg').value.trim(), 'Có ' + LOAI[loai].dg.toLowerCase(), 'Ghi rõ nội dung nghiệp vụ — hiện trên sổ và phiếu in.'],
      ['dong', coSo.length >= 2 && co.every((r) => (!r.no && !r.co) || r.tk), 'Ít nhất 2 dòng, mỗi dòng có tài khoản và số tiền', coSo.length < 2 ? 'Cần ít nhất 2 dòng có số tiền (1 Nợ + 1 Có).' : 'Có dòng thiếu tài khoản.'],
      ['can', no === cO && no > 0, 'Tổng Nợ bằng tổng Có', no === cO ? '' : 'Lệch ' + KD.tienVnd(Math.abs(no - cO)) + '.'],
    ];
    k.forEach((x) => { if (!x[1]) loi.push(x); });
    return { k, loi };
  }
  function veKiem() {
    const { k } = kiem();
    $('ct-kiem').innerHTML = k.map((x) => dongKiem(x[1] ? 'ok' : 'loi', x[2], x[1] ? '' : x[3])).join('');
    $('ct-ngay-ht-gy').textContent = '';
    const nhanQuy = $('ct-quy-nhan'), tipQuy = nhanQuy.querySelector('.kd-tip');
    if (loai === 'phieu_chi' && !tipQuy) nhanQuy.insertAdjacentHTML('beforeend', KD.tip('Phần mềm chưa tự chặn phiếu chi vượt tồn quỹ — xem tồn ở Sổ quỹ trước khi chi.'));
    else if (loai !== 'phieu_chi' && tipQuy) tipQuy.remove();
  }
  ['ct-dg', 'ct-ngay-ht'].forEach((id) => $(id).addEventListener('input', () => tinh()));
  $('ct-ngay-ct').addEventListener('change', (e) => { if (!$('ct-ngay-ht').dataset.sua) { $('ct-ngay-ht').value = e.target.value; tinh(); } });
  $('ct-ngay-ht').addEventListener('change', (e) => { e.target.dataset.sua = '1'; tinh(); });

  /* ── Đổi loại chứng từ (chỉ khi lập mới) ── */
  $('ct-loai').addEventListener('click', (e) => {
    const b = e.target.closest('[data-loai]'); if (!b || b.dataset.loai === loai) return;
    loai = b.dataset.loai; try { KT.url.ghi({ loai }, {}); } catch (x) { /* URL không ghi được trong khung xem */ }
    dung();
  });

  /* ── Ghi sổ ── */
  function goiDi() {
    const nguoi = $('ct-nguoi').value.trim();
    const dienGiai = $('ct-dg').value.trim() + (nguoi ? ' — ' + LOAI[loai].nguoi + ': ' + nguoi : '');
    const lines = [];
    dong.forEach((r) => { if (r.no > 0) lines.push({ loai: 'no', account_code: r.tk, so_tien: r.no, ghi_chu: r.dg || null }); if (r.co > 0) lines.push({ loai: 'co', account_code: r.tk, so_tien: r.co, ghi_chu: r.dg || null }); });
    return { ngay: $('ct-ngay-ht').value, mo_ta: dienGiai, source_type: loai, source_id: null, lines };
  }
  function baoLoi(msg) { $('ct-loi').textContent = msg; $('ct-loi').hidden = !msg; }
  $('ct-ghi').addEventListener('click', async () => {
    baoLoi('');
    const { loi } = kiem();
    if (loi.length) { baoLoi('Chưa ghi sổ được — chưa đạt "' + loi[0][2] + '"' + (loi[0][3] ? ': ' + loi[0][3] : '') + (loi.length > 1 ? ' (còn ' + (loi.length - 1) + ' mục chưa đạt ở cột phải)' : '')); return; }
    const nut = $('ct-ghi'); nut.disabled = true;
    try {
      const r = await KD.api('/api/journal', KD.JSON_POST(goiDi()));
      window.showToast && window.showToast('ok', 'Đã ghi sổ ' + r.ma_but_toan);
      u.id = r.id; cheDo = 'xem'; try { KT.url.ghi({ id: r.id }, {}); } catch (x) { /* khung xem */ } tai();
    } catch (e) { baoLoi('Chưa ghi sổ được: ' + e.message); } finally { nut.disabled = false; }
  });

  /* ── Xem: meta, liên quan, đảo ── */
  function veMeta() {
    const xem = cheDo === 'xem';
    const tt = xem ? (ct.trang_thai === 'da_huy' ? pill('warning', 'Đã bị đảo') : pill('success', 'Đã ghi sổ')) : pill('muted', 'Chưa ghi sổ');
    $('ct-pill').innerHTML = tt;
    $('ct-ma').textContent = xem ? ct.ma_but_toan : ''; $('ct-ma').hidden = !xem;   // số CT chỉ có sau khi ghi sổ (ô "Số chứng từ" đã ghi rõ)
    $('ct-meta').innerHTML = xem ? '<span>Loại: <b>' + esc(KT.loaiCt(loai).nhan) + '</b></span><span>Ngày hạch toán: <b>' + KD.ngay(ct.ngay) + '</b></span><span>Người lập: <b>' + esc(ct.created_by || '—') + '</b></span>'
      : '<span>Loại: <b>' + esc(LOAI[loai].ten) + '</b></span>';
    if (xem) { $('ct-in').href = '/ketoan/in?loai=chung_tu&id=' + encodeURIComponent(ct.id); $('ct-sao').href = '/ketoan/chung-tu?loai=' + loai; }
  }
  function veLienQuan() {
    const xem = cheDo === 'xem', L = LOAI[loai], o = [];
    if (xem) o.push(['/ketoan/so-cai?ky=tuy_chinh&tu=' + ct.ngay + '&den=' + ct.ngay + '&tim=' + encodeURIComponent(ct.ma_but_toan), 'bi-journal-text', 'Mở trên Sổ kế toán', 'Xem cùng các bút toán ngày ' + KD.ngay(ct.ngay)]);
    if (L.tien) o.push(['/ketoan/so-quy', 'bi-safe', 'Sổ quỹ tiền mặt', '']);
    o.push([L.ve[0], 'bi-list-ul', 'Danh sách chứng từ', L.ve[1]]);
    $('ct-lq').innerHTML = o.map((x) => '<li><a href="' + x[0] + '"><i class="bi ' + x[1] + '" aria-hidden="true"></i><span class="kd-related__ten">' + esc(x[2]) + '</span>' + (x[3] ? '<span class="kd-related__sub">' + esc(x[3]) + '</span>' : '') + '</a></li>').join('');
  }
  const dlgDao = $('ct-dlg-dao');
  $('ct-dao').addEventListener('click', () => {
    $('ct-dao-nd').textContent = 'Hệ thống lập bút toán ngược dấu (đổi Nợ ↔ Có) của ' + ct.ma_but_toan + ' — ' + KD.tienVnd(ct.tong_tien) + ', hạch toán theo NGÀY HÔM NAY. Chứng từ gốc giữ nguyên để lưu vết.';
    $('ct-dao-ngay').value = homNay(); $('ct-dao-ly-do').value = ''; KD.moHopThoai(dlgDao);
  });
  $('ct-form-dao').addEventListener('submit', async (e) => {
    e.preventDefault(); const ly = $('ct-dao-ly-do').value.trim();
    if (!ly) { $('ct-dao-ly-do').focus(); return KD.baoLoiHopThoai(dlgDao, 'Ghi lý do đảo bút toán (chỉ để đối chiếu nội bộ, máy chủ không lưu lý do này).'); }
    const nut = $('ct-dao-ok'); nut.disabled = true;
    try { const rev = await KD.api('/api/journal/' + ct.id + '/void', { method: 'POST' }); dlgDao.close();
      window.showToast && window.showToast('ok', 'Đã ghi bút toán đảo ' + rev.ma_but_toan); u.id = rev.id; try { KT.url.ghi({ id: rev.id }, {}); } catch (x) { /* khung xem */ } tai(); }
    catch (err) { KD.baoLoiHopThoai(dlgDao, 'Chưa đảo được: ' + err.message); } finally { nut.disabled = false; }
  });

  tai();
})();
