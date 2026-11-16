// Filter bars (`form.filter-bar[data-filter]`): the items its selector matches are shown when
// every field allows them. An item lists what it is per field, `data-filter-<name>`: a
// search field matches part of its text, any other field one of its space-separated words,
// "*" matching every value. An empty field allows anything. `[data-filter-count]` in the bar
// says how many are shown.
for (const bar of document.querySelectorAll("form.filter-bar[data-filter]")) {
  const count = bar.querySelector("[data-filter-count]");

  function allows(item, name, value) {
    const listed = item.dataset[`filter${name[0].toUpperCase()}${name.slice(1)}`] ?? "";
    if (bar.querySelector(`[name="${name}"]`).type === "search") {
      return listed.toLowerCase().includes(value.trim().toLowerCase());
    }
    const words = listed.split(" ");
    return words.includes(value) || words.includes("*");
  }

  function apply() {
    const fields = [...new FormData(bar)].filter(([, value]) => value.trim());
    const items = document.querySelectorAll(bar.dataset.filter);
    let shown = 0;
    for (const item of items) {
      item.hidden = !fields.every(([name, value]) => allows(item, name, value));
      if (!item.hidden) shown += 1;
    }
    if (count) count.textContent = shown === items.length ? `${shown}` : `${shown} of ${items.length}`;
  }

  bar.addEventListener("input", apply);
  bar.addEventListener("submit", (event) => event.preventDefault());
  apply();
}

// Editable stat tiles dim a zero as it's typed.
document.addEventListener("input", (event) => {
  const field = event.target;
  if (field.matches(".stat-tiles.edit input[type=number]")) {
    field.closest("label").classList.toggle("zero", Number(field.value) === 0);
  }
});

// The set grid lights the column under the pointer.
for (const grid of document.querySelectorAll("table.set-grid")) {
  grid.addEventListener("mouseover", (event) => {
    const cell = event.target.closest("td, th");
    const column = cell && cell.cellIndex > 0 && !cell.closest(".set-group") ? cell.cellIndex : -1;
    for (const row of grid.rows) {
      for (const other of row.cells) other.classList.toggle("lit", other.cellIndex === column && row.cells.length > 1);
    }
  });
  grid.addEventListener("mouseleave", () => {
    for (const lit of grid.querySelectorAll(".lit")) lit.classList.remove("lit");
  });
}
