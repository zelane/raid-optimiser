// A page's own tabs in the band under the bar, instead of its section's pages: the page
// teleports them to `#page-subnav` (`<Teleport defer to="#page-subnav">`) and calls
// `usePageSubnav()`, which tells the layout to show the band (counted, since the next page sets
// up before the last one goes).
import { inject, onUnmounted, provide, ref, type Ref } from "vue";

const KEY = Symbol("page subnav");

export function providePageSubnav(): Ref<number> {
  const pages = ref(0);
  provide(KEY, pages);
  return pages;
}

export function usePageSubnav() {
  const pages = inject<Ref<number>>(KEY);
  if (!pages) return;
  pages.value += 1;
  onUnmounted(() => (pages.value -= 1));
}
