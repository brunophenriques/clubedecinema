const API = "";

function el(id) { return document.getElementById(id); }

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  }[c]));
}

/* -----------------------------
   Auth storage
------------------------------ */
const TOKEN_KEY = "cinema_club_token";
function getToken() { return localStorage.getItem(TOKEN_KEY); }
function setToken(t) { localStorage.setItem(TOKEN_KEY, t); }
function clearToken() { localStorage.removeItem(TOKEN_KEY); }

function votedKey(weekId){ return `cinema_club_voted_week_${weekId}`; }

/* -----------------------------
   Toasts
------------------------------ */
function ensureToastRoot() {
  let root = document.getElementById("toastRoot");
  if (!root) {
    root = document.createElement("div");
    root.id = "toastRoot";
    document.body.appendChild(root);
  }
  return root;
}

function toast(message, type = "info", ms = 3200) {
  const root = ensureToastRoot();
  const t = document.createElement("div");
  t.className = `toast toast--${type}`;
  t.innerHTML = `
    <div class="toast__dot"></div>
    <div class="toast__msg">${escapeHtml(message)}</div>
    <button class="toast__x" aria-label="Fechar">✕</button>
  `;
  root.appendChild(t);

  const kill = () => {
    t.classList.add("toast--out");
    setTimeout(() => t.remove(), 220);
  };

  t.querySelector(".toast__x").addEventListener("click", kill);
  setTimeout(kill, ms);
}

/* -----------------------------
   HTTP helpers
------------------------------ */
async function parseError(res) {
  const ct = res.headers.get("content-type") || "";
  let payloadText = "";
  try {
    if (ct.includes("application/json")) {
      const j = await res.json();
      const detail = j?.detail ?? j?.message ?? JSON.stringify(j);
      return { status: res.status, detail: String(detail) };
    } else {
      payloadText = await res.text();
      return { status: res.status, detail: payloadText || `HTTP ${res.status}` };
    }
  } catch {
    return { status: res.status, detail: payloadText || `HTTP ${res.status}` };
  }
}

