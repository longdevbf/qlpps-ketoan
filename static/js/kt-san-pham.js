/* kt-san-pham.js — Danh mục sản phẩm dùng chung (khung: kt-danh-sach.js). Giữ nghiệp vụ màn cũ #page-san-pham:
   thêm / sửa / tạm dừng / xoá, ảnh, bảng giá theo kích thước, danh mục kế toán (ketoan.product), lựa chọn cộng thêm (addon) xem ở panel.
   Kế toán là nơi DUY NHẤT được ghi danh mục này (products.py) — các app khác chỉ đọc. */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-san-pham')) return;
  const H = KT.H, $ = (id) => document.getElementById(id);
  const MASTER = { 'Đồ Gỗ': 'warning', 'Đồ Mây': 'success', 'Dự Án': 'info' };
  const UNIT = { fixed: 'Cố định theo cái / bộ', met_dai: 'Theo mét dài', met_vuong: 'Theo mét vuông', size_table: 'Bảng giá theo kích thước' };
  const CACH = { flat: 'Cộng thẳng', per_m2: 'Nhân theo m²', per_m_dai: 'Nhân theo mét dài' };
  const docSo = (v) => Number(String(v || '').replace(/[^\d]/g, '')) || 0;
  const anh = (x, lon) => (x.hinh_anh ? '<img class="kt-sp-anh' + (lon ? ' kt-sp-anh--lon' : '') + '" src="' + esc(x.hinh_anh) + '" alt="" loading="lazy">' : '<span class="kt-sp-anh kt-sp-anh--rong' + (lon ? ' kt-sp-anh--lon' : '') + '" title="Chưa có ảnh"><i class="bi bi-image" aria-hidden="true"></i></span>');
  const pillMaster = (m) => (m ? H.pill(MASTER[m] || 'muted', m) : '<span class="kd-muted">—</span>');
  let DM = [], NHOM = [];

  const ds = KT.danhSach({
    pfx: 'sp', api: (q) => '/api/products?' + KT.url.qs({ q: q.q, nhom_hang: q.nhom_hang, nhom_master: q.nhom_master, active_only: q.active_only }), donVi: 'sản phẩm', khongTrang: true,
    macDinh: { q: '', nhom_hang: '', nhom_master: '', active_only: 'true', page: 1, size: 500, sort: '' },
    chuyen: (mang) => { const dong = Array.isArray(mang) ? mang : (mang.items || []), dang = dong.filter((x) => x.active);
      return { dong, tong_dong: dong.length, tong: { so: dong.length, dang_ban: dang.length, go: dang.filter((x) => x.nhom_master === 'Đồ Gỗ').length, may: dang.filter((x) => x.nhom_master === 'Đồ Mây').length, du_an: dang.filter((x) => x.nhom_master === 'Dự Án').length, chua_nhom: dang.filter((x) => !['Đồ Gỗ', 'Đồ Mây', 'Dự Án'].includes(x.nhom_master)).length, chua_gia: dang.filter((x) => !(+x.gia_co_ban > 0)).length } }; },
    cot: [
      { key: 'anh', nhan: 'Ảnh', ve: (r) => anh(r) },
      // Gọn cột (đợt 4): mã thành dòng phụ dưới tên; nhóm hàng + nhóm master chung một cột.
      { key: 'ten', nhan: 'Sản phẩm', ve: (r) => H.ten(r.ten_sp, [r.ma_sp, r.label && r.label !== r.ten_sp ? r.label : (r.kich_thuoc_chuan || '')].filter(Boolean).join(' · ')) },
      { key: 'nhom', nhan: 'Nhóm', ve: (r) => (r.nhom_hang ? '<span class="kd-chip kd-chip--xam">' + esc(r.nhom_hang) + '</span> ' : '') + (r.nhom_master ? pillMaster(r.nhom_master) : r.nhom_hang ? '' : '<span class="kd-muted">—</span>') },
      { key: 'dvt', nhan: 'ĐVT', ve: (r) => esc(r.dvt || '—') },
      { key: 'gia', nhan: 'Giá bán', num: true, ve: (r) => (+r.gia_co_ban > 0 ? KD.tien(r.gia_co_ban) + (r.unit && r.unit !== 'fixed' ? '<span class="kt-khach__ma">' + esc(UNIT[r.unit] || '') + '</span>' : '') : '<span class="kd-muted">Chưa đặt</span>') },
      { key: 'tt', nhan: 'Trạng thái', ve: (r) => (r.active ? H.pill('success', 'Đang bán') : H.pill('muted', 'Tạm dừng')) },
      { key: 'act', nhan: 'Thao tác', act: true, nhanDong: (r) => r.ma_sp },
    ],
    kpi: {
      // Nêu đủ phần không thuộc Gỗ/Mây để Gỗ + Mây + phần này = Đang bán (QA nhất quán 25/09: 42 = 21 + 16 + 5 chưa có nhóm master).
      dang_ban: (d) => ({ v: H.dem(d.tong.dang_ban, 'sản phẩm'), phu: [d.tong.du_an ? KD.soDem(d.tong.du_an) + ' hạng mục dự án' : '', d.tong.chua_nhom ? KD.soDem(d.tong.chua_nhom) + ' chưa có nhóm master' : ''].filter(Boolean).join(' · ') || 'Theo bộ lọc đang chọn' }),
      go: (d) => ({ v: H.dem(d.tong.go, 'sản phẩm'), phu: 'Có trần chiết khấu' + KD.tip('Trần chiết khấu theo cơ chế HCNS.') }),
      may: (d) => ({ v: H.dem(d.tong.may, 'sản phẩm'), phu: 'Gồm ghế Papasan' + KD.tip('Ghế Papasan được miễn chiết khấu.') }),
      chua_gia: (d) => ({ v: H.dem(d.tong.chua_gia, 'sản phẩm'), phu: d.tong.chua_gia ? H.pill('warning', 'Cần đặt giá') + KD.tip('Đặt giá ở màn Tồn kho hoặc bấm Sửa sản phẩm.', 'kd-tip--trai') : H.pill('success', 'Đủ giá bán') }),
    },
    rong: (d, coLoc) => (coLoc ? ['Không có sản phẩm nào khớp bộ lọc', 'Thử bỏ bớt điều kiện lọc.'] : ['Chưa có sản phẩm nào', 'Bấm "Thêm sản phẩm" để tạo sản phẩm đầu tiên cho báo giá.']),
    loi: 'Không tải được danh mục sản phẩm',
    sauTai: () => { if (NHOM.length) return; KD.api('/api/products/meta/nhom-hang').then((n) => { NHOM = n || []; const giu = ds.st.nhom_hang;   // nhóm trên URL không còn trong danh sách vẫn hiện đúng trong ô lọc
      H.napChon($('sp-nhom_hang'), NHOM.concat(giu && !NHOM.includes(giu) ? [giu] : []).map((x) => [x, x]), 'Tất cả nhóm hàng', giu); $('sp-f-nhom-ds').innerHTML = NHOM.map((x) => '<option value="' + esc(x) + '">').join(''); }).catch(() => {}); },
    panel: {
      tai: (r) => '/api/products/' + r.id,
      ve: (x) => '<div class="kd-panel__id kt-p-id">' + anh(x, true) + '<div><div class="kd-panel__code">' + esc(x.ma_sp) + (x.active ? H.pill('success', 'Đang bán') : H.pill('muted', 'Tạm dừng')) + '</div><p class="kd-meta">' + esc(x.ten_sp) + '</p></div></div>'
        + H.kv([['Nhóm hàng', esc(x.nhom_hang || '—')], ['Nhóm master', pillMaster(x.nhom_master)], ['Đơn vị tính', esc(x.dvt || '—')], ['Cách tính giá', esc(UNIT[x.unit] || '—')], ['Giá bán cơ bản', +x.gia_co_ban > 0 ? KD.tienVnd(x.gia_co_ban) : 'Chưa đặt', true], ['Giá sàn', +x.gia_min > 0 ? KD.tienVnd(x.gia_min) : '—'], ['Kích thước chuẩn', esc(x.kich_thuoc_chuan || '—')], ['Màu chuẩn', esc(x.mau_chuan || '—')]])
        + (x.sizes && Object.keys(x.sizes).length ? H.khoi('bi-rulers', 'Giá theo kích thước', '<table class="kt-bang-nho"><tbody>' + Object.entries(x.sizes).map(([k, v]) => '<tr><td>' + esc(k) + '</td><td class="num">' + KD.tien(v) + '</td></tr>').join('') + '</tbody></table>') : '')
        + H.khoi('bi-plus-square', 'Lựa chọn cộng thêm (' + KD.soDem((x.addons || []).length) + ')', (x.addons || []).length ? '<table class="kt-bang-nho"><thead><tr><th scope="col">Lựa chọn</th><th scope="col">Cách tính</th><th scope="col" class="num">Giá</th></tr></thead><tbody>'
          + x.addons.map((a) => '<tr><td>' + esc(a.ten_addon) + '</td><td>' + esc(CACH[a.cach_tinh] || '—') + '</td><td class="num">' + KD.tien(a.gia_addon) + '</td></tr>').join('') + '</tbody></table><p class="kd-meta">Sửa lựa chọn ở màn Thuộc tính sản phẩm.</p>' : KD.khoiRong('Chưa có lựa chọn cộng thêm', 'Thêm ở màn Thuộc tính sản phẩm.'))
        + (x.mo_ta ? H.khoi('bi-card-text', 'Mô tả cho Marketing', '<p>' + esc(x.mo_ta) + '</p>') : '') + (x.ghi_chu ? H.khoi('bi-sticky', 'Ghi chú nội bộ', '<p>' + esc(x.ghi_chu) + '</p>') : ''),
      nut: (x) => '<button type="button" class="kd-btn kd-btn--grow" data-sua="' + x.id + '"><i class="bi bi-pencil" aria-hidden="true"></i>Sửa</button><a class="kd-btn kd-btn--grow" href="/ketoan/thuoc-tinh?nhom=' + encodeURIComponent(x.nhom_master || '') + '&sp=' + x.id + '"><i class="bi bi-sliders" aria-hidden="true"></i>Thuộc tính</a>',
    },
    menu: (r) => [
      { nhan: 'Sửa sản phẩm', icon: 'bi-pencil', onClick: () => moSua(r.id) },
      { nhan: 'Thuộc tính và lựa chọn', icon: 'bi-sliders', href: '/ketoan/thuoc-tinh?nhom=' + encodeURIComponent(r.nhom_master || '') + '&sp=' + r.id },
      { nhan: r.active ? 'Tạm dừng bán' : 'Bán lại', icon: r.active ? 'bi-pause-circle' : 'bi-play-circle', onClick: () => doiTrangThai(r) },
      '-',
      { nhan: 'Xoá sản phẩm', icon: 'bi-trash', danger: true, onClick: () => moXoa(r) },
    ],
  });

  /* ── Thêm / sửa ── */
  const dlg = $('sp-dlg'); let dangSua = null, tepCho = null, boAnh = false;
  const napDm = async () => { if (DM.length) return; try { DM = (await KD.api('/api/product-category')).filter((c) => c.active); } catch (e) { DM = []; }
    H.napChon($('sp-f-dm'), DM.map((c) => [String(c.id), (c.ma_nhom ? '[' + c.ma_nhom + '] ' : '') + c.ten_nhom]), '— Chưa chọn —'); };
  function dongSize(k, v) { return '<tr><td><input class="kd-input" data-size-k value="' + esc(k || '') + '" placeholder="Vd: 1m6" aria-label="Kích thước"></td><td><input class="kd-input num" data-size-v inputmode="numeric" value="' + (v ? KD.tien(v) : '') + '" aria-label="Giá theo kích thước"></td><td><button type="button" class="kd-icon-btn" data-size-xoa aria-label="Xoá dòng"><i class="bi bi-x-lg" aria-hidden="true"></i></button></td></tr>'; }
  const hienSize = () => { $('sp-f-size-o').hidden = $('sp-f-unit').value !== 'size_table'; if (!$('sp-f-size-o').hidden && !$('sp-f-size').children.length) $('sp-f-size').innerHTML = dongSize(); };
  $('sp-f-unit').addEventListener('change', hienSize);
  $('sp-f-size-them').addEventListener('click', () => { $('sp-f-size').insertAdjacentHTML('beforeend', dongSize()); $('sp-f-size').lastElementChild.querySelector('input').focus(); });
  $('sp-f-size').addEventListener('click', (e) => { const b = e.target.closest('[data-size-xoa]'); if (b) b.closest('tr').remove(); });
  $('sp-f-size').addEventListener('input', (e) => { if (e.target.matches('[data-size-v]')) { const n = docSo(e.target.value); e.target.value = n ? KD.tien(n) : ''; } });
  ['sp-f-gia', 'sp-f-gia-min'].forEach((id) => $(id).addEventListener('input', (e) => { const n = docSo(e.target.value); e.target.value = n ? KD.tien(n) : ''; }));
  function hienAnh(src) { $('sp-f-anh').hidden = !src; $('sp-f-anh-rong').hidden = !!src; if (src) $('sp-f-anh').src = src; $('sp-f-anh-bo').hidden = !src; }
  $('sp-f-tep').addEventListener('change', (e) => { const f = e.target.files[0]; if (!f) return; tepCho = f; boAnh = false; hienAnh(URL.createObjectURL(f)); });
  $('sp-f-anh-bo').addEventListener('click', () => { tepCho = null; boAnh = true; $('sp-f-tep').value = ''; hienAnh(''); });
  async function mo(x) {
    dangSua = x; tepCho = null; boAnh = false; $('sp-form').reset(); await napDm();
    $('sp-dlg-td').textContent = x ? 'Sửa sản phẩm ' + x.ma_sp : 'Thêm sản phẩm';
    const v = x || { active: true, thu_tu: 0 };
    $('sp-f-ma').value = v.ma_sp || ''; $('sp-f-ten').value = v.ten_sp || ''; $('sp-f-nhom').value = v.nhom_hang || ''; $('sp-f-master').value = v.nhom_master || ''; $('sp-f-dvt').value = v.dvt || '';
    $('sp-f-unit').value = v.unit === 'bo' || v.unit === 'cai' ? 'fixed' : (v.unit || ''); $('sp-f-thu-tu').value = v.thu_tu || 0; $('sp-f-gia').value = +v.gia_co_ban > 0 ? KD.tien(v.gia_co_ban) : ''; $('sp-f-gia-min').value = +v.gia_min > 0 ? KD.tien(v.gia_min) : '';
    $('sp-f-kt').value = v.kich_thuoc_chuan || ''; $('sp-f-mau').value = v.mau_chuan || ''; $('sp-f-mo-ta').value = v.mo_ta || ''; $('sp-f-ghi-chu').value = v.ghi_chu || ''; $('sp-f-active').checked = v.active !== false;
    $('sp-f-size').innerHTML = v.sizes ? Object.entries(v.sizes).map(([k, g]) => dongSize(k, g)).join('') : ''; hienSize(); hienAnh(v.hinh_anh || '');
    $('sp-f-dm').value = '';
    if (x) KD.api('/api/product?' + KT.url.qs({ q: x.ma_sp })).then((d) => { const it = (d.items || d || []).find((y) => y.ma_sp === x.ma_sp); if (it && it.category_id) $('sp-f-dm').value = String(it.category_id); }).catch(() => {});
    KD.moHopThoai(dlg); (x ? $('sp-f-ten') : $('sp-f-ma')).focus();
  }
  async function moSua(id) { try { mo(await KD.api('/api/products/' + id)); } catch (e) { window.showToast && window.showToast('err', 'Không mở được sản phẩm: ' + e.message); } }
  $('sp-them').addEventListener('click', () => mo(null));
  document.addEventListener('click', (e) => { const b = e.target.closest('#sp-p-nut [data-sua]'); if (b) moSua(b.dataset.sua); });
  $('sp-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const ma = $('sp-f-ma').value.trim(), ten = $('sp-f-ten').value.trim();
    if (!ma) { $('sp-f-ma').focus(); return KD.baoLoiHopThoai(dlg, 'Nhập mã sản phẩm.'); }
    if (!ten) { $('sp-f-ten').focus(); return KD.baoLoiHopThoai(dlg, 'Nhập tên sản phẩm.'); }
    const gia = docSo($('sp-f-gia').value), san = docSo($('sp-f-gia-min').value);
    if (san && gia && san > gia) { $('sp-f-gia-min').focus(); return KD.baoLoiHopThoai(dlg, 'Giá sàn không được cao hơn giá bán cơ bản.'); }
    const sizes = {}; if ($('sp-f-unit').value === 'size_table') [...$('sp-f-size').querySelectorAll('tr')].forEach((tr) => { const k = tr.querySelector('[data-size-k]').value.trim(), v = docSo(tr.querySelector('[data-size-v]').value); if (k && v) sizes[k] = v; });
    const body = { ma_sp: ma, ten_sp: ten, nhom_hang: $('sp-f-nhom').value.trim() || null, nhom_master: $('sp-f-master').value || null, dvt: $('sp-f-dvt').value.trim() || null, unit: $('sp-f-unit').value || null, thu_tu: +$('sp-f-thu-tu').value || 0,
      gia_co_ban: gia, gia_min: san || null, sizes: Object.keys(sizes).length ? sizes : null, kich_thuoc_chuan: $('sp-f-kt').value.trim() || null, mau_chuan: $('sp-f-mau').value.trim() || null,
      mo_ta: $('sp-f-mo-ta').value.trim() || null, ghi_chu: $('sp-f-ghi-chu').value.trim() || null, active: $('sp-f-active').checked };
    if (boAnh) body.hinh_anh = null;
    const nut = $('sp-f-ok'); nut.disabled = true;
    try {
      const x = dangSua ? await KD.api('/api/products/' + dangSua.id, Object.assign(KD.JSON_POST(body), { method: 'PUT' })) : await KD.api('/api/products', KD.JSON_POST(body));
      const loiPhu = [];
      if (tepCho) { const fd = new FormData(); fd.append('file', tepCho); try { await KD.api('/api/products/' + x.id + '/upload-image', { method: 'POST', body: fd }); } catch (er) { loiPhu.push('tải ảnh lỗi: ' + er.message); } }
      if ($('sp-f-dm').value) { try { await KD.api('/api/product/by-ma-sp/' + encodeURIComponent(ma) + '/category', Object.assign(KD.JSON_POST({ category_id: +$('sp-f-dm').value, ten_sp: ten, dvt: body.dvt }), { method: 'PUT' })); } catch (er) { loiPhu.push('gán danh mục kế toán lỗi: ' + er.message); } }
      dlg.close(); ds.dongPanel(); NHOM = [];
      window.showToast && window.showToast(loiPhu.length ? 'warn' : 'ok', (dangSua ? 'Đã cập nhật ' : 'Đã thêm ') + ma + (loiPhu.length ? ' — nhưng ' + loiPhu.join('; ') : dangSua ? '' : ' — khai báo phân khúc, màu, lựa chọn ở màn Thuộc tính'));
      ds.tai();
    } catch (err) { KD.baoLoiHopThoai(dlg, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; }
  });

  /* ── Tạm dừng / bán lại · xoá ── */
  async function doiTrangThai(r) { try { await KD.api('/api/products/' + r.id, Object.assign(KD.JSON_POST({ active: !r.active }), { method: 'PUT' })); window.showToast && window.showToast('ok', (r.active ? 'Đã tạm dừng ' : 'Đã mở bán lại ') + r.ma_sp); ds.tai(); }
    catch (e) { window.showToast && window.showToast('err', 'Chưa đổi được trạng thái: ' + e.message); } }
  const dlgXoa = $('sp-dlg-xoa'); let dangXoa = null;
  function moXoa(r) { dangXoa = r; $('sp-xoa-td').textContent = 'Xoá sản phẩm ' + r.ma_sp + '?'; $('sp-xoa-nd').textContent = 'Xoá hẳn "' + r.ten_sp + '" cùng các lựa chọn cộng thêm và thuộc tính riêng. Không hoàn tác được. Sản phẩm đã lên báo giá / đơn hàng thì nên Tạm dừng thay vì xoá.'; KD.moHopThoai(dlgXoa); dlgXoa.querySelector('[data-dong]').focus(); }
  $('sp-xoa-ok').addEventListener('click', async () => { const nut = $('sp-xoa-ok'); nut.disabled = true;
    try { await KD.api('/api/products/' + dangXoa.id, { method: 'DELETE', headers: { Accept: 'application/json' } }); dlgXoa.close(); ds.dongPanel(); window.showToast && window.showToast('ok', 'Đã xoá ' + dangXoa.ma_sp); ds.tai(); }
    catch (e) { KD.baoLoiHopThoai(dlgXoa, 'Chưa xoá được: ' + e.message); } finally { nut.disabled = false; } });
  ds.tai();
})();
