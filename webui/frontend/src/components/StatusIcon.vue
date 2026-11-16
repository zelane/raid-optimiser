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
