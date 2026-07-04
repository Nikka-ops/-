const $ = (id) => document.getElementById(id);

let currentBank = null;
let currentPosts = [];
let currentClusters = [];
let currentBankQuestions = [];
let currentCompanies = [];
let currentSlug = null;
let frequencyReportText = "";
let activeCompany = "";
let activeSource = "all";
let activeTopic = "all";
let activeConfidence = "all";
let bankUiStats = null;
let bankTopics = [];
let viewMode = "posts";
let techRoles = [];
let mergedBankCount = 0;
let focusRoleIds = ["data", "ai_app"];
const FOCUS_ROLE_FALLBACK = [
  { id: "data", label: "数据开发", search_as: "数据开发", category: "技术岗", keywords: [] },
  { id: "ai_app", label: "Agent 开发", search_as: "Agent 开发", category: "技术岗", keywords: [] },
];
let selectedRoleId = "data";
let currentJobs = [];
let jobsMeta = null;
let jobsLoading = false;
let jobsLoadError = "";
let activeJobType = "all"; // "all" | "full" | "intern"
let companyGroups = [];

const RECENCY_WINDOW_DAYS = 90;
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
  const company = post.company_label || post.company || "";
  const fallbackStyle = `background:${companyGradient(company)}`;
  return `<div class="${cls}"><figure class="post-image-fig"><img src="${escapeHtml(imageProxyUrl(urls[0]))}" alt="面经封面" loading="lazy" onerror="this.style.display='none';this.parentElement.style.cssText='${fallbackStyle};display:flex;align-items:center;justify-content:center';this.parentElement.innerHTML+='<span class=\\'card-co-badge\\'>${escapeHtml(company)}</span>'" /></figure>${urls.length > 1 ? `<span class="img-more">共 ${urls.length} 页</span>` : ""}</div>`;
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
  if (s.includes("xiaohongshu") || s.includes("xhs")) return { name: "小红书", cls: "src-xhs", id: "xiaohongshu" };
  if (s.includes("nowcoder")) return { name: "牛客", cls: "src-nc", id: "nowcoder" };
  if (source === "xiaohongshu") return { name: "小红书", cls: "src-xhs", id: "xiaohongshu" };
  if (source === "nowcoder") return { name: "牛客", cls: "src-nc", id: "nowcoder" };
  return { name: "其他", cls: "src-default", id: "other" };
}

function postSourceKind(post) {
  return sourceLabel(post.url, post.source).id;
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
  const heroDesc = $("feedHint").querySelector(".hero-desc");
  if (heroDesc) heroDesc.innerHTML = `「${role.label}」暂无面经库 — 点 <strong>构建面经库</strong> 联网抓取，或等待自动读取本地缓存`;
  const emptyP = $("feedEmpty").querySelector("p");
  if (emptyP) {
    emptyP.textContent = `「${role.label}」还没有已保存的面经库`;
  }
  renderCurrentView();
}

function applyFocusRoleFilter() {
  const allowed = new Set(focusRoleIds.map(canonicalRoleId));
  techRoles = (techRoles.length ? techRoles : FOCUS_ROLE_FALLBACK).filter((r) =>
    allowed.has(canonicalRoleId(r.id)),
  );
  if (!techRoles.length) techRoles = [...FOCUS_ROLE_FALLBACK];
  if (!allowed.has(selectedRoleId)) selectedRoleId = techRoles[0].id;
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
    // 有指定公司：优先选包含这些公司的快照
    const withCo = pool.filter((s) => {
      const snapCos = (s.companies || []).map(normRole);
      return companiesNorm.some((c) => snapCos.includes(c));
    });
    if (withCo.length) candidates = withCo;
  }
  // 无公司筛选时：直接取最新快照（不再强制要求无公司快照，避免选到旧/损坏快照）

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

const OTHER_BUCKET = "其他";

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

function otherCompanyCount(counts, presetSet) {
  let total = 0;
  for (const [name, n] of Object.entries(counts)) {
    const label = String(name || "").trim();
    if (label && label !== "未标注" && !presetSet.has(label)) total += n;
  }
  return total;
}

function matchesCompanyLabel(label) {
  if (!activeCompany) return true;
  const n = String(label || "").trim();
  if (activeCompany === OTHER_BUCKET) {
    return n && n !== "未标注" && !allPresetCompanies().has(n);
  }
  return n === activeCompany;
}

function matchesCompanyTags(tags) {
  if (!activeCompany) return true;
  const list = tags || [];
  if (activeCompany === OTHER_BUCKET) {
    return list.some((t) => {
      const n = String(t || "").trim();
      return n && n !== "未标注" && !allPresetCompanies().has(n);
    });
  }
  return list.includes(activeCompany);
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

  const others = otherCompanyCount(counts, presetSet);
  if (others > 0) {
    html += `<div class="company-group"><div class="company-group-head"><span class="company-group-label">其他</span></div><div class="chip-row">${companyChipHtml(OTHER_BUCKET, others, activeCompany === OTHER_BUCKET)}</div></div>`;
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
    if (!matchesCompanyLabel(p.company_label)) return false;
    if (activeSource !== "all" && postSourceKind(p) !== activeSource) return false;
    if (!search) return true;
    const hay = [p.title, p.preview, p.raw_text, p.company_label, p.role_label, p.source]
      .join(" ")
      .toLowerCase();
    return hay.includes(search);
  });
}

function postsBySource(list) {
  const xhs = [];
  const nc = [];
  const other = [];
  for (const p of list) {
    const kind = postSourceKind(p);
    if (kind === "xiaohongshu") xhs.push(p);
    else if (kind === "nowcoder") nc.push(p);
    else other.push(p);
  }
  return { xhs, nc, other };
}

