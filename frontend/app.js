/* =============================================
   Clube de Cinema — app.js (index page)
   ============================================= */

const API = "";

function el(id) { return document.getElementById(id); }

function escapeHtml(s) {
  return String(s).replace(/[&<>\"']/g, (c) => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  }[c]));
}

/* ── Auth storage ── */
const TOKEN_KEY = "cinema_club_token";
function getToken() { return localStorage.getItem(TOKEN_KEY); }
function setToken(t) { localStorage.setItem(TOKEN_KEY, t); }
function clearToken() { localStorage.removeItem(TOKEN_KEY); }
function votedKey(weekId) { return `cinema_club_voted_week_${weekId}`; }

/* ── Letterboxd member cache ── */
let _lbMembers = null; // { userId: {avatar_url, username, letterboxd_username} }

async function getLbMembers() {
  if (_lbMembers) return _lbMembers;
  try {
    const list = await apiGet("/letterboxd/members");
    _lbMembers = {};
    for (const m of list) _lbMembers[m.user_id] = m;
  } catch { _lbMembers = {}; }
  return _lbMembers;
}

function invalidateLbCache() { _lbMembers = null; }

/* ── Reactions ── */
const REACTION_EMOJIS = ["👍", "😐", "67", "🇮🇱"];
function encodeEmoji(e) { return encodeURIComponent(e).replace(/%/g, "_"); }

async function loadReactions(filmId) {
  try {
    const [counts, mine] = await Promise.all([
      apiGet(`/films/${filmId}/reactions`),
      getToken() ? apiGet(`/films/${filmId}/reactions/me`, { auth: true }) : Promise.resolve({ emoji: null }),
    ]);

    const chipsEl = document.getElementById(`chips-${filmId}`);
    if (!chipsEl) return;

    // Render only emojis that have at least 1 reaction
    const html = REACTION_EMOJIS
      .filter(e => (counts.counts?.[e] || 0) > 0)
      .map(e => {
        const count = counts.counts[e];
        const isMe = mine.emoji === e;
        return `<button class="reaction-chip${isMe ? " reaction-chip--mine" : ""}" data-film="${filmId}" data-emoji="${escapeHtml(e)}" title="${escapeHtml(e)}">
          <span>${e}</span><span class="reaction-chip__count">${count}</span>
        </button>`;
      }).join("");

    chipsEl.innerHTML = html;

    // Mark picker button active if user has reacted
    const addBtn = document.querySelector(`.reaction-add-btn[data-film="${filmId}"]`);
    if (addBtn) addBtn.classList.toggle("reaction-add-btn--active", !!mine.emoji);
  } catch {}
}

async function toggleReaction(filmId, emoji) {
  if (!getToken()) { toast("Precisas de login para reagir.", "info"); openAuthModal("login"); return; }
  try {
    const res = await apiPost(`/films/${filmId}/reactions`, { emoji }, { auth: true });
    await loadReactions(filmId);
  } catch (e) {
    toast(String(e?.message || "Erro."), "error");
  }
}

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

/* ── Current user (global) ── */
let _currentUser = null;

/* ── Auth state ── */
async function refreshAuthState() {
  const line = el("authStatusLine");
  const btnLogin = el("btnLogin");
  const btnLogout = el("btnLogout");
  const navAdmin = el("navAdmin");

  if (navAdmin) navAdmin.style.display = "none";

  const token = getToken();
  if (!token) {
    _currentUser = null;
    if (line) line.textContent = "Não autenticado.";
    if (btnLogin) btnLogin.style.display = "";
    if (btnLogout) btnLogout.style.display = "none";
    const avatarPillOut = el("authAvatarPill");
    if (avatarPillOut) avatarPillOut.style.display = "none";
    const btnLbOut = el("btnLetterboxd");
    if (btnLbOut) btnLbOut.style.display = "none";
    return null;
  }

  try {
    const me = await apiGet("/auth/me", { auth: true });
    _currentUser = me;

    // Update avatar in header
    updateHeaderAvatar(me);
    const avatarPill = el("authAvatarPill");
    if (avatarPill) avatarPill.style.display = me.letterboxd_avatar_url ? "" : "none";
    const btnLb = el("btnLetterboxd");
    if (btnLb) {
      btnLb.style.display = "";
      btnLb.title = me.letterboxd_username ? `Letterboxd: @${me.letterboxd_username}` : "Ligar Letterboxd";
      btnLb.classList.toggle("lb-connect-btn--connected", !!me.letterboxd_username);
    }

    if (line) {
      line.innerHTML = `<a class="auth-pill__user--link" href="/profile/${encodeURIComponent(me.username)}">@${escapeHtml(me.username)}</a>`;
    }
    if (btnLogin) btnLogin.style.display = "none";
    if (btnLogout) btnLogout.style.display = "";
    if (navAdmin && me?.is_admin) navAdmin.style.display = "";

    // Show letterboxd connect popup if not yet connected
    if (!me.letterboxd_username) {
      setTimeout(() => showLetterboxdPopup(), 800);
    }

    return me;
  } catch {
    _currentUser = null;
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

/* ── Avatar helpers ── */
function avatarHTML(user, size = 28) {
  const url = user?.avatar_url || user?.letterboxd_avatar_url;
  const name = user?.username || "?";
  if (url) {
    return `<img class="lb-avatar" src="${escapeHtml(url)}" alt="${escapeHtml(name)}" title="@${escapeHtml(name)}" width="${size}" height="${size}" style="width:${size}px;height:${size}px" />`;
  }
  const initials = name.slice(0, 2).toUpperCase();
  return `<div class="lb-avatar lb-avatar--initials" title="@${escapeHtml(name)}" style="width:${size}px;height:${size}px;font-size:${Math.round(size*0.38)}px">${escapeHtml(initials)}</div>`;
}

function updateHeaderAvatar(me) {
  let pill = el("authAvatarPill");
  if (!pill) return;
  const url = me?.letterboxd_avatar_url;
  if (url) {
    pill.innerHTML = `<img class="lb-avatar" src="${escapeHtml(url)}" alt="@${escapeHtml(me.username)}" width="28" height="28" />`;
  } else {
    pill.textContent = (me?.username || "?").slice(0, 2).toUpperCase();
  }
}

/* ── Letterboxd connect / settings popup ── */
function showLetterboxdPopup() {
  if (el("lbPopup")) el("lbPopup").remove();

  const me = _currentUser;
  const isConnected = !!(me?.letterboxd_username);
  const avatarUrl = me?.avatar_url || "";

  const pop = document.createElement("div");
  pop.id = "lbPopup";
  pop.innerHTML = `
    <div class="lb-popup__panel">
      <button class="lb-popup__close" id="lbPopupClose" type="button" aria-label="Fechar">✕</button>

      <div class="lb-popup__title">Perfil</div>

      <!-- Avatar upload -->
      <div class="lb-popup__avatar-row">
        <div class="lb-popup__avatar-preview" id="lbAvatarPreview">
          ${avatarUrl
            ? `<img src="${escapeHtml(avatarUrl)}" alt="avatar" />`
            : `<div class="lb-avatar lb-avatar--initials" style="width:60px;height:60px;font-size:20px">${escapeHtml((me?.username||"?").slice(0,2).toUpperCase())}</div>`
          }
        </div>
        <div class="lb-popup__avatar-inputs">
          <div class="lb-popup__label">Foto de perfil</div>
          <label class="lb-popup__upload-btn" for="lbAvatarFile">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            Escolher imagem
          </label>
          <input type="file" id="lbAvatarFile" accept="image/*" style="display:none" />
          <div class="lb-popup__avatar-hint">JPG, PNG ou GIF · máx 2MB</div>
          <button class="btn primary" id="lbAvatarSave" type="button" style="display:none;margin-top:4px">Guardar foto</button>
        </div>
      </div>

      ${isConnected
        ? `<div class="lb-popup__logo">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/><path d="M8 12l3 3 5-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            Letterboxd · <strong>@${escapeHtml(me.letterboxd_username)}</strong>
          </div>`
        : `<div class="lb-popup__logo">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/><path d="M8 12l3 3 5-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            Letterboxd
          </div>
          <div class="lb-popup__sub">Liga para ver quem viu os filmes e as suas avaliações.</div>`
      }

      <!-- Username -->
      <label class="lb-popup__label">Username do Letterboxd</label>
      <div style="display:flex;gap:8px">
        <input id="lbPopupInput" class="input" placeholder="username" value="${escapeHtml(me?.letterboxd_username || "")}" autocomplete="off" style="flex:1" />
        <button class="btn primary" id="lbPopupSave" type="button">${isConnected ? "Atualizar" : "Ligar"}</button>
      </div>

      <div class="lb-popup__msg" id="lbPopupMsg"></div>

      ${isConnected ? `<button class="btn lb-popup__sync" id="lbPopupSync" type="button">↻ Sincronizar Letterboxd</button>` : ""}
      <button class="btn ghost lb-popup__skip" id="lbPopupSkip" type="button">Fechar</button>
    </div>
  `;
  document.body.appendChild(pop);

  // Close
  el("lbPopupClose")?.addEventListener("click", () => pop.remove());
  el("lbPopupSkip")?.addEventListener("click", () => pop.remove());

  // Clicking the preview also opens file picker
  el("lbAvatarPreview")?.addEventListener("click", () => el("lbAvatarFile")?.click());

  // File picker → base64 preview
  el("lbAvatarFile")?.addEventListener("change", (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 2_500_000) {
      el("lbPopupMsg").textContent = "Imagem demasiado grande (máx 2MB).";
      return;
    }
    const reader = new FileReader();
    reader.onload = (ev) => {
      const dataUrl = ev.target.result;
      el("lbAvatarPreview").innerHTML = `<img src="${escapeHtml(dataUrl)}" alt="avatar" />`;
      el("lbAvatarSave").style.display = "";
      el("lbAvatarSave").dataset.dataUrl = dataUrl;
    };
    reader.readAsDataURL(file);
  });

  // Save avatar
  el("lbAvatarSave")?.addEventListener("click", async () => {
    const dataUrl = el("lbAvatarSave").dataset.dataUrl;
    if (!dataUrl) return;
    const btn = el("lbAvatarSave");
    btn.disabled = true; btn.textContent = "A guardar…";
    try {
      await apiPatch("/auth/avatar", { avatar_url: dataUrl }, { auth: true });
      invalidateLbCache();
      await refreshAuthState();
      const msg = el("lbPopupMsg");
      if (msg) { msg.textContent = "Foto atualizada ✓"; msg.style.color = "#2a9d5c"; }
      btn.style.display = "none";
      setTimeout(() => { if (el("lbPopupMsg")) { el("lbPopupMsg").textContent = ""; el("lbPopupMsg").style.color = ""; } }, 2500);
    } catch (e) {
      const msg = el("lbPopupMsg");
      if (msg) { msg.textContent = String(e?.message || "Erro ao guardar."); msg.style.color = ""; }
      btn.disabled = false; btn.textContent = "Guardar foto";
    }
  });

  // Save username + sync
  el("lbPopupSave")?.addEventListener("click", async () => {
    const username = (el("lbPopupInput")?.value || "").trim();
    if (!username) { el("lbPopupMsg").textContent = "Introduz o teu username."; return; }
    const btn = el("lbPopupSave");
    btn.disabled = true; btn.textContent = "A ligar…";
    el("lbPopupMsg").textContent = "";
    try {
      const res = await apiPatch("/auth/letterboxd", { letterboxd_username: username }, { auth: true });
      if (res.error && res.synced === 0) {
        el("lbPopupMsg").textContent = `Erro: ${res.error}`;
        btn.disabled = false; btn.textContent = isConnected ? "Atualizar" : "Ligar";
        return;
      }
      invalidateLbCache();
      toast(`Letterboxd ligado! ${res.synced} entradas sincronizadas.`, "success", 4000);
      pop.remove();
      await refreshAuthState();
      await load();
    } catch (e) {
      el("lbPopupMsg").textContent = String(e?.message || "Erro ao ligar.");
      btn.disabled = false; btn.textContent = isConnected ? "Atualizar" : "Ligar";
    }
  });

  // Manual sync
  el("lbPopupSync")?.addEventListener("click", async () => {
    const btn = el("lbPopupSync");
    btn.disabled = true; btn.textContent = "A sincronizar…";
    try {
      const res = await apiPost("/auth/letterboxd/sync", {}, { auth: true });
      invalidateLbCache();
      await refreshAuthState();
      toast(`Sincronizado! ${res.synced} entradas.`, "success", 3000);
      const msg = el("lbPopupMsg");
      if (msg) { msg.textContent = `Última sync: agora · ${res.synced} entradas`; msg.style.color = "#2a9d5c"; }
    } catch (e) {
      const msg = el("lbPopupMsg");
      if (msg) { msg.textContent = String(e?.message || "Erro na sync."); msg.style.color = ""; }
    } finally { btn.disabled = false; btn.textContent = "↻ Sincronizar Letterboxd"; }
  });

  el("lbPopupInput")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") el("lbPopupSave")?.click();
  });

  requestAnimationFrame(() => pop.classList.add("lb-popup--visible"));
}

/* ── HTTP PATCH helper ── */
async function apiPatch(path, body, { auth = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && getToken()) headers["Authorization"] = `Bearer ${getToken()}`;
  const res = await fetch(`${API}${path}`, { method: "PATCH", headers, body: JSON.stringify(body ?? {}) });
  if (!res.ok) {
    const err = await parseError(res);
    throw Object.assign(new Error(err.detail), { status: err.status });
  }
  return res.json();
}

/* ── Letterboxd watcher strip ── */
async function buildWatcherStrip(tmdbId) {
  if (!tmdbId) return "";
  try {
    const watchers = await apiGet(`/letterboxd/film/${tmdbId}`);
    if (!watchers || watchers.length === 0) return "";

    const stars = (r) => {
      if (r == null) return "";
      const full = Math.floor(r);
      const half = (r % 1) >= 0.5 ? 1 : 0;
      return "★".repeat(full) + (half ? "½" : "");
    };

    const avatars = watchers.map(w => {
      const lbUser = w.letterboxd_username || w.username;
      return `<span class="lb-watcher" title="@${escapeHtml(lbUser)}${w.rating != null ? ` · ${stars(w.rating)}` : ''}">
        ${avatarHTML(w, 24)}
        ${w.rating != null ? `<span class="lb-watcher__stars">${stars(w.rating)}</span>` : ""}
      </span>`;
    }).join("");

    return `<div class="lb-strip"><span class="lb-strip__label">Visto por</span><div class="lb-strip__avatars">${avatars}</div></div>`;
  } catch {
    return "";
  }
}

/* ── Poster HTML ── */
function posterHTML(f) {
  const lbQuery = f.tmdb_id
    ? `tmdb:${f.tmdb_id}`
    : encodeURIComponent(`${f.title}${f.year ? ` ${f.year}` : ""}`);
  const letterboxdUrl = `https://letterboxd.com/search/${lbQuery}/`;

  const vidkingUrl = f.tmdb_id
    ? `https://www.vidking.net/embed/movie/${f.tmdb_id}`
    : `https://www.vidking.net/search/${encodeURIComponent(f.title + (f.year ? ` ${f.year}` : ""))}`;
  const vidkingIsEmbed = !!f.tmdb_id;

  const posterContent = f.poster_url
    ? `<img src="${escapeHtml(f.poster_url)}" alt="${escapeHtml(f.title)}" loading="lazy"/>`
    : `<span>${escapeHtml((f.title || "").split(" ").slice(0,2).map(s => s[0]?.toUpperCase()).join("") || "🎬")}</span>`;

  const posterClass = f.poster_url ? "poster" : "poster placeholder";

  return `
    <div class="${posterClass}" data-letterboxd="${escapeHtml(letterboxdUrl)}" data-vidking="${escapeHtml(vidkingUrl)}" data-title="${escapeHtml(f.title)}">
      ${posterContent}
      <div class="poster-overlay">
        <a class="poster-btn poster-btn--know" href="${escapeHtml(letterboxdUrl)}" target="_blank" rel="noopener noreferrer">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
          Saber mais
        </a>
        <button class="poster-btn poster-btn--play" data-vidking="${escapeHtml(vidkingUrl)}" data-embed="${vidkingIsEmbed ? '1' : '0'}" data-title="${escapeHtml(f.title)}">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          Reproduzir
        </button>
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
          <iframe id="playerIframe" allowfullscreen allow="fullscreen; picture-in-picture" frameborder="0"></iframe>
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
        <div class="lb-strip-placeholder"></div>
      </div>
      <div class="reaction-bar" id="reactions-${f.id}">
        <div class="reaction-add-wrap">
          <button class="reaction-add-btn" data-film="${f.id}" title="Reagir">😊</button>
          <div class="reaction-picker" id="picker-${f.id}">
            ${REACTION_EMOJIS.map(e => `
              <button class="reaction-picker__btn" data-film="${f.id}" data-emoji="${escapeHtml(e)}">${e}</button>
            `).join("")}
          </div>
        </div>
        <div class="reaction-chips" id="chips-${f.id}"></div>
      </div>
      <div class="film-actions">
        <button class="btn${canVote ? " primary" : ""}" ${canVote ? "" : "disabled"}>
          ${btnLabel}
        </button>
        ${isWinner ? `<span class="badge badge--open">Vencedor</span>` : ""}
      </div>
    </div>
  `;

  // Async: inject watcher strip once loaded
  if (f.tmdb_id) {
    buildWatcherStrip(f.tmdb_id).then(html => {
      const placeholder = div.querySelector(".lb-strip-placeholder");
      if (placeholder && html) placeholder.outerHTML = html;
      else if (placeholder) placeholder.remove();
    });
  } else {
    div.querySelector(".lb-strip-placeholder")?.remove();
  }

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
  _chatWeekId = week.id;
  el("weekTitle").textContent = week.title;
  el("heroTitle").textContent = week.title;

  // Show chat button
  const btnChat = el("btnChat");
  if (btnChat) btnChat.style.display = "";

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

  shown.forEach(f => {
    filmsEl.appendChild(filmCard(week, f, alreadyVoted));
    loadReactions(f.id);
  });

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

  // Load "visto pelo clube" section independently
  loadClubWatched();
}

/* ── "Visto pelo Clube" section ── */
async function loadClubWatched() {
  const section = el("clubWatchedSection");
  if (!section) return;

  try {
    // Get last 5 closed weeks with winners
    const weeks = await apiGet("/weeks");
    const winners = weeks
      .filter(w => !w.is_open && w.winner_film_id)
      .slice(0, 5);

    if (!winners.length) { section.style.display = "none"; return; }

    // For each winner fetch letterboxd data
    const cards = await Promise.all(winners.map(async (w) => {
      const win = (w.films || []).find(f => Number(f.id) === Number(w.winner_film_id));
      if (!win) return null;

      let watchers = [];
      if (win.tmdb_id) {
        try { watchers = await apiGet(`/letterboxd/film/${win.tmdb_id}`); } catch {}
      }
      return { week: w, film: win, watchers };
    }));

    const valid = cards.filter(Boolean);
    if (!valid.length) { section.style.display = "none"; return; }

    // Only show section if at least one film has watchers
    const hasAnyWatchers = valid.some(c => c.watchers.length > 0);

    section.style.display = "";
    const grid = el("clubWatchedGrid");
    if (!grid) return;
    grid.innerHTML = "";

    valid.forEach(({ week: w, film, watchers }) => {
      const card = buildWatchedCard(w, film, watchers);
      grid.appendChild(card);
    });

    // Hide section header hint if no watchers at all
    const hint = el("clubWatchedHint");
    if (hint) hint.textContent = hasAnyWatchers
      ? "O que o clube achou dos vencedores recentes."
      : "Liga o teu Letterboxd para ver quem viu o quê.";

  } catch (e) {
    section.style.display = "none";
  }
}

function starsHTML(rating) {
  if (rating == null) return "";
  const full = Math.floor(rating);
  const half = (rating % 1) >= 0.5;
  let s = "★".repeat(full);
  if (half) s += "½";
  return s;
}

function buildWatchedCard(week, film, watchers) {
  const div = document.createElement("div");
  div.className = "watched-card";

  const raters = watchers.filter(w => w.rating != null);
  const avg = raters.length
    ? (raters.reduce((s, w) => s + w.rating, 0) / raters.length).toFixed(1)
    : null;

  // Watcher avatars — each is a link to their Letterboxd profile
  const watcherAvatars = watchers.map(w => {
    const lbUser = w.letterboxd_username || w.username;
    const stars = starsHTML(w.rating);
    const tip = `@${lbUser}${w.rating != null ? ` · ${stars}` : ""}`;
    const href = `https://letterboxd.com/${encodeURIComponent(lbUser)}/`;

    const avatarEl = w.avatar_url
      ? `<img class="wc-avatar" src="${escapeHtml(w.avatar_url)}" alt="@${escapeHtml(lbUser)}" title="${escapeHtml(tip)}" width="36" height="36"/>`
      : `<div class="wc-avatar wc-avatar--initials" title="${escapeHtml(tip)}">${escapeHtml(lbUser.slice(0,2).toUpperCase())}</div>`;

    return `<a class="wc-watcher" href="${href}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(tip)}">
      ${avatarEl}
      ${stars ? `<span class="wc-stars">${escapeHtml(stars)}</span>` : `<span class="wc-stars" style="opacity:0">·</span>`}
    </a>`;
  }).join("");

  const noWatchers = watchers.length === 0;

  // avg badge shown on poster on hover
  const avgBadge = avg != null ? `
    <div class="wc-avg-badge">
      <span class="wc-avg-badge__stars">${escapeHtml(starsHTML(parseFloat(avg)))}</span>
      <span class="wc-avg-badge__num">${avg}</span>
    </div>` : "";

  div.innerHTML = `
    <div class="wc-poster-wrap">
      ${film.poster_url
        ? `<img class="wc-poster" src="${escapeHtml(film.poster_url)}" alt="${escapeHtml(film.title)}" loading="lazy"/>`
        : `<div class="wc-poster wc-poster--ph">${escapeHtml((film.title||"").slice(0,2).toUpperCase())}</div>`
      }
      <div class="wc-trophy">🏆</div>
      ${avgBadge}
    </div>
    <div class="wc-body">
      <div class="wc-week">${escapeHtml(week.title)}</div>
      <div class="wc-title">${escapeHtml(film.title)}${film.year ? `<span class="wc-year"> (${film.year})</span>` : ""}</div>
      ${film.director ? `<div class="wc-director">Dir. ${escapeHtml(film.director)}</div>` : ""}
      ${!noWatchers ? `
        <div class="wc-watchers">
          <div class="wc-watchers__label">Visto por</div>
          <div class="wc-watchers__row">${watcherAvatars}</div>
        </div>
      ` : `<div class="wc-unseen">Ninguém viu ainda</div>`}
    </div>
  `;

  return div;
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

/* ── Theme toggle ── */
function initTheme() {
  const saved = localStorage.getItem("cc_theme") || "light";
  document.documentElement.setAttribute("data-theme", saved);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("cc_theme", next);
}

initTheme();

/* ── Chat ── */
let _chatWeekId = null;
let _chatPollInterval = null;
let _chatLastCount = 0;

function openChat(weekId, weekTitle) {
  _chatWeekId = weekId;
  el("chatWeekLabel").textContent = weekTitle || `Semana #${weekId}`;
  el("chatPanel").classList.add("chat-panel--open");
  el("chatOverlay").classList.add("chat-overlay--visible");
  document.body.style.overflow = "hidden";
  el("chatBadge").style.display = "none";
  _chatLastCount = 0;
  fetchChat();
  _chatPollInterval = setInterval(fetchChat, 6000);
  setTimeout(() => el("chatInput")?.focus(), 300);
}

function closeChat() {
  el("chatPanel").classList.remove("chat-panel--open");
  el("chatOverlay").classList.remove("chat-overlay--visible");
  document.body.style.overflow = "";
  if (_chatPollInterval) { clearInterval(_chatPollInterval); _chatPollInterval = null; }
}

async function fetchChat() {
  if (!_chatWeekId) return;
  try {
    const msgs = await apiGet(`/weeks/${_chatWeekId}/chat`);
    renderChatMessages(msgs);
    // Update badge if panel closed
    if (!el("chatPanel").classList.contains("chat-panel--open") && msgs.length > _chatLastCount) {
      el("chatBadge").style.display = "";
      el("chatBadge").textContent = msgs.length - _chatLastCount;
    }
  } catch {}
}

function renderChatMessages(msgs) {
  const container = el("chatMessages");
  const empty = el("chatEmpty");
  if (!msgs.length) { if (empty) empty.style.display = ""; return; }
  if (empty) empty.style.display = "none";

  const wasAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 60;
  const prevCount = container.querySelectorAll(".chat-msg").length;

  // Only re-render if count changed
  if (msgs.length === prevCount) return;

  container.innerHTML = "";
  const me = _currentUser;

  msgs.forEach(msg => {
    const isMe = me && msg.user.id === me.id;
    const div = document.createElement("div");
    div.className = `chat-msg ${isMe ? "chat-msg--me" : ""}`;
    div.dataset.id = msg.id;

    const avatar = msg.user.avatar_url
      ? `<img class="lb-avatar chat-msg__avatar" src="${escapeHtml(msg.user.avatar_url)}" alt="${escapeHtml(msg.user.username)}" width="28" height="28"/>`
      : `<div class="lb-avatar lb-avatar--initials chat-msg__avatar" style="width:28px;height:28px;font-size:10px">${escapeHtml(msg.user.username.slice(0,2).toUpperCase())}</div>`;

    const time = new Date(msg.created_at * 1000).toLocaleTimeString("pt", { hour: "2-digit", minute: "2-digit" });

    div.innerHTML = `
      ${!isMe ? avatar : ""}
      <div class="chat-msg__bubble">
        ${!isMe ? `<div class="chat-msg__name">${escapeHtml(msg.user.username)}</div>` : ""}
        <div class="chat-msg__text">${escapeHtml(msg.content)}</div>
        <div class="chat-msg__time">${time}${isMe ? ` <button class="chat-msg__del" data-id="${msg.id}" title="Apagar">✕</button>` : ""}</div>
      </div>
      ${isMe ? avatar : ""}
    `;
    container.appendChild(div);
  });

  if (wasAtBottom || msgs.length !== prevCount) {
    container.scrollTop = container.scrollHeight;
  }

  _chatLastCount = msgs.length;
}

async function sendChatMessage() {
  if (!getToken()) { toast("Precisas de login para comentar.", "info"); openAuthModal("login"); return; }
  if (!_chatWeekId) return;
  const input = el("chatInput");
  const content = (input.value || "").trim();
  if (!content) return;

  const btn = el("chatSend");
  btn.disabled = true;
  input.disabled = true;

  try {
    await apiPost(`/weeks/${_chatWeekId}/chat`, { content }, { auth: true });
    input.value = "";
    input.style.height = "auto";
    await fetchChat();
  } catch (e) {
    toast(String(e?.message || "Erro ao enviar."), "error");
  } finally {
    btn.disabled = false;
    input.disabled = false;
    input.focus();
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

  // Permanent delegated handler for play buttons
  el("films")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".poster-btn--play");
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    const url = btn.dataset.vidking;
    const title = btn.dataset.title;
    const isEmbed = btn.dataset.embed === "1";
    if (!url) return;
    if (isEmbed) openPlayerModal(url, title);
    else window.open(url, "_blank", "noopener,noreferrer");
  });

  // Reaction picker toggle
  el("films")?.addEventListener("click", (e) => {
    const addBtn = e.target.closest(".reaction-add-btn");
    if (addBtn) {
      e.preventDefault(); e.stopPropagation();
      const picker = addBtn.closest(".reaction-add-wrap")?.querySelector(".reaction-picker");
      document.querySelectorAll(".reaction-picker--open").forEach(p => {
        if (p !== picker) p.classList.remove("reaction-picker--open");
      });
      picker?.classList.toggle("reaction-picker--open");
      return;
    }
    // Picker emoji click
    const pickerBtn = e.target.closest(".reaction-picker__btn");
    if (pickerBtn) {
      e.preventDefault(); e.stopPropagation();
      pickerBtn.closest(".reaction-picker")?.classList.remove("reaction-picker--open");
      toggleReaction(pickerBtn.dataset.film, pickerBtn.dataset.emoji);
      return;
    }
    // Chip click (toggle off)
    const chip = e.target.closest(".reaction-chip");
    if (chip) {
      e.preventDefault(); e.stopPropagation();
      toggleReaction(chip.dataset.film, chip.dataset.emoji);
      return;
    }
  });

  // Close picker when clicking outside
  document.addEventListener("click", () => {
    document.querySelectorAll(".reaction-picker--open").forEach(p => p.classList.remove("reaction-picker--open"));
  });

  // Chat delete delegation
  el("chatMessages")?.addEventListener("click", async (e) => {
    const btn = e.target.closest(".chat-msg__del");
    if (!btn) return;
    const id = btn.dataset.id;
    try {
      await fetch(`${API}/chat/${id}`, { method: "DELETE", headers: { Authorization: `Bearer ${getToken()}` } });
      await fetchChat();
    } catch {}
  });

  // Chat panel
  el("btnChat")?.addEventListener("click", () => {
    if (_chatWeekId) openChat(_chatWeekId, el("weekTitle")?.textContent);
  });
  el("chatClose")?.addEventListener("click", closeChat);
  el("chatOverlay")?.addEventListener("click", closeChat);
  el("chatSend")?.addEventListener("click", sendChatMessage);
  el("chatInput")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChatMessage(); }
  });
  el("chatInput")?.addEventListener("input", (e) => {
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
  });

  el("btnTheme")?.addEventListener("click", toggleTheme);

  // Letterboxd settings button + avatar both open popup
  el("btnLetterboxd")?.addEventListener("click", () => showLetterboxdPopup());
  el("authAvatarPill")?.addEventListener("click", () => { if (getToken()) showLetterboxdPopup(); });
});