(() => {
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const url = value => {
    try { const parsed = new URL(value); return parsed.protocol === "https:" ? parsed.href : ""; }
    catch { return ""; }
  };
  let dialog, controller, activeFilm;

  function ensureDialog() {
    if (dialog) return;
    dialog = document.createElement("dialog");
    dialog.id = "movieDetailsDialog";
    dialog.className = "movie-sheet";
    dialog.setAttribute("aria-labelledby", "movieDetailsTitle");
    dialog.innerHTML = `<button type="button" class="movie-sheet__close" aria-label="Fechar ficha do filme">✕</button><div id="movieDetailsBody" aria-live="polite"></div>`;
    document.body.append(dialog);
    dialog.querySelector(".movie-sheet__close").addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", event => {
      if (event.target !== dialog) return;
      const rect = dialog.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
    });
    dialog.addEventListener("close", () => {
      controller?.abort();
      dialog.querySelector("iframe")?.remove();
    });
  }

  function render(data, notice = "", retry = false) {
    activeFilm = data;
    const metadata = [data.year, data.runtime ? `${data.runtime} min` : null, ...(data.genres || [])].filter(Boolean);
    const backdrop = url(data.backdrop_url);
    const poster = url(data.poster_url);
    const lb = url(data.letterboxd_url) || `https://letterboxd.com/search/${encodeURIComponent(`${data.title || ""} ${data.year || ""}`.trim())}/`;
    const original = data.original_title && data.original_title !== data.title ? data.original_title : "";
    const tmdb = url(data.tmdb_url);
    dialog.querySelector("#movieDetailsBody").innerHTML = `
      ${backdrop ? `<div class="movie-sheet__still"><img src="${escape(backdrop)}" alt="Fotograma de ${escape(data.title)}" /></div>` : ""}
      <div class="movie-sheet__content">
        <header class="movie-sheet__header">
          <span class="kicker">Clube de Cinema / Ficha do filme</span>
          <h2 id="movieDetailsTitle">${escape(data.title || "Filme")}</h2>
          ${original ? `<p class="movie-sheet__original">${escape(original)}</p>` : ""}
          <p class="movie-sheet__meta">${escape(metadata.join(" · "))}</p>
        </header>
        <div class="movie-sheet__columns">
          <aside class="movie-sheet__poster">${poster ? `<img src="${escape(poster)}" alt="Poster de ${escape(data.title)}" />` : `<span>Clube de Cinema</span>`}</aside>
          <section class="movie-sheet__story">
            ${(data.directors || []).length ? `<p class="movie-sheet__director"><span>Um filme de</span> ${escape(data.directors.join(" / "))}</p>` : ""}
            ${notice ? `<p class="movie-sheet__notice" role="status">${escape(notice)} ${retry ? '<button class="movie-sheet__retry" type="button">Tentar novamente</button>' : ""}</p>` : ""}
            <h3>Sinopse</h3>
            <p class="movie-sheet__overview" ${data.overview_language ? `lang="${escape(data.overview_language)}"` : ""}>${escape(data.overview || (data.source === "tmdb" ? "Ainda não há sinopse disponível para este filme." : "A sinopse aparecerá quando a informação do filme estiver disponível."))}</p>
            ${data.overview_language === "en" ? '<p class="muted small">Sinopse disponível em inglês.</p>' : ""}
            ${(data.cast || []).length ? `<h3>Com</h3><ul class="movie-sheet__cast">${data.cast.map(person => `<li><strong>${escape(person.name)}</strong>${person.character ? `<span>${escape(person.character)}</span>` : ""}</li>`).join("")}</ul>` : ""}
            <div class="movie-sheet__actions">
              <a class="btn primary" href="${escape(lb)}" target="_blank" rel="noopener noreferrer">Ver no Letterboxd ↗</a>
              <button class="btn movie-sheet__trailer-button" type="button">Ver trailer</button>
              ${tmdb ? `<a class="movie-sheet__source" href="${escape(tmdb)}" target="_blank" rel="noopener noreferrer">Ficha no TMDB ↗</a>` : ""}
            </div>
            <div class="movie-sheet__trailer" aria-live="polite"></div>
          </section>
        </div>
        ${data.source === "tmdb" ? '<footer class="movie-sheet__credits">Informação e imagens: TMDB. <a href="/como-funciona#creditos">Créditos</a></footer>' : ""}
      </div>`;
    dialog.querySelectorAll("img").forEach(img => img.addEventListener("error", () => { img.parentElement.hidden = true; }));
    dialog.querySelector(".movie-sheet__retry")?.addEventListener("click", () => open(data));
    dialog.querySelector(".movie-sheet__trailer-button").addEventListener("click", showTrailer);
  }

  async function showTrailer(event) {
    const button = event.currentTarget;
    const film = activeFilm;
    const request = controller;
    button.disabled = true;
    const box = dialog.querySelector(".movie-sheet__trailer");
    box.textContent = "A procurar o trailer…";
    try {
      if (!film.tmdb_id) throw new Error("No match");
      const response = await fetch(`/movies/${encodeURIComponent(film.tmdb_id)}/trailer`, {signal: request.signal});
      if (!response.ok) throw new Error("Unavailable");
      const data = await response.json();
      if (request !== controller || !dialog.open) return;
      if (!/^https:\/\/www\.youtube\.com\/embed\/[\w-]+(?:\?|$)/.test(data.embed_url || "")) throw new Error("No trailer");
      box.innerHTML = `<iframe src="${escape(data.embed_url)}" title="Trailer de ${escape(film.title)}" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen></iframe>`;
    } catch (error) {
      if (error.name === "AbortError" || request !== controller || !dialog.open) return;
      const search = `https://www.youtube.com/results?search_query=${encodeURIComponent(`${film.title} ${film.year || ""} trailer`)}`;
      box.innerHTML = `Não há trailer disponível aqui. <a href="${escape(search)}" target="_blank" rel="noopener noreferrer">Procurar no YouTube ↗</a>`;
    } finally { button.disabled = false; }
  }

  async function open(film) {
    ensureDialog();
    controller?.abort();
    const request = controller = new AbortController();
    render(film, "A carregar a ficha do filme…");
    if (!dialog.open) dialog.showModal();
    dialog.scrollTop = 0;
    const endpoint = film.film_id ? `/films/${encodeURIComponent(film.film_id)}/details` : film.tmdb_id ? `/movies/${encodeURIComponent(film.tmdb_id)}/details` : null;
    try {
      if (!endpoint) throw new Error("No match");
      const response = await fetch(endpoint, {signal: request.signal});
      if (!response.ok) throw new Error("Unavailable");
      const data = await response.json();
      if (request !== controller || !dialog.open) return;
      const notice = data.details_status === "unmatched"
        ? "Este filme ainda não tem uma ficha associada. Podes procurá-lo no Letterboxd."
        : data.details_status === "unavailable" ? "Não foi possível carregar a informação adicional. Mostramos os dados do clube." : "";
      render({...film, ...data}, notice, data.details_status === "unavailable");
    } catch (error) {
      if (error.name === "AbortError" || request !== controller || !dialog.open) return;
      render(film, "Não foi possível carregar a ficha. Podes tentar novamente ou abrir o Letterboxd.", true);
    }
  }

  document.addEventListener("click", event => {
    const button = event.target.closest("[data-film-details]");
    if (!button) return;
    event.preventDefault();
    open({film_id: button.dataset.filmId || null, tmdb_id: button.dataset.tmdbId || null,
      title: button.dataset.title, year: button.dataset.year, poster_url: button.dataset.poster,
      directors: button.dataset.director ? [button.dataset.director] : []});
  });
  window.CinemaMovieDetails = {open};
})();
