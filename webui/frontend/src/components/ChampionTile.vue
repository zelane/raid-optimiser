<script setup lang="ts">
// A champion as the game's collection shows them: the portrait in its rarity frame, with
// affinity, level and empower on it, and the stars under it. An enemy has no level or stars.
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
    :class="[size, `rarity-${rarity}`]"
    :title="`${champion.name}, ${champion.rarity}`"
  >
    <div class="tile-frame">
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
      :colours="champion.stars"
      :title="starsTitle"
      kind="champion-stars"
    />
  </figure>
</template>

<style scoped>
/* After the game's collection: the portrait (140x182) in its rarity frame. Overlays scale with
   the tile's font size. */
.tile {
  --tile-width: 5rem;

  position: relative;
  width: var(--tile-width);
  margin: 0;
  font-size: calc(var(--tile-width) / 4.5);

  &.large {
    --tile-width: 8.5rem;
  }

  &.small {
    --tile-width: 3.5rem;
  }

  .champion-stars {
    display: flex;
    justify-content: center;
    margin-top: .3em;
  }
}

/* The stars are Stars' root (reached); each a sixth of the tile across. (A :deep() only
   compiles right in a rule of its own, not nested.) */
.tile .champion-stars :deep(.star) {
  width: calc(100% / 6 + 0.1em);
  gap: 1px;
  /* margin: 0 -0.05em; */
}

.tile-frame {
  position: relative;
  overflow: hidden;
  aspect-ratio: 140 / 182;
  border: 1px solid var(--rarity);
  background: var(--art-backdrop);

  /* The frame, as the game's: a band of the rarity's colour, its outer edge lit. */
  /* outline: 1px solid var(--rarity-light); */
}

.tile-art {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  border: 3px solid black;
}

.tile-missing {
  display: grid;
  place-items: center;
  height: 100%;
  padding: 0.2em;
  font-size: 0.7em;
  color: var(--on-art-muted);
  text-align: center;
}

.tile-affinity {
  position: absolute;
  bottom: 0.1em;
  left: 0.1em;
  width: 1.05em;
}

.tile-level,
.tile-empower {
  position: absolute;
  font-weight: 800;
  line-height: 1;
  color: var(--on-art);
  text-shadow:
    0 0 2px var(--art-backdrop),
    0 0 2px var(--art-backdrop),
    1px 1px 1px var(--art-backdrop);
}

.tile-level {
  right: 0.15em;
  bottom: 0.1em;
  font-size: 0.92em;
}

.tile-empower {
  top: 0.15em;
  right: 0.15em;
  font-size: 1em;
  color: var(--empower);
}
</style>
