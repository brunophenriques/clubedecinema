(function () {
  const DELAY_MS = 1800;
  const API_PATH_RE = /^\/(auth|weeks|admin|letterboxd|films|api|users|search|chat|health)\b/;
  let pending = 0;
  let timer = null;
  let banner = null;
  let errorVisible = false;

  function isApiRequest(input) {
    try {
      const raw = typeof input === "string" ? input : input?.url;
      if (!raw) return false;
      const url = new URL(raw, window.location.origin);
      return url.origin === window.location.origin && API_PATH_RE.test(url.pathname);
    } catch {
      return false;
    }
  }

  function ensureBanner() {
    if (banner) return banner;
    banner = document.createElement("div");
    banner.id = "coldStartNotice";
    banner.className = "cold-start";
    banner.setAttribute("role", "status");
    banner.innerHTML = `
      <div class="cold-start__title">A acordar o servidor...</div>
      <div class="cold-start__body">Isto pode demorar uns segundos.</div>
      <button class="btn primary cold-start__retry" type="button" style="display:none">Tentar outra vez</button>
    `;
    banner.querySelector(".cold-start__retry")?.addEventListener("click", () => window.location.reload());
    document.body.appendChild(banner);
    return banner;
  }

  function showWaking() {
    const el = ensureBanner();
    errorVisible = false;
    el.classList.remove("cold-start--error");
    el.querySelector(".cold-start__title").textContent = "A acordar o servidor...";
    el.querySelector(".cold-start__body").textContent = "Isto pode demorar uns segundos.";
    el.querySelector(".cold-start__retry").style.display = "none";
    el.classList.add("cold-start--visible");
  }

  function showError() {
    const el = ensureBanner();
    errorVisible = true;
    el.classList.add("cold-start--error", "cold-start--visible");
    el.querySelector(".cold-start__title").textContent = "Nao conseguimos falar com o servidor.";
    el.querySelector(".cold-start__body").textContent = "Pode ainda estar a acordar. Espera um momento e tenta de novo.";
    el.querySelector(".cold-start__retry").style.display = "";
  }

  function hide() {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    if (!errorVisible && banner) banner.classList.remove("cold-start--visible");
  }

  function start() {
    pending += 1;
    if (!timer) timer = setTimeout(() => {
      if (pending > 0) showWaking();
    }, DELAY_MS);
  }

  function finish() {
    pending = Math.max(0, pending - 1);
    if (pending === 0) hide();
  }

  const originalFetch = window.fetch.bind(window);
  window.fetch = async function patchedFetch(input, init) {
    const tracked = isApiRequest(input);
    if (tracked) start();
    try {
      const response = await originalFetch(input, init);
      if (tracked && !response.ok && response.status >= 500) showError();
      else if (tracked && response.ok) errorVisible = false;
      return response;
    } catch (error) {
      if (tracked) showError();
      throw error;
    } finally {
      if (tracked) finish();
    }
  };
})();
