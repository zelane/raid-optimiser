<script setup lang="ts">
// A buff, debuff or effect: the game's icon, or a glyph where it has none.
defineProps<{ url: string | null; label: string; size?: string }>();
</script>

<template>
  <img
    v-if="url"
    class="status-icon"
    :class="size"
    :src="url"
    :alt="label"
    :title="label"
    loading="lazy"
  />
  <span v-else class="status-icon glyph" :class="size" :title="label" :aria-label="label">✦</span>
</template>

<style scoped>
.status-icon {
  flex: none;
  width: 1.5rem;
  height: 1.5rem;
  border-radius: var(--radius);
  object-fit: contain;

  &.small {
    width: 1.15rem;
    height: 1.15rem;
  }

  &.glyph {
    display: inline-grid;
    place-items: center;
    border: 1px solid color-mix(in srgb, var(--primary) 50%, transparent);
    font-size: var(--text-xs);
    color: var(--primary);
    background: color-mix(in srgb, var(--primary) 15%, transparent);
  }

  &.small.glyph {
    font-size: var(--text-2xs);
  }
}
</style>
