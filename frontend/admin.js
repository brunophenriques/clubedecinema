/* =============================================
   Clube de Cinema — admin.js
   No more alert()/prompt() — everything in-UI
   ============================================= */

const API = "";

function $(id) { return document.getElementById(id); }

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  }[c]));
}

/* ── Auth storage ── */
const TOKEN_KEY = "cinema_club_token";
function getToken() { return localStorage.getItem(TOKEN_KEY); }
function setToken(t) { localStorage.setItem(TOKEN_KEY, t); }
function clearToken() { localStorage.removeItem(TOKEN_KEY); }
function authHeaders() {
  const t = getToken();
  return t ? { "Authorization": `Bearer ${t}` } : {};
}

let currentWeekData = null;

/* ── Toast ── */
const ICONS = { success: "✓", error: "✕", info: "·" };

function ensureToastRoot() {
  let root = document.getElementById("toastRoot");
  if (!root) {
    root = document.createElement("div");
    root.id = "toastRoot";
    document.body.appendChild(root);
  }
  return root;
}

function toast(message, type = "info", ms = 3400) {
  const root = ensureToastRoot();
  const t = document.createElement("div");
  t.className = `toast toast--${type}`;
  t.innerHTML = `
    <div class="toast__icon">${ICONS[type] || "·"}</div>
    <div class="toast__msg">${escapeHtml(message)}</div>
    <button class="toast__x" aria-label="Fechar">✕</button>
  `;
  root.appendChild(t);
  const kill = () => { t.classList.add("toast--out"); setTimeout(() => t.remove(), 200); };
  t.querySelector(".toast__x").addEventListener("click", kill);
  setTimeout(kill, ms);
}

/* ── Confirm modal ── */
function showConfirm(message) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "hof-modal is-open";
    overlay.style.cssText = "display:flex";
    overlay.innerHTML = `
      <div class="hof-modal__backdrop"></div>
      <div class="hof-modal__panel" role="dialog" aria-modal="true" style="max-width:380px">
        <div class="hof-modal__head">
          <div class="hof-modal__title">Confirmar</div>
        </div>
        <div class="hof-modal__body">
          <p style="margin-bottom:18px; color:var(--ink-60)">${escapeHtml(message)}</p>
          <div style="display:flex; gap:10px; justify-content:flex-end">
            <button id="_cancelBtn" class="btn">Cancelar</button>
            <button id="_confirmBtn" class="btn primary">Confirmar</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    const close = (val) => { overlay.remove(); resolve(val); };
    overlay.querySelector("#_cancelBtn").addEventListener("click", () => close(false));
    overlay.querySelector("#_confirmBtn").addEventListener("click", () => close(true));
    overlay.querySelector(".hof-modal__backdrop").addEventListener("click", () => close(false));
  });
}

/* ── Edit film modal ── */
function showEditFilmModal(film) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "hof-modal is-open";
    overlay.style.cssText = "display:flex";
    overlay.innerHTML = `
      <div class="hof-modal__backdrop"></div>
      <div class="hof-modal__panel" role="dialog" aria-modal="true" style="max-width:460px">
        <div class="hof-modal__head">
          <div>
            <div class="hof-modal__title">Editar Filme</div>
            <div class="muted small">${escapeHtml(film.submitted_title || film.title || "—")}</div>
          </div>
          <button id="_editClose" class="btn ghost">✕</button>
        </div>
        <div class="hof-modal__body">
          <div style="display:grid; gap:10px">
            <div>
              <label class="muted small" style="display:block;margin-bottom:4px">Título</label>
              <input id="_editTitle" class="input" value="${escapeHtml(film.submitted_title || film.title || "")}" />
            </div>
            <div>
              <label class="muted small" style="display:block;margin-bottom:4px">Ano</label>
              <input id="_editYear" class="input" placeholder="(vazio = sem ano)" value="${film.submitted_year ?? film.year ?? ""}" inputmode="numeric" />
            </div>
          </div>
          <div style="display:flex; gap:10px; justify-content:flex-end; margin-top:18px">
            <button id="_editCancel" class="btn">Cancelar</button>
            <button id="_editSave" class="btn primary">Guardar e re-match</button>
          </div>
          <div class="muted small" id="_editMsg" style="margin-top:8px;text-align:center"></div>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    const close = (val) => { overlay.remove(); resolve(val); };

    overlay.querySelector("#_editClose").addEventListener("click", () => close(null));
    overlay.querySelector("#_editCancel").addEventListener("click", () => close(null));
    overlay.querySelector(".hof-modal__backdrop").addEventListener("click", () => close(null));
    overlay.querySelector("#_editSave").addEventListener("click", () => {
      const title = overlay.querySelector("#_editTitle").value.trim();
      const yearRaw = overlay.querySelector("#_editYear").value.trim();
      if (!title) { overlay.querySelector("#_editMsg").textContent = "Título obrigatório."; return; }
      close({ title, year: yearRaw ? Number(yearRaw) : null });
    });

    setTimeout(() => overlay.querySelector("#_editTitle")?.focus(), 50);
  });
}

