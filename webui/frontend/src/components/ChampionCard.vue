<script setup lang="ts">
// A champion wherever one is listed: their tile and, unless `name` is false, their name under
// it (after their faction's banner with `banner`), linking to their optimiser (`href`: a URL,
// or false for no link). `size`: the tile's ("small", "large"); `card`: on a card, lit in their
// rarity when pointed at. The default slot goes under the link (a lock picker, a note).
import { computed } from "vue";
import type { ChampionRow } from "../types/generated/webui.service.views";
import ChampionTile from "./ChampionTile.vue";
import PageLink from "./PageLink.vue";

const props = withDefaults(
  defineProps<{
    champion: ChampionRow;
    size?: string;
    name?: boolean;
    banner?: boolean;
    card?: boolean;
    href?: string | false;
  }>(),
  { size: "", name: true, banner: false, card: false, href: undefined },
);

const url = computed(() =>
  props.href === undefined ? `/champions/${props.champion.id}` : props.href,
);
const classes = computed(() => [
  "champion",
  props.size,
  { card: props.card },
  `rarity-${props.champion.rarity.toLowerCase()}`,
]);
</script>

<template>
  <div :class="classes">
    <component :is="url ? PageLink : 'div'" v-bind="url ? { href: url } : {}">
      <ChampionTile :champion="champion" :size="size" />
      <span v-if="name" class="champion-name">
        <template v-if="banner">
          <img
            v-if="champion.faction_icon_url"
            class="faction"
            :src="champion.faction_icon_url"
            :alt="champion.faction"
            :title="champion.faction"
          />
          <small v-else>{{ champion.faction }}</small>
        </template>
        <span class="clamp">{{ champion.name }}</span>
      </span>
    </component>
    <slot />
  </div>
</template>
