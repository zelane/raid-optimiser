<script setup lang="ts">
// The frame an event's plan draws in, under the card's milestones: folded like the card's rules,
// its title and the milestone it aims at in the summary ("Runs to reach 6,300: 40 × Prism
// Jewels"), the plan itself in the slot.
import { formatCount } from "../composables/format";
import type { MilestoneRow } from "../types/generated/webui.service.events";

const { title, target } = defineProps<{ title: string; target: MilestoneRow }>();
</script>

<template>
  <details class="plan-panel">
    <summary>
      {{ title }}
      <small class="muted">to reach {{ formatCount(target.points) }}: {{ target.prize }}</small>
    </summary>
    <slot />
  </details>
</template>

<style scoped>
/* The title bold beside the milestone; opened, a gap before the plan. */
.plan-panel {
  > summary {
    font-weight: 700;
  }

  &[open] > summary {
    margin-bottom: var(--space-s);
    color: inherit;
  }
}
</style>
