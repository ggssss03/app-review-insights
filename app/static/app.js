const $ = (id) => document.getElementById(id);

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

/* 份额百分比：最大余数法，保证各项之和恒为 100 */
function pctShares(values) {
  const nums = values.map((v) => Number(v) || 0);
  const total = nums.reduce((a, b) => a + b, 0) || 1;
  const exact = nums.map((v) => (v / total) * 100);
  const base = exact.map(Math.floor);
  let rem = 100 - base.reduce((a, b) => a + b, 0);
  const order = exact.map((v, i) => [v - Math.floor(v), i]).sort((a, b) => b[0] - a[0]);
  for (let k = 0; k < rem && k < order.length; k++) base[order[k][1]] += 1;
  return base;
}

function badge(label, cls) {
  return `<span class="badge ${esc(cls)}">${esc(label)}</span>`;
}

async function api(path, options = {}) {
  const resp = await fetch(path, options);
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
  return data;
}

async function init() {
  try {
    const health = await api("/api/health");
    $("health").textContent = `v${health.version} · LLM ${health.llm_available ? "已配置" : "未配置（确定性模式）"}`;
  } catch (e) {
    $("health").textContent = "服务不可用";
  }
  document.querySelectorAll(".tab").forEach((btn) =>
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      renderTab(btn.dataset.tab);
    })
  );
  $("start-btn").addEventListener("click", start);
  $("import-btn").addEventListener("click", doImport);
}

let currentAppId = null;
let currentRunId = null;
let pollTimer = null;

async function start() {
  const url = $("url").value.trim();
  const goal = $("goal").value.trim();
  if (!url) return showMsg("请填写 App Store 链接或应用 ID", true);
  $("start-btn").disabled = true;
  $("form-msg").textContent = "已提交，正在启动分析…";
  $("progress-card").classList.remove("hidden");
  $("progress-list").innerHTML = "";
  $("result-card").classList.add("hidden");
  try {
    const run = await api("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        goal,
        llm: $("use-llm").checked,
        fresh: $("fresh").checked,
      }),
    });
    currentAppId = run.app_id;
    currentRunId = run.run_id;
    tickerPush(`分析任务已提交（${run.app_id}）`);
    showMsg(`运行已启动（${run.app_id}），等待进度…`);
    pollTimer = setInterval(pollStatus, 800);
  } catch (e) {
    showMsg(`启动失败：${e.message}`, true);
    $("start-btn").disabled = false;
  }
}

async function pollStatus() {
  if (!currentRunId) return;
  try {
    const status = await api(`/api/status/${currentRunId}`);
    renderProgress(status.progress || []);
    if (status.status === "done") {
      clearInterval(pollTimer);
      $("start-btn").disabled = false;
      showMsg("分析完成。");
      await loadResults(status.result);
    } else if (status.status === "error") {
      clearInterval(pollTimer);
      $("start-btn").disabled = false;
      showMsg(`分析失败：${status.error}`, true);
      $("result-card").classList.add("hidden");
    }
  } catch (e) {
    clearInterval(pollTimer);
    $("start-btn").disabled = false;
    showMsg(`状态查询失败：${e.message}`, true);
  }
}

function renderProgress(events) {
  const list = $("progress-list");
  list.innerHTML = events
    .map((e) => `<li class="${esc(e.status)}"><strong>${esc(e.stage)}</strong> <span class="term-status">${esc(e.status)}</span>：${esc(e.detail)}</li>`)
    .join("");
  const last = events[events.length - 1];
  if (last) tickerPush(`${last.stage} · ${last.status}：${last.detail}`);
}

async function loadResults(summary) {
  $("result-card").classList.remove("hidden");
  $("summary-data") || null;
  window.__summary = summary;
  renderTab("summary");
  const cc = (summary && summary.counts) || {};
  tickerPush(`分析完成：${cc.reviews || 0} 条评论 · ${cc.findings || 0} 项发现 · ${(summary && summary.traceability ? summary.traceability.passed_checks : 0) || 0} 项追溯通过`);
}

async function fetchStage(stage) {
  if (!currentAppId) return null;
  const data = await api(`/api/artifacts/${currentAppId}?stage=${stage}`);
  return data.data;
}

