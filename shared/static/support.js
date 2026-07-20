/* Support module — full-dynamic client. Every render comes from real API. */
(function () {
  const S = window.__SUPPORT__ || {};
  const $  = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const esc = (s) => (s == null ? "" : String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])));

  const fmtTime = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    const now = new Date();
    const diff = (now - d) / 1000;
    if (diff < 60) return "vừa xong";
    if (diff < 3600) return Math.floor(diff / 60) + "′";
    if (diff < 86400) return Math.floor(diff / 3600) + "g";
    if (diff < 86400 * 7) return Math.floor(diff / 86400) + " ngày";
    return d.toLocaleDateString("vi-VN");
  };
  const fmtFull = (iso) => {
    if (!iso) return "—";
    return new Date(iso).toLocaleString("vi-VN");
  };
  const initial = (s) => (s && String(s)[0] || "?").toUpperCase();

  const LOAI = { bug: "Bug", feature: "Feature", nang_cap: "Upgrade", cach_dung: "Hỏi cách" };
  const LOAI_BADGE = { bug: "b-danger", feature: "b-purple", nang_cap: "b-primary", cach_dung: "" };
  const LOAI_ICON = { bug: "i-bug", feature: "i-sparkle", nang_cap: "i-arrow-r", cach_dung: "i-msg" };
  const UT = { khan: "Khẩn", cao: "Cao", vua: "Vừa", thap: "Thấp" };
  const UT_BADGE = { khan: "b-danger", cao: "b-warning", vua: "", thap: "b-success" };
  const UT_STRIPE = { khan: "crit", cao: "warn", vua: "norm", thap: "low" };
  const ST = { moi: "Mới", tiep_nhan: "Tiếp nhận", dang_xu_ly: "Đang xử lý", cho_phan_hoi: "Chờ phản hồi", da_xu_ly: "Đã xử lý", dong: "Đã đóng" };
  const ST_IDX = { moi: 0, tiep_nhan: 1, dang_xu_ly: 2, cho_phan_hoi: 3, da_xu_ly: 4, dong: 4 };
  const ST_PILL = { moi: "st-new", tiep_nhan: "st-new", dang_xu_ly: "st-doing", cho_phan_hoi: "st-wait", da_xu_ly: "st-done", dong: "st-closed" };
  const BUG = { chua_tai_hien: -1, da_tai_hien: 0, dang_debug: 1, da_fix: 2, da_deploy: 3, qa_verified: 4 };
  const BUG_LABEL = { chua_tai_hien: "Chưa tái hiện", da_tai_hien: "Đã tái hiện", dang_debug: "Đang debug", da_fix: "Đã fix", da_deploy: "Đã deploy", qa_verified: "QA verified" };
  const BUG_NEXT = { null: "da_tai_hien", chua_tai_hien: "da_tai_hien", da_tai_hien: "dang_debug", dang_debug: "da_fix", da_fix: "da_deploy", da_deploy: "qa_verified", qa_verified: null };

  let currentFilter = null;

  // ══ View switching ═════════════════════════════════════════════════
  const tabs = $$(".sub-tab");
  const views = $$(".view");
  function activateView(id) {
    tabs.forEach(t => t.removeAttribute("aria-current"));
    const tab = tabs.find(t => t.dataset.tab === id);
    if (tab) { tab.setAttribute("aria-current", "page"); if (id === "detail") tab.style.display = ""; }
    views.forEach(v => v.classList.remove("active"));
    const v = document.getElementById("view-" + id);
    if (v) v.classList.add("active");
  }
  tabs.forEach(t => t.addEventListener("click", () => {
    const id = t.dataset.tab;
    if (id === "mine") location.href = "/support";
    else if (id === "raise") location.href = "/support/new";
    else if (id === "detail" && S.initial_tid) location.href = "/support/" + S.initial_tid;
  }));

  // ══ MINE ═══════════════════════════════════════════════════════════
  async function loadMine() {
    const url = "/api/support/tickets/mine" + (currentFilter ? "?trang_thai=" + currentFilter : "");
    try {
      const r = await fetch(url, { credentials: "same-origin" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const data = await r.json();
      renderHero(data);
      renderFilters(data.counts || {});
      renderMineTable(data.items || []);
      const cnt = $("#tabMineCount"); if (cnt) cnt.textContent = data.counts ? data.counts.total : (data.count || 0);
    } catch (e) {
      const tbl = $("#mineTable");
      if (tbl) tbl.insertAdjacentHTML("beforeend",
        `<div style="padding:32px;text-align:center;color:var(--danger);grid-column:1/-1;">Lỗi tải: ${esc(e.message)}</div>`);
    }
  }

  function renderHero(data) {
    const u = data.user || S.user;
    const name = u.ho_ten || u.username || "bạn";
    $("#heroName").textContent = name;
    const counts = data.counts || { total: 0, dang_xu_ly: 0, cho_phan_hoi: 0, da_xu_ly: 0 };
    const doing = counts.dang_xu_ly + counts.tiep_nhan;
    if (counts.total === 0) {
      $("#heroTitle").innerHTML = 'Chưa có ticket nào. Bạn muốn <span class="hl">gửi yêu cầu đầu tiên?</span>';
      $("#heroSub").textContent = "Bấm nút bên dưới để mở form. Team CN sẽ phản hồi qua chuông trong app.";
    } else if (doing > 0) {
      $("#heroTitle").innerHTML = `Có <span class="hl">${doing}</span> ticket đang được đội CN xử lý cho bạn`;
      $("#heroSub").textContent = `Tổng ${counts.total} ticket. ${counts.cho_phan_hoi > 0 ? counts.cho_phan_hoi + " chờ bạn phản hồi thêm. " : ""}${counts.da_xu_ly > 0 ? counts.da_xu_ly + " đã xử lý xong." : ""}`;
    } else {
      $("#heroTitle").innerHTML = `Bạn có <span class="hl">${counts.total}</span> ticket đã gửi`;
      $("#heroSub").textContent = "Tất cả đã hoàn tất hoặc đóng. Cần thêm gì cứ tạo mới!";
    }
    // Stats pills
    const stats = [
      { n: counts.total, l: "Tổng", cls: "" },
      { n: doing, l: "Đang xử lý", cls: "stat-doing" },
      { n: counts.cho_phan_hoi, l: "Chờ tôi", cls: "stat-wait" },
      { n: counts.da_xu_ly + counts.dong, l: "Xong", cls: "stat-done" },
    ];
    $("#heroStats").innerHTML = stats.map(s => `
      <div class="stat-pill ${s.cls}">
        <span class="stat-num count-up" data-to="${s.n}">${s.n}</span>
        <span class="stat-lbl">${s.l}</span>
      </div>`).join("");
    // Animate counters
    $$(".count-up", $("#heroStats")).forEach(el => {
      const to = parseInt(el.dataset.to) || 0;
      el.textContent = "0";
      const dur = 900;
      const start = performance.now();
      function step(now) {
        const t = Math.min(1, (now - start) / dur);
        el.textContent = Math.round((1 - Math.pow(1 - t, 3)) * to);
        if (t < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    });
  }

  function renderFilters(counts) {
    const items = [
      { key: null, label: "Tất cả", n: counts.total || 0 },
      { key: "dang_xu_ly", label: "Đang xử lý", n: counts.dang_xu_ly || 0 },
      { key: "cho_phan_hoi", label: "Chờ tôi phản hồi", n: counts.cho_phan_hoi || 0 },
      { key: "da_xu_ly", label: "Đã xử lý", n: counts.da_xu_ly || 0 },
      { key: "dong", label: "Đã đóng", n: counts.dong || 0 },
    ];
    const row = $("#filterRow");
    row.innerHTML = items.map(it => `
      <button class="filter-chip" aria-pressed="${it.key === currentFilter ? "true" : "false"}" data-key="${it.key === null ? "" : it.key}">
        ${esc(it.label)} <span class="count">${it.n}</span>
      </button>`).join("");
    $$(".filter-chip", row).forEach(c => c.addEventListener("click", () => {
      currentFilter = c.dataset.key || null;
      loadMine();
    }));
  }

  function renderMineTable(items) {
    const tbl = $("#mineTable");
    const header = tbl.querySelector(".t-row.head");
    tbl.innerHTML = "";
    tbl.appendChild(header);
    if (!items.length) {
      tbl.insertAdjacentHTML("beforeend", `
        <div style="padding:48px 24px;text-align:center;color:var(--text-3);font-size:13.5px;grid-column:1/-1;">
          <div style="font-size:36px;margin-bottom:8px;">📭</div>
          Chưa có ticket nào${currentFilter ? " trong danh mục này" : ""}.
          ${!currentFilter ? '<br><a href="/support/new" style="color:var(--primary);">Bấm để tạo ticket đầu tiên →</a>' : ""}
        </div>`);
      return;
    }
    items.forEach(t => tbl.insertAdjacentHTML("beforeend", renderMineRow(t)));
    $$(".t-row.item", tbl).forEach(r => r.addEventListener("click", () => {
      const id = r.dataset.id; if (id) location.href = "/support/" + id;
    }));
  }

  function renderMineRow(t) {
    const stripe = UT_STRIPE[t.muc_uu_tien] || "norm";
    const bLoai = `<span class="badge ${LOAI_BADGE[t.loai] || ""}"><svg class="i i-12"><use href="#${LOAI_ICON[t.loai] || "i-msg"}"/></svg> ${esc(LOAI[t.loai] || t.loai)}</span>`;
    const bUt = `<span class="badge ${UT_BADGE[t.muc_uu_tien] || ""}"><span class="dot"></span> ${esc(UT[t.muc_uu_tien] || t.muc_uu_tien)}</span>`;
    let bugMini = "";
    if (t.loai === "bug" && t.bug_status) {
      const cls = t.bug_status === "da_fix" ? " st-fixed" : (t.bug_status === "qa_verified" ? " st-ver" : "");
      bugMini = `<span class="bug-mini${cls}">${esc(BUG_LABEL[t.bug_status] || t.bug_status)}</span>`;
    }
    const pill = `<span class="status-pill ${ST_PILL[t.trang_thai] || ""}"><span class="dot"></span> ${esc(ST[t.trang_thai] || t.trang_thai)}</span>`;
    return `
    <div class="t-row item" data-id="${t.id}">
      <div class="stripe ${stripe}"></div>
      <div class="col-id">ITQ-${String(t.id).padStart(3, "0")}</div>
      <div class="col-title">
        <span class="tt">${esc(t.tieu_de)}</span>
        <span class="tm">${bLoai} ${bUt} ${bugMini}</span>
      </div>
      <div class="col-status">${pill}</div>
      <div class="col-app"><span class="dot"></span> ${esc(t.app_source || "—")}</div>
      <div class="col-time">${esc(fmtTime(t.updated_at || t.created_at))}</div>
    </div>`;
  }

  // ══ DETAIL ═════════════════════════════════════════════════════════
  let currentTicket = null;

  async function loadDetail(tid) {
    if (!tid) return;
    try {
      const r = await fetch("/api/support/tickets/" + tid, { credentials: "same-origin" });
      if (r.status === 403) return renderDetailError("Bạn không có quyền xem ticket này.");
      if (r.status === 404) return renderDetailError("Ticket không tồn tại.");
      if (!r.ok) throw new Error("HTTP " + r.status);
      const t = await r.json();
      currentTicket = t;
      renderDetail(t);
    } catch (e) {
      renderDetailError("Lỗi tải: " + e.message);
    }
  }
  function renderDetailError(msg) {
    $("#view-detail").innerHTML = `<div style="padding:48px;text-align:center;color:var(--text-2);font-size:14px;"><div style="font-size:32px;margin-bottom:8px;">⚠️</div>${esc(msg)}<br><a href="/support" style="color:var(--primary);display:inline-block;margin-top:16px;">← Về danh sách</a></div>`;
  }

  function renderDetail(t) {
    $("#detailTicketId").textContent = "ITQ-" + String(t.id).padStart(3, "0");
    $("#detailTitle").textContent = t.tieu_de;

    // Badges
    const badges = [
      `<span class="badge ${LOAI_BADGE[t.loai] || ""}"><svg class="i i-12"><use href="#${LOAI_ICON[t.loai] || "i-msg"}"/></svg> ${esc(LOAI[t.loai] || t.loai)}</span>`,
      `<span class="badge ${UT_BADGE[t.muc_uu_tien] || ""}"><span class="dot"></span> Ưu tiên ${esc(UT[t.muc_uu_tien] || t.muc_uu_tien)}</span>`,
      `<span class="badge b-primary"><span class="dot"></span> ${esc(ST[t.trang_thai] || t.trang_thai)}</span>`,
      t.app_source ? `<span class="badge"><svg class="i i-12"><use href="#i-branch"/></svg> ${esc(t.app_source)}</span>` : "",
    ];
    $("#detailBadges").innerHTML = badges.join("");

    // People + times
    const bpi = initial(t.nguoi_bao_ho_ten || t.nguoi_bao);
    const xpi = initial(t.nguoi_xu_ly_ho_ten || t.nguoi_xu_ly);
    $("#detailPeople").innerHTML = `
      <span class="m-item"><span class="m-label">Báo</span>
        <span class="person-mini"><span class="av av-sm av-r">${esc(bpi)}</span> ${esc(t.nguoi_bao_ho_ten || t.nguoi_bao || "?")}</span></span>
      <span class="m-item"><span class="m-label">Xử lý</span>
        <span class="person-mini">${t.nguoi_xu_ly ? `<span class="av av-sm av-b">${esc(xpi)}</span> ${esc(t.nguoi_xu_ly_ho_ten || t.nguoi_xu_ly)}` : "<em class='dim'>Chưa gán</em>"}</span></span>
      <span class="m-item"><span class="m-label">Mở</span><span class="person-mini mono" style="font-size:12px;">${fmtTime(t.created_at)}</span></span>
      <span class="m-item"><span class="m-label">Cập nhật</span><span class="person-mini mono" style="font-size:12px;">${fmtTime(t.updated_at)}</span></span>`;

    // Actions
    const isCn = t.viewer_is_cn || S.is_cn;
    const acts = [];
    acts.push(`<button class="btn btn-ghost btn-sm" onclick="location.href='/support'"><svg class="i i-14"><use href="#i-arrow-r"/></svg> Về danh sách</button>`);
    if (isCn) {
      if (t.trang_thai !== "dong") {
        acts.push(`<button class="btn btn-sm" data-act="status" data-st="dang_xu_ly">Nhận xử lý</button>`);
        acts.push(`<button class="btn btn-sm" data-act="status" data-st="cho_phan_hoi">Chờ raiser</button>`);
        acts.push(`<button class="btn btn-primary btn-sm" data-act="status" data-st="da_xu_ly"><svg class="i i-14"><use href="#i-check"/></svg> Đã xử lý</button>`);
        acts.push(`<button class="btn btn-sm" data-act="status" data-st="dong">Đóng</button>`);
      } else {
        acts.push(`<button class="btn btn-sm" data-act="status" data-st="dang_xu_ly">Mở lại</button>`);
      }
    }
    $("#detailActions").innerHTML = acts.join(" ");
    $$('#detailActions [data-act="status"]').forEach(b => b.addEventListener("click", () => changeStatus(t.id, b.dataset.st)));

    // Stepper
    const stepIdx = ST_IDX[t.trang_thai] ?? 0;
    $$("#mainSteps .step").forEach(s => {
      const idx = parseInt(s.dataset.idx);
      s.classList.remove("done", "current");
      if (idx < stepIdx) s.classList.add("done");
      else if (idx === stepIdx) s.classList.add("current");
    });
    $("#railFill").style.width = `calc(${stepIdx * 25}% - 32px)`;

    // Bug flow
    if (t.loai === "bug") {
      $("#bugFlowWrap").style.display = "";
      const bIdx = BUG[t.bug_status] ?? -1;  // -1 = chua_tai_hien
      $$("#bugSteps .bstep").forEach(s => {
        const idx = parseInt(s.dataset.idx);
        s.classList.remove("done", "current");
        if (idx < bIdx) s.classList.add("done");
        else if (idx === bIdx) s.classList.add("current");
      });
      const pctShown = Math.max(0, bIdx + 1);
      $("#brailFill").style.width = ((pctShown / 5) * 100) + "%";
      $("#bugFlowCount").textContent = `${pctShown}/5`;
      if (isCn) {
        const btn = $("#btnBugAdvance");
        const nextKey = BUG_NEXT[t.bug_status || "null"] || null;
        if (nextKey) {
          btn.style.display = "";
          btn.dataset.next = nextKey;
          btn.onclick = () => changeBugStatus(t.id, nextKey);
        } else {
          btn.style.display = "none";
        }
      }
      // Click each bug step (CN) to jump
      if (isCn) {
        $$("#bugSteps .bstep").forEach(s => s.addEventListener("click", () => changeBugStatus(t.id, s.dataset.val)));
        $$("#bugSteps .bstep").forEach(s => s.style.cursor = "pointer");
      }
    } else {
      $("#bugFlowWrap").style.display = "none";
    }

    // Description
    const descHtml = t.mo_ta ? esc(t.mo_ta).replace(/\n/g, "<br>") : "<em class='dim'>(không có mô tả)</em>";
    $("#detailDesc").innerHTML = `<p>${descHtml}</p>`;

    // Attachments — render REAL image thumbnails, click opens lightbox modal
    const attachs = (t.attachments || []).filter(a => a.url);
    window.__ATTACHS__ = attachs;  // for lightbox nav
    if (attachs.length) {
      $("#attachCard").style.display = "";
      $("#attachCount").textContent = attachs.length;
      $("#detailAttach").innerHTML = attachs.map((a, i) => {
        const isImg = !a.content_type || a.content_type.startsWith("image/");
        const prev = isImg
          ? `<div class="attach-prev" style="padding:0;background:#F1F5F9;">
               <img src="${esc(a.url)}" alt="${esc(a.orig_name || a.filename)}" loading="lazy"
                    style="width:100%;height:100%;object-fit:cover;display:block;"
                    onerror="this.style.display='none';this.parentElement.style.display='flex';this.parentElement.innerHTML='<svg class=&quot;i&quot; style=&quot;width:32px;height:32px;color:var(--danger);&quot;><use href=&quot;#i-alert&quot;/></svg>';">
             </div>`
          : `<div class="attach-prev p${(i % 4) + 1}"><svg class="i"><use href="#i-file"/></svg></div>`;
        return `
        <div class="attach" data-lb-idx="${i}">
          ${prev}
          <div class="attach-body">
            <div class="attach-name">${esc(a.orig_name || a.filename)}</div>
            <div class="attach-sub"><span>${((a.size_bytes || 0) / 1024).toFixed(0)} KB</span>${a.content_type ? '<span>·</span><span>' + esc(a.content_type.split("/")[1] || "") + '</span>' : ''}</div>
          </div>
        </div>`;
      }).join("");
      // Wire click → lightbox
      $$("#detailAttach .attach").forEach(card => {
        card.addEventListener("click", () => {
          const idx = parseInt(card.dataset.lbIdx);
          openLightbox(idx);
        });
      });
    } else {
      $("#attachCard").style.display = "none";
      window.__ATTACHS__ = [];
    }

    // Timeline events
    const events = t.events || [];
    $("#detailTimeline").innerHTML = events.length ? events.map(e => renderEvent(e)).join("") : `<div class="dim" style="padding:12px 0;font-size:13px;">Chưa có hoạt động.</div>`;

    // Comments
    renderComments(t.comments || []);

    // Sidebar
    renderSidebar(t, isCn);

    // Wire comment send
    const btnSend = $("#btnSendComment");
    if (btnSend) btnSend.onclick = () => sendComment(t.id);
    const cInp = $("#commentInput");
    if (cInp) cInp.onkeydown = (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) sendComment(t.id); };
  }

  function renderEvent(e) {
    let iconCls = "t-attach", icon = "i-act", txt = e.text || e.kind;
    if (e.kind === "created") { iconCls = "t-create"; icon = "i-plus"; }
    else if (e.kind === "assigned") { iconCls = "t-assign"; icon = "i-user"; }
    else if (e.kind === "support_change_status") { iconCls = "t-status"; icon = "i-arrow-r"; }
    else if (e.kind === "support_change_bug_status") { iconCls = "t-bug"; icon = "i-bug"; }
    else if (e.kind === "support_add_comment") { iconCls = "t-attach"; icon = "i-msg"; }
    const actorName = e.actor_ho_ten || e.actor || "system";
    return `<div class="tl">
      <div class="tl-icon ${iconCls}"><svg><use href="#${icon}"/></svg></div>
      <div class="tl-body"><strong>${esc(actorName)}</strong> ${esc(txt)}<span class="tl-time">${esc(fmtTime(e.when))}</span></div>
    </div>`;
  }

  function renderComments(cmts) {
    $("#commentCount").textContent = cmts.length;
    const host = $("#commentList");
    if (!cmts.length) {
      host.innerHTML = `<div style="padding:12px 0;color:var(--text-3);font-size:13px;">Chưa có bình luận. Là người đầu tiên viết!</div>`;
      return;
    }
    host.innerHTML = cmts.map(c => {
      const av = c.is_cn_author ? "av-b" : "av-r";
      const cls = c.is_noi_bo ? " internal" : "";
      const badge = c.is_cn_author
        ? '<span class="badge b-primary">Công Nghệ</span>'
        : '<span class="badge">Raiser</span>';
      const internalBadge = c.is_noi_bo ? '<span class="badge b-warning"><svg class="i i-12"><use href="#i-eye"/></svg> Nội bộ CN</span>' : "";
      return `<div class="comment${cls}">
        <div class="av av-md ${av}">${esc(initial(c.ho_ten || c.username))}</div>
        <div class="comment-body">
          <div class="comment-head">
            <span class="c-author">${esc(c.ho_ten || c.username)}</span>
            ${badge}
            ${internalBadge}
            <span class="c-time">${esc(fmtTime(c.created_at))}</span>
          </div>
          <div class="comment-content prose prose-sm"><p>${esc(c.noi_dung).replace(/\n/g, "<br>")}</p></div>
        </div>
      </div>`;
    }).join("");
  }

  function renderSidebar(t, isCn) {
    const bpi = initial(t.nguoi_bao_ho_ten || t.nguoi_bao);
    const xpi = initial(t.nguoi_xu_ly_ho_ten || t.nguoi_xu_ly);
    $("#sideStatus").innerHTML = `
      <div class="row"><span class="lbl">Workflow</span><span class="badge b-primary"><span class="dot"></span> ${esc(ST[t.trang_thai] || t.trang_thai)}</span></div>
      <div class="row"><span class="lbl">Ưu tiên</span><span class="badge ${UT_BADGE[t.muc_uu_tien]}"><span class="dot"></span> ${esc(UT[t.muc_uu_tien] || t.muc_uu_tien)}</span></div>
      <div class="row"><span class="lbl">Loại</span><span class="badge ${LOAI_BADGE[t.loai]}"><svg class="i i-12"><use href="#${LOAI_ICON[t.loai] || "i-msg"}"/></svg> ${esc(LOAI[t.loai] || t.loai)}</span></div>
      ${t.loai === "bug" && t.bug_status ? `<div class="row"><span class="lbl">Bug status</span><span class="badge b-danger"><span class="dot"></span> ${esc(BUG_LABEL[t.bug_status])}</span></div>` : ""}`;

    $("#sidePeople").innerHTML = `
      <div class="row people"><span class="lbl">Người báo</span>
        <div class="person"><span class="av av-sm av-r">${esc(bpi)}</span>
          <div class="person-info"><div>${esc(t.nguoi_bao || "?")}</div><div class="dim">${esc(t.nguoi_bao_ho_ten || "")}${t.nguoi_bao_phong_ban ? " · " + esc(t.nguoi_bao_phong_ban) : ""}</div></div></div></div>
      <div class="row people"><span class="lbl">Người xử lý</span>
        <div class="person">${t.nguoi_xu_ly ? `<span class="av av-sm av-b">${esc(xpi)}</span><div class="person-info"><div>${esc(t.nguoi_xu_ly)}</div><div class="dim">${esc(t.nguoi_xu_ly_ho_ten || "")}</div></div>` : '<em class="dim">Chưa gán</em>'}</div></div>`;

    const now = new Date();
    const slaPh = t.sla_phan_hoi_han ? new Date(t.sla_phan_hoi_han) : null;
    const slaXl = t.sla_xu_ly_han ? new Date(t.sla_xu_ly_han) : null;
    const phRes = slaPh ? (now < slaPh ? { txt: "Còn " + timeUntil(slaPh), cls: "p-warn" } : { txt: "Quá hạn", cls: "p-warn" }) : { txt: "—", cls: "" };
    const xlRes = slaXl ? (now < slaXl ? { txt: "Còn " + timeUntil(slaXl), cls: "p-warn" } : { txt: "Quá hạn", cls: "p-warn" }) : { txt: "—", cls: "" };
    $("#sideSla").innerHTML = `
      <div class="row"><span class="lbl">Phản hồi</span><span class="${phRes.cls}" style="font-size:12px;">${esc(phRes.txt)}</span></div>
      <div class="row"><span class="lbl">Xử lý xong</span><span class="${xlRes.cls}" style="font-size:12px;">${esc(xlRes.txt)}</span></div>
      <div class="row"><span class="lbl">Mở lúc</span><span class="mono" style="font-size:11.5px;">${esc(fmtFull(t.created_at))}</span></div>
      ${t.closed_at ? `<div class="row"><span class="lbl">Đóng lúc</span><span class="mono" style="font-size:11.5px;">${esc(fmtFull(t.closed_at))}</span></div>` : ""}`;

    $("#sideDetails").innerHTML = `
      <div class="row"><span class="lbl">App</span><span class="mono-chip"><span class="dot"></span> ${esc(t.app_source || "?")}.qlpps.com</span></div>
      <div class="row"><span class="lbl">Phòng ban báo</span><span style="font-size:12px;">${esc(t.nguoi_bao_phong_ban || "—")}</span></div>
      <div class="row"><span class="lbl">Số ảnh kèm</span><span class="mono" style="font-size:12px;">${(t.attachments || []).length}</span></div>`;

    const rel = t.related || [];
    if (rel.length === 0) {
      $("#sideRelated").innerHTML = `<div class="dim" style="font-size:12px;padding:4px 0;">Chưa có ticket khác</div>`;
    } else {
      $("#sideRelated").innerHTML = rel.map(r => {
        const done = r.trang_thai === "da_xu_ly" || r.trang_thai === "dong";
        const cls = done ? "status-done" : "status-doing";
        const ic = done ? "i-check" : "";
        return `<a class="rel" href="/support/${r.id}">
          <span class="rel-status ${cls}">${ic ? `<svg class="i i-12"><use href="#${ic}"/></svg>` : "◐"}</span>
          <span class="rel-id">ITQ-${String(r.id).padStart(3, "0")}</span>
          <span class="rel-title">${esc(r.tieu_de)}</span>
        </a>`;
      }).join("");
    }
  }

  function timeUntil(d) {
    const diff = (d - new Date()) / 1000;
    if (diff < 0) return "quá hạn";
    if (diff < 3600) return Math.floor(diff / 60) + "m";
    if (diff < 86400) return Math.floor(diff / 3600) + "h " + Math.floor((diff % 3600) / 60) + "m";
    return Math.floor(diff / 86400) + " ngày";
  }

  async function changeStatus(tid, st) {
    try {
      const r = await fetch(`/api/support/tickets/${tid}/status`, {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trang_thai: st }),
      });
      if (!r.ok) throw new Error(await parseErr(r));
      showToast(`Đã đổi trạng thái → ${ST[st] || st}`);
      loadDetail(tid);
    } catch (e) { showToast("Lỗi: " + e.message, "danger"); }
  }

  async function changeBugStatus(tid, bs) {
    try {
      const r = await fetch(`/api/support/tickets/${tid}/bug-status`, {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bug_status: bs }),
      });
      if (!r.ok) throw new Error(await parseErr(r));
      showToast(`Bug status → ${BUG_LABEL[bs] || bs}`);
      loadDetail(tid);
    } catch (e) { showToast("Lỗi: " + e.message, "danger"); }
  }

  async function sendComment(tid) {
    const inp = $("#commentInput");
    const txt = inp.value.trim();
    if (!txt) return;
    const internal = $("#cmtInternal") && $("#cmtInternal").checked;
    try {
      const r = await fetch(`/api/support/tickets/${tid}/comment`, {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ noi_dung: txt, is_noi_bo: !!internal }),
      });
      if (!r.ok) throw new Error(await parseErr(r));
      inp.value = "";
      showToast("Đã gửi bình luận");
      loadDetail(tid);
    } catch (e) { showToast("Lỗi: " + e.message, "danger"); }
  }

  async function parseErr(r) {
    try { const j = await r.json(); return j.detail || ("HTTP " + r.status); } catch (_) { return "HTTP " + r.status; }
  }

  // ══ RAISE ══════════════════════════════════════════════════════════
  function wireRaise() {
    const view = $("#view-raise");
    if (!view) return;
    window.__PENDING_FILES__ = [];

    const btnSubmit = $("#submitBtn");
    if (btnSubmit) btnSubmit.addEventListener("click", submitRaise);

    // File input
    if (!$("#supportFileInput")) {
      const inp = document.createElement("input");
      inp.type = "file"; inp.multiple = true; inp.accept = "image/*"; inp.id = "supportFileInput"; inp.style.display = "none";
      inp.addEventListener("change", () => { addFiles(Array.from(inp.files || [])); inp.value = ""; });
      document.body.appendChild(inp);
    }
    view.querySelectorAll(".attach-btn, .thumb.add").forEach(b =>
      b.addEventListener("click", (e) => { e.preventDefault(); $("#supportFileInput").click(); }));

    const zone = $("#attachZone");
    if (zone) {
      ["dragenter","dragover"].forEach(ev => zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.add("hover"); }));
      ["dragleave"].forEach(ev => zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.remove("hover"); }));
      zone.addEventListener("drop", e => {
        e.preventDefault(); zone.classList.remove("hover");
        addFiles(Array.from(e.dataTransfer?.files || []).filter(f => f.type.startsWith("image/")));
      });
    }
    // Paste from clipboard
    view.addEventListener("paste", e => {
      const files = Array.from(e.clipboardData?.items || []).filter(x => x.type.startsWith("image/")).map(x => x.getAsFile()).filter(Boolean);
      if (files.length) addFiles(files);
    });
    // Cmd+Enter submit
    view.addEventListener("keydown", e => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submitRaise(e);
    });
  }

  function addFiles(files) {
    if (!files || !files.length) return;
    const grid = $("#thumbGrid");
    const addBtn = grid.querySelector(".thumb.add");
    files.slice(0, 20).forEach(f => {
      window.__PENDING_FILES__.push(f);
      const idx = window.__PENDING_FILES__.length - 1;
      const el = document.createElement("div");
      el.className = "thumb t" + ((idx % 4) + 1);
      el.dataset.idx = idx;
      const rd = new FileReader();
      rd.onload = e => { el.style.background = `center/cover no-repeat url("${e.target.result}")`; };
      rd.readAsDataURL(f);
      el.innerHTML = `<button class="rm" title="Xóa" type="button">×</button><span class="name">${esc(f.name)}</span>`;
      el.querySelector(".rm").addEventListener("click", e => {
        e.stopPropagation();
        const rmi = parseInt(el.dataset.idx);
        window.__PENDING_FILES__[rmi] = null;
        el.remove(); updateAttachMeta();
      });
      grid.insertBefore(el, addBtn);
    });
    updateAttachMeta();
  }

  function updateAttachMeta() {
    const meta = $("#view-raise .drop-meta span:first-child");
    if (!meta) return;
    const files = (window.__PENDING_FILES__ || []).filter(Boolean);
    const mb = files.reduce((s, f) => s + f.size, 0) / (1024 * 1024);
    meta.innerHTML = `${files.length} ảnh · <span class="dim">${mb.toFixed(1)} MB / 80 MB</span>`;
  }

  async function submitRaise(ev) {
    if (ev) ev.preventDefault();
    const view = $("#view-raise");
    const btn = $("#submitBtn");
    const tieu_de = $("#tieude").value.trim();
    if (!tieu_de || tieu_de.length < 4) { showToast("Tiêu đề tối thiểu 4 ký tự", "danger"); return; }
    const orig = btn.innerHTML;
    btn.disabled = true; btn.innerHTML = '<svg class="i i-14"><use href="#i-clock"/></svg> Đang gửi…';
    try {
      const fd = new FormData();
      fd.append("tieu_de", tieu_de);
      fd.append("mo_ta", $("#mota").value.trim());
      const loai = view.querySelector('[data-radio="loai"] .chip-radio.active')?.dataset.val || "bug";
      const pri = view.querySelector('[data-radio="pri"] .chip-radio.active')?.dataset.val || "vua";
      fd.append("loai", loai);
      fd.append("muc_uu_tien", pri);
      (window.__PENDING_FILES__ || []).filter(Boolean).forEach(f => fd.append("images", f));
      const r = await fetch("/api/support/tickets", { method: "POST", body: fd, credentials: "same-origin" });
      if (!r.ok) throw new Error(await parseErr(r));
      const t = await r.json();
      showToast(`Đã gửi ITQ-${String(t.id).padStart(3, "0")}!`);
      setTimeout(() => location.href = "/support/" + t.id, 800);
    } catch (e) {
      showToast("Lỗi: " + e.message, "danger");
      btn.disabled = false; btn.innerHTML = orig;
    }
  }

  // ══ Global bits ═════════════════════════════════════════════════════
  function showToast(msg, kind) {
    const t = $("#toast"); if (!t) return;
    $("#toast-msg").textContent = msg;
    t.style.background = kind === "danger" ? "#B91C1C" : "";
    t.style.display = "inline-flex";
    clearTimeout(window.__toast_t);
    window.__toast_t = setTimeout(() => t.style.display = "none", 2400);
  }

  // Chip radio toggle (used in Raise + potentially Filter re-render)
  function wireChipRadios(scope) {
    (scope || document).querySelectorAll(".chip-row[data-radio]").forEach(row => {
      row.querySelectorAll(".chip-radio").forEach(chip => chip.addEventListener("click", (e) => {
        e.preventDefault();
        row.querySelectorAll(".chip-radio").forEach(c => c.classList.remove("active"));
        chip.classList.add("active");
      }));
    });
  }
  wireChipRadios();

  // Avatar dropdown
  const avMenu = $("#avatarMenu"), avBtn = $("#avatarBtn");
  if (avBtn && avMenu) {
    avBtn.addEventListener("click", e => { e.stopPropagation(); avMenu.classList.toggle("open"); });
    document.addEventListener("click", e => { if (!avMenu.contains(e.target)) avMenu.classList.remove("open"); });
    const menu = avMenu.querySelector(".avatar-menu");
    if (menu) menu.addEventListener("click", e => e.stopPropagation());
  }

  // Welcome dismiss
  const hero = $("#welcomeHero");
  if (hero) {
    hero.querySelector(".hero-dismiss")?.addEventListener("click", () => {
      hero.style.transition = "all 0.4s ease";
      hero.style.transform = "translateY(-20px) scale(0.98)";
      hero.style.opacity = "0";
      setTimeout(() => hero.style.display = "none", 400);
    });
  }

  // Confetti
  function confetti(x, y) {
    const colors = ["#2563EB","#60A5FA","#22C55E","#F59E0B","#EF4444","#8B5CF6","#EC4899","#FCD34D"];
    for (let i = 0; i < 30; i++) {
      const p = document.createElement("span");
      p.className = "confetti-piece";
      p.style.left = x + "px"; p.style.top = y + "px";
      p.style.background = colors[i % colors.length];
      const a = (Math.PI * 2 * i) / 30 + (Math.random() - 0.5) * 0.4;
      const d = 120 + Math.random() * 200;
      p.style.setProperty("--dx", Math.cos(a) * d + "px");
      p.style.setProperty("--dy", Math.sin(a) * d * 0.6 + 100 + Math.random() * 200 + "px");
      p.style.setProperty("--rot", (Math.random() * 1080 - 540) + "deg");
      document.body.appendChild(p);
      setTimeout(() => p.remove(), 2400);
    }
  }
  document.querySelectorAll(".btn-confetti").forEach(b => b.addEventListener("click", () => {
    const r = b.getBoundingClientRect();
    confetti(r.left + r.width / 2, r.top + r.height / 2);
  }));

  const fh = $("#floatHelp");
  if (fh) fh.addEventListener("click", () => {
    const r = fh.getBoundingClientRect(); confetti(r.left + r.width / 2, r.top + r.height / 2);
  });

  // ══ Boot ═══════════════════════════════════════════════════════════
  activateView(S.initial_view || "mine");
  if (S.initial_view === "mine" || !S.initial_view) loadMine();
  if (S.initial_view === "detail" && S.initial_tid) loadDetail(S.initial_tid);
  if (S.initial_view === "raise") wireRaise();
  // In case tab is switched dynamically, wire raise too
  else if (S.initial_view !== "raise") wireRaise();
})();

