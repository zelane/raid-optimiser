<script setup lang="ts">
// Stars, flat, in the rarity colours: each star's own colour (`colours`: plain, ascended,
// awakened), or `count` filled of `of`.
import { computed } from "vue";
import type { StarView } from "../types/generated/webui.service.views";

const props = defineProps<{
  count?: number;
  colours?: StarView[];
  of?: number;
  title?: string;
  kind?: string;
}>();
const filled = computed(() => props.count ?? 0);

const stars = computed(() =>
  props.colours
    ? props.colours.map((star) => star.colour)
    : Array.from({ length: props.of ?? filled.value }, (_, n) =>
        n < filled.value ? "yellow" : "off",
      ),
);
</script>

<template>
  <span class="stars" :class="kind" :title="title || `${filled} stars`">
    <span v-for="(colour, n) in stars" :key="n" class="star" :class="`star-${colour}`" />
  </span>
</template>

<style scoped>
/* Stars at the text's height, each a star-clipped box lit from the top, in its rarity's
   colours: plain the Legendary gold, ascended the Epic violet, awakened the Mythical scarlet;
   those not earned muted. */
.stars {
  display: inline-flex;
  vertical-align: middle;

  /* A 1px black stroke: the stars are clipped, so it's drawn round the row's outline. */
  filter: drop-shadow(1px 0 0 var(--shadow)) drop-shadow(-1px 0 0 var(--shadow))
    drop-shadow(0 1px 0 var(--shadow)) drop-shadow(0 -1px 0 var(--shadow));
}

.star {
  --star: var(--outline-variant);
  --star-light: var(--outline-variant);

  flex: none;
  aspect-ratio: 1;
  width: 1em;
  background: linear-gradient(var(--star-light), var(--star) 70%);
  clip-path: polygon(
    50% 0%,
    61.8% 34.5%,
    100% 34.5%,
    69.1% 57.3%,
    80.9% 95.1%,
    50% 72.4%,
    19.1% 95.1%,
    30.9% 57.3%,
    0% 34.5%,
    38.2% 34.5%
  );
}

.star-yellow {
  --star: var(--rarity-legendary);
  --star-light: var(--rarity-legendary-light);
}

.star-purple {
  --star: var(--rarity-epic);
  --star-light: var(--rarity-epic-light);
}

.star-red {
  --star: var(--rarity-mythical);
  --star-light: var(--rarity-mythical-light);
}
</style>
