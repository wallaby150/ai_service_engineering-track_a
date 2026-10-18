// 목 UI: 서버(/api)를 부르고 그린다. 숫자를 계산하지 않는다 — 표기만 바꾼다.
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, body) {
  const res = await fetch(`/api${path}`, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : "요청이 계약에 맞지 않습니다";
    throw new Error(`${detail}${data.request_id ? ` (요청 ${data.request_id})` : ""}`);
  }
  return data;
}

// ── 표기 ─────────────────────────────────────────────
function pct(p) {
  if (p === null || p === undefined) return "통계 없음";
  const v = p * 100;
  if (v >= 10) return `${v.toFixed(1)}%`;
  if (v >= 0.1) return `${v.toFixed(2)}%`;
  return `${v.toPrecision(2)}%`;
}
function oneIn(n) {
  if (!n) return "—";
  if (n < 1.05) return "거의 확실";
  return `약 ${Math.round(n).toLocaleString("ko-KR")}분의 1`;
}
// 표기만 바꾼다(값은 서버가 낸 것): 24,291,700 → "약 2,429만"
function man(n) {
  if (n == null) return "—";
  if (n < 10000) return `약 ${Math.round(n).toLocaleString("ko-KR")}`;
  return `약 ${Math.round(n / 10000).toLocaleString("ko-KR")}만`;
}

function pace(c) {
  if (!c.births_per_year) return "";
  const speed = c.births_per_minute >= 1
    ? `1분에 약 ${c.births_per_minute.toFixed(1)}명`
    : `약 ${c.minutes_per_birth.toFixed(1)}분에 1명`;
  return `<p class="pace">${esc(c.name_ko)}에서는 한 해 ${man(c.births_per_year)} 명, ${speed}이 태어납니다.</p>`;
}

// 위치 한 줄 — 무엇을 요약할지는 서버(core/position.py)가 골랐다. 여기서는 비율을 표기만 한다
function position(h) {
  if (!h) return "";
  const p = (x) => `${(x * 100).toFixed(1)}%`;
  const year = h.year ? ` <span class="badge">${esc(h.year)}</span>` : "";
  const cover = (x) => `통계가 있는 나라의 출생아 ${p(x)}`;
  if (h.node === "survival") {
    // 생존은 '유리·불리'로 나누지 않는다. 같은 일을 겪는 아이의 비율, 살아남았다면 맞지 못한 아이의 비율만
    const died = h.value !== "survived_5";
    const c = died ? h.country.same : h.country.below;
    const w = h.world ? (died ? h.world.same : h.world.below) : null;
    const what = died ? "같은 일을 겪는 아이" : "다섯 살을 맞지 못하는 아이";
    return `<p class="position"><b>${esc(h.node_label)} — ${esc(h.value_label)}</b>${year}<br>
      이 나라에서 태어나는 같은 성별 아이 중 ${what}: ${p(c)}${w !== null ? `<br>세계(${cover(h.world_coverage)}): ${p(w)}` : ""}</p>`;
  }
  const world = h.world
    ? `<br>세계(${cover(h.world_coverage)}): 더 낮은 구간 ${p(h.world.below)} · 같은 구간 ${p(h.world.same)} · 더 높은 구간 ${p(h.world.above)}` : "";
  return `<p class="position"><b>${esc(h.node_label)} — ${esc(h.value_label)}</b>${year}<br>
    이 나라에서 태어나는 아이 중 더 낮은 구간 ${p(h.country.below)} · 같은 구간 ${p(h.country.same)} · 더 높은 구간 ${p(h.country.above)}${world}</p>`;
}

