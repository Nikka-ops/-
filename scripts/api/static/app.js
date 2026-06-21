const $ = (id) => document.getElementById(id);

let currentBank = null;
let currentPosts = [];
let currentClusters = [];
let currentBankQuestions = [];
let currentCompanies = [];
let currentSlug = null;
let frequencyReportText = "";
let activeCompany = "";
let viewMode = "posts";
let techRoles = [];
let mergedBankCount = 0;
let selectedRoleId = "ai_app";
let currentJobs = [];
let jobsMeta = null;
let jobsLoading = false;
let jobsLoadError = "";
let companyGroups = [];

const RECENCY_WINDOW_DAYS = 365;
const MERGED_AI_ROLE_NORMS = new Set(["ai应用开发", "agent开发", "ai/agent应用开发"]);

function canonicalRoleId(id) {
  return id === "agent" ? "ai_app" : id;
}

function equivalentRoleIds(roleId) {
  const c = canonicalRoleId(roleId);
  if (c === "ai_app") return new Set(["ai_app", "agent"]);
  return new Set([c]);
}

const COMPANY_GRADIENTS = [
  "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
  "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)",
  "linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)",
  "linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)",
  "linear-gradient(135deg, #fa709a 0%, #fee140 100%)",
  "linear-gradient(135deg, #a18cd1 0%, #fbc2eb 100%)",
  "linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%)",
  "linear-gradient(135deg, #fccb90 0%, #d57eeb 100%)",
];

function parseCompanies(raw) {
  return raw.split(/[,，、\n]/).map((s) => s.trim()).filter(Boolean);
}

