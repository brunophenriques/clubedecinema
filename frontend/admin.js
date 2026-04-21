const API = "";

function $(id) { return document.getElementById(id); }

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

/* -----------------------------
   HARD GUARD (redirect if not admin)
   ✅ FIX: validate admin via /auth/me (does not depend on week existing)
------------------------------ */
async function guardAdminOrRedirect() {
  const token = getToken();
  if (!token) {
    window.location.replace("index.html");
    return false;
  }

  try {
    const res = await fetch(`${API}/auth/me`, {
      headers: { "Authorization": `Bearer ${token}` }
    });

    if (res.status === 401) {
      clearToken();
      window.location.replace("index.html");
      return false;
    }

    if (!res.ok) {
      window.location.replace("index.html");
      return false;
    }

    const me = await res.json();
    if (!me?.is_admin) {
      window.location.replace("index.html");
      return false;
    }

    return true;
  } catch {
    window.location.replace("index.html");
    return false;
  }
}

/* -----------------------------
   Admin UI helpers
------------------------------ */
function badge(text) {
  return `<span style="
    display:inline-flex;align-items:center;gap:6px;
    padding:4px 10px;border-radius:999px;
    border:1px solid #E9E5EE;background:#FBFAFD;
    font-size:12px;color:#6B6874;
  ">${text}</span>`;
}
function badgeWarn(text) {
  return `<span style="
    display:inline-flex;align-items:center;gap:6px;
    padding:4px 10px;border-radius:999px;
    border:1px solid rgba(240,139,184,.45);
    background: rgba(240,139,184,.10);
    font-size:12px;color:#7a2f4d;font-weight:700;
  ">${text}</span>`;
}

function setBusy(btn, busy, labelBusy = "A processar…") {
  if (!btn) return;
  btn.disabled = !!busy;
  if (busy) {
    btn.dataset.oldText = btn.textContent;
    btn.textContent = labelBusy;
  } else if (btn.dataset.oldText) {
    btn.textContent = btn.dataset.oldText;
    delete btn.dataset.oldText;
  }
}

/* -----------------------------
   HTTP helpers (Bearer)
------------------------------ */
async function parseError(res) {
  const ct = res.headers.get("content-type") || "";
  try {
    if (ct.includes("application/json")) {
      const j = await res.json();
      const detail = j?.detail ?? j?.message ?? JSON.stringify(j);
      return { status: res.status, detail: String(detail) };
    }
    const t = await res.text();
    return { status: res.status, detail: t || `HTTP ${res.status}` };
  } catch {
    return { status: res.status, detail: `HTTP ${res.status}` };
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

function splitErr(e) {
  const raw = String(e?.message ?? e ?? "");
  const idx = raw.indexOf("|");
  if (idx !== -1) return { status: Number(raw.slice(0, idx)), detail: raw.slice(idx + 1) };
  return { status: null, detail: raw };
}

/* -----------------------------
   Auth modal
------------------------------ */
function openAuthModal(mode = "login") {
  setAuthMode(mode);
  $("authModal").style.display = "block";
  $("authUser")?.focus();
}
function closeAuthModal() {
  const m = $("authModal");
  if (m) m.style.display = "none";
}
function setAuthMode(mode) {
  $("tabLogin")?.classList.toggle("is-active", mode === "login");
  $("tabRegister")?.classList.toggle("is-active", mode === "register");

  $("authSubmit").dataset.mode = mode;
  $("authSubmit").textContent = (mode === "register") ? "Criar conta" : "Entrar";
  $("authPass").setAttribute("autocomplete", mode === "register" ? "new-password" : "current-password");
  $("authMsg").textContent = (mode === "register")
    ? "Escolhe um username (min 3) e password (min 4)."
    : "Entra com o teu username e password.";
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
    if (line) line.textContent = `Autenticado como @${me.username}`;
    if (btnLogin) btnLogin.style.display = "none";
    if (btnLogout) btnLogout.style.display = "";
    return me;
  } catch {
    clearToken();
    if (line) line.textContent = "Sessão expirada. Faz login novamente.";
    if (btnLogin) btnLogin.style.display = "";
    if (btnLogout) btnLogout.style.display = "none";
    return null;
  }
}

/* -----------------------------
   Film buttons wiring
------------------------------ */
function connectFilmButtons(week) {
  const box = $("currentWeek");
  if (!box) return;

  box.querySelectorAll("[data-rematch]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const filmId = Number(btn.getAttribute("data-rematch"));
      if (!filmId) return;

      const old = btn.textContent;
      btn.disabled = true;
      btn.textContent = "A corrigir…";

      try {
        await apiPost(`/admin/films/${filmId}/rematch`, {}, { auth: true });
        await load();
        alert("Rematch feito.");
      } catch (e) {
        console.error(e);
        const { status, detail } = splitErr(e);
        alert(`Erro (${status ?? "?"}): ${detail}`);
      } finally {
        btn.disabled = false;
        btn.textContent = old;
      }
    });
  });

  box.querySelectorAll("[data-edit]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const filmId = Number(btn.getAttribute("data-edit"));
      if (!filmId) return;

      const film = (week.films || []).find((x) => Number(x.id) === filmId);
      if (!film) return alert("Filme não encontrado.");

      const currentTitle = film.submitted_title || film.title || "";
      const currentYear = film.submitted_year ?? film.year ?? "";

      const newTitle = prompt("Novo título (deixa igual se estiver ok):", currentTitle);
      if (newTitle === null) return;

      const newYearRaw = prompt("Novo ano (podes deixar vazio):", String(currentYear));
      if (newYearRaw === null) return;

      const payload = {
        title: String(newTitle).trim(),
        year: String(newYearRaw).trim() === "" ? null : Number(newYearRaw),
      };

      const old = btn.textContent;
      btn.disabled = true;
      btn.textContent = "A guardar…";

      try {
        await apiPost(`/admin/films/${filmId}/rematch`, payload, { auth: true });
        await load();
        alert("Atualizado e re-match feito.");
      } catch (e) {
        console.error(e);
        const { status, detail } = splitErr(e);
        alert(`Erro (${status ?? "?"}): ${detail}`);
      } finally {
        btn.disabled = false;
        btn.textContent = old;
      }
    });
  });
}

