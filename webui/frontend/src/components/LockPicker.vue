<script setup lang="ts">
// A champion's lock (0: unlocked), saved as soon as it's changed.
import { router } from "@inertiajs/vue3";
import type { ListedChampion } from "../types/generated/webui.service.finder";

const { listed, levels } = defineProps<{ listed: ListedChampion; levels: number[] }>();

function lock(event: Event) {
  const level = (event.target as HTMLSelectElement).value;
  router.post(
    `/champions/${listed.champion.id}/lock`,
    { level },
    { forceFormData: true, preserveScroll: true, preserveState: true, only: ["finder"] },
  );
}
</script>

<template>
  <select
    class="lock small"
    :class="{ 'is-locked': listed.lock }"
    :aria-label="`Lock ${listed.champion.name}`"
    title="A locked champion's gear is used only by solves allowing their lock level"
    :value="listed.lock"
    @change="lock"
  >
    <option :value="0">Unlocked</option>
    <option v-for="level in levels" :key="level" :value="level">Lock {{ level }}</option>
  </select>
</template>

<style scoped>
/* A lock: muted when unlocked, brass when locked; the card's width on a card. */
select.lock {
  &:not(.is-locked) {
    color: var(--on-surface-variant);
  }

  &.is-locked {
    border-color: var(--primary);
    color: var(--primary);
  }
}

.champion.card select.lock {
  width: 100%;
  font-size: var(--text-2xs);
}
</style>
