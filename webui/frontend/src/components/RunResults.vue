<script setup lang="ts">
// A run's builds: the ledger (the gear worn now, then a build a row, each change beside its
// value), and the picked build's details under it (the first to begin with).
import { ref, watch } from "vue";
import { plural } from "../composables/format";
import type { ResultsView } from "../types/generated/webui.service.results";
import BuildDetail from "./BuildDetail.vue";
import Ledger from "./Ledger.vue";

const props = defineProps<{ results: ResultsView }>();
const picked = ref(props.results.builds[0]?.number ?? 0);

watch(
  () => props.results,
  (results) => (picked.value = results.builds[0]?.number ?? 0),
);
</script>

<template>
  <div class="panel results-panel stack" style="--space: var(--space-m)">
    <p class="cluster note" style="--space: var(--space-xs) var(--space-l)">
      <span class="badge info">
        Found {{ plural(results.builds.length, "build") }} in {{ results.seconds.toFixed(1) }}s
      </span>
      <span v-if="results.champion_level_note" class="planned">
        {{ results.champion.name }} {{ results.champion_level_note }}.
      </span>
      <span v-if="results.lore_of_steel">Lore of Steel applied.</span>
      <span v-if="results.damage">The DMG row is {{ results.damage }}.</span>
    </p>

    <div class="table-well">
      <Ledger
        :current="results.current"
        :rows="
          results.builds.map((build) => ({
            key: build.number,
            picked: build.number === picked,
            stats: build.stats,
          }))
        "
        pickable
        @pick="(number) => (picked = number)"
      >
        <template #head="{ key }">
          <button type="button" class="build-pick" :aria-pressed="key === picked">
            Build {{ key }}
          </button>
        </template>
      </Ledger>
    </div>
  </div>
  <template v-for="build in results.builds" :key="build.number">
    <BuildDetail v-if="build.number === picked" :build="build" :champion="results.champion" />
  </template>
</template>

<style scoped>
.results-panel {
  margin-bottom: var(--space-2xl);
  padding: var(--space-l) var(--space-xl);
}

/* A build's row heading: its name, a button, brass when picked. */
button.build-pick {
  --button-bg: transparent;
  --button-edge: transparent;
  --button-fg: inherit;

  padding: 0;
  font-weight: 700;
  white-space: nowrap;
}

tr.picked .build-pick {
  color: var(--primary);
}
</style>