// 두 나라 값을 나란히 놓기만 한다. 차이·배율은 계산하지 않는다(숫자는 서버의 core가 낸다)
function compare(life) {
  const home = $("home-country").value;
  const a = profiles[life.country.iso3], b = profiles[home];
  if (!home || !a || !b || home === life.country.iso3) return "";
  const sex = life.steps[1].value, sexLabel = life.steps[1].value_label;
  const v = (x, unit = "") => (x === null || x === undefined ? "통계 없음" : `${x}${unit}`);
  const yr = (y) => (y ? `<span class="yr">${esc(String(y))}년</span>` : "");
  const rows = [
    [`다섯 살을 맞지 못하는 ${sexLabel}아이 (1,000명당)`, (p) => v(p.by_sex[sex].u5mr_per_1000, "명") + yr(p.survival_year)],
    [`${sexLabel === "남자" ? "남성" : "여성"} 기대수명`, (p) => v(p.by_sex[sex].life_expectancy, "세") + yr(p.life_expectancy_year)],
    ["하루 $3.00 미만(극빈) 인구 비율", (p) => v(p.pct_below_3_00, "%") + yr(p.economy_year)],
    ["하루 $8.30 미만 인구 비율", (p) => v(p.pct_below_8_30, "%") + yr(p.economy_year)],
    ["세계 출생아 중 비중", (p) => v(p.share_of_world_births_pct, "%")],
  ];
  const body = rows.map(([k, f]) => `<tr><td>${esc(k)}</td><td>${f(a)}</td><td>${f(b)}</td></tr>`).join("");
  return `<table class="compare"><caption>내가 실제로 태어난 나라와 나란히</caption>
    <thead><tr><th></th><th>${esc(a.name_ko)}</th><th>${esc(b.name_ko)} (내 나라)</th></tr></thead><tbody>${body}</tbody></table>`;
}

function peers(list) {
  if (!list || !list.length) return "";
  const items = list.map((x) => `<li><b>${esc(x.country_name)}</b> · ${x.summary.map(esc).join(" · ")}
    <a href="?seed=${x.seed}">이 사람으로 보기</a></li>`).join("");
  return `<div class="peers"><h3>같은 순간 세계에서 태어난 다른 ${list.length}명</h3><ul>${items}</ul></div>`;
}

const times = (n) => (n == null ? "—" : `${n.toLocaleString("ko-KR")}번`);

function setStatus(id, text, isError = false) {
  const el = $(id);
  el.textContent = text;
  el.classList.toggle("error", isError);
}

// ── 초기화 ───────────────────────────────────────────
let live = false; // 서버에 AI 서사가 붙어 있는가 (/api/config)
let lastLife = null; // 마지막 '다시 태어나기' 결과 — 내 나라를 바꾸면 이걸 다시 그린다
let profiles = {}; // 나라별 비교 지표 — 전부 한 번 받아 두고 '내 나라'는 브라우저 안에서 고른다

// '내 실제 나라'는 이 브라우저에만 둔다. 저장소를 못 쓰는 환경(사생활 보호 창 등)에서도 화면은 돈다
const HOME_KEY = "reborn.home-country";
function loadHome() { try { return localStorage.getItem(HOME_KEY) || ""; } catch (e) { return ""; } }
function saveHome(v) { try { v ? localStorage.setItem(HOME_KEY, v) : localStorage.removeItem(HOME_KEY); } catch (e) { /* 저장 못 해도 이번 화면에선 쓴다 */ } }

async function init() {
  try {
    const [config, meta] = await Promise.all([api("/config"), api("/meta")]);
    live = config.mode === "live";
    $("banner").textContent = config.mode === "offline"
      ? `v${config.version} · AI 없이 동작 중 — 확률은 코드가 계산하고, 이야기는 템플릿이 씁니다.`
      : `v${config.version} · AI 서사 사용 중 (${config.narrator})`;
    const opts = meta.countries.map((c) => `<option value="${c.iso3}">${esc(c.name_ko)}</option>`).join("");
    $("reborn-country").insertAdjacentHTML("beforeend", opts);
    $("home-country").insertAdjacentHTML("beforeend", opts);
    $("home-country").value = loadHome();
    api("/profiles").then((r) => { profiles = Object.fromEntries(r.profiles.map((x) => [x.iso3, x])); })
      .catch(() => { /* 비교표만 빠진다 */ });
    $("odds-country").insertAdjacentHTML("beforeend", opts);
    const korean = ["province", "employment", "occupation"].filter((n) => meta.nodes[n]);
    $("odds-korea").hidden = korean.length === 0;  // 한국 상세 데이터가 있을 때만
    for (const node of ["sex", "survival", "economy", ...korean]) {
      $(`odds-${node}`).insertAdjacentHTML("beforeend",
        meta.nodes[node].values.map((v) => `<option value="${v.value}">${esc(v.label)}</option>`).join(""));
    }
    const q = new URLSearchParams(location.search);
    if (q.get("country")) $("reborn-country").value = q.get("country");
    if (q.get("seed")) { $("reborn-seed").value = q.get("seed"); reborn(); }
  } catch (e) {
    $("banner").textContent = `서버에 연결하지 못했습니다: ${e.message}`;
  }
}

