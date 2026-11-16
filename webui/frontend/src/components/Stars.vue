<script setup lang="ts">
// Stars: the game's art (`art`, plain ★ where a star has none), or `count` filled of `of`.
import { computed } from "vue";
import type { StarView } from "../types/generated/webui.service.views";

const props = defineProps<{
  count?: number;
  art?: StarView[];
  of?: number;
  title?: string;
  kind?: string;
}>();
const filled = computed(() => props.count ?? 0);
</script>

<template>
  <span class="stars" :class="kind" :title="title || `${filled} stars`">
    <template v-if="art">
      <template v-for="(star, n) in art" :key="n">
        <img v-if="star.image_url" :src="star.image_url" alt="" />
        <span v-else :class="`star-${star.colour}`">★</span>
      </template>
    </template>
    <template v-else>
      <span v-for="n in of ?? filled" :key="n" :class="{ off: n > filled }">★</span>
    </template>
  </span>
</template>

<style scoped>
/* A piece's stars: inline, the art at the text's height. */
.piece-stars {
  display: inline-flex;
  vertical-align: middle;

  img {
    height: 1em;
    margin-right: -0.1em;
  }
}

/* Stars in the legendary gold, those not earned muted; the game's star colours by kind. */
.stars {
  color: var(--rarity-legendary);
  letter-spacing: -0.1em;

  .off {
    color: var(--outline-variant);
  }
}

.star-yellow {
  color: var(--rarity-legendary);
}

.star-purple {
  color: var(--rarity-epic);
}

.star-red {
  color: var(--stat-down);
}
</style>
