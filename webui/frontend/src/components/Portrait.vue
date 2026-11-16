<script setup lang="ts">
// A champion as a round portrait, rimmed in their rarity's colour (none: muted); `name` is its
// alt and, without art, its first letters.
defineProps<{ url: string | null; name: string; rarity?: string; size?: string; title?: string }>();
</script>

<template>
  <span
    class="portrait"
    :class="[size, rarity ? `rarity-${rarity.toLowerCase()}` : '']"
    :title="title"
  >
    <img v-if="url" :src="url" :alt="name" loading="lazy" />
    <span v-else>{{ name.slice(0, 2) }}</span>
  </span>
</template>