// ── 다시 태어나기 ─────────────────────────────────────
// 칸마다 근거 한 줄: 출처 · 기준 연도 배지 · 추정 배지 · 통계 없음 배지 · 가정(접어 둔 설명)
function badges(s) {
  const out = [];
  if (s.value === null) out.push(`<span class="badge none">통계 없음</span>`);
  else if (s.year) out.push(`<span class="badge">${esc(s.year)}</span>`);
  if (s.assumed) out.push(`<span class="badge est" title="통계가 없어 정해 둔 값을 썼습니다">추정</span>`);
  return out.join("");
}

function evidence(s) {
  const why = s.assumption
    ? `<details class="why"><summary>가정</summary>${esc(s.assumption)}</details>` : "";
  return `<span class="src">${badges(s)} ${esc(s.source)}${why}</span>`;
}

function renderLife(life, fixedCountry) {
  const steps = life.steps.map((s) => `
    <li><span class="k">${esc(s.node_label)}</span>
        <span class="v">${esc(s.value_label ?? "통계 없음")}</span>
        <span class="p">${pct(s.p)}${s.one_in ? `<span class="oi">${s.one_in.toLocaleString("ko-KR")}명 중 1명</span>` : ""}</span>
        ${evidence(s)}</li>`).join("");
  const share = `${location.origin}${location.pathname}?seed=${life.seed}${fixedCountry ? `&country=${life.country.iso3}` : ""}`;
  return `
    <div class="big">${esc(life.country.name_ko)}${place(life)}에서 ${esc(life.steps[1].value_label)}아이로 태어났습니다</div>
    ${pace(life.country)}
    ${position(life.headline)}
    <ul class="chain">${steps}</ul>
    ${compare(life)}
    ${peers(life.same_moment)}
    <p>이 조합이 그대로 나올 확률은 <b>${oneIn(life.one_in)}</b>입니다${life.complete ? "" : " (통계가 없는 칸은 빼고 계산)"}.</p>
    <div class="story" data-seed="${life.seed}" data-country="${fixedCountry ? life.country.iso3 : ""}">
      ${renderStory(life.narrative)}
    </div>
    <p class="share">같은 인생 다시 보기: <a href="${esc(share)}">${esc(share)}</a></p>`;
}

function place(life) {
  const p = life.steps.find((s) => s.node === "province");
  return p && p.value_label ? ` ${esc(p.value_label)}` : "";
}

function renderStory(n) {
  const button = live && n.narrator === "scripted" && !n.note
    ? `<p class="ai-slot"><button class="secondary story-ai">AI 해석 보기</button></p>` : "";
  return `
    <h3>${esc(n.title)} <span class="tag">템플릿 서사</span></h3>
    ${n.paragraphs.map((p) => `<p>${esc(p)}</p>`).join("")}
    ${n.note ? `<p class="note">${esc(n.note)}</p>` : ""}
    ${button}`;
}

// AI 해석은 버튼을 눌렀을 때만 부른다 — 비용과 지연은 원할 때만. 템플릿 글은 그대로 두고 아래에 덧붙인다
async function writeStory(box) {
  const slot = box.querySelector(".ai-slot");
  const btn = slot.querySelector(".story-ai");
  btn.disabled = true;
  btn.textContent = "AI가 통계를 조회하고 해석하는 중… (몇 초)";
  try {
    const r = await api("/story", { seed: Number(box.dataset.seed), country: box.dataset.country || null });
    const n = r.narrative;
    if (n.narrator !== "llm") {  // 해석을 못 만들었다 — 템플릿은 그대로, 사유만 알린다
      slot.outerHTML = `<p class="note">${esc(n.note || "AI 해석을 만들지 못했습니다.")}</p>`;
      return;
    }
    const calls = `<p class="share">조회 ${r.plan.map((p) => esc(p.tool + (p.metric ? `(${p.metric})` : ""))).join(", ")}`
      + ` · 작성 ${r.attempts}회 · 모델 호출 ${r.llm_calls.length}번 · $${r.cost_usd.toFixed(4)}</p>`;
    slot.outerHTML = `<div class="ai-note">
      <h3>${esc(n.title)} <span class="tag">AI 해석</span></h3>
      ${n.paragraphs.map((p) => `<p>${esc(p)}</p>`).join("")}
      <p class="share">화면에 없는 비교만 덧붙였습니다. 숫자는 코드가 근거와 대조했습니다.</p>${calls}</div>`;
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "AI 해석 보기";
    slot.insertAdjacentHTML("beforeend", `<span class="note"> ${esc(e.message)}</span>`);
  }
}

