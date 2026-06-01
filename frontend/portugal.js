/* =====================================================
   portugal.js — tema Portugal 🇵🇹
   ===================================================== */

const PT_INTRO_KEY = "pt_intro_seen";

if (new URLSearchParams(window.location.search).get("reset") === "1") {
  localStorage.removeItem(PT_INTRO_KEY);
}

const isMobile = window.innerWidth < 768;

function addDecorations() {
  // Overlay no html — não cria stacking context no body
  document.documentElement.classList.add("pt-active-html");

  // Bandeiras laterais
  if (!document.querySelector(".pt-flag-left")) {
    const l = document.createElement("div"); l.className = "pt-flag-left";
    const r = document.createElement("div"); r.className = "pt-flag-right";
    document.body.appendChild(l);
    document.body.appendChild(r);
  }

  // Bandeira + faixas + CR7s no hero
  document.body.classList.add("pt-active");
  const hero = document.getElementById("heroSection");
  if (hero && !document.querySelector(".pt-hero-flag")) {
    ["pt-hero-flag","pt-hero-left-strip","pt-hero-right-strip"].forEach(cls => {
      const d = document.createElement("div"); d.className = cls;
      hero.insertBefore(d, hero.firstChild);
    });

    // CR7 esquerda (cuecas verdes)
    const cr7l = document.createElement("img");
    cr7l.className = "pt-cr7-left";
    cr7l.src = "/static/ronaldo2.png";
    cr7l.alt = "";
    hero.appendChild(cr7l);

    // CR7 direita (com bola)
    const cr7r = document.createElement("img");
    cr7r.className = "pt-cr7-right";
    cr7r.src = "/static/ronaldo1.png";
    cr7r.alt = "";
    hero.appendChild(cr7r);
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
      addDecorations();
    forcePtTitle();
  }
});
