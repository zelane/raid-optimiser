<script setup lang="ts">
// The champion finder: a dialog listing the account's champions as the filters narrow them
// (`/finder`, as JSON); a pick is announced (`picked`) for the page to act on. `only`: a
// page's fixed hold on the list (`service.finder.OnlyView`'s fields). Enter in the search
// takes the first; Escape, × or the backdrop close it. The filters (not the name) are the
// champion list's, remembered in this browser.
import { ref, watch } from "vue";
import { readKept, writeKept } from "../composables/kept";
import type { FinderView, ListedChampion } from "../types/generated/webui.service.finder";
import ChampionCard from "./ChampionCard.vue";
import ChampionFilters, { KEPT, REMEMBERED, type Filters } from "./ChampionFilters.vue";

const props = defineProps<{ only?: [string, string][]; onlyLabel?: string | null }>();
const emit = defineEmits<{ picked: [listed: ListedChampion] }>();

const dialog = ref<HTMLDialogElement>();
const filters = ref<Filters>({ q: "", rarity: "", faction: "", grade: "" });
const found = ref<FinderView | null>(null);
const busy = ref(false);
let pending: ReturnType<typeof setTimeout> | undefined;
let asked = 0;

function open() {
  filters.value = { ...filters.value, q: "", ...readKept(KEPT, REMEMBERED) };
  dialog.value?.showModal();
  dialog.value?.querySelector<HTMLInputElement>('input[type="search"]')?.focus();
  search();
}

defineExpose({ open });

watch(filters, (now, before) => {
  writeKept(KEPT, Object.fromEntries(REMEMBERED.map((name) => [name, now[name]])));
  clearTimeout(pending);
  pending = setTimeout(search, now.q !== before.q ? 200 : 0);
});

async function search() {
  const query = new URLSearchParams(
    Object.entries(filters.value).filter(([, value]) => value) as [string, string][],
  );
  for (const [name, value] of props.only ?? []) query.append(name, value);
  const ask = ++asked;
  busy.value = true;

  try {
    const response = await fetch(`/finder?${query}`, { headers: { Accept: "application/json" } });
    if (response.ok && ask === asked) found.value = (await response.json()) as FinderView;
  } finally {
    if (ask === asked) busy.value = false;
  }
}

function pick(listed: ListedChampion) {
  dialog.value?.close();
  emit("picked", listed);
}

function takeFirst() {
  const first = found.value?.picks[0];
  if (first) pick(first);
}

function closeOnBackdrop(event: MouseEvent) {
  if (event.target === dialog.value) dialog.value?.close();
}
</script>

<template>
  <dialog ref="dialog" class="finder" aria-labelledby="finder-title" @click="closeOnBackdrop">
    <article class="stack" style="--space: var(--space-m)">
      <div class="panel-head">
        <h2 id="finder-title">Find a champion</h2>
        <button type="button" class="icon" aria-label="Close" @click="dialog?.close()">×</button>
      </div>
      <ChampionFilters
        v-if="found"
        v-model="filters"
        :finder="found"
        placeholder="Name (Enter takes the first)"
        @keydown.enter.prevent="takeFirst"
      />
      <p v-if="onlyLabel" class="note info">
        The target admits only {{ onlyLabel }}: only they are listed.
      </p>
      <div
        class="finder-results stack"
        :class="{ busy }"
        style="--space: var(--space-s)"
        aria-live="polite"
      >
        <template v-if="found">
          <p class="caps">{{ found.found }} champion{{ found.found !== 1 ? "s" : "" }}</p>
          <div v-if="found.picks.length" class="champion-grid">
            <ChampionCard
              v-for="listed in found.picks"
              :key="listed.champion.id"
              :champion="listed.champion"
              :title="listed.choice"
              :href="false"
              banner
              card
              class="finder-pick"
              role="button"
              tabindex="0"
              @click="pick(listed)"
              @keydown.enter="pick(listed)"
            />
          </div>
          <p v-else>No champion matches: try fewer letters, or other filters.</p>
        </template>
      </div>
    </article>
  </dialog>
</template>
