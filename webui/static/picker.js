// A team finder's pickers (`_team.html`: what to bring, gear). Each is a search box over a
// dropdown of what isn't chosen yet, in groups; typing narrows it to the options whose text holds it, and a pick
// adds a field named by the picker's `data-picker` and reloads the page with it, where it shows
// as a removable chip. Arrow keys move between the shown options; Enter picks the focused one,
// or in the search box the only one left; Escape closes.
for (const picker of document.querySelectorAll("[data-picker]")) {
  const search = picker.querySelector(".picker-search");
  const list = picker.querySelector(".picker-options");
  const empty = picker.querySelector(".picker-empty");
  const options = [...picker.querySelectorAll(".picker-option")];
  const groups = [...picker.querySelectorAll(".picker-group")];

  const shown = () => options.filter((option) => !option.hidden);

  const open = () => {
    list.hidden = false;
    search.setAttribute("aria-expanded", "true");
  };

  const close = () => {
    list.hidden = true;
    search.setAttribute("aria-expanded", "false");
  };

  const pick = (option) => {
    const form = picker.closest("form");
    const field = document.createElement("input");
    field.type = "hidden";
    field.name = picker.dataset.picker;
    field.value = option.dataset.value;
    form.append(field);
    form.submit();
  };

  const narrow = () => {
    const text = search.value.trim().toLowerCase();

    for (const option of options) {
      option.hidden = Boolean(text) && !option.textContent.toLowerCase().includes(text);
    }

    for (const group of groups) {
      group.hidden = !group.querySelector(".picker-option:not([hidden])");
    }

    empty.hidden = shown().length > 0;
  };

  const step = (from, by) => {
    const visible = shown();
    const next = visible[visible.indexOf(from) + by];

    if (next) next.focus();
    else if (by < 0) search.focus();
  };

  narrow();
  search.addEventListener("focus", open);
  search.addEventListener("click", open);
  search.addEventListener("input", () => {
    open();
    narrow();
  });

  search.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      open();
      shown()[0]?.focus();
    } else if (event.key === "Enter") {
      event.preventDefault();
      const visible = shown();
      if (visible.length === 1) pick(visible[0]);
    } else if (event.key === "Escape") {
      close();
    }
  });

  for (const option of options) {
    option.addEventListener("click", () => pick(option));

    option.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        step(option, event.key === "ArrowDown" ? 1 : -1);
      } else if (event.key === "Escape") {
        search.focus();
        close();
      }
    });
  }

  picker.addEventListener("focusout", (event) => {
    if (!picker.contains(event.relatedTarget)) close();
  });

  document.addEventListener("pointerdown", (event) => {
    if (!picker.contains(event.target)) close();
  });
}
