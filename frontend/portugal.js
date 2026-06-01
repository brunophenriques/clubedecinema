/* =====================================================
   portugal.js — lógica exclusiva do tema Portugal 🇵🇹
   ===================================================== */

const PT_INTRO_KEY = "pt_intro_seen";

if (new URLSearchParams(window.location.search).get("reset") === "1") {
  localStorage.removeItem(PT_INTRO_KEY);
}

const isMobile = window.innerWidth < 768;

/* ══════════════════════════════════════
   DECORAÇÕES
   ══════════════════════════════════════ */
function addDecorations() {
  // Fundo com bandeira
  document.body.classList.add("pt-active");

  // Bandeiras laterais
  const l = document.createElement("div"); l.className = "pt-flag-left";
  const r = document.createElement("div"); r.className = "pt-flag-right";
  document.body.appendChild(l);
  document.body.appendChild(r);

  // Bandeira SVG atrás do título
  const heroSection = document.getElementById("heroSection");
  if (heroSection && !document.querySelector(".pt-flag-svg-bg")) {
    heroSection.style.position = "relative";
    heroSection.style.overflow = "hidden";
    const svgFlag = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svgFlag.setAttribute("viewBox", "0 0 900 600");
    svgFlag.setAttribute("class", "pt-flag-svg-bg");
    svgFlag.innerHTML = `
      <rect width="300" height="600" fill="#006600"/>
      <rect x="300" width="600" height="600" fill="#d4000e"/>
      <ellipse cx="300" cy="300" rx="120" ry="120" fill="#FFD700" stroke="#006600" stroke-width="8"/>
      <ellipse cx="300" cy="300" rx="96" ry="96" fill="#fff"/>
      <ellipse cx="300" cy="300" rx="72" ry="72" fill="#d4000e"/>
    `;
    heroSection.appendChild(svgFlag);
  }

  // Escudo Estrela da Amadora
  const estrela = document.createElement("div");
  estrela.className = "pt-estrela-badge";
  estrela.innerHTML = `<img src="/static/estreladamadora.png" alt="Estrela da Amadora" />`;
  document.body.appendChild(estrela);

  // Paulo Moreira
  const paulo = document.createElement("img");
  paulo.className = "pt-paulo";
  paulo.src = "/static/paulomoreira.png";
  paulo.alt = "Paulo Moreira";
  document.body.appendChild(paulo);

  // Botão "Porquê?" inline abaixo do subtítulo
  const heroSub = document.getElementById("heroSub");
  if (heroSub && !document.getElementById("ptWhyInlineBtn")) {
    const btn = document.createElement("button");
    btn.id = "ptWhyInlineBtn";
    btn.className = "pt-why-inline-btn";
    btn.innerHTML = `🇵🇹 Porquê esta semana?`;
    btn.addEventListener("click", () => {
      document.getElementById("ptWhyPopup").style.display = "flex";
    });
    heroSub.insertAdjacentElement("afterend", btn);
  }
}

/* ══════════════════════════════════════
   TÍTULO
   ══════════════════════════════════════ */
function forcePtTitle() {
  setTimeout(() => {
    const heroTitle = document.getElementById("heroTitle");
    const brandSub  = document.querySelector(".brand-sub");
    if (heroTitle) heroTitle.textContent = "Semana Portuguesa";
    if (brandSub)  brandSub.textContent  = "Semana Portuguesa 🇵🇹";
  }, 900);
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
  muteBtn.innerHTML = "🔊";
  muteBtn.title = "Hino Nacional";
  muteBtn.addEventListener("click", () => {
    _anthemMuted = !_anthemMuted;
    iframe.src = `https://www.youtube.com/embed/_-vct5dNaNY?autoplay=1&loop=1&playlist=_-vct5dNaNY&mute=${_anthemMuted ? 1 : 0}`;
    muteBtn.innerHTML = _anthemMuted ? "🔇" : "🔊";
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
    <div class="pt-intro__bg-gif"></div>
    <div class="pt-intro__box">
      <button class="pt-intro__close" id="ptIntroClose">✕ Saltar</button>
      <div class="pt-intro__label">🇵🇹 Semana Portuguesa</div>
      <iframe
        src="https://www.youtube.com/embed/YrZTw6uh4Yk?autoplay=1&controls=1"
        allow="autoplay; encrypted-media"
        allowfullscreen>
      </iframe>
    </div>`;
  document.body.appendChild(overlay);
  document.getElementById("ptIntroClose").addEventListener("click", closeIntro);
}

function closeIntro() {
  localStorage.setItem(PT_INTRO_KEY, "1");
  document.getElementById("ptIntroOverlay")?.remove();
  startAnthem();
  addDecorations();
  forcePtTitle();
}

/* ══════════════════════════════════════
   MOBILE
   ══════════════════════════════════════ */
function showMobilePopup() {
  addDecorations();
  forcePtTitle();
  const popup = document.createElement("div");
  popup.className = "pt-mobile-popup";
  popup.innerHTML = `
    <div class="pt-mobile-inner">
      <span class="pt-mobile-close" id="ptMobClose">✕</span>
      <p>🖥️ Vai ao PC ver a magia!</p>
    </div>`;
  document.body.appendChild(popup);
  document.getElementById("ptMobClose").addEventListener("click", () => popup.remove());
}

/* ══════════════════════════════════════
   INIT
   ══════════════════════════════════════ */
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("ptWhyClose")?.addEventListener("click", () => {
    document.getElementById("ptWhyPopup").style.display = "none";
  });
  document.getElementById("ptWhyPopup")?.addEventListener("click", e => {
    if (e.target === document.getElementById("ptWhyPopup"))
      document.getElementById("ptWhyPopup").style.display = "none";
  });

  if (isMobile) { showMobilePopup(); return; }

  if (!localStorage.getItem(PT_INTRO_KEY)) {
    showIntro();
  } else {
    startAnthem();
    addDecorations();
    forcePtTitle();
  }
});