function payloadBase() {
  const custom = $("role").value.trim();
  const body = {
    role_id: selectedRoleId,
    role: custom,
    companies: parseCompanies($("companies").value),
    refresh: $("refresh").checked,
    rebuild_only: $("rebuildOnly").checked,
    discover_nowcoder: $("discoverNowcoder").checked,
    discover_max_per_query: Number($("discoverMax").value) || 50,
    xhs_use_export: $("xhsUseExport").checked,
    xhs_priority: $("xhsPriority").checked,
    xhs_live: $("xhsLive").checked,
    xhs_deep: $("xhsDeep").checked,
    from_report: $("useLocalReport").checked,
    agent_handoff: false,
  };
  if ($("useLocalReport").checked) {
    body.raw_posts = $("rawPosts").value.trim() || "examples/sample_raw_posts.json";
  }
  return body;
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function imageProxyUrl(url) {
  if (!url) return "";
  const u = String(url).trim();
  if (!u.startsWith("http")) {
    return `/api/local-asset?path=${encodeURIComponent(u)}`;
  }
  try {
    const host = new URL(u).hostname;
    if (host.includes("nowcoder.com") || host.includes("xhscdn.com")) {
      return `/api/proxy-image?url=${encodeURIComponent(u)}`;
    }
  } catch {
    /* ignore */
  }
  return u;
}

function renderImageCarousel(post) {
  const urls = postImageUrls(post);
  if (!urls.length) return "";
  const ocrPages = post.image_page_ocr || post.image_ocr_pages || [];
  const slides = urls
    .map((u, i) => {
      const ocr = ocrPages[i]
        ? `<div class="xhs-slide-ocr">${escapeHtml(ocrPages[i].slice(0, 280))}${ocrPages[i].length > 280 ? "…" : ""}</div>`
        : "";
      return `<div class="xhs-carousel-slide${i === 0 ? " active" : ""}" data-index="${i}">
        <img src="${escapeHtml(imageProxyUrl(u))}" alt="面经第${i + 1}页" />
        ${ocr}
      </div>`;
    })
    .join("");
  return `<div class="xhs-carousel" data-total="${urls.length}">
    <div class="xhs-carousel-viewport">
      <div class="xhs-carousel-track">${slides}</div>
    </div>
    <button type="button" class="xhs-carousel-btn prev" aria-label="上一页">‹</button>
    <button type="button" class="xhs-carousel-btn next" aria-label="下一页">›</button>
    <div class="xhs-carousel-footer">
      <div class="xhs-carousel-dots">${urls
        .map(
          (_, i) =>
            `<button type="button" class="xhs-dot${i === 0 ? " active" : ""}" data-index="${i}" aria-label="第${i + 1}页"></button>`,
        )
        .join("")}</div>
      <span class="xhs-carousel-counter">1 / ${urls.length}</span>
    </div>
  </div>`;
}

function initImageCarousel(root) {
  const carousel = root.querySelector(".xhs-carousel");
  if (!carousel) return;
  const slides = [...carousel.querySelectorAll(".xhs-carousel-slide")];
  const dots = [...carousel.querySelectorAll(".xhs-dot")];
  const counter = carousel.querySelector(".xhs-carousel-counter");
  const total = slides.length;
  if (total <= 1) {
    carousel.querySelectorAll(".xhs-carousel-btn").forEach((b) => (b.hidden = true));
    return;
  }
  let idx = 0;

  function go(n) {
    idx = (n + total) % total;
    slides.forEach((s, i) => s.classList.toggle("active", i === idx));
    dots.forEach((d, i) => d.classList.toggle("active", i === idx));
    if (counter) counter.textContent = `${idx + 1} / ${total}`;
  }

  carousel.querySelector(".xhs-carousel-btn.prev")?.addEventListener("click", () => go(idx - 1));
  carousel.querySelector(".xhs-carousel-btn.next")?.addEventListener("click", () => go(idx + 1));
  dots.forEach((d) => {
    d.addEventListener("click", () => go(Number(d.dataset.index)));
  });

  let startX = 0;
  carousel.addEventListener(
    "touchstart",
    (e) => {
      startX = e.touches[0].clientX;
    },
    { passive: true },
  );
  carousel.addEventListener(
    "touchend",
    (e) => {
      const dx = e.changedTouches[0].clientX - startX;
      if (dx > 50) go(idx - 1);
      else if (dx < -50) go(idx + 1);
    },
    { passive: true },
  );
}

function renderPostImages(post, { modal = false } = {}) {
  const urls = postImageUrls(post);
  if (!urls.length) return "";
  if (modal) {
    return renderImageCarousel(post);
  }
  const cls = "post-images card-thumb";
  return `<div class="${cls}"><figure class="post-image-fig"><img src="${escapeHtml(imageProxyUrl(urls[0]))}" alt="面经封面" loading="lazy" /></figure>${urls.length > 1 ? `<span class="img-more">共 ${urls.length} 页</span>` : ""}</div>`;
}

function postImageUrls(post) {
  if (post.image_urls && post.image_urls.length) return post.image_urls;
  return (post.asset_paths || []).filter((u) => /^https?:\/\//i.test(String(u)));
}

function postPlainText(post) {
  if (post.display_text) return post.display_text;
  const raw = post.raw_text || post.content_text || post.locator_text || "";
  if (!raw) return post.preview || "";
  return raw
    .replace(/\[图片 OCR 第\s*\d+\s*页\]\s*\n?/gi, "")
    .replace(/#[^\s#]+(?:\[话题\])?#?/g, "")
    .replace(/(?<![#\w/])#[\w\u4e00-\u9fff]{2,}(?:\[话题\])?/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function postBodyHtml(post) {
  if (post.display_html) return post.display_html;
  const text = postPlainText(post);
  if (!text) return "";
  return text
    .split("\n")
    .map((line) => {
      const t = line.trim();
      if (!t) return "<br>";
      const cls = /^\d+[\.\、\)）]/.test(t) || /^[\-•●]/.test(t) ? "post-line bullet" : "post-line";
      return `<p class="${cls}">${escapeHtml(t)}</p>`;
    })
    .join("");
}

function setLoading(on, msg = "") {
  $("submitBank").disabled = on;
  $("status").textContent = msg;
  $("feedLoading").hidden = !on;
}

function companyGradient(name) {
  let h = 0;
  for (let i = 0; i < name.length; i += 1) h = (h + name.charCodeAt(i) * 17) % COMPANY_GRADIENTS.length;
  return COMPANY_GRADIENTS[h];
}

function sourceLabel(ref, source) {
  const s = ref || source || "";
  if (s.includes("xiaohongshu") || s.includes("xhs")) return { name: "小红书", cls: "src-xhs" };
  if (s.includes("nowcoder")) return { name: "牛客", cls: "src-nc" };
  return { name: source === "xiaohongshu" ? "小红书" : source === "nowcoder" ? "牛客" : "面经", cls: "src-default" };
}

function highlightText(text, query) {
  const safe = escapeHtml(text);
  if (!query) return safe;
  const re = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
  return safe.replace(re, "<mark>$1</mark>");
}

function normRole(text) {
  return String(text || "").replace(/\s+/g, "").toLowerCase();
}

function bankMatchesRole(bank, role) {
  if (bank.role_id && bank.role_id === role.id) return true;
  const bankRole = normRole(bank.role);
  const targets = [normRole(role.search_as), normRole(role.label)].filter(Boolean);
  return targets.some((t) => bankRole === t);
}

function pickBankForRole(role, list, { companies = [] } = {}) {
  const byId = list.filter((b) => b.role_id && b.role_id === role.id);
  const pool = byId.length ? byId : list.filter((b) => bankMatchesRole(b, role));
  if (!pool.length) return null;

  const companiesNorm = companies.map(normRole).filter(Boolean);
  let candidates = pool;
  if (!companiesNorm.length) {
    const roleOnly = pool.filter((b) => !((b.companies || []).length));
    if (roleOnly.length) candidates = roleOnly;
  } else {
    const withCo = pool.filter((b) => {
      const bankCos = (b.companies || []).map(normRole);
      return companiesNorm.some((c) => bankCos.includes(c));
    });
    if (withCo.length) candidates = withCo;
    else candidates = pool;
  }

  candidates.sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
  return candidates[0];
}

async function loadRoleBundle(role, companies = []) {
  const qs =
    companies.length > 0
      ? `?companies=${encodeURIComponent(companies.join(","))}`
      : "";
  return getJson(`/api/role-bundle/${encodeURIComponent(canonicalRoleId(role.id))}${qs}`);
}

function syncRoleFromBank() {
  if (!currentBank?.role || !techRoles.length) return;
  const bankRole = normRole(currentBank.role);
  const role = techRoles.find(
    (r) => normRole(r.search_as) === bankRole || normRole(r.label) === bankRole
      || (r.id === "ai_app" && MERGED_AI_ROLE_NORMS.has(bankRole)),
  );
  if (!role) return;
  selectedRoleId = role.id;
  $("role").value = role.search_as;
  renderRoleChips($("roleChipRow"), selectRole);
  renderRoleChips($("roleChipRowDrawer"), selectRole);
}

function showRolePending(role) {
  currentBank = {
    role: role.search_as,
    generated_at: "",
    recency_window_days: RECENCY_WINDOW_DAYS,
  };
  currentPosts = [];
  currentClusters = [];
  currentCompanies = [];
  currentSlug = null;
  frequencyReportText = "";
  activeCompany = "";
  $("searchQ").value = "";
  $("feedError").hidden = true;
  renderCompanyChips();
  $("feedHint").hidden = false;
  $("feedHint").textContent =
    `「${role.label}」暂无面经库 — 打开页会自动读本地缓存；点 ⚙「抓取并生成面经库」才会联网更新`;
  const emptyP = $("feedEmpty").querySelector("p");
  if (emptyP) {
    emptyP.textContent = `「${role.label}」还没有已保存的面经库`;
  }
  renderCurrentView();
}

function renderRoleChips(container, onSelect) {
  if (!container || !techRoles.length) return;
  container.innerHTML = techRoles
    .map((r) => {
      const active = r.id === selectedRoleId;
      return `<button type="button" class="chip role-chip${active ? " active" : ""}" data-role-id="${escapeHtml(r.id)}" title="${escapeHtml(r.search_as)}">${escapeHtml(r.label)}</button>`;
    })
    .join("");
  container.querySelectorAll(".role-chip").forEach((btn) => {
    btn.addEventListener("click", () => onSelect(btn.dataset.roleId));
  });
}

function pickJobsSnapshot(snaps, roleId, roleLabel, companies = []) {
  if (!snaps?.length) return null;
  const roleNorm = normRole(roleLabel);
  const companiesNorm = companies.map(normRole).filter(Boolean);

  let pool = [];
  if (roleId) {
    const ids = equivalentRoleIds(roleId);
    const byId = snaps.filter((s) => ids.has(s.role_id));
    if (byId.length) pool = byId;
  }
  if (!pool.length && roleNorm) {
    pool = snaps.filter(
      (s) => normRole(s.role) === roleNorm
        || (canonicalRoleId(roleId) === "ai_app" && MERGED_AI_ROLE_NORMS.has(normRole(s.role))),
    );
  }
  if (!pool.length) return null;

  let candidates = pool;
  if (companiesNorm.length) {
    const withCo = pool.filter((s) => {
      const snapCos = (s.companies || []).map(normRole);
      return companiesNorm.some((c) => snapCos.includes(c));
    });
    if (withCo.length) candidates = withCo;
    else candidates = pool;
  } else {
    const roleOnly = pool.filter((s) => !((s.companies || []).length));
    if (roleOnly.length) candidates = roleOnly;
  }

  candidates.sort((a, b) => String(b.fetched_at || "").localeCompare(String(a.fetched_at || "")));
  return candidates[0] || null;
}

async function selectRole(roleId) {
  const rid = canonicalRoleId(roleId);
  const role = techRoles.find((r) => r.id === rid);
  if (!role) return;
  selectedRoleId = rid;
  $("role").value = role.search_as;
  renderRoleChips($("roleChipRow"), selectRole);
  renderRoleChips($("roleChipRowDrawer"), selectRole);
  activeCompany = "";

  setLoading(true);
  try {
    const companies = parseCompanies($("companies").value);
    const data = await loadRoleBundle(role, companies);
    showBundle(data);
    await refreshBankList();
  } catch (err) {
    if (err?.error === "no_banks_for_role") {
      showRolePending(role);
    } else {
      showError(humanError(err));
    }
  } finally {
    setLoading(false);
  }
  await loadLatestJobsSnapshot();
  renderCurrentView();
}

function allPresetCompanies() {
  const set = new Set();
  companyGroups.forEach((g) => (g.companies || []).forEach((c) => set.add(c)));
  return set;
}

function companyCountsForCurrentView() {
  const counts = {};
  const bump = (name) => {
    const n = String(name || "").trim();
    if (!n || n === "未标注") return;
    counts[n] = (counts[n] || 0) + 1;
  };
  if (viewMode === "jobs") {
    currentJobs.forEach((j) => bump(j.company));
  } else if (viewMode === "bank") {
    bankQuestionRows().forEach((q) => (q.company_tags || []).forEach(bump));
  } else {
    currentPosts.forEach((p) => bump(p.company_label));
  }
  return counts;
}

function totalItemsForCurrentView() {
  if (viewMode === "jobs") return currentJobs.length;
  if (viewMode === "bank") return bankQuestionRows().length;
  return currentPosts.length;
}

function collectOtherCompanies(counts, presetSet) {
  const other = new Set();
  const addName = (name) => {
    const n = String(name || "").trim();
    if (n && n !== "未标注" && !presetSet.has(n)) other.add(n);
  };
  currentCompanies.forEach((c) => addName(c.name));
  currentPosts.forEach((p) => addName(p.company_label));
  currentJobs.forEach((j) => addName(j.company));
  bankQuestionRows().forEach((q) => (q.company_tags || []).forEach(addName));
  Object.keys(counts).forEach((n) => addName(n));
  return [...other].sort(
    (a, b) => (counts[b] || 0) - (counts[a] || 0) || a.localeCompare(b, "zh-CN"),
  );
}

function companyChipHtml(name, count, active) {
  const label = name === "全部" ? "全部" : count > 0 ? `${name} (${count})` : name;
  return `<button type="button" class="chip${active ? " active" : ""}" data-company="${escapeHtml(name)}">${escapeHtml(label)}</button>`;
}

function syncCompaniesInput() {
  const input = $("companies");
  if (!input) return;
  input.value = activeCompany || "";
}

function renderCompanyChips() {
  const container = $("companyFilter");
  if (!container) return;
  const counts = companyCountsForCurrentView();
  const presetSet = allPresetCompanies();
  const total = totalItemsForCurrentView();

  let html = `<div class="company-group"><div class="chip-row">${companyChipHtml("全部", total, !activeCompany)}</div></div>`;

  companyGroups.forEach((group) => {
    const chips = (group.companies || [])
      .map((name) => companyChipHtml(name, counts[name] || 0, activeCompany === name))
      .join("");
    html += `<div class="company-group"><div class="company-group-head"><span class="company-group-label">${escapeHtml(group.label)}</span></div><div class="chip-row">${chips}</div></div>`;
  });

  const others = collectOtherCompanies(counts, presetSet);
  if (others.length) {
    const chips = others
      .map((name) => companyChipHtml(name, counts[name] || 0, activeCompany === name))
      .join("");
    html += `<div class="company-group"><div class="company-group-head"><span class="company-group-label">其他</span></div><div class="chip-row">${chips}</div></div>`;
  }

  container.innerHTML = html;
  container.querySelectorAll(".chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      activeCompany = btn.dataset.company === "全部" ? "" : btn.dataset.company;
      renderCompanyChips();
      renderCurrentView();
      syncCompaniesInput();
    });
  });
}

function filteredPosts() {
  const search = $("searchQ").value.trim().toLowerCase();
  return currentPosts.filter((p) => {
    if (activeCompany && p.company_label !== activeCompany) return false;
    if (!search) return true;
    const hay = [p.title, p.preview, p.raw_text, p.company_label, p.role_label, p.source]
      .join(" ")
      .toLowerCase();
    return hay.includes(search);
  });
}

function renderPostCard(post, index, query) {
  const src = sourceLabel(post.url, post.source);
  const company = post.company_label || "未标注";
  const hasImg = postImageUrls(post).length > 0;
  const coverH = hasImg ? 120 : 56 + Math.min(48, Math.floor((post.preview || "").length / 8));
  const thumb = hasImg ? renderPostImages(post) : "";
  const previewText = post.preview || (hasImg ? "图片面经，点击查看" : "");
  return `<article class="feed-card post-card" role="listitem" data-index="${index}" tabindex="0">
    <div class="card-cover${hasImg ? " has-image" : ""}" style="height:${coverH}px;background:${hasImg ? "#f0f0f0" : companyGradient(company)}">
      ${thumb}
      <span class="card-src ${src.cls}">${src.name}</span>
      <span class="card-co-badge">${escapeHtml(company)}</span>
    </div>
    <div class="card-body">
      <h3 class="card-title">${highlightText(post.title || "面经分享", query)}</h3>
      <p class="card-preview">${highlightText(previewText, query)}</p>
      <div class="card-foot">
        <span class="card-role">${escapeHtml(post.role_label || "")}</span>
        ${post.posted_at ? `<span class="card-date">${escapeHtml(post.posted_at)}</span>` : ""}
      </div>
    </div>
  </article>`;
}

function setViewMode(mode) {
  viewMode = mode;
  $("viewPosts").classList.toggle("active", mode === "posts");
  $("viewBank").classList.toggle("active", mode === "bank");
  $("viewJobs").classList.toggle("active", mode === "jobs");
  $("exportJson").hidden = mode === "jobs";
  $("exportBank").hidden = mode === "jobs";
  $("exportMd").hidden = mode === "jobs";
  $("exportJobs").hidden = mode !== "jobs";
  renderCompanyChips();
  if (mode === "jobs") {
    loadLatestJobsSnapshot();
  } else {
    renderCurrentView();
  }
}

function normalizeBankQuestions(rows) {
  return (rows || []).map((q, i) => ({
    ...q,
    rank: q.rank ?? i + 1,
    cluster_id: q.cluster_id || `c${String(i + 1).padStart(3, "0")}`,
    batch_count: q.batch_count ?? q.freq ?? 1,
    confidence: q.confidence || "低频",
  }));
}

function bankQuestionRows() {
  if (currentBankQuestions.length) {
    return currentBankQuestions;
  }
  return normalizeBankQuestions(
    currentClusters.map((c) => ({
      rank: c.rank,
      text: c.representative,
      cluster_id: c.cluster_id,
      batch_count: c.batch_count ?? c.freq,
      confidence: c.confidence,
      topic: c.topic,
      company_tags: c.company_tags,
      role_tags: c.role_tags,
      variants: c.variants,
      latest_posted_at: c.latest_posted_at,
      score: c.score,
      source_refs: c.source_refs,
    })),
  );
}

function filteredQuestions() {
  const search = $("searchQ").value.trim().toLowerCase();
  return bankQuestionRows().filter((q) => {
    if (activeCompany && !(q.company_tags || []).includes(activeCompany)) return false;
    if (!search) return true;
    const hay = [
      q.text,
      ...(q.variants || []),
      q.topic,
      ...(q.company_tags || []),
    ]
      .join(" ")
      .toLowerCase();
    return hay.includes(search);
  });
}

function filteredClusters() {
  const search = $("searchQ").value.trim().toLowerCase();
  return currentClusters.filter((c) => {
    if (activeCompany && !(c.company_tags || []).includes(activeCompany)) return false;
    if (!search) return true;
    const hay = [
      c.representative,
      ...(c.variants || []),
      c.topic,
      ...(c.company_tags || []),
    ].join(" ").toLowerCase();
    return hay.includes(search);
  });
}

function renderBankView() {
  const query = $("searchQ").value.trim();
  const list = filteredQuestions();
  const total = bankQuestionRows().length;
  $("feedGrid").hidden = true;
  $("bankListView").hidden = list.length === 0;
  $("jobsListView").hidden = true;
  $("feedEmpty").hidden = list.length > 0 || total === 0;
  $("feedHint").hidden = query.length > 0 || activeCompany || total > 0;

  if (currentBank) {
    $("feedMeta").hidden = false;
    $("bankTitle").textContent = `${currentBank.role || "题库"} · 题目列表`;
    const win = currentBank.recency_window_days || RECENCY_WINDOW_DAYS;
    $("bankSubtitle").textContent =
      `${list.length} / ${total} 道题 · 近 ${win} 天面经 · 按出现频次排序`;
  }

  $("bankListView").innerHTML = list
    .map(
      (q) => `<li class="cluster-item question-item" data-id="${escapeHtml(q.cluster_id || String(q.rank))}">
        <div class="cluster-rank">#${q.rank ?? ""}</div>
        <div class="cluster-body">
          <div class="cluster-title">${highlightText(q.text, query)}</div>
          <div class="cluster-meta">
            <span class="pill conf-${escapeHtml(q.confidence || "低频")}">${escapeHtml(q.confidence || "低频")}</span>
            <span class="pill">出现 ${q.batch_count ?? q.freq ?? 1} 次</span>
            <span class="pill topic">${escapeHtml(q.topic || "综合")}</span>
            ${(q.company_tags || []).slice(0, 2).map((co) => `<span class="pill">${escapeHtml(co)}</span>`).join("")}
          </div>
          ${(q.variants || []).length ? `<p class="cluster-variants">同类：${escapeHtml(q.variants.slice(0, 2).join("；"))}</p>` : ""}
        </div>
      </li>`
    )
    .join("");

  $("bankListView").querySelectorAll(".question-item").forEach((el) => {
    el.addEventListener("click", () => {
      const q = list.find((x) => (x.cluster_id || String(x.rank)) === el.dataset.id);
      if (q) openQuestionModal(q);
    });
  });
}

function relatedPostsForJob(job) {
  const urls = new Set((job.extra?.interview_post_urls || []).filter(Boolean));
  const fromCache = currentPosts.filter(
    (p) => urls.has(p.url) || urls.has(p.source_url),
  );
  if (fromCache.length) return fromCache;
  const company = String(job.company || "").trim();
  const title = String(job.title || "").trim().toLowerCase();
  if (!company) return [];
  return currentPosts.filter((p) => {
    const co = String(p.company_label || p.company || "").trim();
    if (!co.includes(company) && !company.includes(co)) return false;
    const blob = `${p.title || ""} ${p.raw_text || ""}`.toLowerCase();
    return title && blob.includes(title.slice(0, 8));
  }).slice(0, 5);
}

function jobInterviewBadge(job) {
  const n = job.extra?.interview_post_count || 0;
  if (n > 0) return `<span class="pill interview-pill">${n} 篇面经</span>`;
  return `<span class="pill muted-pill">无面经</span>`;
}

function jobDescBadge(job) {
  const has = (job.description || "").trim().length > 40;
  if (has) return "";
  return `<span class="pill muted-pill">无JD正文</span>`;
}

function filteredJobs() {
  const search = $("searchQ").value.trim().toLowerCase();
  const list = currentJobs.filter((j) => {
    if (activeCompany && j.company !== activeCompany) return false;
    if (!search) return true;
    const hay = [
      j.title,
      j.company,
      j.city,
      j.description,
      ...(j.tags || []),
    ]
      .join(" ")
      .toLowerCase();
    return hay.includes(search);
  });
  list.sort((a, b) => {
    const da = a.posted_at || "";
    const db = b.posted_at || "";
    if (da !== db) return db.localeCompare(da);
    return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
  });
  return list;
}

function jobSourceLabel(source) {
  const s = String(source || "");
  if (s.includes("boss")) return { name: "Boss", cls: "src-boss" };
  if (s.includes("job_pro")) return { name: "官网", cls: "src-official" };
  if (s.includes("bytedance")) return { name: "字节", cls: "src-official" };
  return { name: "招聘", cls: "src-default" };
}

function renderJobsView() {
  const query = $("searchQ").value.trim();
  const list = filteredJobs();
  const total = currentJobs.length;
  const searching = query.length > 0 || activeCompany;

  $("clearSearch").hidden = !query;
  $("feedGrid").hidden = true;
  $("bankListView").hidden = true;
  $("jobsListView").hidden = list.length === 0 && !jobsLoading;
  $("feedEmpty").hidden = list.length > 0 || total > 0 || jobsLoading;
  $("feedHint").hidden = searching || total > 0 || jobsLoading || jobsLoadError;
  $("fetchJobsInline").hidden = total > 0 || jobsLoading;
  $("resetFilters").hidden = viewMode === "jobs" && total === 0;

  if (jobsLoadError) {
    $("feedError").hidden = false;
    $("feedError").textContent = jobsLoadError;
  } else if (viewMode === "jobs") {
    $("feedError").hidden = true;
  }

  $("feedMeta").hidden = false;
  const roleLabel = $("role").value.trim() || currentBank?.role || "岗位";
  $("bankTitle").textContent = `${roleLabel} · 在招岗位`;
  const newCount = jobsMeta?.new_count ?? currentJobs.filter((j) => j.is_new).length;
  const fetchedAt = jobsMeta?.fetched_at || jobsMeta?.meta?.fetched_at || "";
  $("bankSubtitle").textContent = jobsLoading
    ? "正在拉取在招 JD…"
    : `${list.length} / ${total} 个岗位 · ${newCount} 个新开 · 近2月官网JD · 按发布日期排序 · ${fetchedAt ? `更新于 ${fetchedAt.slice(0, 19).replace("T", " ")}` : "点击 ⚙ 拉取在招岗位"}`;

  if (!jobsLoading && total === 0) {
    const emptyP = $("feedEmpty").querySelector("p");
    if (emptyP) {
      emptyP.textContent = jobsLoadError
        ? jobsLoadError
        : "暂无在招岗位 — 点击下方按钮拉取（需 Node.js + job-pro）";
    }
  }

  $("jobsListView").innerHTML = list
    .map((j, i) => {
      const src = jobSourceLabel(j.source);
      const descPreview = (j.description || "").replace(/\s+/g, " ").slice(0, 120);
      return `<li class="cluster-item job-item" data-index="${i}">
        <div class="cluster-rank">${j.is_new ? '<span class="job-new">新</span>' : "JD"}</div>
        <div class="cluster-body">
          <div class="cluster-title">${highlightText(j.title, query)}</div>
          <div class="cluster-meta">
            <span class="pill company-pill">${escapeHtml(j.company || "")}</span>
            ${j.city ? `<span class="pill">${escapeHtml(j.city)}</span>` : ""}
            ${j.posted_at ? `<span class="pill">${escapeHtml(j.posted_at)}</span>` : ""}
            ${j.salary ? `<span class="pill salary-pill">${escapeHtml(j.salary)}</span>` : ""}
            <span class="pill src-pill ${src.cls}">${escapeHtml(src.name)}</span>
            ${jobInterviewBadge(j)}
            ${jobDescBadge(j)}
            ${(j.tags || []).slice(0, 2).map((t) => `<span class="pill">${escapeHtml(t)}</span>`).join("")}
          </div>
          ${descPreview ? `<p class="cluster-variants">${highlightText(descPreview, query)}${(j.description || "").length > 120 ? "…" : ""}</p>` : ""}
        </div>
      </li>`;
    })
    .join("");

  $("jobsListView").querySelectorAll(".job-item").forEach((el) => {
    el.addEventListener("click", () => {
      const idx = Number(el.dataset.index);
      openJobModal(list[idx]);
    });
  });
}

function renderJobModalBody(job) {
  const src = jobSourceLabel(job.source);
  const desc = (job.description || "").trim();
  const descHtml = desc
    ? desc
        .split("\n")
        .map((line) => {
          const t = line.trim();
          if (!t) return "<br>";
          return `<p class="post-line">${escapeHtml(t)}</p>`;
        })
        .join("")
    : '<p class="muted">正在拉取岗位介绍…</p>';
  const related = relatedPostsForJob(job);
  const snippets = job.extra?.interview_snippets || [];
  let interviewHtml = "";
  if (related.length) {
    interviewHtml = `<section class="modal-section"><h3>相关面经（近3月）</h3><ul class="modal-interview-list">${related
      .map(
        (p) =>
          `<li><strong>${escapeHtml(p.company_label || p.company || "")}</strong> ${escapeHtml((p.title || p.raw_text || "").slice(0, 120))}${(p.url || p.source_url) ? ` <a href="${escapeHtml(p.url || p.source_url)}" target="_blank" rel="noopener">原文</a>` : ""}</li>`,
      )
      .join("")}</ul></section>`;
  } else if (snippets.length) {
    interviewHtml = `<section class="modal-section"><h3>相关面经片段</h3>${snippets
      .map((s) => `<p class="cluster-variants">${escapeHtml(s)}</p>`)
      .join("")}</section>`;
  } else {
    interviewHtml =
      '<p class="muted">暂无匹配面经 — 可重新「抓取面经」或拉取岗位时自动牛客补充搜索</p>';
  }
  $("modalBody").innerHTML = `
    <div class="modal-head">
      <span class="pill company-pill">${escapeHtml(job.company || "")}</span>
      ${job.is_new ? '<span class="pill job-new-pill">新开</span>' : ""}
      <span class="pill src-pill ${src.cls}">${escapeHtml(src.name)}</span>
      ${job.city ? `<span class="pill">${escapeHtml(job.city)}</span>` : ""}
      ${job.salary ? `<span class="pill salary-pill">${escapeHtml(job.salary)}</span>` : ""}
      ${jobInterviewBadge(job)}
    </div>
    <h2>${escapeHtml(job.title || "")}</h2>
    <div class="modal-job-body">${descHtml}</div>
    ${interviewHtml}
    <dl class="modal-dl">
      ${job.experience ? `<dt>经验</dt><dd>${escapeHtml(job.experience)}</dd>` : ""}
      ${job.education ? `<dt>学历</dt><dd>${escapeHtml(job.education)}</dd>` : ""}
      ${job.posted_at ? `<dt>发布</dt><dd>${escapeHtml(job.posted_at)}</dd>` : ""}
    </dl>
    ${job.url && job.url.startsWith("http") ? `<p><a class="modal-link" href="${escapeHtml(job.url)}" target="_blank" rel="noopener">查看官网职位 ↗</a></p>` : ""}
  `;
}

async function openJobModal(job) {
  if (!job) return;
  renderJobModalBody(job);
  $("cardModal").hidden = false;

  if ((job.description || "").trim()) return;

  const slug = jobsMeta?.slug || "";
  try {
    const data = await postJson("/api/jobs/enrich", { job, slug });
    if (data.description) {
      job.description = data.description;
      const idx = currentJobs.findIndex(
        (j) => j.source === job.source && j.source_id === job.source_id,
      );
      if (idx >= 0) currentJobs[idx].description = data.description;
      renderJobModalBody(job);
      if (viewMode === "jobs") renderJobsView();
    } else {
      $("modalBody").querySelector(".modal-job-body").innerHTML =
        '<p class="muted">暂无岗位介绍正文。Boss 需在专用 Chrome 登录；官网岗位请重新拉取。</p>';
    }
  } catch (err) {
    const el = $("modalBody").querySelector(".modal-job-body");
    if (el) {
      el.innerHTML = `<p class="muted">拉取岗位介绍失败：${escapeHtml(err.error || err.message || "未知错误")}</p>`;
    }
  }
}

async function loadLatestJobsSnapshot() {
  jobsLoading = true;
  jobsLoadError = "";
  if (viewMode === "jobs") renderJobsView();
  try {
    const data = await getJson("/api/jobs");
    const snaps = data.snapshots || [];
    const roleLabel = $("role").value.trim();
    const companies = parseCompanies($("companies").value);
    const match = pickJobsSnapshot(snaps, selectedRoleId, roleLabel, companies);
    if (!match?.slug) {
      currentJobs = [];
      jobsMeta = null;
      if (viewMode === "jobs" && snaps.length) {
        jobsLoadError = `「${roleLabel || "当前岗位"}」暂无在招岗位缓存，请点击 ⚙ 拉取`;
      }
      return;
    }
    const bundle = await getJson(`/api/jobs/${encodeURIComponent(match.slug)}`);
    currentJobs = bundle.jobs || [];
    jobsMeta = { ...bundle.meta, slug: match.slug };
    renderCompanyChips();
  } catch (err) {
    currentJobs = [];
    jobsMeta = null;
    jobsLoadError = humanJobsError(err);
  } finally {
    jobsLoading = false;
    if (viewMode === "jobs") renderJobsView();
  }
}

async function loadXhsStatus() {
  const el = $("xhsStatus");
  if (!el) return;
  try {
    const s = await getJson("/api/xhs/status");
    const parts = [];
    parts.push(s.cookie_configured ? "Cookie 已配置" : "Cookie 未配置（.env XHS_WEB_SESSION）");
    parts.push(`本地 JSON ${s.export_files || 0} 个`);
    if (s.latest_export_at) parts.push(`最新 ${s.latest_export_at.replace("T", " ").replace("+00:00", " UTC")}`);
    if (!s.mediacrawler_installed) parts.push("MediaCrawler 未安装");
    el.textContent = parts.join(" · ");
    el.classList.toggle("warn", !s.cookie_configured);
  } catch {
    el.textContent = "无法读取小红书状态";
    el.classList.add("warn");
  }
}

async function runXhsScrapeSafe() {
  const btn = $("submitXhsScrape");
  if (!btn) return;
  btn.disabled = true;
  $("xhsStatus").textContent = "正在抓取…（MediaCrawler，可能数分钟，勿关页面）";
  try {
    const data = await postJson("/api/xhs/scrape-safe", {
      role_id: selectedRoleId,
      companies: parseCompanies($("companies").value),
      batch_size: 2,
      pause_seconds: 60,
    });
    const kw = (data.keywords || []).join("、");
    $("xhsStatus").textContent = `抓取完成 ${data.keywords?.length || 0} 个词：${kw}`;
    await loadXhsStatus();
  } catch (err) {
    $("xhsStatus").textContent = err.message || err.error || "小红书抓取失败";
    $("xhsStatus").classList.add("warn");
  } finally {
    btn.disabled = false;
  }
}

async function runFetchJobs() {
  $("submitJobs").disabled = true;
  $("jobsStatus").textContent = "拉取在招岗位…";
  jobsLoading = true;
  jobsLoadError = "";
  if (viewMode === "jobs") renderJobsView();
  try {
    const body = {
      role_id: selectedRoleId,
      role: $("role").value.trim(),
      companies: parseCompanies($("companies").value),
      max_per_query: 100,
      no_boss: !$("jobProBoss").checked,
      boss_cdp: $("jobProBoss").checked,
      job_pro_scope: $("jobProScope").value,
      job_pro_details: $("jobProDetails").checked,
      skip_interview_discover: true,
    };
    const data = await postJson("/api/jobs/fetch", body);
    currentJobs = data.jobs || [];
    jobsMeta = {
      slug: data.slug,
      fetched_at: data.paths?.fetched_at,
      new_count: data.new_count,
      job_count: data.job_count,
      sources: data.sources,
    };
    renderCompanyChips();
    $("jobsStatus").textContent = `完成 ${data.job_count} 个岗位（${data.new_count} 新开）`;
    if ((data.warnings || []).length) {
      $("jobsStatus").textContent += ` · ${data.warnings[0]}`;
    }
    setViewMode("jobs");
    closeDrawer();
  } catch (err) {
    $("jobsStatus").textContent = err.error || err.message || "拉取失败";
  } finally {
    jobsLoading = false;
    $("submitJobs").disabled = false;
    if (viewMode === "jobs") renderJobsView();
  }
}

function openQuestionModal(q) {
  $("modalBody").innerHTML = `
    <div class="modal-head">
      <span class="pill">#${q.rank}</span>
      <span class="pill">出现 ${q.batch_count ?? q.freq ?? 1} 次</span>
      <span class="pill topic">${escapeHtml(q.topic || "")}</span>
    </div>
    <h2>${escapeHtml(q.text)}</h2>
    ${(q.variants || []).length ? `<p class="cluster-variants"><strong>同类表述：</strong>${escapeHtml(q.variants.join("；"))}</p>` : ""}
    <dl class="modal-dl">
      <dt>公司</dt><dd>${escapeHtml((q.company_tags || []).join("、") || "未标注")}</dd>
      <dt>岗位</dt><dd>${escapeHtml((q.role_tags || []).join("、") || "未标注")}</dd>
      <dt>最近出现</dt><dd>${escapeHtml(q.latest_posted_at || "—")}</dd>
      ${q.score != null ? `<dt>综合分</dt><dd>${q.score}</dd>` : ""}
    </dl>
  `;
  $("cardModal").hidden = false;
}

function openClusterModal(c) {
  openQuestionModal({
    rank: c.rank,
    text: c.representative,
    batch_count: c.batch_count,
    topic: c.topic,
    variants: c.variants,
    company_tags: c.company_tags,
    role_tags: c.role_tags,
    latest_posted_at: c.latest_posted_at,
    score: c.score,
  });
}

function renderCurrentView() {
  if (viewMode === "bank") renderBankView();
  else if (viewMode === "jobs") renderJobsView();
  else renderFeed();
}

function renderFeed() {
  if (viewMode === "bank") {
    renderBankView();
    return;
  }
  const query = $("searchQ").value.trim();
  const list = filteredPosts();
  const total = currentPosts.length;
  const searching = query.length > 0 || activeCompany;

  $("clearSearch").hidden = !query;
  $("feedHint").hidden = searching || total > 0;
  $("feedEmpty").hidden = list.length > 0 || total === 0;
  $("feedGrid").hidden = list.length === 0;
  $("bankListView").hidden = true;
  $("jobsListView").hidden = true;

  if (currentBank || total > 0) {
    $("feedMeta").hidden = false;
    $("bankTitle").textContent = currentBank?.role || "面经库";
    const win = currentBank?.recency_window_days || RECENCY_WINDOW_DAYS;
    const cacheAt = currentBank?.cache_updated_at || currentBank?.generated_at || "";
    const cacheHint = cacheAt ? ` · 缓存 ${String(cacheAt).slice(0, 19).replace("T", " ")}` : "";
    $("bankSubtitle").textContent =
      `${list.length} / ${total} 篇面经${mergedBankCount > 1 ? ` · 合并 ${mergedBankCount} 个库` : ""} · 近 ${win} 天${cacheHint}`;
  }

  $("feedGrid").innerHTML = list.map((p, i) => renderPostCard(p, i, query)).join("");
  $("feedGrid").querySelectorAll(".post-card").forEach((el) => {
    const idx = Number(el.dataset.index);
    const open = () => openPostModal(list[idx]);
    el.addEventListener("click", open);
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        open();
      }
    });
  });
}

