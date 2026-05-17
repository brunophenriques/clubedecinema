/* =============================================
   Clube de Cinema — app.js (index page)
   ============================================= */

const API = "";

function el(id) { return document.getElementById(id); }

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
function votedKey(weekId) { return `cinema_club_voted_week_${weekId}`; }

/* ── Toast system ── */
function ensureToastRoot() {
  let root = document.getElementById("toastRoot");
  if (!root) {
    root = document.createElement("div");
    root.id = "toastRoot";
    document.body.appendChild(root);
  }
  return root;
}

const ICONS = { success: "✓", error: "✕", info: "·" };

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

  const kill = () => {
    t.classList.add("toast--out");
    setTimeout(() => t.remove(), 200);
  };
  t.querySelector(".toast__x").addEventListener("click", kill);
  setTimeout(kill, ms);
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
  if (auth && getToken()) headers["Authorization"] = `Bearer ${getToken()}`;
  const res = await fetch(`${API}${path}`, { headers });
  if (!res.ok) {
    const err = await parseError(res);
    throw Object.assign(new Error(err.detail), { status: err.status });
  }
  return res.json();
}

async function apiPost(path, body, { auth = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && getToken()) headers["Authorization"] = `Bearer ${getToken()}`;
  const res = await fetch(`${API}${path}`, { method: "POST", headers, body: JSON.stringify(body ?? {}) });
  if (!res.ok) {
    const err = await parseError(res);
    throw Object.assign(new Error(err.detail), { status: err.status });
  }
  return res.json();
}

/* ── Error messages ── */
function prettyVoteError(e) {
  const s = e?.status;
  const m = String(e?.message || "");
  if (s === 401) return "Tens de fazer login para votar.";
  if (s === 403) return "Sem permissão (só submitters podem votar).";
  if (m.includes("already voted")) return "Já votaste esta semana.";
  if (m.includes("Voting is closed")) return "A votação está fechada.";
  if (m.includes("Voting not started")) return "A votação ainda não começou.";
  if (m.includes("own film")) return "Não podes votar no teu próprio filme.";
  return "Erro ao votar. Vê a consola.";
}

function prettySubmitError(e) {
  const s = e?.status;
  const m = String(e?.message || "");
  if (s === 401) return "Tens de fazer login para submeter.";
  if (m.includes("already submitted")) return "Já submeteste um filme esta semana.";
  if (m.includes("Week is closed")) return "A semana está fechada.";
  if (m.includes("title required")) return "Título obrigatório.";
  return "Erro ao submeter. Vê a consola.";
}

/* ── Auth modal ── */
function openAuthModal(mode = "login") {
  setAuthMode(mode);
  el("authModal").style.display = "block";
  setTimeout(() => el("authUser")?.focus(), 50);
}

function closeAuthModal() {
  const m = el("authModal");
  if (m) m.style.display = "none";
}

function setAuthMode(mode) {
  el("tabLogin")?.classList.toggle("is-active", mode === "login");
  el("tabRegister")?.classList.toggle("is-active", mode === "register");
  el("authSubmit").dataset.mode = mode;
  el("authSubmit").textContent = mode === "register" ? "Criar conta" : "Entrar";
  el("authPass").setAttribute("autocomplete", mode === "register" ? "new-password" : "current-password");
  el("authMsg").textContent = mode === "register"
    ? "Escolhe um username (mín. 3 caracteres) e password (mín. 4)."
    : "";
}

/* ── Auth state ── */
async function refreshAuthState() {
  const line = el("authStatusLine");
  const btnLogin = el("btnLogin");
  const btnLogout = el("btnLogout");
  const navAdmin = el("navAdmin");

  if (navAdmin) navAdmin.style.display = "none";

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
    if (navAdmin && me?.is_admin) navAdmin.style.display = "";
    return me;
  } catch {
    clearToken();
    if (line) line.textContent = "Sessão expirada.";
    if (btnLogin) btnLogin.style.display = "";
    if (btnLogout) btnLogout.style.display = "none";
    return null;
  }
}

