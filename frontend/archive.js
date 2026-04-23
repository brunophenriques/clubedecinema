/* =============================================
   Clube de Cinema — archive.js
   ============================================= */

const API = "";

const apiLabel = document.getElementById("apiLabel");
if (apiLabel) apiLabel.textContent = API || "(mesmo servidor)";

function el(id) { return document.getElementById(id); }

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  }[c]));
}

/* ── Toast ── */
const ICONS = { success: "✓", error: "✕", info: "·" };
function ensureToastRoot() {
  let root = document.getElementById("toastRoot");
  if (!root) { root = document.createElement("div"); root.id = "toastRoot"; document.body.appendChild(root); }
  return root;
}
function toast(message, type = "info", ms = 3400) {
  const root = ensureToastRoot();
  const t = document.createElement("div");
  t.className = `toast toast--${type}`;
  t.innerHTML = `<div class="toast__icon">${ICONS[type]||"·"}</div><div class="toast__msg">${escapeHtml(message)}</div><button class="toast__x">✕</button>`;
  root.appendChild(t);
  const kill = () => { t.classList.add("toast--out"); setTimeout(() => t.remove(), 200); };
  t.querySelector(".toast__x").addEventListener("click", kill);
  setTimeout(kill, ms);
}

/* ── Auth helpers ── */
function getToken() { return localStorage.getItem("cinema_club_token"); }

async function refreshNavAdmin() {
  const navAdmin = document.getElementById("navAdmin");
  if (!navAdmin) return;
  navAdmin.style.display = "none";
  const token = getToken();
  if (!token) return;
  try {
    const res = await fetch(`${API}/auth/me`, { headers: { "Authorization": `Bearer ${token}` } });
    if (!res.ok) return;
    const me = await res.json();
    if (me?.is_admin) navAdmin.style.display = "";
  } catch {}
}

