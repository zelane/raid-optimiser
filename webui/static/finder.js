// The champion finder (_finder.html): a button marked `data-finder` opens it; it lists what
// the filters match (htmx, `/finder`). A pick follows its link (the champion's optimiser),
// unless the opener says `data-finder="slot"`: then the pick's choice goes into the field
// `data-finder-target` names (a hidden one, say), and its form is submitted.
// Enter in the search takes the first; Escape, × or the backdrop close it. The filters
// (rarity, faction, stars; not the name) are remembered in this browser, `KEPT` in
// localStorage, and set again each time it opens.
(function () {
  const dialog = document.getElementById("finder");
  if (!dialog) return;

  const form = dialog.querySelector("form");
  const search = form.elements.namedItem("q");
  const KEPT = "finder-filters";
  const remembered = ["rarity", "faction", "grade"];
  let opener = null;

  function restore() {
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(KEPT) || "{}"); } catch {}

    for (const name of remembered) {
      const field = form.elements.namedItem(name);
      const value = saved[name];
      // A value no longer offered (a faction the account has none of now) is left as it is.
      if (field && typeof value === "string" && [...field.options].some((o) => o.value === value)) {
        field.value = value;
      }
    }
  }

  function remember() {
    const kept = Object.fromEntries(remembered.map((name) => [name, form.elements.namedItem(name)?.value ?? ""]));
    try { localStorage.setItem(KEPT, JSON.stringify(kept)); } catch {}
  }

  form.addEventListener("change", remember);

  document.addEventListener("click", (event) => {
    const open = event.target.closest("[data-finder]");
    if (open) {
      opener = open;
      restore();
      dialog.showModal();
      search.select();
      htmx.trigger(form, "finder:open");
      return;
    }

    const pick = event.target.closest(".finder-pick");
    if (pick && dialog.contains(pick)) {
      event.preventDefault();
      choose(pick);
    }
  });

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog || event.target.closest("[data-finder-close]")) dialog.close();
  });

  search.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const first = dialog.querySelector(".finder-pick");
    if (first) choose(first);
  });

  function choose(pick) {
    dialog.close();

    if (opener?.dataset.finder === "slot") {
      const field = document.getElementById(opener.dataset.finderTarget);
      field.value = pick.dataset.choice;
      field.form.submit();
      return;
    }

    window.location.href = pick.href;
  }
})();
