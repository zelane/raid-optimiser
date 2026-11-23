<script setup lang="ts">
// Something asked for, as a chip whose × takes it off: a link to the page without it (`href`),
// or, with none, a button announcing `remove` (for a page's own form state). The slot is what's
// asked (its icons and name); `kind` colours its border (`--kind`, which the slot may use too):
// a debuff (red) or buff (blue), or a count of them; an effect or mechanic (neutral), or gear.
// Assumed ones (`assumed`) are dashed.
import { Link } from "@inertiajs/vue3";

defineProps<{ href?: string; title: string; kind: string }>();
defineEmits<{ remove: [] }>();
</script>

<template>
  <Link
    v-if="href"
    class="remove-chip"
    :class="`kind-${kind}`"
    :href="href"
    :title="title"
    preserve-scroll
    preserve-state
  >
    <span class="chip-body"><slot /></span>
    <span class="chip-remove" aria-hidden="true">×</span>
  </Link>
  <button
    v-else
    type="button"
    class="remove-chip"
    :class="`kind-${kind}`"
    :title="title"
    @click="$emit('remove')"
  >
    <span class="chip-body"><slot /></span>
    <span class="chip-remove" aria-hidden="true">×</span>
  </button>
</template>

<style scoped>
/* A squared chip on a quiet face, its border in the kind's colour (full on hover, when the ×
   shows too). */
.remove-chip {
  --kind: var(--secondary);

  display: inline-flex;
  align-items: stretch;
  padding: 0;
  border: 2px solid color-mix(in srgb, var(--kind) 55%, var(--outline));
  border-radius: 0;
  font-size: var(--text-xs);
  font-weight: 400;
  line-height: 1.2;
  color: var(--on-surface);
  text-align: start;
  text-decoration: none;
  background: var(--surface-container);
  transition: border-color var(--transition);

  &:hover {
    border-color: var(--kind);
  }

  &:focus-visible {
    outline: 1px solid var(--primary);
    outline-offset: 2px;
  }

  &.assumed {
    border-style: dashed;
  }

  &.kind-debuff {
    --kind: var(--debuff);
  }

  &.kind-buff {
    --kind: var(--buff);
  }

  &.kind-gear {
    --kind: var(--primary);
  }
}

.chip-body {
  display: inline-flex;
  gap: var(--space-s);
  align-items: center;
  padding: var(--space-2xs) var(--space-xs) var(--space-2xs) var(--space-s);
}

.chip-remove {
  display: grid;
  place-items: center;
  padding-inline: var(--space-xs) var(--space-s);
  font-weight: 700;
  color: var(--on-surface-variant);
  opacity: 0.35;
  transition:
    color var(--transition),
    opacity var(--transition);
}

.remove-chip:hover .chip-remove {
  color: var(--stat-down);
  opacity: 1;
}
</style>
