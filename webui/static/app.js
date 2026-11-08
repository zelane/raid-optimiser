// Champion page: time solves; when a run is shown (the latest on opening the page, a new
// one, or one picked from the history), restore the form it was asked with and mark it in
// the history. Runs themselves are kept server-side.
(function () {
  forgetOldStorage();

  const form = document.querySelector("form[data-champion]");
  if (!form) return;

  const results = document.getElementById("results");
  const timer = document.getElementById("timer");
  let started = 0;
  let ticking = null;

  showRun();

  form.addEventListener("htmx:beforeRequest", () => {
    started = performance.now();
    showElapsed();
    ticking = setInterval(showElapsed, 100);
  });

  form.addEventListener("htmx:afterRequest", () => clearInterval(ticking));

  document.body.addEventListener("htmx:afterSwap", (event) => {
    if (event.detail.target === results) showRun();
    if (event.detail.target.id === "history") markCurrent();
  });

  // The history is swapped out of band after a solve, so mark it once that's settled too.
  document.body.addEventListener("htmx:oobAfterSwap", markCurrent);

  function showElapsed() {
    timer.textContent = ((performance.now() - started) / 1000).toFixed(1) + "s";
  }

  function showRun() {
    const saved = results.querySelector(".run-form");
    if (saved) restore(JSON.parse(saved.textContent));
    markCurrent();
  }

  function markCurrent() {
    const run = results.querySelector(".run");
    const current = run ? run.dataset.runId : null;

    for (const item of document.querySelectorAll("#history li")) {
      item.classList.toggle("current", item.dataset.runId === current);
    }
  }

  function restore(values) {
    form.reset();

    for (const [name, value] of Object.entries(values)) {
      const field = form.elements.namedItem(name);
      if (field) field.value = value;
    }
  }

  // Forms and results used to be kept in this browser; they're in the store now.
  function forgetOldStorage() {
    try {
      for (const key of Object.keys(localStorage)) {
        if (key.startsWith("raid-optimiser-")) localStorage.removeItem(key);
      }
    } catch (e) { /* storage unavailable */ }
  }
})();