async function renderTab(tab) {
  const el = $("tab-content");
  try {
    if (tab === "summary") el.innerHTML = renderSummary(window.__summary);
    else if (tab === "raw") el.innerHTML = renderRaw(await fetchStage("raw"));
    else if (tab === "topics") el.innerHTML = renderTopics(await fetchStage("topics"));
    else if (tab === "findings") el.innerHTML = renderFindings(await fetchStage("findings"));
    else if (tab === "requirements") el.innerHTML = renderRequirements(await fetchStage("requirements"));
    else if (tab === "testcases") el.innerHTML = renderTestCases(await fetchStage("testcases"));
    else if (tab === "traceability") el.innerHTML = renderTraceability(await fetchStage("traceability"));
    else if (tab === "clean") el.innerHTML = renderClean(await fetchStage("clean"));
  } catch (e) {
    el.innerHTML = `<div class="msg error">加载失败：${esc(e.message)}</div>`;
  }
  el.querySelectorAll(":scope > *").forEach((node, i) => {
    node.classList.add("anim-in");
    node.style.setProperty("--i", i);
  });
}

function renderSummary(s) {
  if (!s) return "<p>暂无结果。</p>";
  const c = s.counts || {};
  const cards = [
    ["评论", c.reviews || 0], ["主题聚类", c.topics || 0], ["关键发现", c.findings || 0],
    ["需求规约", c.requirements || 0], ["验收用例", c.test_cases || 0],
  ].map(([lbl, num]) =>
    `<div class="kpi-card"><div class="num" data-count="${Number(num) || 0}">0</div><div class="lbl">${lbl}</div></div>`
  ).join("");
  const trace = s.traceability || {};
  setTimeout(() => animateCounts(), 30);
  return `
    <div class="summary-grid">${cards}</div>
    ${renderDist(s.clean_stats)}
    ${renderScope(s.scope)}
    <div class="meta-row">
      <div class="meta-chip"><span class="meta-label">说明</span>
        <ul class="note-list">${(s.notes || []).map((n) => `<li>${esc(n)}</li>`).join("")}</ul>
      </div>
      <div class="meta-chip">
        <span class="meta-label">溯源校验</span>
        <span class="trace-big">${trace.passed_checks || 0}/${trace.total_checks || 0} <small>通过</small></span>
        <span class="trace-tag ${s.model_driven ? "model" : ""}">${s.model_driven ? "模型驱动" : "确定性模式"}</span>
      </div>
    </div>
  `;
}

const FOCUS_LABELS = {
  pricing: "定价",
  subscription_conversion: "订阅转化",
  usability: "可用性",
  performance: "性能",
  features: "功能",
  other: "其他",
};

function renderScope(scope) {
  if (!scope) return "";
  const areas = (scope.focus_areas || []).map((a) =>
    `<span class="focus-tag">${esc(FOCUS_LABELS[a] || a)}</span>`
  ).join("");
  const star = scope.star_filter || {};
  const starText = (star.min == null && star.max == null)
    ? "不限"
    : `最低 ${star.min ?? "—"} 星 ～ 最高 ${star.max ?? "—"} 星`;
  const versionText = scope.version_filter ? `版本 ${esc(scope.version_filter)}` : "不限版本";
  return `
    <div class="scope-card">
      <div class="scope-head">
        <span class="scope-title">▣ 分析范围</span>
        <span class="scope-mode">${(scope.note || "").includes("全量") ? "全量分析" : "定向分析"}</span>
      </div>
      <div class="scope-body">
        <div class="scope-row">
          <span class="meta-label">关注维度</span>
          <div class="focus-tags">${areas || '<span class="muted">未指定（全量）</span>'}</div>
        </div>
        <div class="scope-row">
          <span class="meta-label">评分筛选</span><span class="scope-val">${esc(starText)}</span>
          <span class="meta-label">版本筛选</span><span class="scope-val">${versionText}</span>
        </div>
        <div class="scope-row">
          <span class="meta-label">范围说明</span>
          <span class="scope-note">${esc(scope.note || "—")}</span>
        </div>
      </div>
    </div>
  `;
}

function renderTopics(t) {
  if (!t || !t.topics) return `<div class="page-head"><h2>◉ 主题聚类</h2></div><p>暂无主题数据。</p>`;
  const total = t.topics.reduce((a, b) => a + (b.count || 0), 0) || 1;
  const shares = pctShares(t.topics.map((x) => x.count || 0));
  const cards = t.topics.map((topic, i) => {
    const share = shares[i];
    return `
    <div class="topic-card">
      <div class="topic-head">
        <span class="topic-idx">C${String(topic.topic_id ?? i + 1).padStart(2, "0")}</span>
        <h3>${esc(topic.label)}</h3>
        <span class="badge stat">样本 ${topic.count || 0}</span>
        <span class="topic-share">占比 ${share}%</span>
      </div>
      <div class="topic-bar"><div class="topic-bar-fill" style="width:${share}%"></div></div>
      <p class="topic-desc">${esc(topic.description || "无描述")}</p>
      ${topic.keywords?.length ? `<div class="kw-row">${topic.keywords.map((k) => `<span class="kw-chip">#${esc(k)}</span>`).join("")}</div>` : ""}
      ${(topic.samples || []).length ? `<div class="sample-list">${topic.samples.slice(0, 4).map((s) => `<div class="sample"><span class="sample-id">${esc(s.review_id)}</span>${esc(s.text)}</div>`).join("")}</div>` : ""}
    </div>`;
  }).join("");
  const modelTag = t.model_driven ? badge("模型驱动", "model") : badge("确定性模式", "stat");
  return `
    <div class="page-head">
      <div>
        <h2>◉ 主题聚类</h2>
        <p class="page-sub">${t.topics.length} 个聚类 · 覆盖 ${total} 条评论 · ${t.embed_backend === "tfidf" ? "TF-IDF 嵌入" : esc(t.embed_backend || "—")}</p>
      </div>
      ${modelTag}
    </div>
    ${cards}`;
}

