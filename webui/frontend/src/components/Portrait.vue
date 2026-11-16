<script setup lang="ts">
// A champion as a round portrait, rimmed in their rarity's colour (none: muted); `name` is its
// alt and, without art, its first letters; `href`: a link (it grows when pointed at).
import PageLink from "./PageLink.vue";

defineProps<{
  url: string | null;
  name: string;
  rarity?: string;
  size?: string;
  title?: string;
  href?: string;
}>();
</script>

<template>
  <component
    :is="href ? PageLink : 'span'"
    v-bind="href ? { href } : {}"
    class="portrait"
    :class="[size, rarity ? `rarity-${rarity.toLowerCase()}` : '']"
    :title="title"
  >
    <img v-if="url" :src="url" :alt="name" loading="lazy" />
    <span v-else>{{ name.slice(0, 2) }}</span>
  </component>
</template>