function bindPostCards(container, list) {
  container.querySelectorAll(".post-card").forEach((el) => {
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

function renderPostGrid(container, list, query) {
  container.innerHTML = list.map((p, i) => renderPostCard(p, i, query)).join("");
  bindPostCards(container, list);
}

function renderPostCard(post, index, query) {
  const src = sourceLabel(post.url, post.source);
  const company = post.company_label || "未标注";
  const hasImg = postImageUrls(post).length > 0;
  const previewText = post.preview || (hasImg ? "图片面经 · 含 OCR" : "");
  const imgBadge = post.images_only ? '<span class="pill pill-img">图</span>' : "";
  const cover = hasImg
    ? `<div class="card-thumb-wrap">${renderPostImages(post)}</div>`
    : `<div class="card-cover-text" style="background:${companyGradient(company)}"><span class="card-co-badge">${escapeHtml(company)}</span></div>`;
  return `<article class="feed-card post-card${post.images_only ? " images-only" : ""}${hasImg ? " has-thumb" : ""}" role="listitem" data-index="${index}" tabindex="0">
    ${cover}
    <div class="card-body">
      <div class="card-head-row">
        <span class="card-src ${src.cls}">${src.name}</span>
        ${hasImg ? `<span class="card-co-inline">${escapeHtml(company)}</span>` : ""}
      </div>
      <h3 class="card-title">${imgBadge}${highlightText(post.title || "面经分享", query)}</h3>
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
  $("genPrepBtn").hidden = mode !== "bank";
  if ($("trendsBtn")) $("trendsBtn").hidden = mode !== "posts";
  if ($("mockBtn")) $("mockBtn").hidden = mode !== "bank";
  if ($("ragSearchBar")) $("ragSearchBar").hidden = mode !== "bank";
  if ($("ragResults") && mode !== "bank") $("ragResults").hidden = true;
  syncSourceFilterBar();
  syncBankFilterBar();
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
      source_labels: c.source_labels || [],
      related_posts: c.related_posts || [],
    })),
  );
}

function syncBankFilterBar() {
  const bar = $("bankFilterBar");
  if (!bar) return;
  const total = bankQuestionRows().length;
  const show = viewMode === "bank" && total > 0;
  bar.hidden = !show;

  const topicRoot = $("bankTopicFilter");
  if (topicRoot && show) {
    const topics = [{ name: "all", count: total, label: "全部" }, ...bankTopics.map((t) => ({ ...t, label: t.name }))];
    topicRoot.innerHTML = topics
      .map((t) => {
        const key = t.name === "all" ? "all" : t.name;
        const label = key === "all" ? `全部 ${t.count}` : `${t.name} ${t.count}`;
        const on = activeTopic === key;
        return `<button type="button" class="chip bank-topic-chip${on ? " active" : ""}" data-topic="${escapeHtml(key)}" role="tab" aria-selected="${on ? "true" : "false"}">${escapeHtml(label)}</button>`;
      })
      .join("");
  }

  bar.querySelectorAll(".bank-conf-chip").forEach((btn) => {
    const on = btn.dataset.confidence === activeConfidence;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
}

function filteredQuestions() {
  const search = $("searchQ").value.trim().toLowerCase();
  return bankQuestionRows().filter((q) => {
    if (!matchesCompanyTags(q.company_tags)) return false;
    if (activeTopic !== "all" && (q.topic || "综合") !== activeTopic) return false;
    if (activeConfidence !== "all" && (q.confidence || "低频") !== activeConfidence) return false;
    if (!search) return true;
    const hay = [
      q.text,
      ...(q.variants || []),
      q.topic,
      ...(q.company_tags || []),
      ...(q.source_labels || []),
    ]
      .join(" ")
      .toLowerCase();
    return hay.includes(search);
  });
}

function renderQuestionItem(q, query, displayRank) {
  const srcPills = (q.source_labels || []).slice(0, 2).map((s) => {
    const cls = s === "小红书" ? "src-xhs" : s === "牛客" ? "src-nc" : "";
    return `<span class="pill ${cls}">${escapeHtml(s)}</span>`;
  }).join("");
  const ansBadge = q.answer ? '<span class="pill answer-pill">有解答</span>' : "";
  const rankNum = displayRank ?? q.rank ?? "";
  const qid = q.cluster_id || String(q.rank);
  const mastery = getMastery(qid);
  const masteryDot = `<span class="mastery-dot mastery-${mastery}" title="${mastery === 'known' ? '已掌握' : mastery === 'fuzzy' ? '模糊' : '待学'}" data-qid="${escapeHtml(qid)}"></span>`;
  return `<li class="cluster-item question-item" data-id="${escapeHtml(qid)}">
    <div class="cluster-rank">#${rankNum}</div>
    <div class="cluster-body">
      <div class="cluster-title">${highlightText(q.text, query)}</div>
      <div class="cluster-meta">
        <span class="pill conf-${escapeHtml(q.confidence || "低频")}">${escapeHtml(q.confidence || "低频")}</span>
        <span class="pill">出现 ${q.batch_count ?? q.freq ?? 1} 次</span>
        <span class="pill topic">${escapeHtml(q.topic || "综合")}</span>
        ${ansBadge}
        ${srcPills}
        ${(q.company_tags || []).slice(0, 2).map((co) => `<span class="pill">${escapeHtml(co)}</span>`).join("")}
      </div>
      ${(q.variants || []).length ? `<p class="cluster-variants">同类：${escapeHtml(q.variants.slice(0, 2).join("；"))}</p>` : ""}
    </div>
    ${masteryDot}
  </li>`;
}

function bindQuestionItems(container, list) {
  container.querySelectorAll(".question-item").forEach((el) => {
    el.addEventListener("click", () => {
      const q = list.find((x) => (x.cluster_id || String(x.rank)) === el.dataset.id);
      if (q) openQuestionModal(q);
    });
  });
}

function filteredClusters() {
  const search = $("searchQ").value.trim().toLowerCase();
  return currentClusters.filter((c) => {
    if (!matchesCompanyTags(c.company_tags)) return false;
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
  syncSourceFilterBar();
  syncBankFilterBar();
  $("feedGrid").hidden = true;
  $("feedSections").hidden = true;

  const useSections = activeTopic === "all" && activeConfidence === "all" && list.length > 0;
  $("bankListView").hidden = useSections || list.length === 0;
  $("bankSections").hidden = !useSections;
  $("jobsListView").hidden = true;
  $("techStackPanel").hidden = true;
  $("jobTypeBar").hidden = true;
  $("feedEmpty").hidden = list.length > 0 || total === 0;
  $("feedHint").hidden = query.length > 0 || activeCompany || activeTopic !== "all" || activeConfidence !== "all" || total > 0;

  if (currentBank) {
    $("feedMeta").hidden = false;
    $("bankTitle").textContent = `${currentBank.role || "题库"} · 高频面试题`;
    const win = currentBank.recency_window_days || RECENCY_WINDOW_DAYS;
    const stats = bankUiStats || {};
    const srcHint = stats.xhs_refs != null ? ` · 来源引用 小红书 ${stats.xhs_refs || 0} · 牛客 ${stats.nc_refs || 0}` : "";
    $("bankSubtitle").textContent =
      `${list.length} / ${total} 道题 · 高频 ${stats.high || 0} · 中频 ${stats.medium || 0} · 近 ${win} 天面经${srcHint} · Top 题含 Agent 参考解答`;
  }

  if (useSections) {
    const byTopic = new Map();
    for (const q of list) {
      const topic = q.topic || "综合";
      if (!byTopic.has(topic)) byTopic.set(topic, []);
      byTopic.get(topic).push(q);
    }
    const order = bankTopics.map((t) => t.name).filter((n) => byTopic.has(n));
    if (byTopic.has("综合") && !order.includes("综合")) order.push("综合");
    for (const name of byTopic.keys()) {
      if (!order.includes(name)) order.push(name);
    }
    $("bankSections").innerHTML = order
      .filter((name) => (byTopic.get(name) || []).length)
      .map((name) => {
        const rows = byTopic.get(name) || [];
        const gridId = `bank-section-${name.replace(/[^\w\u4e00-\u9fff]+/g, "_")}`;
        return `<section class="bank-topic-section" aria-label="${escapeHtml(name)}">
          <div class="feed-section-head">
            <h2 class="feed-section-title"><span class="section-topic">${escapeHtml(name)}</span><span class="section-count">${rows.length} 题</span></h2>
          </div>
          <ol id="${gridId}" class="bank-rank-list bank-section-list"></ol>
        </section>`;
      })
      .join("");
    order.filter((name) => (byTopic.get(name) || []).length).forEach((name) => {
      const rows = byTopic.get(name) || [];
      const gridId = `bank-section-${name.replace(/[^\w\u4e00-\u9fff]+/g, "_")}`;
      const el = $(gridId);
      if (el) {
        el.innerHTML = rows.map((q, i) => renderQuestionItem(q, query, i + 1)).join("");
        bindQuestionItems(el, rows);
      }
    });
    return;
  }

  $("bankListView").innerHTML = list.map((q, i) => renderQuestionItem(q, query, i + 1)).join("");
  bindQuestionItems($("bankListView"), list);
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

function isInternJob(job) {
  const title = (job.title || "").toLowerCase();
  const tags  = (job.tags || []).map(t => String(t).toLowerCase());
  return title.includes("实习") || title.includes("intern")
    || tags.some(t => t === "intern" || t === "实习" || t.includes("intern"));
}

function filteredJobs() {
  const search = $("searchQ").value.trim().toLowerCase();
  const list = currentJobs.filter((j) => {
    if (!matchesCompanyLabel(j.company)) return false;
    if (activeJobType === "intern" && !isInternJob(j)) return false;
    if (activeJobType === "full"   &&  isInternJob(j)) return false;
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
  syncSourceFilterBar();

  $("clearSearch").hidden = !query;
  $("feedGrid").hidden = true;
  $("feedSections").hidden = true;
  $("bankListView").hidden = true;
  $("bankSections").hidden = true;
  // tech stack panel: show when jobs are loaded, load data lazily
  if (total > 0 && !techStackData && !techStackLoading) loadTechStack();
  $("techStackPanel").hidden = total === 0 || techStackLoading;

  // job type bar
  const internCount = currentJobs.filter(isInternJob).length;
  const fullCount   = total - internCount;
  $("jobTypeBar").hidden = total === 0;
  $("jobCountAll").textContent    = total;
  $("jobCountFull").textContent   = fullCount;
  $("jobCountIntern").textContent = internCount;
  $("jobTypeBar").querySelectorAll(".job-type-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.type === activeJobType);
  });

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
    : `${list.length} / ${total} 个岗位 · ${newCount} 个新开 · 近2月官网JD · 按发布日期排序 · ${fetchedAt ? `更新于 ${fetchedAt.slice(0, 19).replace("T", " ")}` : "点击 拉取在招岗位"}`;

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
      const intern = isInternJob(j);
      const descPreview = (j.description || "").replace(/\s+/g, " ").slice(0, 120);
      return `<li class="cluster-item job-item" data-index="${i}">
        <div class="cluster-rank">${j.is_new ? '<span class="job-new">新</span>' : intern ? '实习' : "JD"}</div>
        <div class="cluster-body">
          <div class="cluster-title">${highlightText(j.title, query)}</div>
          <div class="cluster-meta">
            <span class="pill company-pill">${escapeHtml(j.company || "")}</span>
            ${intern ? `<span class="pill intern-pill">实习</span>` : ""}
            ${j.city ? `<span class="pill">${escapeHtml(j.city)}</span>` : ""}
            ${j.posted_at ? `<span class="pill">${escapeHtml(j.posted_at)}</span>` : ""}
            ${j.salary ? `<span class="pill salary-pill">${escapeHtml(j.salary)}</span>` : ""}
            <span class="pill src-pill ${src.cls}">${escapeHtml(src.name)}</span>
            ${jobInterviewBadge(j)}
            ${jobDescBadge(j)}
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
    ${desc ? `<div style="margin-top:12px"><button class="ghost" onclick="runJdAnalysis(${JSON.stringify(desc)})">分析 JD 覆盖缺口</button></div>` : ""}
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
        jobsLoadError = `「${roleLabel || "当前岗位"}」暂无在招岗位缓存，请点击 拉取`;
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
    parts.push(s.cookie_configured ? `Cookie 已配置（${s.cookie_source || "env"}）` : "Cookie 未配置（CDP Chrome 或 XHS_COOKIES）");
    parts.push(`本地 JSON ${s.export_files || 0} 个`);
    if (s.latest_export_at) parts.push(`最新 ${s.latest_export_at.replace("T", " ").replace("+00:00", " UTC")}`);
    if (!s.spider_xhs_installed) parts.push("Spider_XHS 未安装");
    if (s.spider_xhs_installed && !s.node_modules_ready) parts.push("需 npm install");
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
  $("xhsStatus").textContent = "正在抓取…";
  try {
    const data = await postJson("/api/xhs/scrape-safe", {
      role_id: selectedRoleId,
      companies: parseCompanies($("companies").value),
      core_only: $("xhsCoreOnly")?.checked ?? true,
      batch_size: 2,
      pause_seconds: 25,
    });
    const kw = (data.keywords || []).slice(0, 6).join("、");
    $("xhsStatus").textContent = `JSON 已更新 ${data.keywords?.length || 0} 词：${kw}${(data.keywords?.length || 0) > 6 ? "…" : ""}`;
    await loadXhsStatus();
  } catch (err) {
    $("xhsStatus").textContent = err.message || err.error || "抓取失败";
    $("xhsStatus").classList.add("warn");
  } finally {
    btn.disabled = false;
  }
}

function formatClassifySummary(classify) {
  if (!classify || typeof classify !== "object") return "";
  const parts = [];
  if (classify.xiaohongshu_export?.post_count != null) {
    parts.push(`导入 ${classify.xiaohongshu_export.post_count}`);
  }
  if (classify.kept != null) parts.push(`入库 ${classify.kept}`);
  for (const [k, v] of Object.entries(classify)) {
    if (k.endsWith("_dropped") && v) parts.push(`${k.replace("_dropped", "")}-${v}`);
  }
  if (classify.xhs_role_matched != null) parts.push(`岗位匹配 ${classify.xhs_role_matched}`);
  return parts.join(" · ");
}

async function runXhsIncremental() {
  const btn = $("submitXhsIncremental");
  if (!btn) return;
  btn.disabled = true;
  setLoading(true, "抓取 + 分类入库…");
  try {
    const body = {
      ...payloadBase(),
      core_only: $("xhsCoreOnly")?.checked ?? true,
      xhs_live: false,
      refresh: true,
      discover_nowcoder: false,
    };
    const data = await postJson("/api/xhs/incremental", body);
    if (data.slug) {
      showBundle({
        slug: data.slug,
        bank: data.bank || {},
        posts: data.posts || [],
        companies: data.companies || [],
      });
      await refreshBankList();
    }
    const summary = formatClassifySummary(data.classify);
    $("xhsStatus").textContent = [
      data.post_count != null ? `${data.post_count} 篇面经` : "",
      data.question_count != null ? `${data.question_count} 题` : "",
      summary,
    ]
      .filter(Boolean)
      .join(" · ");
    $("status").textContent = $("xhsStatus").textContent;
    if ((data.ingest_warnings || []).length) {
      $("status").textContent += ` · ${data.ingest_warnings[0]}`;
    }
    if (data.xhs?.error) {
      $("xhsStatus").textContent += ` · 抓取: ${data.xhs.error.slice(0, 80)}`;
      $("xhsStatus").classList.add("warn");
    }
    closeDrawer();
  } catch (err) {
    $("xhsStatus").textContent = err.message || err.error || "失败";
    $("xhsStatus").classList.add("warn");
  } finally {
    btn.disabled = false;
    setLoading(false);
    await loadXhsStatus();
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
      role_ids: focusRoleIds,
      role_id: selectedRoleId,
      role: $("role").value.trim(),
      companies: parseCompanies($("companies").value),
      max_per_query: 100,
      no_boss: !$("jobProBoss").checked,
      boss_cdp: $("jobProBoss").checked,
      job_pro_scope: $("jobProScope").value,
      job_pro_details: $("jobProDetails").checked,
      job_recency_days: RECENCY_WINDOW_DAYS,
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
  const related = (q.related_posts || []).length
    ? q.related_posts
    : (q.source_refs || [])
        .map((url) => currentPosts.find((p) => p.url === url || p.source_url === url))
        .filter(Boolean)
        .slice(0, 6)
        .map((p) => ({
          url: p.source_url || p.url,
          title: p.title || "面经原文",
          source: p.source,
          company_label: p.company_label || p.company || "",
          posted_at: p.posted_at || "",
        }));
  const relatedHtml = related.length
    ? `<div class="question-related"><h3>来源面经</h3><ul>${related
        .map((p) => {
          const src = sourceLabel(p.url || p.source, p.source);
          return `<li><span class="pill ${src.cls}">${src.name}</span> <strong>${escapeHtml(p.company_label || "")}</strong> ${escapeHtml(p.title || "")}${p.url ? ` <a href="${escapeHtml(p.url)}" target="_blank" rel="noopener">原文</a>` : ""}</li>`;
        })
        .join("")}</ul></div>`
    : "";
  const srcLine = (q.source_labels || []).length
    ? `<dt>来源</dt><dd>${escapeHtml(q.source_labels.join("、"))}</dd>`
    : "";
  $("modalBody").innerHTML = `
    <div class="modal-head">
      <span class="pill">#${q.rank}</span>
      <span class="pill conf-${escapeHtml(q.confidence || "低频")}">${escapeHtml(q.confidence || "低频")}</span>
      <span class="pill">出现 ${q.batch_count ?? q.freq ?? 1} 次</span>
      <span class="pill topic">${escapeHtml(q.topic || "综合")}</span>
    </div>
    <h2>${escapeHtml(q.text)}</h2>
    ${q.answer ? `<div class="question-answer"><h3>参考解答</h3><div class="answer-body">${escapeHtml(q.answer).replace(/\n/g, "<br>")}</div></div>` : ""}
    ${(q.variants || []).length ? `<p class="cluster-variants"><strong>同类表述：</strong>${escapeHtml(q.variants.join("；"))}</p>` : ""}
    <dl class="modal-dl">
      <dt>公司</dt><dd>${escapeHtml((q.company_tags || []).join("、") || "未标注")}</dd>
      <dt>岗位</dt><dd>${escapeHtml((q.role_tags || []).join("、") || "未标注")}</dd>
      ${srcLine}
      <dt>最近出现</dt><dd>${escapeHtml(q.latest_posted_at || "—")}</dd>
      ${q.score != null ? `<dt>综合分</dt><dd>${q.score}</dd>` : ""}
    </dl>
    ${relatedHtml}
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

function syncSourceFilterBar() {
  const bar = $("sourceFilterBar");
  if (!bar) return;
  const show = viewMode === "posts" && currentPosts.length > 0;
  bar.hidden = !show;
  bar.querySelectorAll(".source-chip").forEach((btn) => {
    const on = btn.dataset.source === activeSource;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
}

function sourceCounts(list) {
  const { xhs, nc, other } = postsBySource(list);
  return { xhs: xhs.length, nc: nc.length, other: other.length, all: list.length };
}

function renderFeed() {
  if (viewMode === "bank") {
    renderBankView();
    return;
  }
  const query = $("searchQ").value.trim();
  const list = filteredPosts();
  const total = currentPosts.length;
  const searching = query.length > 0 || activeCompany || activeSource !== "all";
  const counts = sourceCounts(
    currentPosts.filter((p) => matchesCompanyLabel(p.company_label) && (
      !query
      || [p.title, p.preview, p.raw_text, p.company_label, p.role_label, p.source].join(" ").toLowerCase().includes(query.toLowerCase())
    )),
  );

  $("clearSearch").hidden = !query;
  $("feedHint").hidden = searching || total > 0;
  $("feedEmpty").hidden = list.length > 0 || total === 0;
  syncSourceFilterBar();

  const useSections = activeSource === "all" && list.length > 0;
  $("feedGrid").hidden = useSections || list.length === 0;
  $("feedSections").hidden = !useSections;

  $("bankListView").hidden = true;
  $("bankSections").hidden = true;
  $("techStackPanel").hidden = true;
  $("jobTypeBar").hidden = true;
  $("jobsListView").hidden = true;

  if (currentBank || total > 0) {
    $("feedMeta").hidden = false;
    $("bankTitle").textContent = currentBank?.role || "面经库";
    const win = currentBank?.recency_window_days || RECENCY_WINDOW_DAYS;
    const cacheAt = currentBank?.cache_updated_at || currentBank?.generated_at || "";
    const cacheHint = cacheAt ? ` · 缓存 ${String(cacheAt).slice(0, 19).replace("T", " ")}` : "";
    const srcHint = ` · 小红书 ${counts.xhs} · 牛客 ${counts.nc}`;
    $("bankSubtitle").textContent =
      `${list.length} / ${total} 篇面经${mergedBankCount > 1 ? ` · 合并 ${mergedBankCount} 个库` : ""}${srcHint} · 近 ${win} 天${cacheHint}`;
  }

  $("sourceFilter")?.querySelectorAll(".source-chip").forEach((btn) => {
    const src = btn.dataset.source;
    let label = btn.textContent.split(" ")[0];
    if (src === "all") label = `全部 ${counts.all}`;
    else if (src === "xiaohongshu") label = `小红书 ${counts.xhs}`;
    else if (src === "nowcoder") label = `牛客 ${counts.nc}`;
    btn.textContent = label;
  });

  if (useSections) {
    const { xhs, nc, other } = postsBySource(list);
    const sections = [
      { key: "xiaohongshu", title: "小红书", cls: "src-xhs", posts: xhs },
      { key: "nowcoder", title: "牛客", cls: "src-nc", posts: nc },
    ];
    if (other.length) {
      sections.push({ key: "other", title: "其他", cls: "src-default", posts: other });
    }
    $("feedSections").innerHTML = sections
      .filter((s) => s.posts.length)
      .map((s) => {
        const gridId = `feed-grid-${s.key}`;
        return `<section class="feed-source-section" aria-label="${escapeHtml(s.title)}面经">
          <div class="feed-section-head">
            <h2 class="feed-section-title"><span class="section-src ${s.cls}">${escapeHtml(s.title)}</span><span class="section-count">${s.posts.length} 篇</span></h2>
          </div>
          <div id="${gridId}" class="feed-grid feed-grid-section" role="list"></div>
        </section>`;
      })
      .join("");
    sections.filter((s) => s.posts.length).forEach((s) => {
      const grid = $(`feed-grid-${s.key}`);
      if (grid) renderPostGrid(grid, s.posts, query);
    });
    return;
  }

  renderPostGrid($("feedGrid"), list, query);
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
  const bankUi = data.question_bank_ui || {};
  currentBankQuestions = normalizeBankQuestions(
    bankUi.questions?.length ? bankUi.questions : data.bank?.questions || [],
  );
  bankTopics = bankUi.topics || [];
  bankUiStats = bankUi.stats || null;
  currentCompanies = data.companies || [];
  currentSlug = data.slug || null;
  frequencyReportText = data.frequency_report || "";
  activeCompany = "";
  activeSource = "all";
  activeTopic = "all";
  activeConfidence = "all";
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
    const cls = formatClassifySummary(data.sources);
    if (cls) $("status").textContent += ` · ${cls}`;
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
$("submitXhsIncremental")?.addEventListener("click", runXhsIncremental);
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
  activeSource = "all";
  activeTopic = "all";
  activeConfidence = "all";
  renderCompanyChips();
  syncCompaniesInput();
  renderCurrentView();
});
$("sourceFilter")?.addEventListener("click", (e) => {
  const btn = e.target.closest(".source-chip");
  if (!btn) return;
  activeSource = btn.dataset.source || "all";
  syncSourceFilterBar();
  renderCurrentView();
});
$("bankFilterBar")?.addEventListener("click", (e) => {
  const topicBtn = e.target.closest(".bank-topic-chip");
  if (topicBtn) {
    activeTopic = topicBtn.dataset.topic || "all";
    syncBankFilterBar();
    renderCurrentView();
    return;
  }
  const confBtn = e.target.closest(".bank-conf-chip");
  if (confBtn) {
    activeConfidence = confBtn.dataset.confidence || "all";
    syncBankFilterBar();
    renderCurrentView();
  }
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
if ($("heroOpenSettings")) $("heroOpenSettings").addEventListener("click", openDrawer);
if ($("heroFetchJobs"))    $("heroFetchJobs").addEventListener("click", runFetchJobs);

// ── 生成备考包 ─────────────────────────────────────────────────────────────
async function runGenPrep() {
  const btn = $("genPrepBtn");
  const role = $("role")?.value?.trim() || currentBank?.role || "数据开发";
  const companies = (currentBank?.companies || []);
  const resumeText = ($("resumeText")?.value || "").trim() || localStorage.getItem("ir_resume_text") || "";

  btn.disabled = true;
  btn.textContent = "⏳ 生成中…";

  try {
    const res = await fetch("/api/prep", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, companies, resume_text: resumeText }),
    });
    const pkg = await res.json();
    if (!res.ok) throw new Error(pkg.error || "生成失败");
    showPrepModal(pkg);
  } catch (e) {
    alert("备考包生成失败：" + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "生成备考包";
  }
}

function showPrepModal(pkg) {
  const hasChains = (pkg.followup_chains || []).length > 0;
  const hasMd = pkg.prep_md?.trim();

  let html = `<h2 style="margin:0 0 16px">${pkg.role} · 备考包</h2>`;

  if (pkg.mode === "heuristic") {
    html += `<p class="hint warn-hint">未配置 DeepSeek API Key，仅展示题目列表（启发式模式）。</p>`;
  }

  if (hasMd) {
    // 简单 Markdown 渲染（加粗/标题/列表）
    const mdHtml = pkg.prep_md
      .replace(/^### (.+)$/gm, "<h4>$1</h4>")
      .replace(/^## (.+)$/gm, "<h3>$1</h3>")
      .replace(/^# (.+)$/gm, "<h2>$1</h2>")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/^- (.+)$/gm, "<li>$1</li>")
      .replace(/(<li>.*<\/li>\n?)+/g, "<ul>$&</ul>")
      .replace(/\n\n/g, "</p><p>")
      .replace(/^(?!<[hup])/gm, "");
    html += `<div class="prep-md">${mdHtml}</div>`;
  }

  if (hasChains) {
    html += `<h3 style="margin:20px 0 10px">项目追问链</h3>`;
    for (const c of pkg.followup_chains) {
      html += `<div class="followup-card">
        <div class="followup-anchor">${c.resume_anchor}</div>
        <div class="followup-trigger">问：${c.seed_question}</div>
        <ul>${c.followups.map(f => `<li>${f}</li>`).join("")}</ul>
        ${c.is_grounded ? '<span class="pill grounded-pill">有据可查</span>' : ""}
      </div>`;
    }
  }

  // 下载按钮
  html += `<div style="margin-top:20px;display:flex;gap:8px">
    <button class="ghost" onclick="downloadBlob('备考包.md', ${JSON.stringify(pkg.prep_md || "")}, 'text/markdown')">下载 Markdown</button>
    <button class="ghost" onclick="downloadBlob('备考包.json', JSON.stringify(${JSON.stringify(pkg)}, null, 2), 'application/json')">下载 JSON</button>
  </div>`;

  $("modalBody").innerHTML = html;
  $("cardModal").hidden = false;
}

$("genPrepBtn").addEventListener("click", runGenPrep);
if ($("trendsBtn")) $("trendsBtn").addEventListener("click", runTrends);
if ($("mockBtn")) $("mockBtn").addEventListener("click", runMockInterview);

// ── 错题本 / 掌握度 ─────────────────────────────────────────────────────────
const MASTERY_LEVELS = ["unknown", "fuzzy", "known"];

function getMastery(qid) {
  return localStorage.getItem(`ir_m_${qid}`) || "unknown";
}
function setMastery(qid, level) {
  localStorage.setItem(`ir_m_${qid}`, level);
}
function cycleMastery(qid) {
  const cur = getMastery(qid);
  const next = MASTERY_LEVELS[(MASTERY_LEVELS.indexOf(cur) + 1) % MASTERY_LEVELS.length];
  setMastery(qid, next);
  return next;
}

// Delegate mastery-dot clicks (works on dynamically rendered lists)
document.addEventListener("click", (e) => {
  const dot = e.target.closest(".mastery-dot");
  if (!dot) return;
  e.stopPropagation();
  const qid = dot.dataset.qid;
  const next = cycleMastery(qid);
  dot.className = `mastery-dot mastery-${next}`;
  dot.title = next === "known" ? "已掌握" : next === "fuzzy" ? "模糊" : "待学";
});

// ── 考点趋势 ────────────────────────────────────────────────────────────────
async function runTrends() {
  const slug = currentSlug;
  if (!slug) { alert("请先加载题库"); return; }
  const btn = document.getElementById("trendsBtn");
  if (btn) { btn.disabled = true; btn.textContent = "分析中…"; }
  try {
    const data = await postJson("/api/trends", { slug });
    showTrendsModal(data);
  } catch (e) {
    alert("趋势分析失败：" + e.message);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "考点趋势"; }
  }
}

function showTrendsModal(d) {
  const tags = (arr, color) => arr.slice(0, 6).map(t =>
    `<span class="pill" style="background:${color};color:#fff;margin:2px">${escapeHtml(t)}</span>`
  ).join("");

  let html = `<h2 style="margin:0 0 4px">考点趋势播报</h2>
    <p style="font-size:12px;color:var(--muted);margin:0 0 16px">${escapeHtml(d.recent_window)} vs ${escapeHtml(d.baseline_window)}</p>`;

  if (d.broadcast) {
    html += `<p style="line-height:1.8;margin-bottom:16px">${escapeHtml(d.broadcast)}</p><hr style="border:none;border-top:1px solid var(--border);margin:16px 0">`;
  }

  if (d.new?.length)     html += `<p><strong>新兴考点</strong><br>${tags(d.new, "#10b981")}</p>`;
  if (d.rising?.length)  html += `<p><strong>升温考点</strong><br>${tags(d.rising, "#f59e0b")}</p>`;
  if (d.falling?.length) html += `<p><strong>降温考点</strong><br>${tags(d.falling, "#94a3b8")}</p>`;

  if (d.topics?.length) {
    html += `<table style="width:100%;border-collapse:collapse;font-size:12px;margin-top:12px">
      <thead><tr style="border-bottom:1px solid var(--border)">
        <th style="text-align:left;padding:5px 8px">考点</th>
        <th style="text-align:center;padding:5px 8px">近期</th>
        <th style="text-align:center;padding:5px 8px">前期</th>
        <th style="text-align:center;padding:5px 8px">变化</th>
      </tr></thead><tbody>`;
    for (const row of d.topics.slice(0, 15)) {
      const pct = row.delta_pct;
      const color = pct > 50 ? "#10b981" : pct < -30 ? "#94a3b8" : "var(--text-2)";
      const arrow = pct > 50 ? "↑" : pct < -30 ? "↓" : "→";
      html += `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:5px 8px">${escapeHtml(row.topic)}</td>
        <td style="text-align:center;padding:5px 8px">${row.recent}</td>
        <td style="text-align:center;padding:5px 8px">${row.baseline}</td>
        <td style="text-align:center;padding:5px 8px;color:${color};font-weight:600">${arrow} ${pct === 999 ? "新" : pct + "%"}</td>
      </tr>`;
    }
    html += `</tbody></table>`;
  }

  $("modalBody").innerHTML = html;
  $("cardModal").hidden = false;
}

// ── 模拟面试 ────────────────────────────────────────────────────────────────
let _mockSession = null;

async function runMockInterview() {
  const role = currentBank?.role || "数据开发";
  const slug = currentSlug || "";
  try {
    const data = await postJson("/api/mock/start", { role, slug });
    if (data.error) throw new Error(data.error);
    _mockSession = { id: data.session_id, total: data.total };
    showMockModal(data.question, data.progress, "");
  } catch (e) {
    alert("模拟面试启动失败：" + e.message);
  }
}

function showMockModal(question, progress, lastComment) {
  $("modalBody").innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <h2 style="margin:0;font-size:16px">模拟面试</h2>
      <span style="font-size:12px;color:var(--muted)">${escapeHtml(progress || "")}</span>
    </div>
    ${lastComment ? `<div class="mock-comment">${escapeHtml(lastComment)}</div>` : ""}
    <div class="mock-question">${escapeHtml(question)}</div>
    <textarea id="mockAnswer" rows="5" placeholder="输入你的回答…" style="width:100%;box-sizing:border-box;margin-top:12px;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius);font-family:var(--font);font-size:13px;resize:vertical;background:var(--surface);color:var(--text)"></textarea>
    <div style="display:flex;gap:8px;margin-top:10px">
      <button class="primary" onclick="submitMockAnswer()" style="flex:1">提交回答</button>
      <button class="ghost" onclick="$('cardModal').hidden=true">结束面试</button>
    </div>`;
  $("cardModal").hidden = false;
  document.getElementById("mockAnswer")?.focus();
}

async function submitMockAnswer() {
  const ans = (document.getElementById("mockAnswer")?.value || "").trim();
  if (!ans) return;
  const btn = document.querySelector("#modalBody button.primary");
  if (btn) { btn.disabled = true; btn.textContent = "等待面试官…"; }

  try {
    const data = await postJson("/api/mock/reply", {
      session_id: _mockSession?.id,
      answer: ans,
    });
    if (data.error) throw new Error(data.error);
    if (data.finished) {
      $("modalBody").innerHTML = `
        <h2 style="margin:0 0 12px">面试结束</h2>
        <div class="mock-comment">${escapeHtml(data.comment)}</div>
        <p style="margin-top:16px;color:var(--muted);font-size:13px">感谢参与！可重新点击「模拟面试」再次练习。</p>
        <button class="primary" onclick="$('cardModal').hidden=true" style="margin-top:12px">关闭</button>`;
    } else {
      showMockModal(data.next_question, data.progress, data.comment);
    }
  } catch (e) {
    if (btn) { btn.disabled = false; btn.textContent = "提交回答"; }
    alert("提交失败：" + e.message);
  }
}

// ── RAG 语义搜索 ────────────────────────────────────────────────────────────
let _ragBuilding = false;

async function runRagSearch(query) {
  if (!currentSlug || !query.trim()) return;
  try {
    const res = await fetch("/api/rag/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug: currentSlug, query, top_k: 12 }),
    });
    const data = await res.json();
    if (data.error === "index_not_built") {
      if (_ragBuilding) return;
      _ragBuilding = true;
      const hint = document.getElementById("ragSearchHint");
      if (hint) hint.textContent = "⏳ 首次使用需构建索引（约1分钟）…";
      await fetch("/api/rag/build", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slug: currentSlug }),
      });
      _ragBuilding = false;
      return runRagSearch(query);
    }
    showRagResults(data.results || [], query);
  } catch (e) {
    console.error("RAG search error", e);
  }
}