/* ── HTTP helpers ── */
async function parseError(res) {
  const ct = res.headers.get("content-type") || "";
  try {
    if (ct.includes("application/json")) {
      const j = await res.json();
      return { status: res.status, detail: String(j?.detail ?? j?.message ?? JSON.stringify(j)) };
    }
    const t = await res.text();
    return { status: res.status, detail: t || `HTTP ${res.status}` };
  } catch {
    return { status: res.status, detail: `HTTP ${res.status}` };
  }
}

async function apiGet(path, { auth = false } = {}) {
  const headers = {};
  if (auth) Object.assign(headers, authHeaders());
  const res = await fetch(`${API}${path}`, { headers });
  if (!res.ok) {
    const err = await parseError(res);
    throw Object.assign(new Error(err.detail), { status: err.status });
  }
  return res.json();
}

async function apiPost(path, body, { auth = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) Object.assign(headers, authHeaders());
  const res = await fetch(`${API}${path}`, { method: "POST", headers, body: JSON.stringify(body ?? {}) });
  if (!res.ok) {
    const err = await parseError(res);
    throw Object.assign(new Error(err.detail), { status: err.status });
  }
  return res.json();
}

async function apiDelete(path) {
  const res = await fetch(`${API}${path}`, { method: "DELETE", headers: authHeaders() });
  if (!res.ok) {
    const err = await parseError(res);
    throw Object.assign(new Error(err.detail), { status: err.status });
  }
  return res.json();
}