/* ── API ── */
async function apiGet(path) {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/* ── Data helpers ── */
function posterHTML(f) {
  if (f?.poster_url) {
    return `<div class="poster"><img src="${escapeHtml(f.poster_url)}" alt="${escapeHtml(f.title||"")}" loading="lazy"/></div>`;
  }
  const initials = (f?.title || "").split(" ").slice(0,2).map(s => (s[0]||"").toUpperCase()).join("") || "🎬";
  return `<div class="poster placeholder"><span>${escapeHtml(initials)}</span></div>`;
}

function hofPosterBlock(url, title) {
  if (url) return `<div class="hof-poster"><img src="${escapeHtml(url)}" alt="${escapeHtml(title||"")}" loading="lazy"/></div>`;
  const initials = (title || "").split(" ").slice(0,2).map(s => (s[0]||"").toUpperCase()).join("") || "🎬";
  return `<div class="hof-poster hof-poster--ph"><span>${escapeHtml(initials)}</span></div>`;
}

function totalVotes(w) {
  return (w?.films || []).reduce((acc, f) => acc + Number(f?.votes || 0), 0);
}

function winnerFilm(w) {
  if (!w?.winner_film_id) return null;
  return (w?.films || []).find(f => Number(f.id) === Number(w.winner_film_id)) || null;
}

function winnerVotes(w) {
  const win = winnerFilm(w);
  return win ? Number(win.votes || 0) : -1;
}

function sortFilmsInWeek(w) {
  return [...(w?.films || [])].sort((a, b) =>
    (Number(b?.votes||0) - Number(a?.votes||0)) ||
    String(a?.title||"").localeCompare(String(b?.title||""), "pt", { sensitivity:"base" })
  );
}

function sortWeeks(weeks, mode) {
  const out = [...weeks];
  out.sort((a, b) => {
    if (mode === "smart") return (Number(!!b.is_open) - Number(!!a.is_open)) || (Number(b.id) - Number(a.id));
    if (mode === "new") return Number(b.id) - Number(a.id);
    if (mode === "old") return Number(a.id) - Number(b.id);
    if (mode === "votes") return totalVotes(b) - totalVotes(a) || (Number(b.id) - Number(a.id));
    if (mode === "winnerVotes") return winnerVotes(b) - winnerVotes(a) || (Number(b.id) - Number(a.id));
    if (mode === "az") return String(a.title||"").localeCompare(String(b.title||""), "pt", { sensitivity:"base" });
    return Number(b.id) - Number(a.id);
  });
  return out;
}

function filterWeeks(weeks, q, onlyClosed) {
  let out = [...weeks];
  if (onlyClosed) out = out.filter(w => !w.is_open);
  const qq = (q || "").trim().toLowerCase();
  if (!qq) return out;
  return out.filter(w => {
    const win = winnerFilm(w);
    const blob = [
      `#${w.id}`, w.id, w.title,
      w.is_open ? "aberta" : "fechada",
      win?.title, win?.director, win?.year,
      ...(w.films||[]).flatMap(f => [f.title, f.director, f.year, f.votes])
    ].join(" ").toLowerCase();
    return blob.includes(qq);
  });
}

/* ── View state ── */
let weeksCache = [];
let view = "archive";

function setView(next) {
  view = next;
  el("viewArchive").classList.toggle("is-active", view === "archive");
  el("viewHof").classList.toggle("is-active", view === "hof");
  el("weeks").style.display = view === "archive" ? "" : "none";
  el("hof").style.display   = view === "hof" ? "" : "none";
  apply();
}

/* ── Archive card ── */
function renderArchiveCard(w) {
  const div = document.createElement("div");
  div.className = "archive-week fade-in";

  const films = sortFilmsInWeek(w);
  const win = winnerFilm(w);
  const badgeClass = w.is_open ? "badge--open" : "badge--closed";
  const stateText = w.is_open ? "Aberta" : "Fechada";
  const weekDisplayId = Math.max(1, Number(w.id) - 6);
  const meta = [`#${weekDisplayId}`, w.is_ready ? "voting ON" : "voting OFF", `${totalVotes(w)} voto(s)`].join(" · ");

  const filmRows = films.map(f => `
    <div class="archive-film">
      ${posterHTML(f)}
      <div class="archive-film-body">
        <div class="archive-film-title">${escapeHtml(f.title||"—")}${f.year ? ` <span class="muted small">(${escapeHtml(String(f.year))})</span>` : ""}</div>
        <div class="muted small">${f.director ? `Dir. ${escapeHtml(f.director)} · ` : ""}${Number(f.votes||0)} voto(s)</div>
      </div>
      <div class="archive-film-votes">${Number(f.votes||0)}</div>
    </div>
  `).join("");

  div.innerHTML = `
    <div class="archive-week-head">
      <div>
        <div class="archive-week-title">${escapeHtml(w.title || `Semana #${w.id}`)}</div>
        <div class="muted small" style="margin-top:4px">${escapeHtml(meta)}</div>
      </div>
      <span class="badge ${badgeClass}">${stateText}</span>
    </div>

    ${(!w.is_open && win) ? `
      <div class="archive-winner">
        <div class="muted small" style="margin-bottom:8px; font-weight:600">🏆 Vencedor</div>
        <div class="archive-film" style="margin:0; background:transparent; border:none; padding:0">
          ${posterHTML(win)}
          <div class="archive-film-body">
            <div class="archive-film-title">${escapeHtml(win.title||"—")}${win.year ? ` <span class="muted small">(${escapeHtml(String(win.year))})</span>` : ""}</div>
            <div class="muted small">${win.director ? `Dir. ${escapeHtml(win.director)} · ` : ""}${Number(win.votes||0)} voto(s)</div>
          </div>
        </div>
      </div>
    ` : ""}

    <details class="details" style="margin-top:12px">
      <summary>Ver todos os filmes (${films.length})</summary>
      <div class="archive-films">${filmRows || `<div class="muted small" style="padding:8px 0">—</div>`}</div>
    </details>
  `;

  return div;
}

/* ── HOF card ── */
function renderHofCard(w) {
  const win = winnerFilm(w);
  const div = document.createElement("button");
  div.type = "button";
  div.className = "hof-card";

  const stateClass = w.is_open ? "badge--open" : "badge--closed";
  const stateText  = w.is_open ? "Aberta" : "Fechada";

  div.innerHTML = `
    <div class="hof-card__top">
      <div class="hof-card__week">${escapeHtml(w.title || `Semana #${w.id}`)}</div>
      <span class="badge ${stateClass}">${stateText}</span>
    </div>
    ${hofPosterBlock(win?.poster_url, win?.title)}
    <div class="hof-card__win">
      <div class="hof-card__winTitle">${escapeHtml(win?.title || "Sem vencedor")}${win?.year ? ` <span class="muted small">(${escapeHtml(String(win.year))})</span>` : ""}</div>
      <div class="muted small" style="margin-top:4px">${win?.director ? `Dir. ${escapeHtml(win.director)}` : "—"} · ${win ? `${Number(win.votes||0)} voto(s)` : "—"}</div>
    </div>
  `;

  div.addEventListener("click", () => openModal(w));
  return div;
}

/* ── Modal ── */
function openModal(week) {
  el("modalTitle").textContent = week.title || `Semana #${week.id}`;
  const weekDisplayId = Math.max(1, Number(week.id) - 6);
  el("modalSub").textContent = `#${weekDisplayId} · ${week.is_open ? "aberta" : "fechada"}`;

  const films = sortFilmsInWeek(week);
  const win = winnerFilm(week);

  const rows = films.map(f => {
    const isWinner = win && Number(f.id) === Number(win.id);
    return `
      <div class="hof-row ${isWinner ? "hof-row--win" : ""}">
        ${hofPosterBlock(f.poster_url, f.title)}
        <div class="hof-row__body">
          <div class="hof-row__title">
            ${escapeHtml(f.title||"—")}
            ${f.year ? `<span class="muted small"> (${escapeHtml(String(f.year))})</span>` : ""}
            ${isWinner ? `<span class="hof-crown">🏆</span>` : ""}
          </div>
          <div class="muted small">${f.director ? `Dir. ${escapeHtml(f.director)}` : "—"}</div>
        </div>
        <div class="hof-row__votes">${Number(f.votes||0)}</div>
      </div>
    `;
  }).join("");

  el("modalBody").innerHTML = `<div class="hof-list">${rows}</div>`;
  el("modal").classList.add("is-open");
  el("modal").setAttribute("aria-hidden", "false");
}

function closeModal() {
  el("modal").classList.remove("is-open");
  el("modal").setAttribute("aria-hidden", "true");
  el("modalBody").innerHTML = "";
}

el("modalClose").addEventListener("click", closeModal);
el("modalBackdrop").addEventListener("click", closeModal);
window.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

/* ── Apply / Load ── */
function apply() {
  const q = el("q").value || "";
  const onlyClosed = !!el("onlyClosed").checked;
  const sortMode = el("sort").value || "smart";

  let weeks = filterWeeks(weeksCache, q, onlyClosed);
  weeks = sortWeeks(weeks, sortMode);

  el("count").textContent = `${weeks.length} / ${weeksCache.length} semanas`;
  el("status").textContent = weeks.length ? "" : "Nada encontrado.";

  el("weeks").innerHTML = "";
  el("hof").innerHTML = "";

  if (view === "archive") {
    weeks.forEach(w => el("weeks").appendChild(renderArchiveCard(w)));
  } else {
    weeks.forEach(w => el("hof").appendChild(renderHofCard(w)));
  }
}

async function load() {
  el("status").textContent = "A carregar…";
  el("weeks").innerHTML = "";
  el("hof").innerHTML = "";
  el("count").textContent = "—";

  try {
    weeksCache = await apiGet("/weeks");
    el("status").textContent = "";
    apply();
    refreshNavAdmin();
  } catch (e) {
    el("status").textContent = "Erro ao carregar.";
    console.error(e);
  }
}

/* ── Listeners ── */
el("refresh").addEventListener("click", () => { toast("A atualizar…", "info", 1200); load(); });
el("q").addEventListener("input", apply);
el("onlyClosed").addEventListener("change", apply);
el("sort").addEventListener("change", apply);
el("viewArchive").addEventListener("click", () => setView("archive"));
el("viewHof").addEventListener("click", () => setView("hof"));

setView("archive");
refreshNavAdmin();
load();