/* -----------------------------
   Render
------------------------------ */
function renderCurrent(week) {
  const status = $("currentStatus");
  const box = $("currentWeek");

  if (!week) {
    if (status) status.textContent = "Sem semana criada ainda.";
    if (box) box.innerHTML = "";
    $("startVoting").disabled = true;
    $("stopVoting").disabled = true;
    $("closeWeek").disabled = true;
    return;
  }

  status.innerHTML = `
    <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:6px">
      ${badge(`Week #${week.id}`)}
      ${badge(week.is_open ? "Aberta" : "Fechada")}
      ${badge(week.is_ready ? "Voting: ON" : "Voting: OFF")}
      ${(week.films || []).some(f => f.needs_review) ? badgeWarn("Há filmes a rever") : ""}
    </div>
  `;

  $("weekId").value = String(week.id);

  const filmsHtml = (week.films || []).map((f) => {
    const review = f.needs_review ? badgeWarn("REVER") : "";
    const ms = (f.match_score === null || f.match_score === undefined) ? "—" : String(f.match_score);

    return `
      <div class="admin-film">
        <div class="admin-left">
          <div class="admin-title">
            ${escapeHtml(f.title)} ${f.year ? `(${f.year})` : ""} ${review}
          </div>

          <div class="admin-meta">
            submitter_key: <code>${escapeHtml(f.submitter_key || "—")}</code> · votos: ${f.votes}
          </div>

          <div class="admin-meta">
            submitted: <strong>${escapeHtml(f.submitted_title || "—")}</strong> · ${f.submitted_year || "—"}
            · tmdb_id: ${f.tmdb_id ?? "—"} · score: ${ms}
          </div>
        </div>

        <div class="admin-right">
          ${f.needs_review ? `<button class="btn" data-rematch="${f.id}">Fix match</button>` : ""}
          <button class="btn" data-edit="${f.id}">Editar</button>
          ${f.poster_url ? `<a class="btn" target="_blank" href="${escapeHtml(f.poster_url)}">Poster</a>` : ""}
        </div>
      </div>
    `;
  }).join("");

  box.innerHTML = `
    <div style="margin-top:10px">
      <div class="muted">Winner film id: <strong>${week.winner_film_id ?? "—"}</strong></div>

      <div style="margin-top:10px" class="muted"><strong>Filmes</strong></div>

      <div class="admin-films">
        ${filmsHtml || `<div class="muted" style="margin-top:8px">Ainda sem filmes.</div>`}
      </div>
    </div>
  `;

  connectFilmButtons(week);

  $("startVoting").disabled = !!week.is_ready;
  $("stopVoting").disabled = !week.is_ready;
  $("closeWeek").disabled = !week.is_open;
}

/* -----------------------------
   Load (Admin endpoint)
   ✅ FIX: 404 => "no week yet" (do NOT redirect)
------------------------------ */
async function load() {
  try {
    const week = await apiGet("/admin/weeks/current", { auth: true });
    renderCurrent(week);
  } catch (e) {
    console.error(e);
    const { status } = splitErr(e);

    if (status === 404) {
      renderCurrent(null);
      return;
    }

    if (status === 401) clearToken();
    window.location.replace("index.html");
  }
}

/* -----------------------------
   Boot
------------------------------ */
document.addEventListener("DOMContentLoaded", async () => {
  // 🔒 bloqueia acesso direto
  const ok = await guardAdminOrRedirect();
  if (!ok) return;

  $("apiLabel").textContent = API;

  // auth buttons
  $("btnLogin")?.addEventListener("click", () => openAuthModal("login"));
  $("btnLogout")?.addEventListener("click", async () => {
    try { await apiPost("/auth/logout", {}, { auth: true }); } catch {}
    clearToken();
    await refreshAuthState();
    window.location.replace("index.html");
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
      const path = (mode === "register") ? "/auth/register" : "/auth/login";
      const out = await apiPost(path, { username, password }, { auth: false });

      if (out?.token) {
        setToken(out.token);

        // valida admin imediatamente
        const ok2 = await guardAdminOrRedirect();
        if (!ok2) return;

        closeAuthModal();
        await refreshAuthState();
        await load();
      } else {
        $("authMsg").textContent = "Resposta inválida do servidor.";
      }
    } catch (err) {
      const { status, detail } = splitErr(err);
      if (status === 409) $("authMsg").textContent = "Esse username já existe.";
      else if (status === 401) $("authMsg").textContent = "Credenciais inválidas.";
      else $("authMsg").textContent = String(detail || "Erro no login.");
      console.error(err);
    } finally {
      $("authSubmit").disabled = false;
    }
  });

  // admin buttons
  $("refresh").addEventListener("click", load);

  $("createWeek").addEventListener("click", async () => {
    const btn = $("createWeek");
    const title = $("newWeekTitle").value.trim();
    if (!title) return alert("Mete um título.");

    try {
      setBusy(btn, true, "A criar…");
      await apiPost("/admin/weeks", { title }, { auth: true });
      $("newWeekTitle").value = "";
      await load();
      alert("Semana criada.");
    } catch (e) {
      console.error(e);
      const { status, detail } = splitErr(e);
      alert(`Erro (${status ?? "?"}): ${detail}`);
    } finally {
      setBusy(btn, false);
    }
  });

  $("addFilm").addEventListener("click", async () => {
    const btn = $("addFilm");

    const weekId = Number($("weekId").value);
    const title = $("filmTitle").value.trim();
    const yearRaw = $("filmYear").value.trim();
    const director = $("filmDirector").value.trim();
    const submitter_key = $("submitterKey").value.trim();

    if (!weekId) return alert("Week ID inválido.");
    if (!title) return alert("Título obrigatório.");
    if (!submitter_key) return alert("submitter_key obrigatório.");

    const body = {
      title,
      year: yearRaw ? Number(yearRaw) : null,
      director: director || null,
      submitter_key,
    };

    try {
      setBusy(btn, true, "A adicionar…");
      await apiPost(`/admin/weeks/${weekId}/films`, body, { auth: true });

      $("filmTitle").value = "";
      $("filmYear").value = "";
      $("filmDirector").value = "";
      $("submitterKey").value = "";

      await load();
      alert("Filme adicionado.");
    } catch (e) {
      console.error(e);
      const { status, detail } = splitErr(e);
      alert(`Erro (${status ?? "?"}): ${detail}`);
    } finally {
      setBusy(btn, false);
    }
  });

  $("startVoting").addEventListener("click", async () => {
    const btn = $("startVoting");
    const weekId = Number($("weekId").value);
    if (!weekId) return alert("Week ID inválido.");

    try {
      setBusy(btn, true, "A abrir…");
      await apiPost(`/admin/weeks/${weekId}/start-voting`, {}, { auth: true });
      await load();
      alert("Votação aberta (is_ready=true).");
    } catch (e) {
      console.error(e);
      const { status, detail } = splitErr(e);
      alert(`Erro (${status ?? "?"}): ${detail}`);
    } finally {
      setBusy(btn, false);
    }
  });

  $("stopVoting").addEventListener("click", async () => {
    const btn = $("stopVoting");
    const weekId = Number($("weekId").value);
    if (!weekId) return alert("Week ID inválido.");

    try {
      setBusy(btn, true, "A parar…");
      await apiPost(`/admin/weeks/${weekId}/stop-voting`, {}, { auth: true });
      await load();
      alert("Votação pausada (is_ready=false).");
    } catch (e) {
      console.error(e);
      const { status, detail } = splitErr(e);
      alert(`Erro (${status ?? "?"}): ${detail}`);
    } finally {
      setBusy(btn, false);
    }
  });

  $("closeWeek").addEventListener("click", async () => {
    const btn = $("closeWeek");
    const weekId = Number($("weekId").value);
    if (!weekId) return alert("Week ID inválido.");

    try {
      setBusy(btn, true, "A fechar…");
      await apiPost(`/admin/weeks/${weekId}/close`, {}, { auth: true });
      await load();
      alert("Semana fechada (is_open=false).");
    } catch (e) {
      console.error(e);
      const { status, detail } = splitErr(e);
      alert(`Erro (${status ?? "?"}): ${detail}`);
    } finally {
      setBusy(btn, false);
    }
  });

  // init
  await refreshAuthState();
  await load();
});