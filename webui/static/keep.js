// Page state kept in this browser, not the address bar, and changes made without loading the
// page again. A page that opts in loads this script in its head with `data-keep="<key>"`,
// `data-swap="<selector>"` (the part of the page its requests re-render) and
// `data-drop="<field> …"` (fields not kept, such as one that starts a slow solve). Its query
// still carries the state to the server, so:
//  - a visit with a query saves it (less the dropped fields) and cleans the address bar;
//  - a visit without one (the nav, a reload) goes to the saved query, if any;
//  - a form submitted or a link to this page followed inside the swapped part is fetched with
//    htmx and only that part replaced (its query saved once it renders); a request the server
//    refuses is loaded as a page instead, so its error shows as before;
//  - a click on a `[data-forget]` link forgets the saved query first ("Empty all").
// Storage may be missing or throw (private windows): then the page just works from its URL.
(function () {
  const script = document.currentScript;
  const key = `keep:${script.dataset.keep}`;
  const swap = script.dataset.swap;
  const drop = (script.dataset.drop || "").split(" ").filter(Boolean);
  const path = location.pathname;

  function save(search) {
    const query = new URLSearchParams(search);
    for (const name of drop) query.delete(name);
    try { localStorage.setItem(key, query.toString()); } catch {}
  }

  if (location.search) {
    save(location.search);
    history.replaceState(history.state, "", path + location.hash);
  } else {
    let saved = "";
    try { saved = localStorage.getItem(key) || ""; } catch {}
    if (saved) location.replace(`${path}?${saved}${location.hash}`);
  }

  function go(url) {
    const href = url.pathname + url.search;
    const part = document.querySelector(swap);
    htmx.ajax("GET", href, { source: part, target: part, select: swap, swap: "outerHTML" }).then(
      () => document.querySelector(swap) !== part && save(url.search),
    );
  }

  // A refused request (bad query, unknown column): show the server's answer as a page.
  document.addEventListener("htmx:responseError", (event) => {
    if (swap && event.detail.elt?.matches?.(swap)) location.href = event.detail.pathInfo.requestPath;
  });

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!swap || event.defaultPrevented || form.hasAttribute("hx-get") || !form.closest(swap)) return;
    if (form.method !== "get") return;
    const url = new URL(form.action, location.href);
    if (url.pathname !== path) return;

    event.preventDefault();
    url.search = new URLSearchParams(new FormData(form, event.submitter)).toString();
    go(url);
  });

  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    if (!link) return;
    if (link.matches("[data-forget]")) {
      try { localStorage.removeItem(key); } catch {}
    }

    const plain = event.button === 0 && !(event.ctrlKey || event.metaKey || event.shiftKey || event.altKey);
    if (!swap || event.defaultPrevented || !plain || !link.closest(swap) || link.target) return;
    const url = new URL(link.href);
    if (url.origin !== location.origin || url.pathname !== path) return;

    event.preventDefault();
    go(url);
  });
})();