document.addEventListener("click", (ev) => {
  const btn = ev.target.closest(".story-ai");
  if (btn) writeStory(btn.closest(".story"));
});

async function reborn() {
  const btn = $("reborn-go");
  const seedText = $("reborn-seed").value.trim();
  const body = { country: $("reborn-country").value || null, seed: seedText === "" ? null : Number(seedText) };
  btn.disabled = true;
  setStatus("reborn-status", "다시 태어나는 중…");
  try {
    const life = await api("/simulate", body);
    lastLife = { life, fixed: body.country };
    $("reborn-result").innerHTML = renderLife(life, body.country);
    $("reborn-result").hidden = false;
    setStatus("reborn-status", `시드 ${life.seed}`);
  } catch (e) {
    setStatus("reborn-status", e.message, true);
  } finally {
    btn.disabled = false;
  }
}

// ── 이렇게 태어날 확률 ────────────────────────────────
function target() {
  const t = {};
  for (const k of ["country", "sex", "survival", "economy", "province", "employment", "occupation"]) {
    const v = $(`odds-${k}`).value;
    if (v) t[k] = v;
  }
  return t;
}

function renderOdds(o) {
  if (o.p === null) return `<p class="note">${esc(o.reason || "계산할 수 없습니다")}</p>`;
  const cover = o.coverage < 0.999 ? `<p class="share">통계가 있는 나라의 출생아(${pct(o.coverage)})만으로 계산했습니다.</p>` : "";
  const steps = o.steps.length
    ? `<p class="share">${o.steps.map((s) => `${esc(s.node_label)} ${esc(s.value_label)} ${pct(s.p)}`).join(" × ")}</p>
       <ul class="chain compact">${o.steps.map((s) => `<li><span class="k">${esc(s.node_label)}</span>${evidence(s)}</li>`).join("")}</ul>`
    : "";
  return `
    <div class="big">${oneIn(o.one_in)}</div>
    <div class="stats">
      <div class="stat"><div class="n">${pct(o.p)}</div><div class="d">정확한 확률</div></div>
      <div class="stat"><div class="n">${times(o.expected_tries && Math.round(o.expected_tries))}</div><div class="d">평균적으로 필요한 다시 태어나기</div></div>
      <div class="stat"><div class="n">${times(o.tries_50)}</div><div class="d">50% 확률로 한 번은 나오는 횟수</div></div>
      <div class="stat"><div class="n">${times(o.tries_90)}</div><div class="d">90% 확률로 한 번은 나오는 횟수</div></div>
    </div>
    ${steps}${cover}
    <p><button class="secondary" id="odds-until">될 때까지 다시 태어나기</button></p>
    <div id="until-result"></div>`;
}

async function odds() {
  const btn = $("odds-go");
  btn.disabled = true;
  setStatus("odds-status", "계산하는 중…");
  try {
    const o = await api("/odds", target());
    $("odds-result").innerHTML = renderOdds(o);
    $("odds-result").hidden = false;
    const until = $("odds-until");
    if (until) until.addEventListener("click", tryUntil);
    setStatus("odds-status", "");
  } catch (e) {
    setStatus("odds-status", e.message, true);
  } finally {
    btn.disabled = false;
  }
}

async function tryUntil() {
  const btn = $("odds-until");
  btn.disabled = true;
  setStatus("odds-status", "조건이 나올 때까지 다시 태어나는 중… (최대 10만 번)");
  try {
    const r = await api("/until", { target: target() });
    $("until-result").innerHTML = r.found
      ? `<p><b>${times(r.tries)}</b> 만에 태어났습니다.</p>${renderLife(r.life, null)}`
      : `<p class="note">${times(r.max_tries)} 다시 태어나도 나오지 않았습니다. 평균적으로 ${times(r.odds.expected_tries && Math.round(r.odds.expected_tries))}이 필요합니다.</p>`;
    setStatus("odds-status", "");
  } catch (e) {
    setStatus("odds-status", e.message, true);
  } finally {
    btn.disabled = false;
  }
}

$("reborn-go").addEventListener("click", reborn);
$("home-country").addEventListener("change", (ev) => {
  saveHome(ev.target.value);
  if (lastLife) $("reborn-result").innerHTML = renderLife(lastLife.life, lastLife.fixed);  // 같은 인생, 비교표만 바뀐다
});
$("odds-go").addEventListener("click", odds);
init();
