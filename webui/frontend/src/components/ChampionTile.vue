<script setup lang="ts">
// A champion as the game's collection shows them: the portrait in its rarity frame, with
// affinity, level and empower on it, the rarity's crest over its lower edge (and a Mythical's
// over its top), and the stars under it. An enemy has no level or stars.
import { computed } from "vue";
import type { TileView } from "../types/views";
import Stars from "./Stars.vue";

const props = defineProps<{ champion: TileView; size?: string }>();
const rarity = computed(() => props.champion.rarity.toLowerCase());

const starsTitle = computed(() => {
  const { grade, ascension, awakening } = props.champion;
  const ascended = ascension ? `, ascended ${ascension}` : "";
  const awakened = awakening ? `, awakened ${awakening}` : "";
  return `${grade} stars${ascended}${awakened}`;
});
</script>

<template>
  <figure
    class="tile"
    :class="[size, `rarity-${rarity}`, { crested: champion.crest_url }]"
    :title="`${champion.name}, ${champion.rarity}`"
  >
    <img
      v-if="champion.crest_top_url"
      class="crest crest-top"
      :src="champion.crest_top_url"
      alt=""
    />
    <img v-if="champion.crest_url" class="crest crest-under" :src="champion.crest_url" alt="" />
    <div class="tile-frame" :class="`frame-${rarity}`">
      <img
        v-if="champion.portrait_url"
        class="tile-art"
        :src="champion.portrait_url"
        :alt="champion.name"
      />
      <span v-else class="tile-missing">{{ champion.name }}</span>
      <img
        v-if="champion.affinity_icon_url"
        class="tile-affinity"
        :src="champion.affinity_icon_url"
        :alt="champion.affinity"
        :title="champion.affinity"
      />
      <span v-if="champion.empower" class="tile-empower" title="empowered">
        +{{ champion.empower }}
      </span>
      <span v-if="champion.level !== undefined" class="tile-level" title="level">
        {{ champion.level }}
      </span>
    </div>
    <Stars
      v-if="champion.stars"
      :count="champion.grade"
      :art="champion.stars"
      :title="starsTitle"
      kind="champion-stars"
    />
  </figure>
</template>