function openPostModal(post) {
  if (!post) return;
  const src = sourceLabel(post.url, post.source);
  const bodyHtml = postBodyHtml(post);
  const imagesHtml = renderPostImages(post, { modal: true });
  const imgUrls = postImageUrls(post);
  const textLen = postPlainText(post).length;
  const ocrPages = post.image_page_ocr || post.image_ocr_pages || [];
  const hasOcrText = ocrPages.some((p) => String(p || "").trim().length > 30);
  let imageNotice = "";
  if (
    imgUrls.length
    && textLen < 80
    && !hasOcrText
    && imgUrls.length > 1
  ) {
    imageNotice = `<p class="image-notice">共 ${imgUrls.length} 页图片，使用下方箭头翻页查看</p>`;
  }
  const linkUrl = post.source_url || post.url || "";
  const linkLabel = post.source_link_label || "查看原文";
  $("modalBody").innerHTML = `
    <div class="modal-cover" style="background:${companyGradient(post.company_label || "未标注")}"></div>
    <div class="modal-head">
      <span class="pill ${src.cls}">${src.name}</span>
      <span class="pill">${escapeHtml(post.company_label || "未标注")}</span>
      <span class="pill">${escapeHtml(post.role_label || "")}</span>
    </div>
    <h2>${escapeHtml(post.title || "面经")}</h2>
    ${imageNotice}
  ${imagesHtml}
    <div class="modal-content formatted-post">${bodyHtml || (imagesHtml ? "" : "<p class='muted'>暂无正文</p>")}</div>
    <div class="modal-foot">
      ${post.posted_at ? `<span>${escapeHtml(post.posted_at)}</span>` : ""}
      ${linkUrl ? `<a href="${escapeHtml(linkUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(linkLabel)}</a>` : ""}
    </div>
  `;
  initImageCarousel($("modalBody"));
  $("cardModal").hidden = false;
}

function closeModal() {
  $("cardModal").hidden = true;
}

function showBundle(data) {
  mergedBankCount = (data.merged_slugs || []).length;
  currentBank = data.bank || null;
  if (data.meta?.updated_at && currentBank) {
    currentBank.cache_updated_at = data.meta.updated_at;
  }
  currentPosts = data.posts || [];
  currentClusters = (data.bank && data.bank.clusters) || [];
  currentBankQuestions = normalizeBankQuestions(data.bank?.questions || []);
  currentCompanies = data.companies || [];
  currentSlug = data.slug || null;
  frequencyReportText = data.frequency_report || "";
  activeCompany = "";
  const warnings = [...(data.ingest_warnings || [])];
  const srcWarn = data.sources?.role_mismatch_warning;
  if (srcWarn && !warnings.includes(srcWarn)) warnings.push(srcWarn);
  if (warnings.length) {
    $("feedError").hidden = false;
    $("feedError").textContent = warnings.join(" · ");
  } else {
    $("feedError").hidden = true;
  }
  const emptyP = $("feedEmpty").querySelector("p");
  if (emptyP && (data.posts || []).length > 0) {
    emptyP.textContent = "没有匹配的面经";
  }
  syncRoleFromBank();
  if (viewMode === "jobs") {
    loadLatestJobsSnapshot();
  } else {
    renderCompanyChips();
    renderCurrentView();
  }
}

function showError(msg) {
  $("feedError").hidden = false;
  $("feedError").textContent = msg;
  closeModal();
}

function humanJobsError(err) {
  const code = err?.error || "";
  if (code === "method_not_allowed") {
    return "Web 服务版本过旧，请在项目目录执行 bash start-web.sh 重启后再试";
  }
  if (code === "snapshot_not_found") return "岗位缓存不存在，请点击拉取";
  return err?.message || code || "加载在招岗位失败";
}

function humanError(err) {
  const msg = err?.message || "";
  if (msg.length > 8) return msg;
  const code = err?.error || "";
  if (code === "bank_not_found") return "缓存面经库已损坏，请点击 ⚙ 重新「抓取并生成面经库」";
  if (code === "xhs_config") return msg || "未配置 XHS_WEB_SESSION，无法抓取小红书";
  if (code === "xhs_scrape_failed") return msg || "小红书抓取失败";
  if (code === "internal_error") return msg || "服务内部错误，请重启 Web 后重试";
  return code || msg || "加载失败";
}

async function getJson(path) {
  const res = await fetch(path);
  const data = await res.json();
  if (!res.ok) throw data;
  return data;
}

async function postJson(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw data;
  return data;
}

async function refreshBankList() {
  const data = await getJson("/api/banks");
  const list = data.banks || [];
  $("bankList").innerHTML = list.length
    ? list.map((b) => `<li><button type="button" class="bank-item${b.slug === currentSlug ? " active" : ""}" data-slug="${escapeHtml(b.slug)}">
        <strong>${escapeHtml(b.role)}</strong><span>${b.post_count} 篇 · ${b.question_count} 题</span></button></li>`).join("")
    : '<li class="muted">暂无</li>';
  $("bankList").querySelectorAll(".bank-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      loadBank(btn.dataset.slug);
      closeDrawer();
    });
  });
  return list;
}

async function loadBank(slug) {
  setLoading(true);
  $("feedError").hidden = true;
  try {
    const data = await getJson(`/api/banks/${encodeURIComponent(slug)}`);
    showBundle(data);
    await refreshBankList();
  } catch (err) {
    showError(humanError(err));
  } finally {
    setLoading(false);
  }
}

async function autoLoadBank() {
  closeModal();
  closeDrawer();
  setLoading(true);
  $("feedError").hidden = true;
  try {
    await refreshBankList();
    const preferredRole = techRoles.find((r) => r.id === selectedRoleId);
    if (preferredRole) {
      try {
        const data = await loadRoleBundle(
          preferredRole,
          parseCompanies($("companies").value),
        );
        showBundle(data);
      } catch (err) {
        if (err?.error === "no_banks_for_role") {
          showRolePending(preferredRole);
        } else {
          throw err;
        }
      }
    }
    await loadLatestJobsSnapshot();
  } catch (err) {
    showError(humanError(err));
  } finally {
    setLoading(false);
    renderCurrentView();
  }
}

async function runBuildBank() {
  setLoading(true, "抓取并整理面经…");
  try {
    const data = await postJson("/api/bank", payloadBase());
    showBundle({
      slug: data.slug,
      bank: data.bank,
      posts: data.posts || [],
      companies: data.companies || [],
      frequency_report: data.frequency_report,
    });
    await refreshBankList();
    $("status").textContent = `完成 ${(data.posts || []).length} 篇面经`;
    if ((data.ingest_warnings || []).length) {
      $("status").textContent += ` · 注意：${data.ingest_warnings[0]}`;
    }
    closeDrawer();
  } catch (err) {
    const detail = err.message || err.error || "失败";
    $("status").textContent = detail.includes("面经") ? detail : `刷新失败：${detail}`;
  } finally {
    setLoading(false);
  }
}

function openDrawer() { $("settingsDrawer").hidden = false; }
function closeDrawer() { $("settingsDrawer").hidden = true; }

function downloadBlob(filename, content, type) {
  const blob = new Blob([content], { type });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
}

$("submitBank").addEventListener("click", runBuildBank);
$("submitXhsScrape")?.addEventListener("click", runXhsScrapeSafe);
$("submitJobs").addEventListener("click", runFetchJobs);
$("fetchJobsInline").addEventListener("click", runFetchJobs);
$("viewPosts").addEventListener("click", () => setViewMode("posts"));
$("viewBank").addEventListener("click", () => setViewMode("bank"));
$("viewJobs").addEventListener("click", () => setViewMode("jobs"));
$("searchQ").addEventListener("input", renderCurrentView);
let roleInputTimer = null;
$("role").addEventListener("input", () => {
  clearTimeout(roleInputTimer);
  roleInputTimer = setTimeout(() => {
    if (viewMode === "jobs") loadLatestJobsSnapshot();
  }, 400);
});
$("companies").addEventListener("input", () => {
  clearTimeout(roleInputTimer);
  roleInputTimer = setTimeout(() => {
    if (viewMode === "jobs") loadLatestJobsSnapshot();
  }, 400);
});
$("clearSearch").addEventListener("click", () => {
  $("searchQ").value = "";
  renderCurrentView();
  $("searchQ").focus();
});
$("resetFilters").addEventListener("click", () => {
  $("searchQ").value = "";
  activeCompany = "";
  renderCompanyChips();
  syncCompaniesInput();
  renderCurrentView();
});
$("exportJson").addEventListener("click", () => {
  if (!currentPosts.length) return;
  downloadBlob(`${currentBank?.role || "面经"}.json`, JSON.stringify(currentPosts, null, 2), "application/json");
});
$("exportBank").addEventListener("click", () => {
  const rows = bankQuestionRows();
  if (!rows.length) return;
  downloadBlob(
    `${currentBank?.role || "题库"}_questions.json`,
    JSON.stringify(rows, null, 2),
    "application/json",
  );
});
$("exportMd").addEventListener("click", () => {
  if (frequencyReportText) downloadBlob("frequency.md", frequencyReportText, "text/markdown");
});
$("exportJobs").addEventListener("click", () => {
  if (!currentJobs.length) return;
  downloadBlob(
    `${$("role").value.trim() || "岗位"}_jobs.json`,
    JSON.stringify(currentJobs, null, 2),
    "application/json",
  );
});
$("toggleSettings").addEventListener("click", openDrawer);
$("closeSettings").addEventListener("click", closeDrawer);
$("drawerBackdrop").addEventListener("click", closeDrawer);
$("modalClose").addEventListener("click", closeModal);
$("modalBackdrop").addEventListener("click", closeModal);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { closeModal(); closeDrawer(); }
});

async function boot() {
  closeModal();
  closeDrawer();
  try {
    const data = await getJson("/api/roles");
    techRoles = data.roles || [];
    if (data.default_role_id) selectedRoleId = canonicalRoleId(data.default_role_id);
    renderRoleChips($("roleChipRow"), selectRole);
    renderRoleChips($("roleChipRowDrawer"), selectRole);
    const current = techRoles.find((r) => r.id === selectedRoleId);
    if (current) $("role").value = current.search_as;
  } catch {
    /* keep defaults */
  }
  try {
    const coData = await getJson("/api/companies");
    companyGroups = coData.groups || [];
    renderCompanyChips();
  } catch {
    /* keep empty groups */
  }
  try {
    const s = await getJson("/api/status");
    if (s.sample_posts) $("rawPosts").value = s.sample_posts;
    else if (s.local_report && !s.local_report.includes("examples/")) {
      $("rawPosts").value = s.local_report;
    }
    const hintParts = [];
    if (s.local_report) {
      const name = s.local_report.split("/").pop();
      hintParts.push(`本地语料 ${s.local_post_count || 0} 篇（${name}）`);
    }
    if (s.sample_posts) {
      hintParts.push(`Demo ${s.sample_post_count || 8} 篇（仅 AI 应用开发）`);
    }
    if (hintParts.length) {
      $("localHint").textContent =
        `${hintParts.join(" · ")}。未勾选联网抓取时，只会自动使用与所选岗位匹配的语料。`;
    }
  } catch {
    /* ignore */
  }
  await loadXhsStatus();
  await autoLoadBank();
}

boot();
