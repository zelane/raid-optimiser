// The colour palette switcher in the nav: sets <html data-palette="..."> (styled in
// palettes.css) and remembers the choice in a cookie, which the server reads to render the
// next page in it (base.html), so pages don't flash the default first.
(function () {
  const COOKIE = "raid_palette";
  const ONE_YEAR = 60 * 60 * 24 * 365; // seconds
  const picker = document.querySelector("select.palette");
  if (!picker) return;

  picker.addEventListener("change", () => {
    const root = document.documentElement;
    root.dataset.palette = picker.value;

    // Vault is dark only (base.html does the same on page load).
    if (picker.value === "vault") root.dataset.theme = "dark";
    else delete root.dataset.theme;

    document.cookie =
      `${COOKIE}=${encodeURIComponent(picker.value)}; path=/; max-age=${ONE_YEAR}; SameSite=Lax`;
  });
})();