/* ── Week status ── */
function setWeekStatus(week, alreadyVoted) {
  const box = el("weekStatus");
  if (!box) return;

  if (!week) {
    box.dataset.state = "pending";
    box.textContent = "Sem semana criada.";
  } else if (!week.is_open) {
    box.dataset.state = "closed";
    box.textContent = "Votação encerrada.";
  } else if (!week.is_ready) {
    box.dataset.state = "pending";
    box.textContent = "A aguardar abertura da votação.";
  } else if (alreadyVoted) {
    box.dataset.state = "voted";
    box.textContent = "Voto registado ✓";
  } else {
    box.dataset.state = "open";
    box.textContent = "Votação aberta — escolhe um filme.";
  }
}

/* ── Poster HTML ── */
function posterHTML(f) {
  // Build Letterboxd search URL using tmdb: search trigger if tmdb_id exists, otherwise title+year
  const lbQuery = f.tmdb_id
    ? `tmdb:${f.tmdb_id}`
    : encodeURIComponent(`${f.title}${f.year ? ` ${f.year}` : ""}`);
  const letterboxdUrl = `https://letterboxd.com/search/${lbQuery}/`;

  // VidKing embed URL — uses TMDB id if available, otherwise we open vidking search
  const vidkingUrl = f.tmdb_id
    ? `https://www.vidking.net/embed/movie/${f.tmdb_id}`
    : null;

  const posterContent = f.poster_url
    ? `<img src="${escapeHtml(f.poster_url)}" alt="${escapeHtml(f.title)}" loading="lazy"/>`
    : `<span>${escapeHtml((f.title || "").split(" ").slice(0,2).map(s => s[0]?.toUpperCase()).join("") || "🎬")}</span>`;

  const posterClass = f.poster_url ? "poster" : "poster placeholder";

  return `
    <div class="${posterClass}" data-letterboxd="${escapeHtml(letterboxdUrl)}" data-vidking="${vidkingUrl ? escapeHtml(vidkingUrl) : ""}" data-title="${escapeHtml(f.title)}">
      ${posterContent}
      <div class="poster-overlay">
        <a class="poster-btn poster-btn--know" href="${escapeHtml(letterboxdUrl)}" target="_blank" rel="noopener noreferrer">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
          Saber mais
        </a>
        ${vidkingUrl ? `<button class="poster-btn poster-btn--play" data-vidking="${escapeHtml(vidkingUrl)}" data-title="${escapeHtml(f.title)}">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          Reproduzir
        </button>` : ""}
      </div>
    </div>`;
}

