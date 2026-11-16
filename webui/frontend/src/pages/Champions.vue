<script setup lang="ts">
// The champion list: the account's champions as the filters narrow them, each with their lock.
// The filters ride in the URL; a change reloads only the list.
import { Head, router } from "@inertiajs/vue3";
import { computed, onMounted, ref, watch } from "vue";
import ChampionCard from "../components/ChampionCard.vue";
import ChampionFilters, { KEPT, REMEMBERED, type Filters } from "../components/ChampionFilters.vue";
import LockPicker from "../components/LockPicker.vue";
import { readKept, writeKept } from "../composables/kept";
import type { FinderView } from "../types/generated/webui.service.finder";

const props = defineProps<{ finder: FinderView; lock_levels: number[] }>();
const query = props.finder.query;

const count = computed(() => {
  const { found, picks } = props.finder;
  const champions = `${found} champion${found !== 1 ? "s" : ""}`;
  return found > picks.length
    ? `${champions}: the first ${picks.length}, narrow the search for the rest`
    : champions;
});
const filters = ref<Filters>({
  q: query.text,
  rarity: query.rarity ?? "",
  faction: query.faction ?? "",
  grade: query.min_grade ? String(query.min_grade) : "",
});

let pending: ReturnType<typeof setTimeout> | undefined;

watch(filters, (now, before) => {
  writeKept(KEPT, Object.fromEntries(REMEMBERED.map((name) => [name, now[name]])));
  clearTimeout(pending);
  pending = setTimeout(search, now.q !== before.q ? 200 : 0);
});

function search() {
  const wanted = Object.fromEntries(Object.entries(filters.value).filter(([, value]) => value));
  router.get("/", wanted, {
    only: ["finder"],
    preserveState: true,
    preserveScroll: true,
    replace: true,
  });
}

// A visit without filters takes the ones this browser remembers (an option no longer offered,
// a faction the account has none of now, is left as it is).
onMounted(() => {
  const kept = readKept(KEPT, REMEMBERED);
  const offered: Record<keyof Filters, string[]> = {
    q: [],
    rarity: props.finder.rarities,
    faction: props.finder.factions.map((faction) => faction.value),
    grade: props.finder.grades.map(String),
  };
  const restored = { ...filters.value };

  for (const name of REMEMBERED) {
    const value = kept[name];
    if (value !== undefined && offered[name].includes(value)) restored[name] = value;
  }

  if (REMEMBERED.some((name) => restored[name] !== filters.value[name])) filters.value = restored;
});
</script>

<template>
  <Head title="Champions" />
  <div class="stack">
    <div class="cluster" style="--space: var(--space-s) var(--space-2xl); --basis: 24rem">
      <h1>Champions</h1>
      <ChampionFilters v-model="filters" :finder="finder" autofocus />
    </div>
    <div class="stack" style="--space: var(--space-s)">
      <p class="caps">{{ count }}</p>
      <div v-if="finder.picks.length" class="champion-grid">
        <ChampionCard
          v-for="listed in finder.picks"
          :key="listed.champion.id"
          :champion="listed.champion"
          banner
          card
        >
          <LockPicker :listed="listed" :levels="lock_levels" />
        </ChampionCard>
      </div>
      <p v-else>No champion matches: try fewer letters, or other filters.</p>
    </div>
  </div>
</template>
