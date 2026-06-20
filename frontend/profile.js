const API = "";
const TOKEN_KEY = "cinema_club_token";
const getToken = () => localStorage.getItem(TOKEN_KEY);

function el(id) { return document.getElementById(id); }
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));
}

/* ── Theme ── */
function initTheme() {
  const saved = localStorage.getItem("cc_theme") || "light";
  document.documentElement.setAttribute("data-theme", saved);
}
function toggleTheme() {
  const html = document.documentElement;
  html.classList.add("theme-transitioning");
  const next = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
  html.setAttribute("data-theme", next);
  localStorage.setItem("cc_theme", next);
  setTimeout(() => html.classList.remove("theme-transitioning"), 300);
}
initTheme();

async function apiGet(path) {
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API}${path}`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function starsHTML(r) {
  if (r == null) return "";
  return "★".repeat(Math.floor(r)) + (r % 1 >= 0.5 ? "½" : "");
}

function avatarEl(user, size = 72) {
  const url = user?.avatar_url;
  const name = user?.username || "?";
  if (url) return `<img class="lb-avatar" src="${escapeHtml(url)}" alt="${escapeHtml(name)}" style="width:${size}px;height:${size}px;border-radius:50%;object-fit:cover;border:3px solid var(--ink-10)" />`;
  const initials = name.slice(0, 2).toUpperCase();
  return `<div class="lb-avatar lb-avatar--initials" style="width:${size}px;height:${size}px;font-size:${Math.round(size * .35)}px;border-radius:50%">${escapeHtml(initials)}</div>`;
}

function formatDate(ts) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleDateString("pt", { day: "numeric", month: "short", year: "numeric" });
}

async function loadProfile() {
  // Get username from URL: /profile/username or ?u=username
  const path = window.location.pathname;
  const match = path.match(/\/profile\/([^/]+)/);
  const params = new URLSearchParams(window.location.search);
  const username = match?.[1] || params.get("u") || "";

  if (!username) {
    showError();
    return;
  }

  try {
    const data = await apiGet(`/users/${encodeURIComponent(username)}/profile`);
    await renderProfile(data);
  } catch (e) {
    showError();
  }
}

function showError() {
  el("profileLoading").style.display = "none";
  el("profileError").style.display = "";
}

async function renderProfile(data) {
  const { user, stats, reaction_counts, submitted_films, letterboxd_entries, most_successful_submitted_film } = data;

  el("profileLoading").style.display = "none";
  el("profileContent").style.display = "";

  // Set page title
  document.title = `@${user.username} — Clube de Cinema`;

  // Hero
  el("profileAvatar").innerHTML = avatarEl(user, 80);
  // Wrap nome + ranking numa linha
  const nameWrap = document.createElement("div");
  nameWrap.style.cssText = "display:flex;align-items:center;gap:10px;flex-wrap:wrap;";
  const nameSpan = document.createElement("h1");
  nameSpan.className = "profile-hero__name";
  nameSpan.textContent = `@${user.username}`;
  nameWrap.appendChild(nameSpan);

  const rank = stats.leaderboard_rank;
  if (rank !== null) {
    const badge = document.createElement("a");
    badge.href = "/leaderboard";
    badge.className = `profile-rank-badge profile-rank-badge--${rank <= 3 ? rank : "other"}`;
    badge.title = "Ver leaderboard";
    badge.textContent = `#${rank}`;
    nameWrap.appendChild(badge);
  }

  const nameEl = el("profileName");
  nameEl.replaceWith(nameWrap);

  const metaParts = [];
  if (user.letterboxd_username) {
    metaParts.push(`<a href="https://letterboxd.com/${escapeHtml(user.letterboxd_username)}/" target="_blank" rel="noopener" class="profile-lb-link">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M8 12l3 3 5-5" stroke-linecap="round" stroke-linejoin="round"/></svg>
      @${escapeHtml(user.letterboxd_username)}
    </a>`);
    if (user.letterboxd_synced_at) {
      metaParts.push(`Letterboxd atualizado ${escapeHtml(formatDate(user.letterboxd_synced_at))}`);
    }
  }
  el("profileMeta").innerHTML = metaParts.join(" · ");

  // Stats
  const statsEl = el("profileStats");
  const statItems = [
    { label: "Filmes submetidos", value: stats.films_submitted, icon: "🎬" },
    { label: "Vencedores", value: stats.films_won, icon: "🏆" },
    { label: "Taxa de vitória", value: `${stats.win_rate}%`, icon: "📊" },
    { label: "Votos dados", value: stats.votes_cast, icon: "🗳️" },
  ];
  statsEl.innerHTML = statItems.map(s => `
    <div class="profile-stat">
      <div class="profile-stat__icon">${s.icon}</div>
      <div class="profile-stat__value">${escapeHtml(String(s.value))}</div>
      <div class="profile-stat__label">${escapeHtml(s.label)}</div>
    </div>
  `).join("");

  const bestEl = el("profileBestFilm");
  if (bestEl && most_successful_submitted_film) {
    const f = most_successful_submitted_film;
    bestEl.innerHTML = `
      <div class="profile-best-film">
        ${f.poster_url
          ? `<img src="${escapeHtml(f.poster_url)}" alt="${escapeHtml(f.title)}" loading="lazy" />`
          : `<div class="profile-best-film__ph">${escapeHtml((f.title || "?").slice(0,2).toUpperCase())}</div>`
        }
        <div>
          <div class="kicker kicker--soft">Melhor submissao</div>
          <div class="profile-best-film__title">${escapeHtml(f.title)}${f.year ? ` (${escapeHtml(String(f.year))})` : ""}</div>
          <div class="profile-best-film__meta">${escapeHtml(f.week_title || "")} - ${f.votes} voto${f.votes !== 1 ? "s" : ""}${f.is_winner ? " - vencedor" : ""}</div>
        </div>
      </div>
    `;
  }

  // Reactions given
  const reactionsEl = el("profileReactions");
  const reactionEntries = Object.entries(reaction_counts);
  if (reactionEntries.length > 0) {
    reactionsEl.innerHTML = `
      <div class="profile-reactions__label">Reações dadas</div>
      <div class="profile-reactions__chips">
        ${reactionEntries.map(([emoji, count]) => `
          <span class="reaction-chip">${emoji} <span class="reaction-chip__count">${count}</span></span>
        `).join("")}
      </div>
    `;
  }

  // Submitted films grid
  const filmsEl = el("profileFilms");
  if (!submitted_films.length) {
    filmsEl.innerHTML = `<p class="muted">Ainda não submeteu nenhum filme.</p>`;
  } else {
    filmsEl.innerHTML = submitted_films.map(f => `
      <div class="profile-film-card ${f.is_winner ? "profile-film-card--winner" : ""}">
        <div class="profile-film-card__poster">
          ${f.poster_url
            ? `<img src="${escapeHtml(f.poster_url)}" alt="${escapeHtml(f.title)}" loading="lazy" />`
            : `<div class="profile-film-card__poster-ph">${escapeHtml((f.title||"").slice(0,2).toUpperCase())}</div>`
          }
          ${f.is_winner ? `<div class="profile-film-card__trophy">🏆</div>` : ""}
        </div>
        <div class="profile-film-card__body">
          <div class="profile-film-card__week">${escapeHtml(f.week_title || "")}</div>
          <div class="profile-film-card__title">${escapeHtml(f.title)}${f.year ? ` <span class="profile-film-card__year">(${f.year})</span>` : ""}</div>
          ${f.director ? `<div class="profile-film-card__dir">Dir. ${escapeHtml(f.director)}</div>` : ""}
          <div class="profile-film-card__votes">${f.votes} voto${f.votes !== 1 ? "s" : ""}</div>
        </div>
      </div>
    `).join("");
  }

  // Letterboxd diary
  if (letterboxd_entries.length > 0) {
    el("profileLbSection").style.display = "";
    el("profileLbList").innerHTML = letterboxd_entries.map(e => `
      <a class="profile-lb-entry" href="${escapeHtml(e.letterboxd_url || "#")}" target="_blank" rel="noopener">
        <div class="profile-lb-entry__title">${escapeHtml(e.film_title)}${e.film_year ? ` <span class="profile-lb-entry__year">(${e.film_year})</span>` : ""}</div>
        <div class="profile-lb-entry__right">
          ${e.rating != null ? `<span class="profile-lb-entry__stars">${starsHTML(e.rating)}</span>` : ""}
          <span class="profile-lb-entry__date">${formatDate(e.watched_date)}</span>
        </div>
      </a>
    `).join("");
  }
}

