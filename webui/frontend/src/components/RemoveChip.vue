<script setup lang="ts">
// Something asked for, as a chip whose × takes it off: a link to the page without it (`href`).
// The slot is what's asked (its icons and name).
import { Link } from "@inertiajs/vue3";

defineProps<{ href: string; title: string }>();
</script>

<template>
  <Link class="chip on" :href="href" :title="title" preserve-scroll preserve-state>
    <slot /><span class="chip-remove" aria-hidden="true">×</span>
  </Link>
</template>

<style scoped>
.chip-remove {
  margin-left: var(--space-3xs);
  font-weight: 700;
  color: var(--on-surface-variant);
}

.chip:hover .chip-remove {
  color: var(--stat-down);
}
</style>