function showRagResults(results, query) {
  const container = document.getElementById("ragResults");
  if (!container) return;
  if (!results.length) {
    container.innerHTML = '<p class="muted">无相关题目</p>';
    container.hidden = false;
    return;
  }
  container.innerHTML = `<h4 style="margin:0 0 8px">语义相关题目（"${escapeHtml(query)}"）</h4>` +
    results.map(r => `<div class="cluster-item" style="margin-bottom:8px;padding:10px 12px">
      <div class="cluster-title">${escapeHtml(r.text)}</div>
      <div class="cluster-meta">
        ${r.topic ? `<span class="pill">${escapeHtml(r.topic)}</span>` : ""}
        <span class="pill" style="opacity:.6">相似度 ${(r.score * 100).toFixed(0)}%</span>
      </div>
    </div>`).join("");
  container.hidden = false;
}

// ── JD 覆盖分析 ─────────────────────────────────────────────────────────────
async function runJdAnalysis(jdText) {
  const slug = currentSlug || "";
  try {
    const res = await fetch("/api/jd-analysis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jd_text: jdText, slug }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "分析失败");
    showJdAnalysisModal(data, jdText);
  } catch (e) {
    alert("JD 分析失败：" + e.message);
  }
}

function showJdAnalysisModal(result, jdText) {
  const skills = result.skill_points || [];
  const gaps = result.gaps || [];
  const rec = result.recommendation || "";

  let html = `<h2 style="margin:0 0 16px">JD 覆盖分析</h2>`;
  if (rec) html += `<p style="margin-bottom:16px">${escapeHtml(rec)}</p>`;

  if (gaps.length) {
    html += `<div class="hint warn-hint" style="margin-bottom:16px"><strong>备考缺口：</strong>${gaps.map(g => `<span class="pill">${escapeHtml(g)}</span>`).join(" ")}</div>`;
  }

  html += `<table style="width:100%;border-collapse:collapse;font-size:.9em">
    <thead><tr style="border-bottom:1px solid var(--border)">
      <th style="text-align:left;padding:6px 8px">技能点</th>
      <th style="text-align:center;padding:6px 8px">题库覆盖</th>
    </tr></thead><tbody>`;
  for (const s of skills) {
    const pct = Math.round((s.coverage || 0) * 100);
    const color = pct >= 70 ? "var(--green)" : pct >= 40 ? "var(--orange)" : "var(--red,#e55)";
    html += `<tr style="border-bottom:1px solid var(--border-light,#eee)">
      <td style="padding:6px 8px">${escapeHtml(s.skill)}</td>
      <td style="padding:6px 8px;text-align:center">
        <span style="color:${color};font-weight:600">${pct}%</span>
        <div style="height:4px;background:var(--border);border-radius:2px;margin-top:4px">
          <div style="height:4px;background:${color};border-radius:2px;width:${pct}%"></div>
        </div>
      </td>
    </tr>`;
  }
  html += `</tbody></table>`;
  $("modalBody").innerHTML = html;
  $("cardModal").hidden = false;
}

// RAG search events
if ($("ragSearchBtn")) {
  $("ragSearchBtn").addEventListener("click", () => {
    const q = ($("ragSearchInput")?.value || "").trim();
    if (q) runRagSearch(q);
  });
}
if ($("ragSearchInput")) {
  $("ragSearchInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const q = e.target.value.trim();
      if (q) runRagSearch(q);
    }
  });
}

