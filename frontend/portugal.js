/* =====================================================
   portugal.js — lógica exclusiva do tema Portugal 🇵🇹
   Só carregado em portugal.html
   ===================================================== */

const API = "";
const TOKEN_KEY = "cinema_club_token";
const PT_INTRO_KEY = "pt_intro_seen";

function el(id) { return document.getElementById(id); }
function getToken() { return localStorage.getItem(TOKEN_KEY); }

/* ── Reset do intro via ?reset=1 ── */
if (new URLSearchParams(window.location.search).get("reset") === "1") {
  localStorage.removeItem(PT_INTRO_KEY);
}

const isMobile = window.innerWidth < 768;

/* ══════════════════════════════════════
   DECORAÇÕES
   ══════════════════════════════════════ */
function addDecorations() {
  // Bandeiras laterais
  const l = document.createElement("div"); l.className = "pt-flag-left";
  const r = document.createElement("div"); r.className = "pt-flag-right";
  document.body.appendChild(l);
  document.body.appendChild(r);

  // Estrela da Amadora
  const estrela = document.createElement("div");
  estrela.className = "pt-estrela-badge";
  estrela.title = "Estrela da Amadora";
  estrela.textContent = "⭐";
  document.body.appendChild(estrela);

  // Botão "Porquê esta semana?"
  const btn = document.createElement("button");
  btn.className = "pt-why-btn";
  btn.textContent = "🇵🇹 Porquê esta semana?";
  btn.addEventListener("click", () => {
    el("ptWhyPopup").style.display = "flex";
  });
  document.body.appendChild(btn);
}

/* ══════════════════════════════════════
   HINO NACIONAL
   ══════════════════════════════════════ */
let _anthemMuted = false;

function startAnthem() {
  const iframe = document.createElement("iframe");
  iframe.id = "ptAnthem";
  iframe.style.cssText = "position:fixed;width:0;height:0;border:0;opacity:0;pointer-events:none;";
  iframe.src = "https://www.youtube.com/embed/_-vct5dNaNY?autoplay=1&loop=1&playlist=_-vct5dNaNY&mute=0";
  document.body.appendChild(iframe);

  const muteBtn = document.createElement("button");
  muteBtn.id = "ptMuteBtn";
  muteBtn.className = "pt-mute-btn";
  muteBtn.textContent = "🔊";
  muteBtn.addEventListener("click", () => {
    _anthemMuted = !_anthemMuted;
    iframe.src = `https://www.youtube.com/embed/_-vct5dNaNY?autoplay=1&loop=1&playlist=_-vct5dNaNY&mute=${_anthemMuted ? 1 : 0}`;
    muteBtn.textContent = _anthemMuted ? "🔇" : "🔊";
  });
  document.body.appendChild(muteBtn);
}

/* ══════════════════════════════════════
   INTRO RONALDO
   ══════════════════════════════════════ */
function showIntro() {
  const overlay = document.createElement("div");
  overlay.id = "ptIntroOverlay";
  overlay.className = "pt-intro__overlay";
  overlay.innerHTML = `
    <div class="pt-intro__box">
      <button class="pt-intro__close" id="ptIntroClose">✕ Saltar</button>
      <iframe
        src="https://www.youtube.com/embed/YrZTw6uh4Yk?autoplay=1&controls=1"
        allow="autoplay; encrypted-media"
        allowfullscreen>
      </iframe>
    </div>`;
  document.body.appendChild(overlay);
  el("ptIntroClose").addEventListener("click", closeIntro);
}

function closeIntro() {
  localStorage.setItem(PT_INTRO_KEY, "1");
  el("ptIntroOverlay")?.remove();
  startAnthem();
  addDecorations();
}

/* ══════════════════════════════════════
   MOBILE
   ══════════════════════════════════════ */
function showMobilePopup() {
  addDecorations();
  const popup = document.createElement("div");
  popup.className = "pt-mobile-popup";
  popup.innerHTML = `
    <div class="pt-mobile-inner">
      <span class="pt-mobile-close" id="ptMobClose">✕</span>
      <p>🖥️ Vai ao PC ver a magia!</p>
    </div>`;
  document.body.appendChild(popup);
  el("ptMobClose").addEventListener("click", () => popup.remove());
}

/* ══════════════════════════════════════
   INIT
   ══════════════════════════════════════ */
document.addEventListener("DOMContentLoaded", () => {
  // Popup "Porquê?" wiring (está no HTML estático)
  el("ptWhyClose")?.addEventListener("click", () => {
    el("ptWhyPopup").style.display = "none";
  });
  el("ptWhyPopup")?.addEventListener("click", e => {
    if (e.target === el("ptWhyPopup")) el("ptWhyPopup").style.display = "none";
  });

  if (isMobile) {
    showMobilePopup();
    return;
  }

  if (!localStorage.getItem(PT_INTRO_KEY)) {
    showIntro();
  } else {
    startAnthem();
    addDecorations();
  }
});