/* ── Player Modal ── */
function openPlayerModal(vidkingUrl, title) {
  let modal = document.getElementById("playerModal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "playerModal";
    modal.innerHTML = `
      <div class="player-modal__backdrop" id="playerBackdrop"></div>
      <div class="player-modal__panel" role="dialog" aria-modal="true">
        <div class="player-modal__head">
          <div class="player-modal__title" id="playerTitle"></div>
          <button class="btn ghost" id="playerClose" type="button">✕</button>
        </div>
        <div class="player-modal__body">
          <iframe id="playerIframe" allowfullscreen allow="autoplay; fullscreen" frameborder="0"></iframe>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    document.getElementById("playerBackdrop").addEventListener("click", closePlayerModal);
    document.getElementById("playerClose").addEventListener("click", closePlayerModal);
    window.addEventListener("keydown", (e) => { if (e.key === "Escape") closePlayerModal(); });
  }
  document.getElementById("playerTitle").textContent = title;
  document.getElementById("playerIframe").src = vidkingUrl;
  modal.style.display = "flex";
  document.body.style.overflow = "hidden";
}

function closePlayerModal() {
  const modal = document.getElementById("playerModal");
  if (modal) {
    modal.style.display = "none";
    const iframe = document.getElementById("playerIframe");
    if (iframe) iframe.src = "";
    document.body.style.overflow = "";
  }
}

/* ── Film card ── */
function filmCard(week, f, alreadyVoted) {
  const div = document.createElement("div");
  div.className = "film-card fade-in";

  const votingEnabled = week.is_open && week.is_ready;
  const canVote = votingEnabled && !alreadyVoted;
  const isWinner = !week.is_open && week.winner_film_id && week.winner_film_id === f.id;

  const btnLabel = alreadyVoted ? "Voto registado ✓"
    : !week.is_open ? "Encerrado"
    : !week.is_ready ? "Em breve"
    : "Votar";

  div.innerHTML = `
    ${posterHTML(f)}
    <div class="film-body">
      <div class="film-top">
        <h3 class="film-title">
          ${escapeHtml(f.title)}
          ${f.year ? `<span class="year">(${f.year})</span>` : ""}
          ${isWinner ? `<span class="trophy">🏆</span>` : ""}
        </h3>
        <div class="film-meta">
          ${f.director ? `Dir. ${escapeHtml(f.director)} · ` : ""}${f.votes} voto${f.votes !== 1 ? "s" : ""}
        </div>
      </div>
      <div class="film-actions">
        <button class="btn${canVote ? " primary" : ""}" ${canVote ? "" : "disabled"}>
          ${btnLabel}
        </button>
        ${isWinner ? `<span class="badge badge--open">Vencedor</span>` : ""}
      </div>
    </div>
  `;

  const btn = div.querySelector("button");
  btn.addEventListener("click", async () => {
    if (!canVote) return;
    if (!getToken()) { toast("Precisas de login para votar.", "info"); openAuthModal("login"); return; }

    btn.disabled = true;
    btn.textContent = "A votar…";

    try {
      const updated = await apiPost(`/weeks/${week.id}/vote`, { film_id: f.id }, { auth: true });
      localStorage.setItem(votedKey(week.id), String(f.id));
      toast("Voto registado ✓", "success");
      render(updated);
    } catch (e) {
      btn.disabled = false;
      btn.textContent = "Votar";
      toast(prettyVoteError(e), "error", 4500);
    }
  });

  return div;
}

/* ── Render week ── */
function render(week) {
  el("weekTitle").textContent = week.title;
  el("heroTitle").textContent = week.title;

  const hint = el("filmsHint");
  if (hint) hint.textContent = week.is_open ? "Escolhe e vota." : "Resultados finais.";

  const votedFilmId = localStorage.getItem(votedKey(week.id));
  const alreadyVoted = Boolean(votedFilmId);

  setWeekStatus(week, alreadyVoted);

  const filmsEl = el("films");
  filmsEl.innerHTML = "";

  const all = week.films || [];
  const LIMIT = 6;
  const btnMore = el("filmsMore");
  let expanded = localStorage.getItem(`cinema_club_films_expanded_${week.id}`) === "1";
  const shown = (!expanded && all.length > LIMIT) ? all.slice(0, LIMIT) : all;

  shown.forEach(f => filmsEl.appendChild(filmCard(week, f, alreadyVoted)));

  // Delegated handler for play buttons
  filmsEl.addEventListener("click", (e) => {
    const btn = e.target.closest(".poster-btn--play");
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    const url = btn.dataset.vidking;
    const title = btn.dataset.title;
    if (url) openPlayerModal(url, title);
    else toast("Player nao disponivel para este filme (sem ID TMDB).", "info");
  }, { once: true });

  if (btnMore) {
    if (all.length <= LIMIT) {
      btnMore.style.display = "none";
    } else {
      btnMore.style.display = "flex";
      btnMore.textContent = expanded ? "↑ Ver menos" : `↓ Ver mais (${all.length - LIMIT} filmes)`;
      btnMore.onclick = () => {
        expanded = !expanded;
        localStorage.setItem(`cinema_club_films_expanded_${week.id}`, expanded ? "1" : "0");
        render(week);
      };
    }
  }

  const submitHint = el("submitHint");
  if (submitHint) {
    if (!getToken()) submitHint.textContent = "Faz login para submeter e votar.";
    else if (!week.is_open) submitHint.textContent = "Semana encerrada.";
    else submitHint.textContent = "Podes submeter 1 filme por semana.";
  }
}

/* ── Load ── */
async function load() {
  const apiLabel = el("apiLabel");
  if (apiLabel) apiLabel.textContent = API || "(mesmo servidor)";

  try {
    const week = await apiGet("/weeks/current");
    render(week);
  } catch (e) {
    el("weekTitle").textContent = "Sem semana criada";
    el("heroTitle").textContent = "Clube de Cinema";
    const ws = el("weekStatus");
    if (ws) { ws.dataset.state = "pending"; ws.textContent = "Sem semana criada."; }
    el("films").innerHTML = "";
  }
}

/* ── Submit film ── */
async function submitFilmCurrentWeek() {
  if (!getToken()) { toast("Precisas de login para submeter.", "info"); openAuthModal("login"); return; }

  let week;
  try { week = await apiGet("/weeks/current"); }
  catch { toast("Sem semana criada.", "error"); return; }

  if (!week?.is_open) { toast("Semana encerrada — não dá para submeter.", "error", 4500); return; }

  const title = (el("subTitle").value || "").trim();
  const yearRaw = (el("subYear").value || "").trim();
  const director = (el("subDirector").value || "").trim();
  const year = yearRaw ? Number(yearRaw) : null;

  if (!title) { toast("Título obrigatório.", "error"); el("subTitle").focus(); return; }
  if (yearRaw && (!Number.isFinite(year) || year < 1880 || year > 2100)) {
    toast("Ano inválido.", "error"); el("subYear").focus(); return;
  }

  const btn = el("subBtn");
  btn.disabled = true;
  btn.textContent = "A submeter…";

  try {
    const updated = await apiPost(`/weeks/${week.id}/submissions`, {
      title, year: year || null, director: director || null
    }, { auth: true });

    toast("Filme submetido ✓", "success");
    el("subTitle").value = "";
    el("subYear").value = "";
    el("subDirector").value = "";
    render(updated);
  } catch (e) {
    toast(prettySubmitError(e), "error", 4500);
  } finally {
    btn.disabled = false;
    btn.textContent = "Submeter";
  }
}

/* ── Boot ── */
document.addEventListener("DOMContentLoaded", async () => {
  el("refresh")?.addEventListener("click", () => { toast("A atualizar…", "info", 1200); load(); });

  el("btnLogin")?.addEventListener("click", () => openAuthModal("login"));
  el("btnLogout")?.addEventListener("click", async () => {
    try { await apiPost("/auth/logout", {}, { auth: true }); } catch {}
    clearToken();
    toast("Sessão terminada.", "success");
    await refreshAuthState();
    await load();
  });

  el("authClose")?.addEventListener("click", closeAuthModal);
  el("authBackdrop")?.addEventListener("click", closeAuthModal);
  window.addEventListener("keydown", (e) => { if (e.key === "Escape") closeAuthModal(); });

  el("tabLogin")?.addEventListener("click", () => setAuthMode("login"));
  el("tabRegister")?.addEventListener("click", () => setAuthMode("register"));

  el("authForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const mode = el("authSubmit").dataset.mode || "login";
    const username = (el("authUser").value || "").trim();
    const password = el("authPass").value || "";

    el("authMsg").textContent = "";
    el("authSubmit").disabled = true;

    try {
      const path = mode === "register" ? "/auth/register" : "/auth/login";
      const out = await apiPost(path, { username, password });
      if (out?.token) {
        setToken(out.token);
        toast(mode === "register" ? "Conta criada ✓" : "Login ✓", "success");
        closeAuthModal();
        await refreshAuthState();
        await load();
      } else {
        el("authMsg").textContent = "Resposta inesperada do servidor.";
      }
    } catch (err) {
      if (err?.status === 409) el("authMsg").textContent = "Esse username já existe.";
      else if (err?.status === 401) el("authMsg").textContent = "Credenciais inválidas.";
      else el("authMsg").textContent = String(err?.message || "Erro no login.");
    } finally {
      el("authSubmit").disabled = false;
    }
  });

  el("submitForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    await submitFilmCurrentWeek();
  });

  await refreshAuthState();
  await load();
});