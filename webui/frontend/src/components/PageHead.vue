<script setup lang="ts">
// A page's title, its lede (the `lede` slot) and what sits at the other end (`aside`).
defineProps<{ title: string; id?: string }>();
</script>

<template>
  <header class="page-head">
    <div>
      <h1 :id="id">{{ title }}</h1>
      <p v-if="$slots.lede" class="lede"><slot name="lede" /></p>
    </div>
    <slot name="aside" />
  </header>
</template>

<style scoped>
/* The title and lede, and what's at the other end (tabs, a tally), wrapping under it when short. */
.page-head {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-l) var(--space-3xl);
  align-items: flex-end;
  justify-content: space-between;

  > div:first-child {
    flex: 1 1 26rem;
  }

  h1 {
    margin: 0 0 var(--space-xs);
  }

  .lede {
    margin: 0;
    font-size: var(--text-s);
  }
}
</style>
