<script setup lang="ts">
// Something asked for, as a chip whose × takes it off: a link to the page without it (`href`).
// The slot is what's asked (its icons and name); `kind` colours its border: a debuff, buff,
// effect or mechanic (a tag's side), a count, or gear. Assumed ones (`assumed`) are dashed.
import { Link } from "@inertiajs/vue3";

defineProps<{ href: string; title: string; kind: string }>();
</script>

<template>
  <Link
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
</template>

<style scoped>
/* A squared chip on a quiet face, its border in the kind's colour (full on hover, when the ×
   shows too). */
.remove-chip {
  --kind: var(--secondary);

  display: inline-flex;
  align-items: stretch;
  border: 1px solid color-mix(in srgb, var(--kind) 55%, var(--outline));
  border-radius: var(--radius-s);
  font-size: var(--text-xs);
  line-height: 1.2;
  color: var(--on-surface);
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
    --kind: var(--error);
  }

  &.kind-buff {
    --kind: var(--tertiary);
  }

  &.kind-effect,
  &.kind-mechanic {
    --kind: var(--form-any);
  }

  &.kind-count {
    --kind: var(--warning);
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
