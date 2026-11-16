// A page's own tabs in the band under the bar, instead of its section's pages (Accessories'
// steps): the page hands the layout its tabs (`usePageSubnav`), and the layout draws them as it
// draws its own. The next page sets its tabs before the last one goes, so each page clears only
// its own.
import { inject, onUnmounted, provide, ref, watchEffect, type Ref } from "vue";

export interface SubnavTab {
  href: string;
  label: string;
  current: boolean;
  badge?: { text: string; tone: string; title: string };
}

export interface PageSubnav {
  label: string;
  tabs: SubnavTab[];
}

interface Held {
  owner: symbol;
  subnav: PageSubnav;
}

const KEY = Symbol("page subnav");

export function providePageSubnav(): Ref<Held | null> {
  const held = ref<Held | null>(null);
  provide(KEY, held);
  return held;
}

export function usePageSubnav(subnav: () => PageSubnav) {
  const held = inject<Ref<Held | null>>(KEY);
  if (!held) return;

  const owner = Symbol("page");
  watchEffect(() => (held.value = { owner, subnav: subnav() }));
  onUnmounted(() => {
    if (held.value?.owner === owner) held.value = null;
  });
}
