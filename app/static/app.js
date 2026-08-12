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
    .map((e) => `<li class="${esc(e.status)}"><strong>${esc(e.stage)}</strong> · ${esc(e.status)}：${esc(e.detail)}</li>`)
    .join("");
}

async function loadResults(summary) {
  $("result-card").classList.remove("hidden");
  $("summary-data") || null;
  window.__summary = summary;
  renderTab("summary");
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
  const c = s.counts;
  const cards = [
    ["评论", c.reviews], ["主题", c.topics], ["发现", c.findings],
    ["需求", c.requirements], ["测试用例", c.test_cases],
  ].map(([lbl, num]) => `<div><div class="num">${num}</div><div class="lbl">${lbl}</div></div>`).join("");
  const trace = s.traceability;
  return `
    <div class="summary-grid">${cards}</div>
    <h3>范围</h3><p>${esc(JSON.stringify(s.scope || {}))}</p>
    <h3>说明</h3><ul>${(s.notes || []).map((n) => `<li>${esc(n)}</li>`).join("")}</ul>
    <h3>追溯校验</h3>
    <p>${trace.passed_checks}/${trace.total_checks} 通过 · 模型驱动：${s.model_driven}</p>
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