/* ============ 原始评论 ============ */
const RAW_SOURCE_LABELS = {
  rss: "RSS 采集",
  "amp-page": "产品页内嵌",
  amp: "AMP 接口",
  itml: "美区 itml",
  import: "导入数据",
};

function renderRaw(reviews) {
  if (!reviews || !reviews.length) {
    return `<div class="page-head"><div><h2>原始评论</h2></div></div><p>暂无原始评论数据（请先采集或导入）。</p>`;
  }
  const rows = reviews
    .slice()
    .sort((a, b) => String(b.updated || "").localeCompare(String(a.updated || "")))
    .slice(0, 100)
    .map((r) => `
      <tr>
        <td><span class="badge stat">${esc(RAW_SOURCE_LABELS[r.source] || r.source || "?")}</span><br>
            <span class="cell-id">${esc(r.review_id || "—")}</span></td>
        <td><span class="stars s${r.rating || 0}">${"★".repeat(r.rating || 0)}<span class="stars-ghost">${"★".repeat(5 - (r.rating || 0))}</span></span></td>
        <td><span class="version-tag">${esc(r.version || "—")}</span></td>
        <td class="cell-id">${esc(r.updated || "—")}</td>
        <td>${r.helpful_votes || 0}</td>
        <td class="cell-body"><span class="cell-title">${esc(r.title || "")}</span>${r.body ? ` ${esc(r.body)}` : ""}</td>
      </tr>`).join("");
  return `
    <div class="page-head">
      <div>
        <h2>原始评论</h2>
        <p class="page-sub">共 ${reviews.length} 条原始评论（按日期倒序，最多展示 100 条）· 来源与采集时间见原始缓存</p>
      </div>
    </div>
    <div class="table-wrap">
      <table class="clean-table"><thead><tr>
        <th>来源 / ID</th><th>评分</th><th>版本</th><th>日期</th><th>有用</th><th>内容</th>
      </tr></thead><tbody>${rows}</tbody></table>
    </div>`;
}