// Resume textarea: save to localStorage on change
if ($("resumeText")) {
  $("resumeText").addEventListener("input", (e) => {
    localStorage.setItem("ir_resume_text", e.target.value);
  });
  // restore on load
  const saved = localStorage.getItem("ir_resume_text");
  if (saved) $("resumeText").value = saved;
}

// job type tabs
$("jobTypeBar").addEventListener("click", (e) => {
  const btn = e.target.closest(".job-type-btn");
  if (!btn) return;
  activeJobType = btn.dataset.type;
  renderJobsView();
});

// ── Tech-stack analysis panel ────────────────────────────────────────────
let techStackData = null;
let techStackLoading = false;

async function loadTechStack() {
  if (techStackLoading) return;
  techStackLoading = true;
  const panel = $("techStackPanel");
  panel.innerHTML = `<div class="ts-loading"><div class="spinner"></div><p>分析技术栈需求中…</p></div>`;
  panel.hidden = false;
  try {
    techStackData = await getJson("/api/jobs/tech-stack");
  } catch (e) {
    techStackData = null;
    panel.innerHTML = `<p class="feed-error">技术栈分析失败：${escapeHtml(String(e))}</p>`;
    techStackLoading = false;
    return;
  }
  techStackLoading = false;
  renderTechStack();
}

