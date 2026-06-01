const API = "";
const TOKEN_KEY = "cinema_club_token";
const getToken = () => localStorage.getItem(TOKEN_KEY);

function el(id) { return document.getElementById(id); }
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));
}

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

function avatarHTML(user, size = 32) {
  const url = user?.avatar_url;
  const name = user?.username || "?";
  const initials = name.slice(0, 2).toUpperCase();
  if (url) {
    return `<img class="lb-table__avatar" src="${escapeHtml(url)}" alt="${escapeHtml(name)}" style="width:${size}px;height:${size}px" />`;
  }
  return `<div class="lb-table__avatar--initials" style="width:${size}px;height:${size}px;font-size:${Math.round(size*.35)}px">${escapeHtml(initials)}</div>`;
}

function podiumAvatarHTML(user, size = 64) {
  const url = user?.avatar_url;
  const name = user?.username || "?";
  const initials = name.slice(0, 2).toUpperCase();
  if (url) {
    return `<img class="lb-podium__avatar" src="${escapeHtml(url)}" alt="${escapeHtml(name)}" style="width:${size}px;height:${size}px" />`;
  }
  return `<div class="lb-podium__avatar--initials" style="width:${size}px;height:${size}px;font-size:${Math.round(size*.35)}px">${escapeHtml(initials)}</div>`;
}

function winRateClass(rate) {
  if (rate >= 40) return "lb-win-rate--high";
  if (rate >= 20) return "lb-win-rate--mid";
  return "lb-win-rate--low";
}

const RANK_EMOJI = { 1: "🥇", 2: "🥈", 3: "🥉" };

function assignRanks(rows) {
  // Assign rank based on wins + win_rate — tied users get same rank
  let rank = 1;
  return rows.map((r, i) => {
    if (i > 0) {
      const prev = rows[i - 1];
      if (r.films_won !== prev.films_won || r.win_rate !== prev.win_rate) {
        rank = i + 1;
      }
    }
    return { ...r, rank };
  });
}

async function loadLeaderboard() {
  try {
    const rawRows = await apiGet("/api/leaderboard");
    const rows = assignRanks(rawRows);

    el("lbLoading").style.display = "none";
    el("lbContent").style.display = "";

    // Podium — group by rank 1, 2, 3
    const podiumGroups = [1, 2, 3].map(r => rows.filter(x => x.rank === r));
    const podiumOrder = [podiumGroups[1], podiumGroups[0], podiumGroups[2]]; // 2nd, 1st, 3rd
    const podiumLabels = [2, 1, 3];

    el("lbPodium").innerHTML = podiumOrder.map((group, pos) => {
      if (!group.length) return "";
      const rankNum = podiumLabels[pos];
      const emoji = RANK_EMOJI[rankNum] || rankNum;
      const size = rankNum === 1 ? 72 : 56;
      const names = group.map(r => `
        <a href="/profile/${escapeHtml(r.username)}" class="lb-podium__name">@${escapeHtml(r.username)}</a>
      `).join("");
      const avatars = group.map(r => podiumAvatarHTML(r, size)).join("");
      const wins = group[0].films_won;
      const rate = group[0].win_rate;
      return `
        <div class="lb-podium__item lb-podium__item--${rankNum}">
          <div class="lb-podium__avatars">${avatars}</div>
          <div class="lb-podium__names">${names}</div>
          <div class="lb-podium__wins">${wins} vitória${wins !== 1 ? "s" : ""} · ${rate}%</div>
          <div class="lb-podium__block">${emoji}</div>
        </div>
      `;
    }).join("");

    // Table
    el("lbTableBody").innerHTML = rows.map(r => {
      const emoji = RANK_EMOJI[r.rank];
      const rankCell = emoji
        ? `<span class="lb-rank-emoji">${emoji}</span>`
        : `<span class="lb-rank-num">${r.rank}</span>`;
      return `
        <tr>
          <td class="lb-table__rank">${rankCell}</td>
          <td>
            <a href="/profile/${escapeHtml(r.username)}" class="lb-table__user">
              ${avatarHTML(r)}
              @${escapeHtml(r.username)}
            </a>
          </td>
          <td><strong>${r.films_won}</strong></td>
          <td><span class="lb-win-rate ${winRateClass(r.win_rate)}">${r.win_rate}%</span></td>
          <td>${r.films_submitted}</td>
          <td>${r.votes_cast}</td>
        </tr>
      `;
    }).join("");

  } catch (e) {
    el("lbLoading").innerHTML = `<p class="muted">Erro ao carregar leaderboard.</p>`;
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  el("btnTheme")?.addEventListener("click", toggleTheme);

  const token = getToken();
  if (token) {
    try {
      const me = await apiGet("/auth/me");
      el("authStatusLine").textContent = `@${me.username}`;
      const avatar = el("authAvatarPill");
      if (avatar && me.avatar_url) {
        avatar.innerHTML = `<img src="${escapeHtml(me.avatar_url)}" width="28" height="28" style="border-radius:50%;object-fit:cover" />`;
        avatar.style.display = "";
      }
      el("btnLogout").style.display = "";
      el("btnLogin").style.display = "none";
    } catch {}
  } else {
    el("btnLogin").style.display = "";
  }

  el("btnLogout")?.addEventListener("click", () => {
    localStorage.removeItem(TOKEN_KEY);
    window.location.href = "/";
  });
  el("btnLogin")?.addEventListener("click", () => { window.location.href = "/"; });

  await loadLeaderboard();
});
