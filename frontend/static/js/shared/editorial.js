/* Shared interface behavior. Page scripts retain their API and auth logic. */
document.addEventListener("DOMContentLoaded", () => {
  const controls = document.querySelector(".auth-pill");
  if (controls) {
    const group = document.createElement("div");
    group.className = "header-controls";
    controls.append(group);
    ["btnLogin","btnLogout","btnChat","btnTheme"].forEach(id => {
      const button = document.getElementById(id);
      if (button) group.append(button);
    });
  }
  const themeButton = document.getElementById("btnTheme");
  const labelTheme = () => {
    if (!themeButton) return;
    const label = document.documentElement.dataset.theme === "dark" ? "Ativar tema claro" : "Ativar tema escuro";
    themeButton.title = label;
    themeButton.setAttribute("aria-label",label);
  };
  labelTheme();
  new MutationObserver(labelTheme).observe(document.documentElement,{attributes:true,attributeFilter:["data-theme"]});
  [ ["btnLogin","Entrar na conta"], ["btnLogout","Sair da conta"], ["btnChat","Abrir chat da semana"], ["refresh","Atualizar filmes"] ].forEach(([id,label]) => {
    const button = document.getElementById(id);
    if (button) { button.title = label; button.setAttribute("aria-label",label); }
  });
  document.querySelectorAll(".brand-title").forEach(title => {
    title.replaceChildren();
    const club = document.createElement("span");
    club.className = "masthead-club";
    club.textContent = "Clube ";
    const join = document.createElement("em");
    join.textContent = "de ";
    const cinema = document.createElement("span");
    cinema.className = "masthead-cinema";
    cinema.textContent = "Cinema";
    title.append(club, join, cinema);
    const brand = title.closest(".brand");
    if (brand && !brand.querySelector(".club-emblem")) {
      const emblem = document.createElement("span");
      emblem.className = "club-emblem";
      emblem.innerHTML = `<svg viewBox="0 0 100 100" role="img" aria-label="67, identidade do Clube de Cinema" xmlns="http://www.w3.org/2000/svg">
        <defs><linearGradient id="club67metal" x1="0" y1="0" x2=".7" y2="1"><stop stop-color="#fff9fc"/><stop offset=".3" stop-color="#c5c5cb"/><stop offset=".48" stop-color="#ffffff"/><stop offset=".65" stop-color="#9d9ca5"/><stop offset="1" stop-color="#ede9ee"/></linearGradient></defs>
        <path d="M22 10H78L94 27V73L78 90H22L6 73V27Z" fill="url(#club67metal)" stroke="#211b20" stroke-width="2"/>
        <path d="M26 17H74L86 30V70L74 83H26L14 70V30Z" fill="#f3add0" stroke="#211b20"/>
        <path d="M19 36L81 27M19 73L81 64" stroke="#fff9fc" stroke-width="2"/>
        <g class="emblem-motion emblem-six"><text x="24" y="65" fill="#211b20" font-family="Bowlby One,Arial,sans-serif" font-size="39" font-weight="400">6</text></g>
        <g class="emblem-motion emblem-seven"><text x="49" y="65" fill="#211b20" font-family="Bowlby One,Arial,sans-serif" font-size="39" font-weight="400">7</text></g>
        <path d="M78 3V17M71 10H85" stroke="#e64b98" stroke-width="3"/>
      </svg>`;
      brand.append(emblem);
      // Opposing six/seven seesaw on separate SVG groups. Each half-cycle
      // eases independently so the digits float rather than shake.
      // Keep the hover target stationary and return from the current position.
      const digits = [...emblem.querySelectorAll(".emblem-motion")];
      const motions = new Map();
      const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
      const settle = () => digits.forEach(digit => {
        const current = getComputedStyle(digit).transform;
        motions.get(digit)?.cancel();
        const motion = digit.animate([{transform:current},{transform:"translateY(0px)"}], {duration:220,easing:"ease-out"});
        motions.set(digit, motion);
      });
      emblem.addEventListener("mouseenter", () => {
        if (reducedMotion.matches) return;
        digits.forEach((digit,index) => {
          const current = getComputedStyle(digit).transform;
          motions.get(digit)?.cancel();
          const direction = index === 0 ? -1 : 1;
          const intro = digit.animate([{transform:current},{transform:`translateY(${direction * 5}px)`}], {duration:300,easing:"ease-in-out",fill:"forwards"});
          motions.set(digit,intro);
          intro.onfinish = () => {
            if (motions.get(digit) !== intro || !emblem.matches(":hover") || reducedMotion.matches) return;
            const loop = digit.animate([0,1,0].map(step => ({transform:`translateY(${direction * (step ? -5 : 5)}px)`,easing:"ease-in-out"})), {duration:1200,iterations:Infinity});
            intro.cancel();
            motions.set(digit,loop);
          };
        });
      });
      emblem.addEventListener("mouseleave",settle);
      reducedMotion.addEventListener("change", () => {
        if (reducedMotion.matches) digits.forEach(digit => { motions.get(digit)?.cancel(); motions.delete(digit); });
      });
    }
  });
  document.querySelectorAll("nav.nav").forEach(nav => {
    nav.setAttribute("aria-label", "Navegação principal");
    nav.querySelector(".active")?.setAttribute("aria-current", "page");
  });
  document.querySelectorAll("button[title]").forEach(button => {
    if (!button.textContent.trim() && !button.hasAttribute("aria-label")) button.setAttribute("aria-label", button.title);
  });
  document.getElementById("chatSend")?.setAttribute("aria-label", "Enviar mensagem");
  document.getElementById("chatClose")?.setAttribute("aria-label", "Fechar chat");
  document.querySelector("#films")?.closest("section")?.querySelector("h2")?.setAttribute("tabindex", "-1");
  // Keep keyboard focus inside the existing non-native dialogs.
  ["authModal", "modal"].forEach(id => {
    const modal = document.getElementById(id);
    if (!modal || modal.tagName === "DIALOG") return;
    let wasOpen = false, trigger;
    const focusable = () => [...modal.querySelectorAll('button, a[href], input, select, textarea, [tabindex="0"]')].filter(e => !e.disabled && e.getClientRects().length);
    const sync = () => {
      const open = !!modal.getClientRects().length;
      if (open && !wasOpen) {
        trigger = document.activeElement;
        modal.setAttribute("role", "dialog");
        modal.setAttribute("aria-modal", "true");
        queueMicrotask(() => focusable()[0]?.focus());
      } else if (!open && wasOpen && trigger?.isConnected) trigger.focus();
      wasOpen = open;
    };
    new MutationObserver(sync).observe(modal, {attributes:true, attributeFilter:["class","style","hidden"]});
    modal.addEventListener("keydown", event => {
      if (event.key !== "Tab") return;
      const controls = focusable();
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    });
    sync();
  });
  const chat = document.getElementById("chatPanel");
  if (chat) {
    const syncChatVisibility = () => {
      const open = chat.classList.contains("chat-panel--open");
      chat.inert = !open;
      chat.setAttribute("aria-hidden", String(!open));
    };
    syncChatVisibility();
    new MutationObserver(syncChatVisibility).observe(chat, { attributes: true, attributeFilter: ["class"] });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && chat.classList.contains("chat-panel--open")) {
        document.getElementById("chatClose")?.click();
        document.getElementById("btnChat")?.focus();
      }
    });
  }
  const dialog = document.getElementById("submissionDialog");
  document.getElementById("openSubmission")?.addEventListener("click", () => {
    dialog?.showModal();
    document.getElementById("subTitle")?.focus();
  });
  document.getElementById("closeSubmission")?.addEventListener("click", () => dialog?.close());
  dialog?.addEventListener("click", event => {
    if (event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
  });
});
