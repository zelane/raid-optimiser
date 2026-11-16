<script setup lang="ts">
// A run's builds: the ledger (the gear worn now, then a build a row, each change beside its
// value), and the picked build's details under it (the first to begin with).
import { ref, watch } from "vue";
import type { ResultsView } from "../types/generated/webui.service.results";
import BuildDetail from "./BuildDetail.vue";

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
        Found {{ results.builds.length }} build{{ results.builds.length !== 1 ? "s" : "" }} in
        {{ results.seconds.toFixed(1) }}s
      </span>
      <span v-if="results.champion_level_note" class="planned">
        {{ results.champion.name }} {{ results.champion_level_note }}.
      </span>
      <span v-if="results.lore_of_steel">Lore of Steel applied.</span>
      <span v-if="results.damage">The DMG row is {{ results.damage }}.</span>
    </p>

    <div class="table-well">
      <table class="ledger">
        <thead>
          <tr>
            <th></th>
            <th v-for="now in results.current" :key="now.label" scope="col">{{ now.label }}</th>
          </tr>
        </thead>
        <tbody>
          <tr class="now">
            <th scope="row">Now</th>
            <td v-for="now in results.current" :key="now.label">{{ now.text }}</td>
          </tr>
          <tr
            v-for="build in results.builds"
            :key="build.number"
            class="build-row"
            :class="{ picked: build.number === picked }"
            @click="picked = build.number"
          >
            <th scope="row">
              <button
                type="button"
                class="build-pick"
                :aria-pressed="build.number === picked"
                @click="picked = build.number"
              >
                Build {{ build.number }}
              </button>
            </th>
            <td v-for="cell in build.stats" :key="cell.label">
              {{ cell.text
              }}<small :class="cell.change ? (cell.better ? 'up' : 'down') : ''">{{
                cell.change ?? ""
              }}</small>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
  <template v-for="build in results.builds" :key="build.number">
    <section v-if="build.number === picked" class="build-detail">
      <BuildDetail :build="build" :champion="results.champion" />
    </section>
  </template>
</template>