async function apiGet(path, { auth = false } = {}) {
  const headers = {};
  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API}${path}`, { headers });
  if (!res.ok) {
    const err = await parseError(res);
    throw new Error(`${err.status}|${err.detail}`);
  }
  return res.json();
}

async function apiPost(path, body, { auth = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) {
    const err = await parseError(res);
    throw new Error(`${err.status}|${err.detail}`);
  }
  return res.json();
}

/* -----------------------------
   UX helpers
------------------------------ */
function splitErr(e) {
  const raw = String(e?.message ?? e ?? "");
  const idx = raw.indexOf("|");
  if (idx !== -1) return { status: Number(raw.slice(0, idx)), detail: raw.slice(idx + 1) };
  return { status: null, detail: raw };
}

function prettyVoteError(e) {
  const { status, detail } = splitErr(e);
  const m = String(detail || "");

  if (status === 401) return "Tens de fazer login para votar.";
  if (status === 403) return "Sem permissão para votar (provavelmente não és submitter desta semana).";
  if (m.includes("already voted")) return "Já votaste esta semana.";
  if (m.includes("Voting is closed")) return "A votação está fechada.";
  if (m.includes("Voting not started yet")) return "A votação ainda não começou (à espera do admin).";
  if (m.includes("Only submitters")) return "Só quem submeteu filmes pode votar (por agora).";
  if (m.includes("own film")) return "Não podes votar no teu próprio filme.";
  if (m.includes("Film not found")) return "Filme não encontrado.";
  return "Não deu para votar. Vê a consola/backend.";
}

function prettySubmitError(e) {
  const { status, detail } = splitErr(e);
  const m = String(detail || "");

  if (status === 401) return "Tens de fazer login para submeter.";
  if (m.includes("already submitted")) return "Já submeteste um filme esta semana.";
  if (m.includes("Week is closed")) return "A semana está fechada.";
  if (m.includes("title required")) return "Título obrigatório.";
  return "Não deu para submeter. Vê a consola/backend.";
}

function setWeekStatus(week, alreadyVoted) {
  const box = el("weekStatus");
  if (!box) return;

  let state = "pending";
  let text = "A carregar…";

  if (!week) {
    state = "pending";
    text = "Ainda não há semana criada.";
  } else if (!week.is_open) {
    state = "closed";
    text = "Votação fechada.";
  } else if (!week.is_ready) {
    state = "pending";
    text = "Votação ainda não começou (à espera do admin).";
  } else if (alreadyVoted) {
    state = "voted";
    text = "✅ Já votaste esta semana.";
  } else {
    state = "open";
    text = "Votação aberta — escolhe um filme.";
  }

  box.dataset.state = state;
  box.innerHTML = `<strong>Status:</strong> ${escapeHtml(text)}`;
}

function posterHTML(f) {
  if (f.poster_url) {
    return `<div class="poster"><img src="${escapeHtml(f.poster_url)}" alt="${escapeHtml(f.title)}"/></div>`;
  }
  const initials = (f.title || "")
    .split(" ")
    .slice(0, 2)
    .map(s => s[0]?.toUpperCase())
    .join("");
  return `<div class="poster placeholder"><span>${escapeHtml(initials || "🎬")}</span></div>`;
}

/* -----------------------------
   Auth modal controls (NO injection)
------------------------------ */
function openAuthModal(mode = "login") {
  setAuthMode(mode);
  el("authModal").style.display = "block";
  el("authUser")?.focus();
}
function closeAuthModal() {
  const m = el("authModal");
  if (m) m.style.display = "none";
}
function setAuthMode(mode) {
  el("tabLogin")?.classList.toggle("is-active", mode === "login");
  el("tabRegister")?.classList.toggle("is-active", mode === "register");

  el("authSubmit").dataset.mode = mode;
  el("authSubmit").textContent = (mode === "register") ? "Criar conta" : "Entrar";
  el("authPass").setAttribute("autocomplete", mode === "register" ? "new-password" : "current-password");
  el("authMsg").textContent = (mode === "register")
    ? "Escolhe um username (min 3) e password (min 4)."
    : "Entra com o teu username e password.";
}

/* -----------------------------
   Auth state
------------------------------ */
async function refreshAuthState() {
  const line = el("authStatusLine");
  const btnLogin = el("btnLogin");
  const btnLogout = el("btnLogout");
  const submitHint = el("submitHint");
  const navAdmin = document.getElementById("navAdmin");

  const token = getToken();

  // default safe UI
  if (navAdmin) navAdmin.style.display = "none";

  if (!token) {
    if (line) line.textContent = "Não autenticado.";
    if (btnLogin) btnLogin.style.display = "";
    if (btnLogout) btnLogout.style.display = "none";
    if (submitHint) submitHint.textContent = "Faz login para submeter e votar.";
    return null;
  }

  try {
    const me = await apiGet("/auth/me", { auth: true });

    if (line) line.textContent = `Autenticado como @${me.username}`;
    if (btnLogin) btnLogin.style.display = "none";
    if (btnLogout) btnLogout.style.display = "";

    if (submitHint) submitHint.textContent = "Podes submeter e votar.";
    if (navAdmin && me?.is_admin) navAdmin.style.display = "";

    return me;
  } catch {
    clearToken();
    if (line) line.textContent = "Sessão expirada. Faz login novamente.";
    if (btnLogin) btnLogin.style.display = "";
    if (btnLogout) btnLogout.style.display = "none";
    if (submitHint) submitHint.textContent = "Faz login para submeter e votar.";
    if (navAdmin) navAdmin.style.display = "none";
    return null;
  }
}   

/* -----------------------------
   Submit film
------------------------------ */
async function submitFilmCurrentWeek() {
  if (!getToken()) {
    toast("Precisas de login para submeter.", "info");
    openAuthModal("login");
    return;
  }

  let week;
  try {
    week = await apiGet("/weeks/current");
  } catch {
    toast("Ainda não há semana criada.", "error");
    return;
  }

  if (!week?.is_open) {
    toast("Semana fechada — não dá para submeter.", "error", 4200);
    return;
  }

  const title = (el("subTitle").value || "").trim();
  const yearRaw = (el("subYear").value || "").trim();
  const director = (el("subDirector").value || "").trim();

  const year = yearRaw ? Number(yearRaw) : null;
  if (!title) {
    toast("Título obrigatório.", "error");
    return;
  }
  if (yearRaw && (!Number.isFinite(year) || year < 1880 || year > 2100)) {
    toast("Ano inválido.", "error");
    return;
  }

  const btn = el("subBtn");
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = "A submeter…";

  try {
    const updated = await apiPost(`/weeks/${week.id}/submissions`, {
      title,
      year: yearRaw ? year : null,
      director: director || null,
    }, { auth: true });

    toast("Filme submetido ✅", "success");
    el("subTitle").value = "";
    el("subYear").value = "";
    el("subDirector").value = "";
    render(updated);
  } catch (e) {
    toast(prettySubmitError(e), "error", 4200);
    console.error(e);
  } finally {
    btn.disabled = false;
    btn.textContent = old;
  }
}

/* -----------------------------
   Film cards + render
------------------------------ */
function filmCard(week, f, alreadyVoted) {
  const div = document.createElement("div");
  div.className = "film-card";

  const votingEnabled = week.is_open && week.is_ready;
  const canVote = votingEnabled && !alreadyVoted;
  const isWinner = (!week.is_open && week.winner_film_id && week.winner_film_id === f.id);

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
          ${f.director ? `Dir. ${escapeHtml(f.director)} · ` : ""}${f.votes} voto(s)
        </div>
      </div>

      <div class="film-actions">
        <button class="btn primary" ${canVote ? "" : "disabled"}>
          ${
            alreadyVoted ? "Voto registado" :
            (!week.is_open ? "Fechado" :
            (!week.is_ready ? "Ainda não" : "Votar"))
          }
        </button>
        <span class="muted small">${isWinner ? "Vencedor" : ""}</span>
      </div>
    </div>
  `;

  const btn = div.querySelector("button");
  btn.addEventListener("click", async () => {
    if (!canVote) return;

    if (!getToken()) {
      toast("Precisas de login para votar.", "info");
      openAuthModal("login");
      return;
    }

    btn.disabled = true;
    const old = btn.textContent;
    btn.textContent = "A votar…";

    try {
      const updated = await apiPost(`/weeks/${week.id}/vote`, {
        film_id: f.id,
      }, { auth: true });

      localStorage.setItem(votedKey(week.id), String(f.id));
      toast("Voto registado ✅", "success");
      render(updated);
    } catch (e) {
      btn.disabled = false;
      btn.textContent = old;
      toast(prettyVoteError(e), "error", 4200);
      console.error(e);
    }
  });

  return div;
}

