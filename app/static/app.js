const $ = (id) => document.getElementById(id);

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

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
      body: JSON.stringify({ url, goal, llm: $("use-llm").checked }),
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
    else if (tab === "topics") el.innerHTML = renderTopics(await fetchStage("topics"));
    else if (tab === "findings") el.innerHTML = renderFindings(await fetchStage("findings"));
    else if (tab === "requirements") el.innerHTML = renderRequirements(await fetchStage("requirements"));
    else if (tab === "testcases") el.innerHTML = renderTestCases(await fetchStage("testcases"));
    else if (tab === "traceability") el.innerHTML = renderTraceability(await fetchStage("traceability"));
    else if (tab === "clean") el.innerHTML = renderClean(await fetchStage("clean"));
  } catch (e) {
    el.innerHTML = `<div class="msg error">加载失败：${esc(e.message)}</div>`;
  }
}

function renderSummary(s) {
  if (!s) return "<p>暂无结果。</p>";
  const c = s.counts || {};
  const cards = [
    ["评论", c.reviews || 0], ["主题", c.topics || 0], ["发现", c.findings || 0],
    ["需求", c.requirements || 0], ["测试用例", c.test_cases || 0],
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
        <span class="meta-label">追溯校验</span>
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
  if (!t || !t.topics) return "<p>暂无主题数据。</p>";
  return t.topics.map((topic) => `
    <div class="topic-card">
      <h3>${esc(topic.label)} ${badge(`样本 ${topic.count}`, "stat")}</h3>
      <p>${esc(topic.description || "无描述")}</p>
      ${topic.keywords?.length ? `<p>关键词：${topic.keywords.map(esc).join("、")}</p>` : ""}
      ${(topic.samples || []).map((s) => `<div class="sample">[${esc(s.review_id)}] ${esc(s.text)}</div>`).join("")}
    </div>`).join("");
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
  let width, height, particles = [];
  const COUNT = 70;
  const COLORS = ["0,229,255", "168,85,247", "255,45,149"];

  function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  }

  function spawn() {
    particles = Array.from({ length: COUNT }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.35,
      vy: (Math.random() - 0.5) * 0.35,
      r: Math.random() * 1.8 + 0.6,
      c: COLORS[Math.floor(Math.random() * COLORS.length)],
      tw: Math.random() * Math.PI * 2,
    }));
  }

  function frame() {
    ctx.clearRect(0, 0, width, height);
    const LINK = 130;
    for (const p of particles) {
      p.x += p.vx;
      p.y += p.vy;
      p.tw += 0.02;
      if (p.x < -20) p.x = width + 20;
      if (p.x > width + 20) p.x = -20;
      if (p.y < -20) p.y = height + 20;
      if (p.y > height + 20) p.y = -20;
      const alpha = 0.35 + 0.3 * Math.sin(p.tw);
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${p.c},${alpha})`;
      ctx.fill();
    }
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const a = particles[i], b = particles[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const d2 = dx * dx + dy * dy;
        if (d2 < LINK * LINK) {
          const alpha = (1 - Math.sqrt(d2) / LINK) * 0.16;
          ctx.strokeStyle = `rgba(0,229,255,${alpha})`;
          ctx.lineWidth = 0.7;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }
    requestAnimationFrame(frame);
  }

  resize();
  spawn();
  window.addEventListener("resize", () => { resize(); spawn(); });
  frame();
})();

/* ============ 标题打字机效果 ============ */
(function initTypewriter() {
  const el = document.querySelector(".subtitle");
  if (!el) return;
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

  const ratingRows = hasRating
    ? [5, 4, 3, 2, 1].map((star) => {
        const n = Number(rd[String(star)] || 0);
        const max = Math.max(1, ...Object.values(rd).map(Number));
        const pct = Math.round((n / max) * 100);
        return `<div class="dist-row"><span class="dist-label">${star}★</span><div class="dist-track"><div class="dist-fill f${star}" style="width:${pct}%"></div></div><span class="dist-val">${n}</span></div>`;
      }).join("")
    : "";

  const langTotal = Object.values(ld).reduce((a, b) => a + Number(b || 0), 0) || 1;
  const langRows = Object.entries(ld)
    .map(([k, v]) => {
      const n = Number(v || 0);
      const pct = Math.round((n / langTotal) * 100);
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