// ═══ LIGHTBOX (image viewer modal) ═════════════════════════════════════
(function () {
  const $  = (sel) => document.querySelector(sel);
  const lb = $("#lightbox");
  if (!lb) return;
  const lbImg      = $("#lbImg");
  const lbName     = $("#lbName");
  const lbCounter  = $("#lbCounter");
  const lbClose    = $("#lbClose");
  const lbPrev     = $("#lbPrev");
  const lbNext     = $("#lbNext");
  const lbBackdrop = $("#lbBackdrop");
  const lbDownload = $("#lbDownload");
  const lbOpen     = $("#lbOpen");
  const lbLoading  = $("#lbLoading");
  let currentIdx = 0;

  function attachs() { return window.__ATTACHS__ || []; }

  function updateNavButtons() {
    const list = attachs();
    lbPrev.disabled = currentIdx <= 0;
    lbNext.disabled = currentIdx >= list.length - 1;
  }

  function show(idx) {
    const list = attachs();
    if (!list.length) return;
    currentIdx = Math.max(0, Math.min(list.length - 1, idx));
    const a = list[currentIdx];
    lbImg.classList.add("loading");
    lbLoading.classList.add("show");
    lbImg.onload = () => { lbImg.classList.remove("loading"); lbLoading.classList.remove("show"); };
    lbImg.onerror = () => { lbLoading.textContent = "Không tải được ảnh"; lbLoading.classList.add("show"); };
    lbImg.src = a.url;
    lbImg.alt = a.orig_name || a.filename || "";
    lbName.textContent = a.orig_name || a.filename || "";
    lbCounter.textContent = `${currentIdx + 1}/${list.length}`;
    if (lbDownload) { lbDownload.href = a.url; lbDownload.setAttribute("download", a.orig_name || a.filename || "image"); }
    if (lbOpen) lbOpen.href = a.url;
    updateNavButtons();
  }

  window.openLightbox = function (idx) {
    show(idx || 0);
    lb.classList.add("open");
    lb.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  };
  function close() {
    lb.classList.remove("open");
    lb.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    lbImg.src = "";
  }
  window.closeLightbox = close;

  lbClose.addEventListener("click", close);
  lbBackdrop.addEventListener("click", close);
  lbImg.addEventListener("click", close);
  lbPrev.addEventListener("click", (e) => { e.stopPropagation(); if (currentIdx > 0) show(currentIdx - 1); });
  lbNext.addEventListener("click", (e) => { e.stopPropagation(); if (currentIdx < attachs().length - 1) show(currentIdx + 1); });

  document.addEventListener("keydown", (e) => {
    if (!lb.classList.contains("open")) return;
    if (e.key === "Escape") close();
    else if (e.key === "ArrowLeft" && currentIdx > 0) show(currentIdx - 1);
    else if (e.key === "ArrowRight" && currentIdx < attachs().length - 1) show(currentIdx + 1);
  });
})();
