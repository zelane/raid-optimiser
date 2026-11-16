<script setup lang="ts">
// A champion as a round portrait, rimmed in their rarity's colour (none: muted); `name` is its
// alt and, without art, its first letters; `href`: a link (it grows when pointed at).
import { Link } from "@inertiajs/vue3";

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
    :is="href ? Link : 'span'"
    v-bind="href ? { href } : {}"
    class="portrait"
    :class="[size, rarity ? `rarity-${rarity.toLowerCase()}` : '']"
    :title="title"
  >
    <img v-if="url" :src="url" :alt="name" loading="lazy" />
    <span v-else>{{ name.slice(0, 2) }}</span>
  </component>
</template>

<style scoped>
/* A champion as a round portrait (`Portrait`), rimmed in their rarity (muted when it
   isn't known); a linked one grows when pointed at. */
.portrait {
  overflow: hidden;
  display: inline-grid;
  flex: none;
  place-items: center;
  width: 1.9rem;
  height: 1.9rem;
  border: 2px solid var(--outline-variant);
  border-radius: 50%;
  font-size: var(--text-2xs);
  text-decoration: none;
  background: var(--outline-variant);
  transition: transform var(--transition);

  &[class*="rarity-"] {
    border-color: var(--rarity);
  }

  &.small {
    width: 1.6rem;
    height: 1.6rem;
    border-width: 1px;
  }

  &:is(a):hover {
    transform: scale(1.15);
  }

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: top;
  }
}
</style>