async function apiPatch(path, body) {
  const res = await fetch(`${API}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) {
    const err = await parseError(res);
    throw Object.assign(new Error(err.detail), { status: err.status });
  }
  return res.json();
}

/* ── Busy helper ── */
function setBusy(btn, busy, label = "A processar…") {
  if (!btn) return;
  btn.disabled = !!busy;
  if (busy) { btn.dataset.oldText = btn.textContent; btn.textContent = label; }
  else if (btn.dataset.oldText) { btn.textContent = btn.dataset.oldText; delete btn.dataset.oldText; }
}

/* ── Guard ── */
async function guardAdminOrRedirect() {
  const token = getToken();
  if (!token) { window.location.replace("/"); return false; }
  try {
    const res = await fetch(`${API}/auth/me`, { headers: { "Authorization": `Bearer ${token}` } });
    if (!res.ok) { clearToken(); window.location.replace("/"); return false; }
    const me = await res.json();
    if (!me?.is_admin) { window.location.replace("/"); return false; }
    return true;
  } catch {
    window.location.replace("/");
    return false;
  }
}

/* ── Auth modal ── */
function openAuthModal(mode = "login") {
  setAuthMode(mode);
  $("authModal").style.display = "block";
  setTimeout(() => $("authUser")?.focus(), 50);
}

function closeAuthModal() {
  const m = $("authModal");
  if (m) m.style.display = "none";
}

function setAuthMode(mode) {
  $("tabLogin")?.classList.toggle("is-active", mode === "login");
  $("tabRegister")?.classList.toggle("is-active", mode === "register");
  $("authSubmit").dataset.mode = mode;
  $("authSubmit").textContent = mode === "register" ? "Criar conta" : "Entrar";
  $("authPass").setAttribute("autocomplete", mode === "register" ? "new-password" : "current-password");
  $("authMsg").textContent = mode === "register" ? "Username (mín. 3) e password (mín. 4)." : "";
}

async function refreshAuthState() {
  const line = $("authStatusLine");
  const btnLogin = $("btnLogin");
  const btnLogout = $("btnLogout");
  const token = getToken();
  if (!token) {
    if (line) line.textContent = "Não autenticado.";
    if (btnLogin) btnLogin.style.display = "";
    if (btnLogout) btnLogout.style.display = "none";
    return null;
  }
  try {
    const me = await apiGet("/auth/me", { auth: true });
    if (line) line.textContent = `@${me.username}`;
    if (btnLogin) btnLogin.style.display = "none";
    if (btnLogout) btnLogout.style.display = "";
    return me;
  } catch {
    clearToken();
    if (line) line.textContent = "Sessão expirada.";
    if (btnLogin) btnLogin.style.display = "";
    if (btnLogout) btnLogout.style.display = "none";
    return null;
  }
}

/* ── Needs review ── */
async function loadNeedsReview() {
  const box = $("needsReview");
  if (!box) return;

  try {
    const films = await apiGet("/admin/films/needs-review", { auth: true });
    if (!films.length) {
      box.innerHTML = `<div class="muted small">Nenhum filme para rever.</div>`;
      return;
    }

    box.innerHTML = "";
    films.forEach((f) => {
      const div = document.createElement("div");
      div.className = "admin-film is-review";
      div.innerHTML = `
        <div class="admin-left">
          <div class="admin-title">
            ${escapeHtml(f.title)} ${f.year ? `(${f.year})` : ""}
            <span class="badge badge--warn">Rever</span>
          </div>
          <div class="admin-meta">
            Submetido: <strong>${escapeHtml(f.submitted_title || "—")}</strong> · ${f.submitted_year || "—"}
          </div>
          <div class="admin-meta">
            tmdb_id: ${f.tmdb_id ?? "—"} · score: ${f.match_score ?? "—"} · week_id: ${f.week_id}
          </div>
        </div>
        <div class="admin-right">
          <button class="btn" data-nr-rematch="${f.id}">Fix match</button>
        </div>
      `;
      box.appendChild(div);

      div.querySelector(`[data-nr-rematch]`).addEventListener("click", async (ev) => {
        const btn = ev.currentTarget;
        setBusy(btn, true, "A corrigir…");
        try {
          await apiPost(`/admin/films/${f.id}/rematch`, {}, { auth: true });
          toast("Rematch feito ✓", "success");
          await load();
        } catch (e) {
          toast(`Erro: ${e.message}`, "error", 5000);
        } finally { setBusy(btn, false); }
      });
    });
  } catch {
    box.innerHTML = `<div class="muted small">Erro ao carregar.</div>`;
  }
}

/* ── Film buttons ── */
function connectFilmButtons(week) {
  const box = $("currentWeek");
  if (!box) return;

  /* Rematch */
  box.querySelectorAll("[data-rematch]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const filmId = Number(btn.getAttribute("data-rematch"));
      setBusy(btn, true, "A corrigir…");
      try {
        await apiPost(`/admin/films/${filmId}/rematch`, {}, { auth: true });
        toast("Rematch feito ✓", "success");
        await load();
      } catch (e) { toast(`Erro: ${e.message}`, "error", 5000); }
      finally { setBusy(btn, false); }
    });
  });

  /* Edit */
  box.querySelectorAll("[data-edit]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const filmId = Number(btn.getAttribute("data-edit"));
      const film = (week.films || []).find((x) => Number(x.id) === filmId);
      if (!film) { toast("Filme não encontrado.", "error"); return; }

      const payload = await showEditFilmModal(film);
      if (!payload) return;

      setBusy(btn, true, "A guardar…");
      try {
        await apiPost(`/admin/films/${filmId}/rematch`, payload, { auth: true });
        toast("Atualizado e re-match feito ✓", "success");
        await load();
      } catch (e) { toast(`Erro: ${e.message}`, "error", 5000); }
      finally { setBusy(btn, false); }
    });
  });

  /* Set winner */
  box.querySelectorAll("[data-set-winner]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const filmId = Number(btn.getAttribute("data-set-winner"));
      if (!currentWeekData) return;
      const film = (currentWeekData.films || []).find(f => Number(f.id) === filmId);
      const ok = await showConfirm(`Definir "${film?.title || filmId}" como vencedor?`);
      if (!ok) return;
      setBusy(btn, true, "A definir…");
      try {
        await apiPost(`/admin/weeks/${currentWeekData.id}/winner`, { film_id: filmId }, { auth: true });
        toast("Vencedor definido ✓", "success");
        await load();
      } catch (e) { toast(`Erro: ${e.message}`, "error", 5000); }
      finally { setBusy(btn, false); }
    });
  });

  /* Delete film */
  box.querySelectorAll("[data-delete-film]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const filmId = Number(btn.getAttribute("data-delete-film"));
      const film = (week.films || []).find(f => Number(f.id) === filmId);
      const ok = await showConfirm(`Apagar o filme "${film?.title || filmId}"? Isto não tem volta.`);
      if (!ok) return;
      setBusy(btn, true, "A apagar…");
      try {
        await apiDelete(`/admin/films/${filmId}`);
        toast("Filme apagado.", "success");
        await load();
      } catch (e) { toast(`Erro: ${e.message}`, "error", 5000); }
      finally { setBusy(btn, false); }
    });
  });
}

/* ── Render current week ── */
function renderCurrent(week) {
  currentWeekData = week;

  const status = $("currentStatus");
  const box = $("currentWeek");
  const startBtn = $("startVoting");
  const stopBtn = $("stopVoting");
  const closeBtn = $("closeWeek");
  const openBtn = $("openWeek");
  const deleteBtn = $("deleteWeek");

  if (!week) {
    if (status) status.innerHTML = `<span class="muted">Sem semana criada ainda.</span>`;
    if (box) box.innerHTML = "";
    [startBtn, stopBtn, closeBtn, openBtn, deleteBtn].forEach(b => { if (b) b.disabled = true; });
    return;
  }

  if (status) {
    const stateClass = week.is_open ? "badge--open" : "badge--closed";
    const stateText = week.is_open ? "Aberta" : "Fechada";
    const reviewFlag = (week.films || []).some(f => f.needs_review)
      ? `<span class="badge badge--warn">⚠ Filmes a rever</span>` : "";

    status.innerHTML = `
      <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center">
        <span class="badge">Week #${week.id}</span>
        <span class="badge ${stateClass}">${stateText}</span>
        <span class="badge">${week.is_ready ? "Voting: ON" : "Voting: OFF"}</span>
        ${reviewFlag}
      </div>
    `;
  }

  if ($("weekId")) $("weekId").value = String(week.id);

  const films = [...(week.films || [])].sort((a, b) => (b.votes || 0) - (a.votes || 0));
  const winnerObj = films.find(f => Number(f.id) === Number(week.winner_film_id));

  const filmsHtml = films.map((f) => {
    const isWinner = Number(week.winner_film_id) === Number(f.id);
    const ms = f.match_score == null ? "—" : String(f.match_score);
    const classes = ["admin-film", isWinner ? "is-winner" : "", f.needs_review ? "is-review" : ""].filter(Boolean).join(" ");

    return `
      <div class="${classes}">
        <div class="admin-left">
          <div class="admin-title">
            ${escapeHtml(f.title)} ${f.year ? `(${f.year})` : ""}
            ${f.needs_review ? `<span class="badge badge--warn">Rever</span>` : ""}
            ${isWinner ? `<span class="badge" style="background:var(--gold-dim);border-color:rgba(200,150,62,.3);color:#8B6020">🏆 Vencedor</span>` : ""}
          </div>
          <div class="admin-meta">submitter: <strong>${escapeHtml(f.submitter_key || "—")}</strong> · votos: ${f.votes}</div>
          <div class="admin-meta">submetido: ${escapeHtml(f.submitted_title || "—")} · ${f.submitted_year || "—"} · tmdb: ${f.tmdb_id ?? "—"} · score: ${ms}</div>
        </div>
        <div class="admin-right">
          <button class="btn" data-set-winner="${f.id}">Set winner</button>
          ${f.needs_review ? `<button class="btn" data-rematch="${f.id}">Fix</button>` : ""}
          <button class="btn" data-edit="${f.id}">Editar</button>
          <button class="btn" data-delete-film="${f.id}">Apagar</button>
          ${f.poster_url ? `<a class="btn" target="_blank" href="${escapeHtml(f.poster_url)}">Poster ↗</a>` : ""}
        </div>
      </div>
    `;
  }).join("");

  if (box) {
    box.innerHTML = `
      <div class="muted small" style="margin-bottom:8px">
        Vencedor: <strong>${winnerObj ? escapeHtml(winnerObj.title) : "—"}</strong>
      </div>
      <div class="admin-films">
        ${filmsHtml || `<div class="muted small" style="padding:12px 0">Ainda sem filmes adicionados.</div>`}
      </div>
    `;
  }

  connectFilmButtons(week);

  if (startBtn) startBtn.disabled = !!week.is_ready;
  if (stopBtn)  stopBtn.disabled  = !week.is_ready;
  if (closeBtn) closeBtn.disabled = !week.is_open;
  if (openBtn)  openBtn.disabled  = !!week.is_open;
  if (deleteBtn) deleteBtn.disabled = false;
}

/* ── Load ── */
async function load() {
  try {
    const week = await apiGet("/admin/weeks/current", { auth: true });
    renderCurrent(week);
    await loadNeedsReview();
  } catch (e) {
    if (e?.status === 404) { renderCurrent(null); await loadNeedsReview(); return; }
    if (e?.status === 401) clearToken();
    window.location.replace("/");
  }
}

/* ── Boot ── */
document.addEventListener("DOMContentLoaded", async () => {
  const ok = await guardAdminOrRedirect();
  if (!ok) return;

  if ($("apiLabel")) $("apiLabel").textContent = API || "(mesmo servidor)";

  $("btnLogin")?.addEventListener("click", () => openAuthModal("login"));
  $("btnLogout")?.addEventListener("click", async () => {
    try { await apiPost("/auth/logout", {}, { auth: true }); } catch {}
    clearToken();
    window.location.replace("/");
  });

  $("authClose")?.addEventListener("click", closeAuthModal);
  $("authBackdrop")?.addEventListener("click", closeAuthModal);
  window.addEventListener("keydown", (e) => { if (e.key === "Escape") closeAuthModal(); });

  $("tabLogin")?.addEventListener("click", () => setAuthMode("login"));
  $("tabRegister")?.addEventListener("click", () => setAuthMode("register"));

  $("authForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const mode = $("authSubmit").dataset.mode || "login";
    const username = ($("authUser").value || "").trim();
    const password = $("authPass").value || "";
    $("authMsg").textContent = "";
    $("authSubmit").disabled = true;
    try {
      const path = mode === "register" ? "/auth/register" : "/auth/login";
      const out = await apiPost(path, { username, password });
      if (out?.token) {
        setToken(out.token);
        const ok2 = await guardAdminOrRedirect();
        if (!ok2) return;
        closeAuthModal();
        await refreshAuthState();
        await load();
      } else {
        $("authMsg").textContent = "Resposta inesperada do servidor.";
      }
    } catch (err) {
      if (err?.status === 409) $("authMsg").textContent = "Esse username já existe.";
      else if (err?.status === 401) $("authMsg").textContent = "Credenciais inválidas.";
      else $("authMsg").textContent = String(err?.message || "Erro no login.");
    } finally {
      $("authSubmit").disabled = false;
    }
  });

  $("refresh")?.addEventListener("click", load);

  /* ── Create week ── */
  $("createWeek")?.addEventListener("click", async () => {
    const btn = $("createWeek");
    const title = $("newWeekTitle").value.trim();
    if (!title) { toast("Insere um título para a semana.", "error"); $("newWeekTitle").focus(); return; }
    try {
      setBusy(btn, true, "A criar…");
      await apiPost("/admin/weeks", { title }, { auth: true });
      $("newWeekTitle").value = "";
      toast(`Semana "${title}" criada ✓`, "success");
      await load();
    } catch (e) { toast(`Erro: ${e.message}`, "error", 5000); }
    finally { setBusy(btn, false); }
  });

  /* ── Add film ── */
  $("addFilm")?.addEventListener("click", async () => {
    const btn = $("addFilm");
    const weekId = Number($("weekId").value);
    const title = $("filmTitle").value.trim();
    const yearRaw = $("filmYear").value.trim();
    const director = $("filmDirector").value.trim();
    const submitter_key = $("submitterKey").value.trim();

    if (!weekId) { toast("Week ID inválido.", "error"); return; }
    if (!title)  { toast("Título obrigatório.", "error"); $("filmTitle").focus(); return; }
    if (!submitter_key) { toast("submitter_key obrigatório.", "error"); $("submitterKey").focus(); return; }

    try {
      setBusy(btn, true, "A adicionar…");
      await apiPost(`/admin/weeks/${weekId}/films`, {
        title, year: yearRaw ? Number(yearRaw) : null,
        director: director || null, submitter_key,
      }, { auth: true });
      $("filmTitle").value = ""; $("filmYear").value = "";
      $("filmDirector").value = ""; $("submitterKey").value = "";
      toast("Filme adicionado ✓", "success");
      await load();
    } catch (e) { toast(`Erro: ${e.message}`, "error", 5000); }
    finally { setBusy(btn, false); }
  });

  /* ── Week action helpers ── */
  async function weekAction(btnId, endpoint, busyLabel, successMsg) {
    const btn = $(btnId);
    if (!btn || !currentWeekData) return;
    const weekId = currentWeekData.id;
    setBusy(btn, true, busyLabel);
    try {
      await apiPost(`/admin/weeks/${weekId}/${endpoint}`, {}, { auth: true });
      toast(successMsg, "success");
      await load();
    } catch (e) { toast(`Erro: ${e.message}`, "error", 5000); }
    finally { setBusy(btn, false); }
  }

  $("startVoting")?.addEventListener("click", () => weekAction("startVoting", "start-voting", "A abrir…", "Votação aberta ✓"));
  $("stopVoting")?.addEventListener("click",  () => weekAction("stopVoting",  "stop-voting",  "A parar…",  "Votação pausada ✓"));
  $("closeWeek")?.addEventListener("click",   () => weekAction("closeWeek",   "close",         "A fechar…", "Semana fechada ✓"));
  $("openWeek")?.addEventListener("click",    () => weekAction("openWeek",    "open",          "A reabrir…","Semana reaberta ✓"));

  /* ── Delete week ── */
  $("deleteWeek")?.addEventListener("click", async () => {
    if (!currentWeekData) return;
    const ok = await showConfirm(`Apagar a semana "${currentWeekData.title}"? Isto apaga todos os filmes e votos. Sem volta.`);
    if (!ok) return;
    const btn = $("deleteWeek");
    setBusy(btn, true, "A apagar…");
    try {
      await apiDelete(`/admin/weeks/${currentWeekData.id}`);
      toast("Semana apagada.", "success");
      renderCurrent(null);
      await load();
    } catch (e) { toast(`Erro: ${e.message}`, "error", 5000); }
    finally { setBusy(btn, false); }
  });

  await refreshAuthState();
  await load();
});