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
const times = (n) => (n == null ? "—" : `${n.toLocaleString("ko-KR")}번`);

function setStatus(id, text, isError = false) {
  const el = $(id);
  el.textContent = text;
  el.classList.toggle("error", isError);
}

// ── 초기화 ───────────────────────────────────────────
async function init() {
  try {
    const [config, meta] = await Promise.all([api("/config"), api("/meta")]);
    $("banner").textContent = config.mode === "offline"
      ? `v${config.version} · AI 없이 동작 중 — 확률은 코드가 계산하고, 이야기는 템플릿이 씁니다.`
      : `v${config.version} · AI 서사 사용 중 (${config.narrator})`;
    const opts = meta.countries.map((c) => `<option value="${c.iso3}">${esc(c.name_ko)}</option>`).join("");
    $("reborn-country").insertAdjacentHTML("beforeend", opts);
    $("odds-country").insertAdjacentHTML("beforeend", opts);
    for (const node of ["sex", "survival", "economy"]) {
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
function renderLife(life, fixedCountry) {
  const steps = life.steps.map((s) => `
    <li><span class="k">${esc(s.node_label)}</span>
        <span class="v">${esc(s.value_label ?? "통계 없음")}</span>
        <span class="p">${pct(s.p)}</span>
        <span class="src">${esc(s.source)}${s.assumed ? " · 가정값 사용" : ""}</span></li>`).join("");
  const n = life.narrative;
  const tag = n.narrator === "scripted" ? "템플릿 서사" : "AI 서사";
  const share = `${location.origin}${location.pathname}?seed=${life.seed}${fixedCountry ? `&country=${life.country.iso3}` : ""}`;
  return `
    <div class="big">${esc(life.country.name_ko)}에서 ${esc(life.steps[1].value_label)}아이로 태어났습니다</div>
    <ul class="chain">${steps}</ul>
    <p>이 조합으로 태어날 확률은 <b>${oneIn(life.one_in)}</b>입니다${life.complete ? "" : " (통계가 없는 칸은 빼고 계산)"}.</p>
    <div class="story">
      <h3>${esc(n.title)} <span class="tag">${tag}</span></h3>
      ${n.paragraphs.map((p) => `<p>${esc(p)}</p>`).join("")}
      ${n.note ? `<p class="note">${esc(n.note)}</p>` : ""}
    </div>
    <p class="share">같은 인생 다시 보기: <a href="${esc(share)}">${esc(share)}</a></p>`;
}

async function reborn() {
  const btn = $("reborn-go");
  const seedText = $("reborn-seed").value.trim();
  const body = { country: $("reborn-country").value || null, seed: seedText === "" ? null : Number(seedText) };
  btn.disabled = true;
  setStatus("reborn-status", "다시 태어나는 중…");
  try {
    const life = await api("/simulate", body);
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
  for (const k of ["country", "sex", "survival", "economy"]) {
    const v = $(`odds-${k}`).value;
    if (v) t[k] = v;
  }
  return t;
}

function renderOdds(o) {
  if (o.p === null) return `<p class="note">${esc(o.reason || "계산할 수 없습니다")}</p>`;
  const cover = o.coverage < 0.999 ? `<p class="share">통계가 있는 나라의 출생아(${pct(o.coverage)})만으로 계산했습니다.</p>` : "";
  const steps = o.steps.length
    ? `<p class="share">${o.steps.map((s) => `${esc(s.node_label)} ${esc(s.value_label)} ${pct(s.p)}`).join(" × ")}</p>` : "";
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
$("odds-go").addEventListener("click", odds);
init();
