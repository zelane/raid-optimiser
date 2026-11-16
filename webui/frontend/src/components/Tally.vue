<script setup lang="ts">
// `count` of `total` as a big figure in its `tone`, a caps `label`, and what the slot adds.
defineProps<{ count: number; total: number; label: string; tone?: string; title?: string }>();
</script>

<template>
  <div class="tally" :title="title">
    <strong class="figure" :class="tone"
      >{{ count }}<small>/{{ total }}</small></strong
    >
    <span class="caps">{{ label }}</span>
    <slot />
  </div>
</template>

<style scoped>
/* A big n/total in its tone over a caps label, on a small panel. */
.tally {
  display: grid;
  grid-template-columns: auto auto;
  gap: 0 var(--space-s);
  align-items: center;
  padding: var(--space-s) var(--space-l);
  border: 1px solid var(--outline-variant);
  border-radius: var(--radius-panel);
  background: var(--surface-container-low);

  strong {
    grid-row: span 2;
    font-size: var(--text-3xl);
    line-height: 1;

    small {
      font-size: 0.55em;
      color: var(--on-surface-variant);
    }
  }
}
</style>