function renderFindings(f) {
  if (!f || !f.length) return "<p>暂无发现。</p>";
  const rows = f.map((x) => `
    <tr>
      <td>${esc(x.id)}<br>${badge(x.provenance || "?", x.provenance)} ${badge(x.status || "kept", x.status || "kept")}</td>
      <td>${esc(x.statement)}</td>
      <td>${x.sample_count}</td>
      <td>${x.confidence ?? "-"}</td>
      <td>${(x.evidence_review_ids || []).slice(0, 6).map(esc).join(", ")}</td>
      <td>${(x.conflicts || []).map(esc).join("；") || "-"}</td>
    </tr>`).join("");
  return `<table><thead><tr><th>ID / 来源</th><th>结论</th><th>样本</th><th>置信</th><th>证据评论</th><th>冲突</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderRequirements(r) {
  if (!r || !r.length) return "<p>暂无需求（需要 LLM 配置生成 PRD）。</p>";
  return `<table><thead><tr><th>编号</th><th>标题</th><th>优先级</th><th>版本</th><th>来源发现</th><th>来源评论</th><th>验收标准</th></tr></thead><tbody>
    ${r.map((x) => `<tr>
      <td>${esc(x.code)} ${badge(x.status || "kept", x.status || "kept")}</td>
      <td><strong>${esc(x.title)}</strong><br><span style="color:var(--muted)">${esc(x.description || "")}</span></td>
      <td>${esc(x.priority)}</td><td>${esc(x.planned_version)}</td>
      <td>${(x.finding_ids || []).map(esc).join(", ") || "-"}</td>
      <td>${(x.review_ids || []).slice(0, 5).map(esc).join(", ") || "-"}</td>
      <td>${(x.acceptance_criteria || []).map(esc).join("；") || "-"}</td>
    </tr>`).join("")}
  </tbody></table>`;
}

function renderTestCases(t) {
  if (!t || !t.length) return "<p>暂无测试用例（需要 LLM 配置生成）。</p>";
  return t.map((x) => `
    <div class="topic-card">
      <h3>${esc(x.code)} · ${esc(x.title)}</h3>
      <p>需求：${(x.requirement_ids || []).map(esc).join(", ")} · 评论：${(x.review_ids || []).map(esc).join(", ") || "-"}</p>
      <div class="gherkin">
        ${(x.gherkin.given || []).map((g) => `<div class="given">Given ${esc(g)}</div>`).join("")}
        ${(x.gherkin.when || []).map((g) => `<div class="when">When ${esc(g)}</div>`).join("")}
        ${(x.gherkin.then || []).map((g) => `<div class="then">Then ${esc(g)}</div>`).join("")}
      </div>
    </div>`).join("");
}

function renderTraceability(t) {
  if (!t) return "<p>暂无校验数据。</p>";
  const rows = (t.checks || []).map((c) => `
    <tr><td>${esc(c.check)}</td><td>${esc(c.id)}</td>
    <td>${c.passed ? badge("通过", "kept") : badge("失败", "removed")}</td>
    <td>${esc(c.detail)}${c.missing?.length ? `（缺失：${c.missing.map(esc).join(", ")}）` : ""}</td></tr>`).join("");
  return `
    <p>${t.summary.passed_checks}/${t.summary.total_checks} 通过 ·
    移除发现 ${t.removed_findings.length} · 移除用例 ${t.removed_test_cases.length} ·
    标注假设需求 ${t.assumption_requirements.length}</p>
    <table><thead><tr><th>检查项</th><th>对象</th><th>结果</th><th>说明</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderClean(c) {
  if (!c) return "<p>暂无清洗数据。</p>";
  const s = c.stats || {};
  const rows = (c.reviews || []).slice(0, 50).map((r) => `
    <tr><td>${esc(r.review_id || r.dedup_key)}</td><td>${esc(r.rating)}</td>
    <td>${esc(r.lang)}</td><td>${esc((r.title + " " + r.body).slice(0, 120))}</td>
    <td>${r.is_junk ? badge("垃圾", "removed") : badge("正常", "kept")}</td></tr>`).join("");
  return `
    <p>输入 ${s.input_count} → 唯一 ${s.unique_count}（去重 ${s.removed_duplicates}，垃圾 ${s.junk_count}）</p>
    <table><thead><tr><th>ID</th><th>评分</th><th>语言</th><th>内容</th><th>状态</th></tr></thead><tbody>${rows}</tbody></table>`;
}

async function doImport() {
  const file = $("import-file").files[0];
  const appId = $("import-app-id").value.trim();
  if (!file || !appId) return showMsg("请选择文件并填写 app id", true);
  const fmt = file.name.endsWith(".csv") ? "csv" : "json";
  const content = await file.text();
  try {
    const result = await api(`/api/import?app_id=${encodeURIComponent(appId)}`, {
      method: "POST",
      headers: { "Content-Type": fmt === "csv" ? "text/csv" : "application/json" },
      body: content,
    });
    showMsg(`导入成功：${result.count} 条评论（${appId}）。`);
    tickerPush(`导入完成：${result.count} 条评论（${appId}）`);
  } catch (e) {
    showMsg(`导入失败：${e.message}`, true);
  }
}

function showMsg(text, isError = false) {
  const el = $("form-msg");
  el.textContent = text;
  el.className = "msg" + (isError ? " error" : "");
}

init();

/* ============ 科幻粒子网络背景 ============ */
(function initParticles() {
  const canvas = document.getElementById("bg-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let width, height, particles = [], comets = [];
  const COUNT = 54;
  const COLORS = ["34,211,238", "167,139,250", "244,114,182", "52,211,153"];

  function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  }

  function spawn() {
    particles = Array.from({ length: COUNT }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.28,
      vy: (Math.random() - 0.5) * 0.28,
      r: Math.random() * 2.2 + 0.7,
      c: COLORS[Math.floor(Math.random() * COLORS.length)],
      tw: Math.random() * Math.PI * 2,
    }));
    comets = Array.from({ length: 3 }, () => spawnComet());
  }

  function spawnComet() {
    const fromLeft = Math.random() > 0.5;
    return {
      x: fromLeft ? -40 : width + 40,
      y: Math.random() * height * 0.55,
      vx: (fromLeft ? 1 : -1) * (2.4 + Math.random() * 1.6),
      vy: 0.9 + Math.random() * 0.8,
      life: 0,
      max: 260 + Math.random() * 180,
    };
  }

  function frame() {
    ctx.clearRect(0, 0, width, height);
    const LINK = 150;
    for (const p of particles) {
      p.x += p.vx;
      p.y += p.vy;
      p.tw += 0.02;
      if (p.x < -20) p.x = width + 20;
      if (p.x > width + 20) p.x = -20;
      if (p.y < -20) p.y = height + 20;
      if (p.y > height + 20) p.y = -20;
      const alpha = 0.35 + 0.3 * Math.sin(p.tw);
      ctx.save();
      ctx.shadowBlur = 10;
      ctx.shadowColor = `rgba(${p.c},0.85)`;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${p.c},${alpha})`;
      ctx.fill();
      ctx.restore();
    }
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const a = particles[i], b = particles[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const d2 = dx * dx + dy * dy;
        if (d2 < LINK * LINK) {
          const alpha = (1 - Math.sqrt(d2) / LINK) * 0.15;
          ctx.strokeStyle = `rgba(${a.c},${alpha})`;
          ctx.lineWidth = 0.6;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }
    for (const c of comets) {
      c.x += c.vx;
      c.y += c.vy;
      c.life += 1;
      if (c.life > c.max || c.x > width + 60 || c.x < -60 || c.y > height + 60) {
        Object.assign(c, spawnComet());
      }
      const t = Math.min(1, c.life / 60);
      const tail = 26 * (0.4 + t);
      const grad = ctx.createLinearGradient(c.x, c.y, c.x - c.vx * tail, c.y - c.vy * tail);
      grad.addColorStop(0, "rgba(165,243,252,0.9)");
      grad.addColorStop(1, "rgba(167,139,250,0)");
      ctx.strokeStyle = grad;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.moveTo(c.x, c.y);
      ctx.lineTo(c.x - c.vx * tail, c.y - c.vy * tail);
      ctx.stroke();
    }
    if (!reduceMotion) requestAnimationFrame(frame);
  }

  resize();
  spawn();
  frame();
  window.addEventListener("resize", () => { resize(); spawn(); });
})();

/* ============ 光标全息光晕 ============ */
(function initCursorGlow() {
  const el = document.getElementById("cursor-glow");
  if (!el) return;
  if (window.matchMedia("(pointer: coarse)").matches) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  let raf = null;
  let tx = window.innerWidth / 2, ty = window.innerHeight / 2;
  let x = tx, y = ty;
  function loop() {
    raf = requestAnimationFrame(loop);
    x += (tx - x) * 0.12;
    y += (ty - y) * 0.12;
    el.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(-50%, -50%)`;
  }
  window.addEventListener("pointermove", (e) => {
    tx = e.clientX;
    ty = e.clientY;
    el.classList.add("on");
    if (!raf) loop();
  }, { passive: true });
  document.addEventListener("mouseleave", () => el.classList.remove("on"));
})();

