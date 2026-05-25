const API = "";
const TOKEN_KEY = "cinema_club_token";
const getToken = () => localStorage.getItem(TOKEN_KEY);

function el(id) { return document.getElementById(id); }
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));
}

/* ── Theme ── */
function initTheme() {
  document.documentElement.setAttribute("data-theme", localStorage.getItem("cc_theme") || "light");
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

/* ── Auth ── */
async function initAuth() {
  const token = getToken();
  if (!token) { el("btnLogin").style.display = ""; return; }
  try {
    const res = await fetch(`${API}/auth/me`, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) { el("btnLogin").style.display = ""; return; }
    const me = await res.json();
    el("authStatusLine").innerHTML = `<a href="/profile/${encodeURIComponent(me.username)}" style="color:inherit;text-decoration:none">@${escapeHtml(me.username)}</a>`;
    el("btnLogout").style.display = "";
    if (me.avatar_url) {
      el("authAvatarPill").innerHTML = `<img src="${escapeHtml(me.avatar_url)}" style="width:28px;height:28px;border-radius:50%;object-fit:cover"/>`;
      el("authAvatarPill").style.display = "";
    }
    if (me.is_admin) { const n = el("navAdmin"); if (n) n.style.display = ""; }
  } catch { el("btnLogin").style.display = ""; }
}

/* ── Search ── */
let searchTimeout = null;

async function search(q) {
  if (!q.trim()) {
    el("watchGrid").innerHTML = "";
    el("watchEmpty").style.display = "none";
    el("watchInitial").style.display = "";
    el("watchStatus").textContent = "";
    el("watchClear").style.display = "none";
    return;
  }

  el("watchClear").style.display = "";
  el("watchInitial").style.display = "none";
  el("watchStatus").textContent = "A pesquisar...";
  el("watchGrid").innerHTML = "";
  el("watchEmpty").style.display = "none";

  try {
    const res = await fetch(`${API}/search/movies?q=${encodeURIComponent(q)}`);
    const data = await res.json();

    el("watchStatus").textContent = data.total > 0 ? `${data.total} resultados` : "";

    if (!data.results?.length) {
      el("watchEmpty").style.display = "";
      return;
    }

    el("watchGrid").innerHTML = "";
    data.results.forEach(m => {
      const card = document.createElement("div");
      card.className = "watch-card";
      card.innerHTML = `
        <div class="watch-card__poster">
          ${m.poster_url
            ? `<img src="${escapeHtml(m.poster_url)}" alt="${escapeHtml(m.title)}" loading="lazy"/>`
            : `<div class="watch-card__poster-ph">${escapeHtml((m.title||"").slice(0,2).toUpperCase())}</div>`
          }
          <div class="watch-card__overlay">
            <button class="watch-play-btn" data-id="${m.id}" data-title="${escapeHtml(m.title)}">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              Reproduzir
            </button>
          </div>
        </div>
        <div class="watch-card__body">
          <div class="watch-card__title">${escapeHtml(m.title)}${m.year ? ` <span class="watch-card__year">(${m.year})</span>` : ""}</div>
          ${m.rating ? `<div class="watch-card__rating">★ ${Number(m.rating).toFixed(1)}</div>` : ""}
        </div>
      `;
      el("watchGrid").appendChild(card);
    });
  } catch {
    el("watchStatus").textContent = "Erro ao pesquisar.";
  }
}

/* ── Player ── */
function openPlayer(tmdbId, title) {
  const url = `https://www.vidking.net/embed/movie/${tmdbId}`;
  el("watchPlayerTitle").textContent = title;
  el("watchPlayerIframe").src = url;
  el("watchPlayerModal").style.display = "flex";
  document.body.style.overflow = "hidden";
}

function closePlayer() {
  el("watchPlayerModal").style.display = "none";
  el("watchPlayerIframe").src = "";
  document.body.style.overflow = "";
}

/* ── Boot ── */
document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initAuth();

  el("btnTheme")?.addEventListener("click", toggleTheme);
  el("btnLogin")?.addEventListener("click", () => window.location.href = "/");
  el("btnLogout")?.addEventListener("click", () => { localStorage.removeItem(TOKEN_KEY); window.location.href = "/"; });

  // Search input
  el("watchInput")?.addEventListener("input", (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => search(e.target.value), 350);
  });

  el("watchInput")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { clearTimeout(searchTimeout); search(e.target.value); }
  });

  el("watchClear")?.addEventListener("click", () => {
    el("watchInput").value = "";
    search("");
    el("watchInput").focus();
  });

  // Play button delegation
  el("watchGrid")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".watch-play-btn");
    if (!btn) return;
    openPlayer(btn.dataset.id, btn.dataset.title);
  });

  // Close player
  el("watchPlayerClose")?.addEventListener("click", closePlayer);
  el("watchPlayerBackdrop")?.addEventListener("click", closePlayer);
  window.addEventListener("keydown", (e) => { if (e.key === "Escape") closePlayer(); });
});
