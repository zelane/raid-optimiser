// Build results: clicking a build's summary row shows or hides its details under it.
document.addEventListener("click", (event) => {
  const row = event.target.closest("tr.build-summary");
  if (!row || event.target.closest("a, input, select")) return;

  const toggle = row.querySelector(".build-toggle");
  const detail = document.getElementById(toggle.getAttribute("aria-controls"));
  const open = toggle.getAttribute("aria-expanded") !== "true";

  toggle.setAttribute("aria-expanded", String(open));
  detail.hidden = !open;
});

// Champion page: set rows are added and removed with their buttons (none to begin with).
// Time solves; when a run is shown (the latest on opening the page, a new
// one, or one picked from the history), restore the form it was asked with and mark it in
// the history. Runs themselves are kept server-side.
(function () {
  forgetOldStorage();

  const form = document.querySelector("form[data-champion]");
  if (!form) return;

  const results = document.getElementById("results");
  const setRows = document.getElementById("set-rows");
  const setRow = document.getElementById("set-row");
  let setRowsAdded = 0; // numbers rows uniquely; the server reads them in page order

  form.querySelector(".add-set").addEventListener("click", () => {
    addSetRow().querySelector("select").focus();
  });

  setRows.addEventListener("click", (event) => {
    const remove = event.target.closest(".remove-set");
    if (remove) remove.closest(".set-row").remove();
  });

  // Reset also clears the set rows (it fires during restore, before the saved ones go back).
  form.addEventListener("reset", () => setRows.replaceChildren());
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

  function addSetRow() {
    const n = setRowsAdded++;
    const row = setRow.content.firstElementChild.cloneNode(true);

    for (const field of row.querySelectorAll("[name]")) {
      field.name = field.name.replace("__n__", n);
    }

    setRows.append(row);
    return row;
  }

  // A saved form's set rows go back first, so their fields exist to be filled; rows left
  // empty (runs from when there were always three) are skipped.
  function restore(values) {
    form.reset();

    for (const [name, value] of Object.entries(values)) {
      const n = name.match(/^set_(\d+)$/)?.[1];
      if (n === undefined || !value) continue;

      const row = addSetRow();
      row.querySelector("select").value = value;
      row.querySelector("input").value = values[`pieces_${n}`] ?? "4";
    }

    for (const [name, value] of Object.entries(values)) {
      if (/^(set|pieces)_\d+$/.test(name)) continue;

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