/* ============ 结果卡片 3D 倾斜 ============ */
(function initTilt() {
  if (window.matchMedia("(pointer: coarse)").matches) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const SEL = ".kpi-card, .topic-card, .finding-card, .req-card, .tc-card";
  let current = null;
  document.addEventListener("pointermove", (e) => {
    const card = e.target.closest(SEL);
    if (!card) return;
    if (card !== current) current = card;
    const r = card.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width - 0.5;
    const py = (e.clientY - r.top) / r.height - 0.5;
    card.style.transform =
      `perspective(900px) rotateX(${(-py * 5).toFixed(2)}deg) rotateY(${(px * 5).toFixed(2)}deg) translateY(-2px)`;
  }, { passive: true });
  document.addEventListener("pointerout", (e) => {
    const card = e.target.closest(SEL);
    if (!card) return;
    if (!e.relatedTarget || !card.contains(e.relatedTarget)) {
      card.style.transform = "";
      current = null;
    }
  });
})();

/* ============ 主按钮磁吸 ============ */
(function initMagnetic() {
  const btn = document.querySelector(".btn.primary");
  if (!btn) return;
  if (window.matchMedia("(pointer: coarse)").matches) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  btn.addEventListener("pointermove", (e) => {
    const r = btn.getBoundingClientRect();
    const dx = e.clientX - (r.left + r.width / 2);
    const dy = e.clientY - (r.top + r.height / 2);
    btn.style.transform = `translate(${(dx * 0.16).toFixed(1)}px, ${(dy * 0.22).toFixed(1)}px)`;
  }, { passive: true });
  btn.addEventListener("pointerleave", () => { btn.style.transform = ""; });
})();

