// The champion filters (_champion_filters.html), on the champion list and in the finder
// dialog: as they change, htmx asks `/finder` for the matches. The filters (rarity, faction,
// stars; not the name) are remembered in this browser, `KEPT` in localStorage, shared by
// both: set again when the list's page loads and each time the dialog opens.
//
// The finder (_finder.html): a button marked `data-finder` opens it. A pick follows its link
// (the champion's optimiser), unless the opener says `data-finder="slot"`: then the pick's
// choice goes into the field `data-finder-target` names (a hidden one, say), the field
// `data-finder-reset` names (if any) is emptied, and its form is submitted. Enter in the
// search takes the first; Escape, × or the backdrop close it.
(function () {
  const KEPT = "finder-filters";
  const remembered = ["rarity", "faction", "grade"];

  // Sets the remembered filters; whether any changed.
  function restore(form) {
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(KEPT) || "{}"); } catch {}
    let changed = false;

    for (const name of remembered) {
      const field = form.elements.namedItem(name);
      const value = saved[name];
      // A value no longer offered (a faction the account has none of now) is left as it is.
      if (field && typeof value === "string" && field.value !== value
          && [...field.options].some((o) => o.value === value)) {
        field.value = value;
        changed = true;
      }
    }

    return changed;
  }

  function remember(form) {
    const kept = Object.fromEntries(remembered.map((name) => [name, form.elements.namedItem(name)?.value ?? ""]));
    try { localStorage.setItem(KEPT, JSON.stringify(kept)); } catch {}
  }

  const dialog = document.getElementById("finder");

  document.addEventListener("DOMContentLoaded", () => {
    for (const form of document.querySelectorAll("form[data-champion-filters]")) {
      form.addEventListener("change", () => remember(form));
      if (!dialog?.contains(form) && restore(form)) htmx.trigger(form, "filters:apply");
    }
  });

  if (!dialog) return;

  const form = dialog.querySelector("form[data-champion-filters]");
  const search = form.elements.namedItem("q");
  let opener = null;

  document.addEventListener("click", (event) => {
    const open = event.target.closest("[data-finder]");
    if (open) {
      opener = open;
      restore(form);
      dialog.showModal();
      search.select();
      htmx.trigger(form, "filters:apply");
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
      const reset = opener.dataset.finderReset && document.getElementById(opener.dataset.finderReset);
      if (reset) reset.value = "";
      field.form.submit();
      return;
    }

    window.location.href = pick.href;
  }
})();
