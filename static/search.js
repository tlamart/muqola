/* Progressive, same-origin search. Only the results subtree is replaced. */
"use strict";
for (const form of document.querySelectorAll("[data-live-search]")) {
  const input = form.elements.namedItem("title");
  const results = document.getElementById(form.dataset.results);
  const status = document.getElementById(form.dataset.status);
  const selected = document.getElementById("selected-game");
  const summary = document.getElementById("selection-status");
  const clear = document.getElementById("clear-selection");
  let generation = 0, timer, controller, composing = false, selectedTitle = "";
  function selection() {
    if (!selected) return;
    for (const radio of results.querySelectorAll('input[name="game_id"]')) {
      radio.checked = radio.value === selected.value;
      radio.required = !selected.value;
    }
    summary.textContent = selected.value ? `Choix conservé : ${selectedTitle || "jeu sélectionné"}.` : "";
    clear.hidden = !selected.value;
  }
  results.addEventListener("change", (event) => {
    if (selected && event.target.matches('input[name="game_id"]')) {
      selected.value = event.target.value;
      selectedTitle = event.target.closest("label").querySelector("strong").textContent;
      selection();
    }
  });
  clear?.addEventListener("click", () => { selected.value = ""; selection(); });
  function cancel() {
    generation += 1;
    clearTimeout(timer);
    controller?.abort();
    results.setAttribute("aria-busy", "false");
  }
  function urlForForm() {
    const url = new URL(form.action || location.href);
    url.search = new URLSearchParams(new FormData(form)).toString();
    return url;
  }
  async function load(url, version) {
    controller = new AbortController();
    results.setAttribute("aria-busy", "true");
    status.textContent = "Recherche en cours…";
    try {
      const response = await fetch(url, {headers: {"X-Requested-With": "live-search"}, signal: controller.signal});
      if (!response.ok || response.redirected) throw new Error("search failed");
      const html = await response.text();
      if (version !== generation) return;
      delete form.dataset.searchFailed;
      const focusInResults = results.contains(document.activeElement);
      results.innerHTML = html;
      selection();
      const count = results.querySelector("[data-result-count]")?.dataset.resultCount || "0";
      status.textContent = `${count} résultat${count === "1" ? "" : "s"}.`;
      history.replaceState(null, "", url);
      if (focusInResults) {
        const target = results.querySelector("h2, legend") || results;
        target.tabIndex = -1; target.focus();
      }
    } catch (error) {
      if (version !== generation || error.name === "AbortError") return;
      status.textContent = "Recherche indisponible. Les résultats précédents sont conservés. Validez avec Entrée pour réessayer en rechargeant la page.";
      form.dataset.searchFailed = "true";
    } finally {
      if (version === generation) results.setAttribute("aria-busy", "false");
    }
  }
  function schedule(immediate = false) {
    cancel();
    delete form.dataset.searchFailed;
    if (composing) return;
    for (const link of document.querySelectorAll("[data-manual-link]")) {
      const target = new URL(link.href); target.searchParams.set("title", input.value); link.href = target;
    }

    if (input.value.trim().length === 1) {
      status.textContent = "Saisissez au moins deux caractères.";
      return;
    }
    const version = generation;
    timer = setTimeout(() => load(urlForForm(), version), immediate ? 0 : 250);
  }
  input.addEventListener("input", () => schedule());
  input.addEventListener("compositionstart", () => { composing = true; cancel(); });
  input.addEventListener("compositionend", () => { composing = false; schedule(); });
  form.addEventListener("change", (event) => { if (event.target !== input) schedule(); });
  form.addEventListener("submit", (event) => {
    if (form.dataset.searchFailed) return;
    event.preventDefault(); schedule(true);
  });
  results.addEventListener("click", (event) => {
    const link = event.target.closest(".pagination a");
    if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault(); cancel(); load(new URL(link.href), generation);
  });
  form.querySelector("[data-search-reset]")?.addEventListener("click", (event) => {
    event.preventDefault(); form.elements.namedItem("only_available").checked = false; schedule(true);
  });
  window.addEventListener("pagehide", cancel);
  window.addEventListener("pageshow", event => { if (event.persisted) schedule(true); });
  selection();
}
