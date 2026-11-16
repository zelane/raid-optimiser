// A page's state kept in this browser: each visit's query is saved (less the `drop` fields,
// such as one that starts a slow search), and a visit without one (the nav, a bookmark) goes
// to the saved one. Storage may be missing or throw (private windows): then the page just works
// from its URL.
import { router, usePage } from "@inertiajs/vue3";
import { onMounted, watch } from "vue";

function storageKey(key: string) {
  return `keep:${key}`;
}

export function useKeptQuery(key: string, drop: string[] = []) {
  const page = usePage();

  function save(url: string) {
    const query = new URL(url, window.location.origin).searchParams;
    for (const name of drop) query.delete(name);
    try {
      localStorage.setItem(storageKey(key), query.toString());
    } catch {
      // Not kept: the URL still has it.
    }
  }

  onMounted(() => {
    if (window.location.search) return save(page.url);

    let saved = "";
    try {
      saved = localStorage.getItem(storageKey(key)) ?? "";
    } catch {
      return;
    }
    if (saved) router.get(`${window.location.pathname}?${saved}`, {}, { replace: true });
  });

  watch(
    () => page.url,
    (url) => {
      if (new URL(url, window.location.origin).search) save(url);
    },
  );
}

export function forgetKept(key: string) {
  try {
    localStorage.removeItem(storageKey(key));
  } catch {
    // Nothing kept.
  }
}
