// Build results: picking a build's row in the ledger (its button, or anywhere on the row)
// shows its pieces under the ledger. One build is shown at a time.
document.addEventListener("click", (event) => {
  const row = event.target.closest("tr.build-row");
  if (!row || event.target.closest("a, input, select")) return;

  for (const other of row.closest("tbody").querySelectorAll("tr.build-row")) {
    const picked = other === row;
    const pick = other.querySelector(".build-pick");
    other.classList.toggle("picked", picked);
    pick.setAttribute("aria-pressed", String(picked));
    document.getElementById(pick.getAttribute("aria-controls")).hidden = !picked;
  }
});

// Champion page: set rows are added and removed with their buttons (none to begin with).
// A target picked (target.js) sets the DEF damage ranks against; the picker says so when that
// DEF no longer matches it.
// Time solves; when a run is shown (the latest on opening the page, a new
// one, or one picked from the history), restore the form it was asked with and mark it in
// the history. Runs themselves are kept server-side.
(function () {
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

  setRows.addEventListener("change", (event) => {
    if (event.target.matches("select")) showSetIcon(event.target.closest(".set-row"));
  });

  // Reset also clears the set rows (it fires during restore, before the saved ones go back),
  // and goes back to the first form once the fields have been reset.
  form.addEventListener("reset", () => {
    setRows.replaceChildren();
    setTimeout(showForm);
  });

  // A mythical's form: the helm picked decides which stats and skills the page shows. The
  // other forms' skill pickers are disabled too, so only the picked one is submitted.
  document.addEventListener("change", (event) => {
    if (event.target.matches('input[name="form"]')) showForm();
  });
  const enemyDef = form.elements.namedItem("enemy_def");

  document.addEventListener("target:picked", (event) => {
    enemyDef.value = event.detail.defence;
    markTargetUse();
  });

  enemyDef.addEventListener("input", markTargetUse);
  markTargetUse();

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

  function showForm() {
    const picked = form.elements.namedItem("form")?.value || "0";

    for (const part of document.querySelectorAll("[data-form]")) {
      part.hidden = part.dataset.form !== picked;
      if (part.matches("select")) part.disabled = part.hidden;
    }
  }

  function markTargetUse() {
    const picker = document.getElementById("target-picker");
    if (picker) picker.classList.toggle("off-target", Number(enemyDef.value) !== Number(picker.dataset.defence));
  }

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

  // A set row's icon: the picked set's, if it has one.
  function showSetIcon(row) {
    const select = row.querySelector("select");
    const icon = row.querySelector(".set-icon img");
    const url = select.selectedOptions[0]?.dataset.icon;
    icon.hidden = !url;
    if (url) icon.src = url;
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
      showSetIcon(row);
    }

    // Only ticked boxes are saved, so every box is set: some are ticked by default.
    for (const box of form.querySelectorAll('input[type="checkbox"]')) {
      box.checked = box.name in values;
    }

    // The form first (a radio group: setting its value picks that radio), then that form's
    // skill: each form has its own picker.
    for (const [name, value] of Object.entries(values)) {
      if (/^(set|pieces)_\d+$/.test(name) || name === "damage_skill") continue;

      const field = form.elements.namedItem(name);
      if (field && field.type !== "checkbox") field.value = value;
    }

    showForm();
    const skill = form.querySelector('select[name="damage_skill"]:not([disabled])');
    if (skill && values.damage_skill) skill.value = values.damage_skill;

    // The run's target, as it was picked (its DEF stays the run's, even if the game's changed).
    showTarget(values.target).then(markTargetUse);
  }
})();