/* ============ 标题打字机效果 ============ */
(function initTypewriter() {
  const el = document.querySelector(".subtitle");
  if (!el) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const full = el.textContent;
  el.textContent = "";
  let i = 0;
  const timer = setInterval(() => {
    i += 2;
    el.textContent = full.slice(0, i);
    if (i >= full.length) {
      clearInterval(timer);
      el.style.borderRight = "none";
    }
  }, 28);
})();

/* ============ 评分 / 语言分布渲染 ============ */
function renderDist(cs) {
  if (!cs) return "";
  const rd = cs.rating_distribution || {};
  const ld = cs.language_distribution || {};
  const hasRating = Object.keys(rd).length > 0;
  const hasLang = Object.keys(ld).length > 0;
  if (!hasRating && !hasLang) return "";

  const ratingKeys = ["5", "4", "3", "2", "1"];
  const ratingVals = ratingKeys.map((k) => Number(rd[k] || 0));
  const ratingShares = pctShares(ratingVals);
  const ratingRows = hasRating
    ? ratingKeys.map((k, i) => {
        const n = ratingVals[i];
        const pct = ratingShares[i];
        return `<div class="dist-row"><span class="dist-label">${k}★</span><div class="dist-track"><div class="dist-fill f${k}" style="width:${pct}%"></div></div><span class="dist-val">${n} · ${pct}%</span></div>`;
      }).join("")
    : "";

  const langEntries = Object.entries(ld);
  const langShares = pctShares(langEntries.map(([, v]) => v));
  const langRows = langEntries
    .map(([k, v], i) => {
      const n = Number(v || 0);
      const pct = langShares[i];
      const name = k === "zh" ? "中文" : k === "en" ? "英文" : k.toUpperCase();
      return `<div class="dist-row"><span class="dist-label">${name}</span><div class="dist-track"><div class="dist-fill lang-fill" style="width:${pct}%"></div></div><span class="dist-val">${n} · ${pct}%</span></div>`;
    })
    .join("");

  return `<div class="dist-panel">
    ${hasRating ? `<div class="dist-col"><h3 class="dist-title">★ 评分分布</h3>${ratingRows}</div>` : ""}
    ${hasLang ? `<div class="dist-col"><h3 class="dist-title">◉ 语言分布</h3>${langRows}</div>` : ""}
  </div>`;
}