function renderTechStack() {
  const panel = $("techStackPanel");
  if (!techStackData) { panel.hidden = true; return; }
  const { total_jobs, categories } = techStackData;
  if (!categories || categories.length === 0) { panel.hidden = true; return; }
  panel.hidden = false;

  // find max count overall for relative bar sizing
  const globalMax = Math.max(...categories.flatMap(c => c.items.map(i => i.count)), 1);

  const cardsHtml = categories.map(cat => {
    const items = cat.items.slice(0, 10); // cap at 10 per card
    const catMax = Math.max(...items.map(i => i.count), 1);
    const rows = items.map(item => {
      const barPct = Math.round(item.count / catMax * 100);
      const isHot  = item.pct >= 10;
      return `<div class="ts-item${isHot ? ' ts-hot' : ''}">
        <span class="ts-item-label" title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</span>
        <div class="ts-bar-wrap"><div class="ts-bar-fill" style="width:${barPct}%"></div></div>
        <span class="ts-item-count">${item.count}</span>
        <span class="ts-item-pct">${item.pct}%</span>
      </div>`;
    }).join('');
    return `<div class="ts-card" data-cat="${escapeHtml(cat.name)}">
      <div class="ts-card-title">${escapeHtml(cat.name)}</div>
      ${rows}
    </div>`;
  }).join('');

  panel.innerHTML = `
    <div class="ts-header">
      <h2>技术栈需求分析</h2>
      <span class="ts-header-meta">基于 ${total_jobs} 个岗位 JD · 数据开发 + Agent 开发</span>
    </div>
    <div class="ts-grid">${cardsHtml}</div>
  `;
}
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
    if (data.focus_role_ids?.length) focusRoleIds = data.focus_role_ids.map(canonicalRoleId);
    if (data.default_role_id) selectedRoleId = canonicalRoleId(data.default_role_id);
    applyFocusRoleFilter();
    renderRoleChips($("roleChipRow"), selectRole);
    renderRoleChips($("roleChipRowDrawer"), selectRole);
    const current = techRoles.find((r) => r.id === selectedRoleId);
    if (current) $("role").value = current.search_as;
  } catch {
    techRoles = [...FOCUS_ROLE_FALLBACK];
    applyFocusRoleFilter();
    renderRoleChips($("roleChipRow"), selectRole);
    renderRoleChips($("roleChipRowDrawer"), selectRole);
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