function render(week) {
  el("weekTitle").textContent = week.title;
  el("heroTitle").textContent = week.title;

  const hint = el("filmsHint");
  if (hint) hint.textContent = week.is_open ? "Escolhe um e vota." : "Resultados finais.";

  const votedFilmId = localStorage.getItem(votedKey(week.id));
  const alreadyVoted = Boolean(votedFilmId);

  setWeekStatus(week, alreadyVoted);

    const filmsEl = el("films");
    filmsEl.innerHTML = "";

    const all = (week.films || []);
    const btnMore = el("filmsMore");

    // default: mostrar só 4 quando há muitos
    const LIMIT = 4;
    let expanded = (localStorage.getItem(`cinema_club_films_expanded_${week.id}`) === "1");

    let shown = all;
    if (!expanded && all.length > LIMIT) shown = all.slice(0, LIMIT);

    shown.forEach(f => filmsEl.appendChild(filmCard(week, f, alreadyVoted)));

    if (btnMore) {
    if (all.length <= LIMIT) {
        btnMore.style.display = "none";
    } else {
        btnMore.style.display = "inline-flex";
        btnMore.textContent = expanded ? "Ver menos" : `Ver mais (${all.length - LIMIT})`;
        btnMore.onclick = () => {
        expanded = !expanded;
        localStorage.setItem(`cinema_club_films_expanded_${week.id}`, expanded ? "1" : "0");
        render(week); // re-render
        };
    }
    }

  const submitHint = el("submitHint");
  if (submitHint) {
    if (!getToken()) submitHint.textContent = "Faz login para submeter e votar.";
    else if (!week.is_open) submitHint.textContent = "Semana fechada — submissões indisponíveis.";
    else submitHint.textContent = "Podes submeter 1 filme por semana.";
  }
}

async function load() {
  const apiLabel = el("apiLabel");
  if (apiLabel) apiLabel.textContent = API;

  try {
    const week = await apiGet("/weeks/current");
    render(week);
  } catch (e) {
    console.error(e);
    el("weekTitle").textContent = "Sem semana criada";
    el("heroTitle").textContent = "Clube de Cinema";

    const ws = el("weekStatus");
    if (ws) {
      ws.dataset.state = "pending";
      ws.textContent = "Ainda não há semana criada.";
    }

    el("films").innerHTML = "";
    toast("Ainda não há semana criada (vê o admin).", "info");
  }
}

/* -----------------------------
   Boot
------------------------------ */
document.addEventListener("DOMContentLoaded", async () => {
  // wiring buttons
  el("refresh")?.addEventListener("click", () => {
    toast("A atualizar…", "info", 1200);
    load();
  });

  el("btnLogin")?.addEventListener("click", () => openAuthModal("login"));
  el("btnLogout")?.addEventListener("click", async () => {
    try { await apiPost("/auth/logout", {}, { auth: true }); } catch {}
    clearToken();
    toast("Logout ✅", "success");
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
      const path = (mode === "register") ? "/auth/register" : "/auth/login";
      const out = await apiPost(path, { username, password }, { auth: false });
      if (out?.token) {
        setToken(out.token);
        toast(mode === "register" ? "Conta criada ✅" : "Login ✅", "success");
        closeAuthModal();
        await refreshAuthState();
        await load();
      } else {
        toast("Resposta inválida do servidor.", "error");
      }
    } catch (err) {
      const { status, detail } = splitErr(err);
      if (status === 409) toast("Esse username já existe.", "error", 4200);
      else if (status === 401) toast("Credenciais inválidas.", "error", 4200);
      else toast(String(detail || "Erro no login."), "error", 4200);
      console.error(err);
    } finally {
      el("authSubmit").disabled = false;
    }
  });

  el("submitForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    await submitFilmCurrentWeek();
  });

  // init
  await refreshAuthState();
  await load();
});