/* ============ KPI 数字滚动 ============ */
function animateCounts() {
  document.querySelectorAll("#tab-content .num[data-count]").forEach((el) => {
    const target = parseInt(el.dataset.count || "0", 10) || 0;
    const start = performance.now();
    const dur = 900;
    function step(t) {
      const p = Math.min(1, (t - start) / dur);
      el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  });
}

/* ============ 底部 LIVE 滚动状态条 ============ */
const tickerMsgs = [];

function tickerRender() {
  const track = document.getElementById("ticker-track");
  if (!track) return;
  const text = tickerMsgs.slice(-18).map((m) => `▸ ${m}`).join("　　");
  track.innerHTML = `<span>${esc(text)}</span><span>${esc(text)}</span>`;
}

function tickerPush(msg) {
  tickerMsgs.push(String(msg));
  if (tickerMsgs.length > 80) tickerMsgs.shift();
  tickerRender();
}

(function initTicker() {
  const boot = [
    "系统启动完成",
    "粒子网络已连接",
    "评论采集引擎就绪（中国区 RSS）",
    "LLM 分析核心待命",
    "等待任务指令…",
  ];
  boot.forEach((m, i) => setTimeout(() => tickerPush(m), 600 + i * 700));
})();

/* ============ 子页面渲染升级（卡片化） ============ */
const PROVENANCE_LABELS = { stat: "统计", model: "模型", rule: "规则" };
const STATUS_LABELS = { kept: "保留", removed: "移除", assumption: "假设" };
const PRIO_LABELS = { P0: "P0 紧急", P1: "P1 高", P2: "P2 中", P3: "P3 低" };
const CHECK_LABELS = {
  finding_evidence: "发现证据校验",
  requirement_support: "需求支撑校验",
  testcase_link: "用例关联校验",
  requirement_review_chain: "需求评论链校验",
};

renderFindings = function (f) {
  if (!f || !f.length) return `<div class="page-head"><h2>◆ 关键发现</h2></div><p>暂无发现。</p>`;
  const cards = f.map((x) => {
    const conf = Math.round((Number(x.confidence) || 0) * 100);
    const evidence = x.evidence_review_ids || [];
    const conflicts = x.conflicts || [];
    const prov = PROVENANCE_LABELS[x.provenance] || esc(x.provenance || "未知");
    const status = STATUS_LABELS[x.status] || esc(x.status || "");
    return `
    <div class="finding-card">
      <div class="finding-head">
        <span class="code-chip">${esc(x.id)}</span>
        <span class="chip prov-${esc(x.provenance)}">${esc(prov)}</span>
        ${x.status ? `<span class="chip status-${esc(x.status)}">${esc(status)}</span>` : ""}
        <div class="conf-meter">
          <span class="conf-label">置信 ${conf}%</span>
          <div class="conf-track"><div class="conf-fill" style="width:${conf}%"></div></div>
        </div>
      </div>
      <p class="finding-statement">${esc(x.statement)}</p>
      <div class="finding-meta">
        <span class="meta-item">◈ 样本 <b>${x.sample_count ?? 0}</b> 条</span>
        <span class="meta-item">◈ 证据 <b>${evidence.length}</b> 条</span>
        ${x.uncertainty && x.uncertainty !== "无" ? `<span class="meta-item warn">⚠ ${esc(x.uncertainty)}</span>` : ""}
      </div>
      ${conflicts.length ? `<div class="conflict-list">${conflicts.map((c) => `<div class="conflict-line">✕ ${esc(c)}</div>`).join("")}</div>` : ""}
      ${evidence.length ? `<div class="evidence-row">证据：${evidence.slice(0, 8).map((id) => `<span class="chip mini">${esc(id)}</span>`).join("")}${evidence.length > 8 ? `<span class="chip mini dim">+${evidence.length - 8}</span>` : ""}</div>` : ""}
      ${x.rationale ? `<div class="rationale">${esc(x.rationale)}</div>` : ""}
    </div>`;
  }).join("");
  return `
    <div class="page-head">
      <div>
        <h2>◆ 关键发现</h2>
        <p class="page-sub">${f.length} 项发现 · 统计 + 模型双重证据评估</p>
      </div>
    </div>
    ${cards}`;
};

renderRequirements = function (r) {
  if (!r || !r.length) return `<div class="page-head"><h2>▣ 需求规约 (PRD)</h2></div><p>暂无需求（需要 LLM 配置生成 PRD）。</p>`;
  const cards = r.map((x) => {
    const prio = String(x.priority || "").toUpperCase();
    const prioCls = prio.startsWith("P0") ? "p0" : prio.startsWith("P1") ? "p1" : prio.startsWith("P2") ? "p2" : "p3";
    return `
    <div class="req-card">
      <div class="req-head">
        <span class="code-chip">${esc(x.code)}</span>
        <h3>${esc(x.title)}</h3>
        <span class="prio ${prioCls}">${esc(PRIO_LABELS[prio] || x.priority || "—")}</span>
        <span class="version-tag">版本 ${esc(x.planned_version || "—")}</span>
      </div>
      ${x.description ? `<p class="req-desc">${esc(x.description)}</p>` : ""}
      <div class="req-meta">
        ${(x.finding_ids || []).length ? `<div class="link-row"><span class="link-label">来源发现</span>${x.finding_ids.map((id) => `<span class="chip mini">${esc(id)}</span>`).join("")}</div>` : ""}
        ${(x.review_ids || []).length ? `<div class="link-row"><span class="link-label">来源评论</span>${x.review_ids.slice(0, 6).map((id) => `<span class="chip mini">${esc(id)}</span>`).join("")}</div>` : ""}
      </div>
      ${(x.acceptance_criteria || []).length ? `<ul class="ac-list">${x.acceptance_criteria.map((c) => `<li><span class="ac-mark">✓</span>${esc(c)}</li>`).join("")}</ul>` : ""}
    </div>`;
  }).join("");
  return `
    <div class="page-head">
      <div>
        <h2>▣ 需求规约 (PRD)</h2>
        <p class="page-sub">${r.length} 项需求 · 版本规划与验收标准</p>
      </div>
    </div>
    ${cards}`;
};

renderTestCases = function (t) {
  if (!t || !t.length) return `<div class="page-head"><h2>▤ 验收用例</h2></div><p>暂无测试用例（需要 LLM 配置生成）。</p>`;
  const cards = t.map((x) => {
    const g = x.gherkin || {};
    const steps = [
      ...(g.given || []).map((s) => `<div class="gstep given"><span class="gword">Given</span><span class="gtext">${esc(s)}</span></div>`),
      ...(g.when || []).map((s) => `<div class="gstep when"><span class="gword">When</span><span class="gtext">${esc(s)}</span></div>`),
      ...(g.then || []).map((s) => `<div class="gstep then"><span class="gword">Then</span><span class="gtext">${esc(s)}</span></div>`),
    ].join("");
    return `
    <div class="tc-card">
      <div class="tc-head">
        <span class="code-chip">${esc(x.code)}</span>
        <h3>${esc(x.title)}</h3>
        <span class="chip mini model">验收</span>
      </div>
      <div class="req-link">需求：${(x.requirement_ids || []).map((id) => `<span class="chip mini">${esc(id)}</span>`).join("") || "—"}</div>
      ${x.review_ids && x.review_ids.length ? `<div class="req-link">评论：${x.review_ids.slice(0, 6).map((id) => `<span class="chip mini">${esc(id)}</span>`).join("")}</div>` : ""}
      <div class="gherkin">${steps}</div>
    </div>`;
  }).join("");
  return `
    <div class="page-head">
      <div>
        <h2>▤ 验收用例</h2>
        <p class="page-sub">${t.length} 个 Gherkin 场景 · 覆盖需求验收</p>
      </div>
    </div>
    ${cards}`;
};

renderTraceability = function (t) {
  if (!t) return `<div class="page-head"><h2>⌁ 溯源校验</h2></div><p>暂无校验数据。</p>`;
  const sum = t.summary || {};
  const total = sum.total_checks || 0;
  const passed = sum.passed_checks || 0;
  const pct = total ? Math.round((passed / total) * 100) : 0;
  const checks = t.checks || [];
  const rows = checks.map((c) => `
    <div class="check-row ${c.passed ? "pass" : "fail"}">
      <span class="check-icon">${c.passed ? "✓" : "✕"}</span>
      <span class="check-type">${esc(CHECK_LABELS[c.check] || c.check)}</span>
      <span class="chip mini">${esc(c.id)}</span>
      <span class="check-detail">${esc(c.detail || "")}</span>
      ${c.missing && c.missing.length ? `<span class="missing">缺失：${c.missing.map(esc).join(", ")}</span>` : ""}
    </div>`).join("");
  return `
    <div class="page-head">
      <div>
        <h2>⌁ 溯源校验</h2>
        <p class="page-sub">需求 ← 发现 ← 评论 全链路一致性检查</p>
      </div>
    </div>
    <div class="trace-overview">
      <div class="trace-score">
        <span class="trace-big">${passed}/${total}</span>
        <span class="trace-rate">通过率 ${pct}%</span>
        <div class="conf-track"><div class="conf-fill ok-fill" style="width:${pct}%"></div></div>
      </div>
      <div class="trace-chips">
        <div class="trace-chip"><b>${t.removed_findings ? t.removed_findings.length : 0}</b><span>移除发现</span></div>
        <div class="trace-chip"><b>${t.removed_test_cases ? t.removed_test_cases.length : 0}</b><span>移除用例</span></div>
        <div class="trace-chip"><b>${t.assumption_requirements ? t.assumption_requirements.length : 0}</b><span>假设需求</span></div>
        <div class="trace-chip"><b>${checks.length}</b><span>总检查项</span></div>
      </div>
    </div>
    <div class="check-list">${rows}</div>`;
};

renderClean = function (c) {
  if (!c) return `<div class="page-head"><h2>✧ 数据清洗</h2></div><p>暂无清洗数据。</p>`;
  const s = c.stats || {};
  const langName = (l) => (l === "zh" ? "中文" : l === "en" ? "英文" : String(l || "?").toUpperCase());
  const rows = (c.reviews || []).slice(0, 50).map((r) => `
    <tr>
      <td class="cell-id">${esc(r.review_id || r.dedup_key || "—")}</td>
      <td><span class="stars s${r.rating}">${"★".repeat(r.rating || 0)}<span class="stars-ghost">${"★".repeat(5 - (r.rating || 0))}</span></span></td>
      <td><span class="lang-chip ${esc(r.lang)}">${langName(r.lang)}</span></td>
      <td class="cell-body"><span class="cell-title">${esc(r.title || "")}</span>${r.body ? ` ${esc(String(r.body).slice(0, 100))}` : ""}</td>
      <td>${r.is_junk ? badge("垃圾", "removed") : badge("正常", "kept")}</td>
    </tr>`).join("");
  const chips = [
    ["输入", s.input_count || 0],
    ["唯一", s.unique_count || 0],
    ["去重", s.removed_duplicates || 0],
    ["垃圾", s.junk_count || 0],
  ].map(([lbl, n]) => `<div class="clean-chip"><b>${n}</b><span>${lbl}</span></div>`).join("");
  return `
    <div class="page-head">
      <div>
        <h2>✧ 数据清洗</h2>
        <p class="page-sub">${s.rules_note ? esc(s.rules_note) : "确定性清洗规则"}</p>
      </div>
    </div>
    <div class="clean-stats">${chips}</div>
    <div class="table-wrap">
      <table class="clean-table"><thead><tr><th>ID</th><th>评分</th><th>语言</th><th>内容</th><th>状态</th></tr></thead><tbody>${rows}</tbody></table>
    </div>`;
};
