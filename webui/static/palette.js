// The colour palette switcher in the nav: sets <html data-palette="..."> (styled in
// palettes.css) and remembers the choice in a cookie, which the server reads to render the
// next page in it (base.html), so pages don't flash the default first.
(function () {
  const COOKIE = "raid_palette";
  const ONE_YEAR = 60 * 60 * 24 * 365; // seconds
  const picker = document.querySelector("select.palette");
  if (!picker) return;

  picker.addEventListener("change", () => {
    document.documentElement.dataset.palette = picker.value;
    document.cookie =
      `${COOKIE}=${encodeURIComponent(picker.value)}; path=/; max-age=${ONE_YEAR}; SameSite=Lax`;
  });
})();
