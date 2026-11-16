<script setup lang="ts">
// Stars: the game's art (`art`, plain ★ where a star has none), or `count` filled of `of`.
import type { StarView } from "../types/generated/webui.service.views";

const props = defineProps<{
  count?: number;
  art?: StarView[];
  of?: number;
  title?: string;
  kind?: string;
}>();
const count = props.count ?? 0;
</script>

<template>
  <span class="stars" :class="kind" :title="title || `${count} stars`">
    <template v-if="art">
      <template v-for="(star, n) in art" :key="n">
        <img v-if="star.image_url" :src="star.image_url" alt="" />
        <span v-else :class="`star-${star.colour}`">★</span>
      </template>
    </template>
    <template v-else>
      <span v-for="n in of ?? count" :key="n" :class="{ off: n > count }">★</span>
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
</style>
