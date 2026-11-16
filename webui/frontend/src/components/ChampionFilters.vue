<script lang="ts">
// The champion filters: name, rarity, faction, fewest stars, as the query `/finder` and the
// champion list read (`q`, `rarity`, `faction`, `grade`; empty: any). The filters (not the
// name) are remembered in this browser, the same for the list and the finder dialog.
import { watch, type Ref } from "vue";
import { writeKept } from "../composables/kept";

export interface Filters {
  q: string;
  rarity: string;
  faction: string;
  grade: string;
}

export const KEPT = "finder-filters";
export const REMEMBERED = ["rarity", "faction", "grade"] as const;

// Searches again on each change (typing in the name waits for a pause), remembering the
// filters as they go.
export function watchFilters(filters: Ref<Filters>, search: () => void) {
  let pending: ReturnType<typeof setTimeout> | undefined;

  watch(filters, (now, before) => {
    writeKept(KEPT, Object.fromEntries(REMEMBERED.map((name) => [name, now[name]])));
    clearTimeout(pending);
    pending = setTimeout(search, now.q !== before.q ? 200 : 0);
  });
}
</script>

<script setup lang="ts">
import { valueOf } from "../composables/format";
import type { FinderView } from "../types/generated/webui.service.finder";

defineProps<{ finder: FinderView; placeholder?: string; autofocus?: boolean }>();
const filters = defineModel<Filters>({ required: true });

function set(name: keyof Filters, event: Event) {
  filters.value = { ...filters.value, [name]: valueOf(event) };
}
</script>

<template>
  <form class="filter-bar grow" @submit.prevent>
    <input
      type="search"
      :value="filters.q"
      :placeholder="placeholder ?? 'Find a champion by name'"
      aria-label="Champion name"
      autocomplete="off"
      :autofocus="autofocus"
      @input="set('q', $event)"
    />
    <select :value="filters.rarity" aria-label="Rarity" @change="set('rarity', $event)">
      <option value="">Any rarity</option>
      <option v-for="rarity in finder.rarities" :key="rarity" :value="rarity">{{ rarity }}</option>
    </select>
    <select :value="filters.faction" aria-label="Faction" @change="set('faction', $event)">
      <option value="">Any faction</option>
      <option v-for="faction in finder.factions" :key="faction.value" :value="faction.value">
        {{ faction.label }}
      </option>
    </select>
    <select :value="filters.grade" aria-label="Fewest stars" @change="set('grade', $event)">
      <option value="">Any stars</option>
      <option v-for="grade in finder.grades" :key="grade" :value="String(grade)">
        {{ grade }}★{{ grade < 6 ? " and up" : "" }}
      </option>
    </select>
  </form>
</template>