/* ── Boot ── */
document.addEventListener("DOMContentLoaded", async () => {
  el("btnTheme")?.addEventListener("click", toggleTheme);

  // Auth state (just for display)
  const token = getToken();
  if (token) {
    try {
      const me = await apiGet("/auth/me");
      const line = el("authStatusLine");
      if (line) line.innerHTML = `<a href="/profile/${encodeURIComponent(me.username)}" style="color:inherit;text-decoration:none">@${escapeHtml(me.username)}</a>`;
      const avatar = el("authAvatarPill");
      if (avatar && me.avatar_url) {
        avatar.innerHTML = `<img class="lb-avatar" src="${escapeHtml(me.avatar_url)}" width="28" height="28" style="border-radius:50%;object-fit:cover" />`;
        avatar.style.display = "";
        avatar.style.cursor = "pointer";
        avatar.onclick = () => window.location.href = `/profile/${encodeURIComponent(me.username)}`;
      }
      el("btnLogout")?.style && (el("btnLogout").style.display = "");
      el("btnLogin")?.style && (el("btnLogin").style.display = "none");
    } catch {}
  } else {
    el("btnLogin").style.display = "";
  }

  el("btnLogout")?.addEventListener("click", () => {
    localStorage.removeItem(TOKEN_KEY);
    window.location.href = "/";
  });

  el("btnLogin")?.addEventListener("click", () => {
    window.location.href = "/";
  });

  await loadProfile();
});
