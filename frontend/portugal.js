/* =====================================================
   portugal.js — tema Portugal 🇵🇹
   ===================================================== */

const PT_INTRO_KEY = "pt_intro_seen";

if (new URLSearchParams(window.location.search).get("reset") === "1") {
  localStorage.removeItem(PT_INTRO_KEY);
}

const isMobile = window.innerWidth < 768;

function addDecorations() {
  // Bandeiras laterais
  if (!document.querySelector(".pt-flag-left")) {
    const l = document.createElement("div"); l.className = "pt-flag-left";
    const r = document.createElement("div"); r.className = "pt-flag-right";
    document.body.appendChild(l);
    document.body.appendChild(r);
  }

  // Bandeira + faixas no hero
  document.body.classList.add("pt-active");
  const hero = document.getElementById("heroSection");
  if (hero && !document.querySelector(".pt-hero-flag")) {
    ["pt-hero-flag","pt-hero-left-strip","pt-hero-right-strip"].forEach(cls => {
      const d = document.createElement("div"); d.className = cls;
      hero.insertBefore(d, hero.firstChild);
    });
  }

  // Ronaldo esquerda (com bola)
  if (!document.querySelector(".pt-ronaldo-left")) {
    const r1 = document.createElement("img");
    r1.className = "pt-ronaldo-left";
    r1.src = "/static/ronaldo1.png";
    r1.alt = "";
    document.body.appendChild(r1);
  }

  // Ronaldo direita (verde)
  if (!document.querySelector(".pt-ronaldo-right")) {
    const r2 = document.createElement("img");
    r2.className = "pt-ronaldo-right";
    r2.src = "/static/ronaldo2.png";
    r2.alt = "";
    document.body.appendChild(r2);
  }

  // Botão "Porquê?" inline
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

function forcePtTitle() {
  setTimeout(() => {
    const heroTitle = document.getElementById("heroTitle");
    const brandSub  = document.querySelector(".brand-sub");
    if (heroTitle) heroTitle.textContent = "Semana Portuguesa";
    if (brandSub)  brandSub.textContent  = "Semana Portuguesa 🇵🇹";
  }, 900);
}

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
  document.getElementById("ptIntroClose").addEventListener("click", closeIntro);
}

function closeIntro() {
  localStorage.setItem(PT_INTRO_KEY, "1");
  document.getElementById("ptIntroOverlay")?.remove();
  startAnthem();
  addDecorations();
  forcePtTitle();
}

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
