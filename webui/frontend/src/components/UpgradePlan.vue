<script setup lang="ts">
// The pieces an event scoring gear upgrades (Gear Enhancement) takes upgraded to reach the
// milestone picked in the card's table (the next not reached by default), folded away like the
// card's rules: for each rank, how many new pieces taken from +0 to +12, all of that rank, the
// rest takes; a big figure each, what one earns under it.
import { computed } from "vue";
import type { MilestoneRow } from "../types/generated/webui.service.events";
import type { UpgradePlan } from "../types/generated/webui.service.upgrades";

const { plan, target, points } = defineProps<{
  plan: UpgradePlan;
  target: MilestoneRow;
  points: number;
}>();

const short = computed(() => target.points - points);

function count(value: number) {
  return value.toLocaleString();
}
</script>

<template>
  <details class="upgrade-plan">
    <summary>
      Upgrades
      <small class="muted">to reach {{ count(target.points) }}: {{ target.prize }}</small>
    </summary>

    <div class="cluster" style="--space: var(--space-l)">
      <div v-for="row in plan.rows" :key="row.stars">
        <span class="figure">{{ count(Math.ceil(short / row.points)) }}</span>
        <span class="caps">{{ row.stars }}★ to +{{ plan.level }}</span>
        <small class="muted detail">{{ count(row.points) }} each</small>
      </div>
    </div>
  </details>
</template>

<style scoped>
/* Folded like the card's rules, the milestone aimed at in its summary; a figure per rank, its
   label and what one earns under it. */
.upgrade-plan {
  > summary {
    font-weight: 700;
  }

  &[open] > summary {
    margin-bottom: var(--space-s);
    color: inherit;
  }
}

.caps,
.detail {
  display: block;
}
</style>
