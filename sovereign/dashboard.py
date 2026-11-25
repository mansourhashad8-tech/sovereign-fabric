"""A single self-contained dashboard. No build step, no CDN, no tracking."""

DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sovereign — measured, not claimed</title>
<style>
  :root {
    --bg: #070a0f; --panel: #0e151f; --panel2: #111b28; --line: #1d2a3a;
    --text: #e8eef8; --muted: #8fa1bb; --accent: #2ee6c5; --accent2: #6aa8ff;
    --green: #46df8b; --amber: #ffb86b; --red: #ff6b81; --mono: ui-monospace, SFMono-Regular, Menlo, monospace;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background:
      radial-gradient(1100px 500px at 15% -10%, #10283a 0%, transparent 60%),
      radial-gradient(900px 400px at 100% 0%, #1a1f3d 0%, transparent 55%), var(--bg);
    color: var(--text); font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    min-height: 100vh;
  }
  .wrap { max-width: 1180px; margin: 0 auto; padding: 28px 20px 60px; }
  header { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
  .brand { display: flex; align-items: center; gap: 12px; }
  .mark { width: 38px; height: 38px; border-radius: 11px; background: linear-gradient(135deg, var(--accent), var(--accent2)); box-shadow: 0 0 28px #2ee6c544; position: relative; }
  .mark::after { content: ""; position: absolute; inset: 9px; border: 2px solid #041018; border-radius: 6px; }
  h1 { font-size: 20px; margin: 0; letter-spacing: .14em; text-transform: uppercase; }
  .sub { color: var(--muted); font-size: 12.5px; letter-spacing: .04em; }
  .pill { display: inline-flex; align-items: center; gap: 8px; padding: 7px 12px; border: 1px solid var(--line); border-radius: 999px; background: #0b131d; color: var(--muted); font-size: 12.5px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
  .dot.ok { background: var(--green); box-shadow: 0 0 10px var(--green); }
  .dot.bad { background: var(--red); box-shadow: 0 0 10px var(--red); }
  .dot.warn { background: var(--amber); box-shadow: 0 0 10px var(--amber); }
  .verdict { margin-top: 22px; padding: 22px 24px; border: 1px solid var(--line); border-radius: 18px; background: linear-gradient(180deg, #101a26, #0b131d); display: flex; gap: 18px; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; }
  .verdict h2 { margin: 0 0 6px; font-size: 17px; font-weight: 600; }
  .verdict p { margin: 0; color: var(--muted); max-width: 760px; }
  .verdict .tag { font: 12px/1 var(--mono); letter-spacing: .1em; text-transform: uppercase; color: var(--accent); }
  .actions { display: flex; gap: 10px; flex-wrap: wrap; }
  button, a.btn { appearance: none; border: 1px solid #2a4a5e; background: #10222c; color: var(--text); padding: 10px 15px; border-radius: 10px; cursor: pointer; font: 600 13px/1 inherit; text-decoration: none; display: inline-flex; align-items: center; gap: 8px; }
  button:hover, a.btn:hover { border-color: var(--accent); color: var(--accent); }
  button:disabled { opacity: .55; cursor: progress; }
  .metrics { margin-top: 18px; display: grid; grid-template-columns: repeat(auto-fit, minmax(165px, 1fr)); gap: 12px; }
  .card { border: 1px solid var(--line); border-radius: 14px; background: var(--panel); padding: 15px 16px; }
  .card .k { color: var(--muted); font-size: 11.5px; letter-spacing: .08em; text-transform: uppercase; }
  .card .v { font: 700 24px/1.2 var(--mono); margin-top: 7px; }
  .card .n { color: var(--muted); font-size: 12px; margin-top: 5px; }
  .grid { margin-top: 16px; display: grid; grid-template-columns: 1.25fr .95fr; gap: 14px; }
  @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
  .panel { border: 1px solid var(--line); border-radius: 16px; background: var(--panel); padding: 18px; }
  .panel h3 { margin: 0 0 12px; font-size: 13px; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); font-weight: 600; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip { font: 12.5px/1 var(--mono); padding: 8px 10px; border-radius: 8px; background: #0b1721; border: 1px solid #1e3446; color: #cfe3f5; }
  .chip .arrow { color: var(--accent); margin-left: 8px; }
  .score { margin-top: 12px; }
  .score .row { display: flex; justify-content: space-between; font-size: 12.5px; color: var(--muted); margin-bottom: 5px; }
  .score .track { height: 7px; border-radius: 99px; background: #0a121b; border: 1px solid #182535; overflow: hidden; }
  .score .fill { height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent2)); }
  .src { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 0; border-bottom: 1px dashed #172333; font-size: 13px; }
  .src:last-child { border-bottom: 0; }
  .src .name { font-family: var(--mono); }
  .src .state { font-size: 11.5px; color: var(--muted); max-width: 58%; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .caps { display: flex; flex-wrap: wrap; gap: 7px; }
  .cap { font: 12px/1 var(--mono); padding: 7px 9px; border-radius: 7px; background: #0b1721; border: 1px solid #1e3446; }
  .cap.admitted { color: var(--accent); border-color: #1f5a52; }
  .cap.quarantined { color: var(--amber); border-color: #5a4720; }
  .limits { margin-top: 16px; color: var(--muted); font-size: 12.5px; }
  .limits li { margin: 4px 0; }
  .err { color: var(--red); }
  .spin { width: 14px; height: 14px; border: 2px solid #2a4a5e; border-top-color: var(--accent); border-radius: 50%; animation: s .8s linear infinite; display: inline-block; }
  @keyframes s { to { transform: rotate(360deg); } }
  footer { margin-top: 26px; display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; color: var(--muted); font-size: 12px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="brand">
      <div class="mark" aria-hidden="true"></div>
      <div>
        <h1>Sovereign</h1>
        <div class="sub">external guardianship · verified synthesis · measured execution</div>
      </div>
    </div>
    <div class="pill"><span id="statusDot" class="dot"></span><span id="statusText">connecting</span></div>
  </header>

  <section class="verdict">
    <div style="flex:1 1 520px">
      <div class="tag" id="verdictTag">verdict</div>
      <h2 id="verdictTitle">Running the full loop…</h2>
      <p id="verdictText">Consult, absorb, plan, execute, validate, benchmark, red-team, then audit its own prose.</p>
    </div>
    <div class="actions">
      <button id="runBtn" onclick="runReport()">Run full report</button>
      <a class="btn" href="/report" target="_blank" rel="noopener">JSON</a>
      <a class="btn" href="/report.md" target="_blank" rel="noopener">Markdown</a>
      <a class="btn" href="/docs" target="_blank" rel="noopener">API</a>
    </div>
  </section>

  <div class="metrics" id="metrics"></div>

  <div class="grid">
    <div class="panel">
      <h3>Cycle</h3>
      <div class="chips" id="plan"></div>
      <div id="scores"></div>
      <p class="limits" id="diagnosis"></p>
    </div>
    <div class="panel">
      <h3>Guardians</h3>
      <div id="sources"></div>
      <p class="limits" id="consult"></p>
    </div>
  </div>

  <div class="grid" style="margin-top:14px">
    <div class="panel">
      <h3>Continuous loop</h3>
      <div class="limits" id="loopStats">not running</div>
      <div class="actions" style="margin-top:12px">
        <button onclick="loopStart()">Start</button>
        <button onclick="loopStop()">Stop</button>
        <button onclick="loopTick()">Tick once</button>
      </div>
    </div>
    <div class="panel">
      <h3>Self-optimization</h3>
      <div class="limits" id="optStats">not run yet — benchmarks equivalent implementations and keeps the faster one</div>
      <div class="actions" style="margin-top:12px">
        <button onclick="optimizeNow()">Optimize hot paths</button>
      </div>
    </div>
  </div>

  <div class="panel" style="margin-top:14px">
    <h3>Self-model <span id="selfStamp" style="text-transform:none;letter-spacing:0;color:var(--muted);font-weight:400"></span></h3>
    <p id="selfVerdict" style="margin:0 0 12px"></p>
    <div class="caps" id="selfCan"></div>
    <div class="limits" id="selfProps"></div>
    <ul class="limits" id="selfLimits"></ul>
  </div>

  <div class="panel" style="margin-top:14px">
    <h3>Research brief</h3>
    <div class="caps" style="margin-bottom:10px">
      <input id="briefQuery" value="retrieval augmented generation"
             style="flex:1;min-width:260px;background:#0b1220;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font:inherit">
      <select id="briefLang"
              style="background:#0b1220;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font:inherit">
        <option value="en">English</option>
        <option value="ar">العربية</option>
      </select>
      <button onclick="runBrief()">Build brief</button>
    </div>
    <pre id="briefOut" class="limits" style="white-space:pre-wrap;max-height:360px;overflow:auto"></pre>
  </div>

  <div class="panel" style="margin-top:14px">
    <h3>Mastery <span id="masteryStamp" style="text-transform:none;letter-spacing:0;color:var(--muted);font-weight:400"></span></h3>
    <div class="caps" id="masteryTable"></div>
    <div style="margin-top:10px"><button onclick="practiceNow()">Practice weakest</button></div>
    <div class="limits" id="masteryOut"></div>
  </div>

  <div class="panel" style="margin-top:14px">
    <h3>Openness &amp; security <span id="securityStamp" style="text-transform:none;letter-spacing:0;color:var(--muted);font-weight:400"></span></h3>
    <div class="caps" id="securityCaps"></div>
    <div class="limits" id="securityOut"></div>
  </div>

  <div class="panel" style="margin-top:14px">
    <h3>Retrieval benchmark <span id="retrievalStamp" style="text-transform:none;letter-spacing:0;color:var(--muted);font-weight:400"></span></h3>
    <div class="actions" style="margin-bottom:10px"><button onclick="loadRetrieval()">Run benchmark</button></div>
    <div class="limits" id="retrievalOut">not run yet — 12 fixed queries across vector, BM25, and hybrid</div>
  </div>

  <div class="panel" style="margin-top:14px">
    <h3>Capabilities</h3>
    <div class="caps" id="caps"></div>
  </div>

  <div class="panel" style="margin-top:14px">
    <h3>Limits</h3>
    <ul class="limits" id="limits"></ul>
  </div>

  <footer>
    <span>Measured, not claimed. Every number above came from this process.</span>
    <span id="stamp"></span>
  </footer>
</div>

<script>
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = (v, d = 2) => Number(v).toFixed(d);

async function get(url) {
  const response = await fetch(url, { headers: { "Accept": "application/json" } });
  if (!response.ok) throw new Error(url + " -> " + response.status);
  return response.json();
}

function card(k, v, n, cls) {
  return `<div class="card"><div class="k">${esc(k)}</div><div class="v ${cls || ''}">${esc(v)}</div><div class="n">${esc(n || '')}</div></div>`;
}

function render(report) {
  const g = report.guardians, c = report.cycle, e = report.execution, r = report.redteam;
  const scores = Object.values(c.validation.scores);
  const minScore = scores.length ? Math.min(...scores) : 0;

  $('verdictTag').textContent = report.ok ? 'completed' : 'not completed';
  $('verdictTag').style.color = report.ok ? 'var(--green)' : 'var(--amber)';
  $('verdictTitle').textContent = report.ok ? 'All six criteria passed.' : 'The loop ran, but the criteria did not all pass.';
  $('verdictText').textContent = report.verdict;
  $('statusDot').className = 'dot ' + (report.ok ? 'ok' : 'warn');
  $('statusText').textContent = (report.ok ? 'healthy' : 'degraded') + ' · ' + num(report.duration_s) + 's';

  $('metrics').innerHTML = [
    card('Guardians', `${g.ok_sources}/${g.total_sources}`, `${g.units} units · ${num(g.cold_s)}s first`),
    card('Plan', c.plan.length, c.plan.join(' → ')),
    card('Validation', c.validation.passed ? 'PASS' : 'FAIL', `lowest score ${num(minScore)}`, c.validation.passed ? '' : 'err'),
    card('Measured speedup', `${e.speedup}×`, `${e.count} tasks · ${e.workers} workers`),
    card('Red-team', `${Math.round(r.coverage * 100)}%`, `${r.caught.length} overclaim patterns caught`),
    card('Self-audit', report.honesty.overclaims.length ? 'FLAGGED' : 'CLEAN', 'the report audits its own prose'),
  ].join('');

  $('plan').innerHTML = c.plan.length
    ? c.plan.map((step, i) => `<span class="chip">${esc(step)}${i < c.plan.length - 1 ? '<span class="arrow">→</span>' : ''}</span>`).join('')
    : '<span class="chip">no plan</span>';

  $('scores').innerHTML = Object.entries(c.validation.scores).map(([k, v]) => `
    <div class="score">
      <div class="row"><span>${esc(k.replaceAll('_', ' '))}</span><span>${num(v)}</span></div>
      <div class="track"><div class="fill" style="width:${Math.max(0, Math.min(100, v * 100))}%"></div></div>
    </div>`).join('');

  $('diagnosis').textContent = c.diagnosis && c.diagnosis.length ? 'Diagnosis: ' + c.diagnosis.join('; ') : '';
  if (c.validation.failures && c.validation.failures.length) {
    $('diagnosis').textContent += ' · Failures: ' + c.validation.failures.join(', ');
  }

  $('sources').innerHTML = Object.entries(g.sources).map(([name, state]) => {
    const cls = state === 'ok' ? 'ok' : (state === 'cooldown' || state === 'timeout') ? 'warn' : 'bad';
    return `<div class="src"><span class="name">${esc(name)}</span><span class="state"><span class="dot ${cls}"></span> ${esc(state)}</span></div>`;
  }).join('');
  $('consult').textContent = `First call ${num(g.cold_s)}s · second ${num(g.warm_s)}s · ${g.units} units absorbed`;

  $('limits').innerHTML = report.limits.map(x => `<li>${esc(x)}</li>`).join('');
  $('stamp').textContent = 'generated ' + new Date().toLocaleString();
}

async function runReport() {
  const button = $('runBtn');
  button.disabled = true;
  button.innerHTML = '<span class="spin"></span> Running';
  $('verdictTitle').textContent = 'Running the full loop…';
  try {
    const report = await get('/report?benchmark_n=150&budget_s=8');
    render(report);
  } catch (error) {
    $('verdictTitle').textContent = 'Report failed';
    $('verdictText').textContent = String(error);
    $('statusDot').className = 'dot bad';
    $('statusText').textContent = 'unreachable';
  } finally {
    button.disabled = false;
    button.textContent = 'Run full report';
  }
}

async function post(url) {
  const response = await fetch(url, { method: 'POST' });
  if (!response.ok) throw new Error(url + ' -> ' + response.status);
  return response.json();
}

function renderLoop(status) {
  const parts = [status.running ? 'running' : 'stopped', 'generation ' + status.generation];
  if (status.last) parts.push('last: ' + status.last.topic + ' · ' + status.last.units + ' units');
  const opt = status.last && status.last.optimization;
  if (opt && opt.chosen) {
    parts.push('optimized ' + opt.name + ' → ' + opt.chosen + ' (' + opt.speedup + 'x)');
    $('optStats').textContent = opt.name + ': ' + opt.chosen + ' ' + opt.speedup + 'x (from loop)';
  }
  if (status.last_error) parts.push('error: ' + status.last_error);
  $('loopStats').textContent = parts.join(' · ');
}

async function loopStart() { try { renderLoop(await post('/loop/start')); } catch (e) { $('loopStats').textContent = String(e); } }
async function loopStop() { try { renderLoop(await post('/loop/stop')); } catch (e) { $('loopStats').textContent = String(e); } }
async function loopTick() { try { renderLoop(await post('/loop/tick')); } catch (e) { $('loopStats').textContent = String(e); } }

function renderOpt(result) {
  if (result.results) {
    $('optStats').textContent = result.results
      .map(x => x.chosen ? x.name + ': ' + x.chosen + ' ' + x.speedup + 'x' : x.name + ': no gain')
      .join(' · ');
  } else {
    $('optStats').textContent = result.chosen
      ? result.name + ': ' + result.chosen + ' ' + result.speedup + 'x (v' + result.version + ')'
      : result.name + ': ' + result.reason;
  }
}

async function optimizeNow() {
  $('optStats').textContent = 'benchmarking equivalent implementations…';
  try { renderOpt(await post('/optimize?repeats=5')); } catch (e) { $('optStats').textContent = String(e); }
}

async function loadLoop() { try { renderLoop(await get('/loop/status')); } catch (e) {} }

setInterval(loadLoop, 5000);
loadLoop();

async function postJson(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {})
  });
  if (!response.ok) throw new Error(response.status + ' ' + await response.text());
  return response.json();
}

async function runBrief() {
  const query = $('briefQuery').value.trim();
  if (!query) return;
  $('briefOut').textContent = 'Consulting sources...';
  try {
    const brief = await postJson('/brief', { query, limit: 5, lang: $('briefLang').value });
    $('briefOut').textContent = brief.markdown;
  } catch (e) {
    $('briefOut').textContent = String(e);
  }
}

async function loadMastery() {
  try {
    const model = await get('/mastery');
    const rows = Object.entries(model.table);
    $('masteryTable').innerHTML = rows.length
      ? rows.map(([goal, row]) =>
          `<span class="cap ${row.rate >= 1 ? 'admitted' : (row.rate > 0 ? '' : 'quarantined')}">${esc(goal)} · ${row.passed}/${row.attempts}</span>`
        ).join('')
      : '<span class="limits">no cycles recorded yet</span>';
    $('masteryStamp').textContent = '· weakest: ' + model.weakest;
  } catch (e) {}
}

async function practiceNow() {
  $('masteryOut').textContent = 'Practising the weakest goal...';
  try {
    const result = await postJson('/mastery/practice?iterations=1&budget_s=8', {});
    const run = result.runs[0] || {};
    $('masteryOut').textContent =
      `practised ${run.goal} · ok=${run.ok} · ${(run.plan || []).join(' → ')}`;
    await loadMastery();
    await loadSelf();
  } catch (e) {
    $('masteryOut').textContent = String(e);
  }
}

loadMastery();
setInterval(loadMastery, 20000);

async function loadSecurity() {
  try {
    const report = await get('/security/audit?online=false');
    const counts = report.finding_counts || {};
    const high = (counts.critical || 0) + (counts.high || 0);
    $('securityCaps').innerHTML = [
      `<span class="cap ${report.openness_passed ? 'admitted' : 'quarantined'}">openness ${report.openness_passed ? 'PASS' : 'REVIEW'}</span>`,
      `<span class="cap ${high ? 'quarantined' : 'admitted'}">${high} high · ${counts.medium || 0} med · ${counts.low || 0} low</span>`,
      `<span class="cap">${report.dependencies.length} deps</span>`,
      `<span class="cap ${report.unknown_licenses.length ? 'quarantined' : 'admitted'}">unknown licences ${report.unknown_licenses.length}</span>`,
      `<span class="cap">${report.source_files.length} files hashed</span>`
    ].join('');
    const osv = report.vulnerability_check || {};
    $('securityOut').textContent =
      `OSV: ${osv.ok ? (osv.vulnerabilities || []).length + ' known' : 'offline (CLI audit is online)'} · ` +
      `report /security/report · SBOM /security/sbom`;
    $('securityStamp').textContent = '· ' + new Date(report.generated_at).toLocaleTimeString();
  } catch (e) {}
}

loadSecurity();
setInterval(loadSecurity, 60000);

async function loadSelf() {
  try {
    const model = await get('/self');
    $('selfVerdict').textContent = model.verdict;
    $('selfCan').innerHTML = Object.values(model.can).map(c =>
      `<span class="cap ${c.possible ? 'admitted' : 'quarantined'}">${c.possible ? '✓' : '×'} ${esc(c.goal)}${c.plan.length ? ' · ' + esc(c.plan.join(' → ')) : ''}</span>`
    ).join('');
    const calibration = model.calibration;
    $('selfProps').textContent = (model.properties
      ? `Property checks: ${model.properties.checks - model.properties.failed}/${model.properties.checks} passed.`
      : '') + (calibration
      ? ` Calibration: Brier ${num(calibration.brier, 3)} vs 0.25 baseline, skill ${num(calibration.skill, 3)} over ${calibration.cycles} cycles.`
      : '');
    $('selfLimits').innerHTML = model.limits.map(x => `<li>${esc(x)}</li>`).join('');
    $('selfStamp').textContent = '· ' + new Date(model.generated_at).toLocaleTimeString();
  } catch (e) {}
}

setInterval(loadSelf, 15000);
loadSelf();

async function loadRetrieval() {
  $('retrievalOut').textContent = 'running the fixed benchmark…';
  try {
    const b = await get('/ranking/benchmark');
    const chips = Object.entries(b.modes).map(([mode, row]) =>
      `<span class="cap ${mode === b.best_mode ? 'admitted' : ''}">${esc(mode)} · nDCG ${num(row.ndcg, 3)} · MRR ${num(row.mrr, 3)}</span>`
    ).join('');
    $('retrievalOut').innerHTML = chips +
      `<div style="margin-top:8px">best: <strong>${esc(b.best_mode)}</strong> · ${b.queries} queries · k=${b.k}</div>`;
    $('retrievalStamp').textContent = '· ' + new Date().toLocaleTimeString();
  } catch (e) {
    $('retrievalOut').textContent = String(e);
  }
}

loadRetrieval();

async function loadBase() {
  try {
    const health = await get('/health');
    $('statusDot').className = 'dot ok';
    $('statusText').textContent = health.status + ' · v' + (health.version || '?');
    const caps = await get('/capabilities');
    $('caps').innerHTML = caps.capabilities.map(c =>
      `<span class="cap ${esc(c.status)}" title="${esc(c.description || '')}">${esc(c.name)}</span>`
    ).join('');
  } catch (error) {
    $('statusText').textContent = 'health check failed';
  }
}

loadBase();
runReport();
</script>
</body>
</html>
"""
