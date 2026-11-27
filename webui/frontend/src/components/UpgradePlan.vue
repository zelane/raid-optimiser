<script setup lang="ts">
// The pieces an event scoring gear upgrades (Gear Enhancement) takes upgraded to reach the
// milestone picked in the card's table (the next not reached by default), folded away like the
// card's rules: for each rank, how many new pieces taken from +0 to +12, all of that rank, the
// rest takes; a big figure each, what one earns under it.
import { computed } from "vue";
import type { MilestoneRow } from "../types/generated/webui.service.events";
import type { UpgradePlan } from "../types/generated/webui.service.upgrades";
import { formatCount } from "../composables/format";
import PlanPanel from "./PlanPanel.vue";
import Stat from "./Stat.vue";

const { plan, target, points } = defineProps<{
  plan: UpgradePlan;
  target: MilestoneRow;
  points: number;
}>();

const short = computed(() => target.points - points);
</script>

<template>
  <PlanPanel title="Upgrades" :target="target">
    <div class="cluster" style="--space: var(--space-l)">
      <Stat
        v-for="row in plan.rows"
        :key="row.stars"
        :value="formatCount(Math.ceil(short / row.points))"
        :label="`${row.stars}★ to +${plan.level}`"
      >
        {{ formatCount(row.points) }} each
      </Stat>
    </div>
  </PlanPanel>
</template>
