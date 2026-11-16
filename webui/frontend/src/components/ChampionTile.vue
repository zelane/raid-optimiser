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

<style scoped>
/* After the game's collection: the portrait (140x182) in its rarity frame, the game's 9-slice
   frames (slices from the sprites' borders, top right bottom left) over a plain border in the
   rarity's colour for when a frame isn't extracted (and Uncommon, which has none). Overlays
   scale with the tile's font size. */
.tile {
  --tile-width: 5rem;
  --crest-height: 0px;

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
    margin-top: 0.15em;
  }
}

/* The stars are Stars' root (reached); their images are inside it. (A :deep() only compiles
   right in a rule of its own, not nested.) */
.tile .champion-stars :deep(img) {
  width: calc(100% / 6 + 0.1em);
  max-width: none;
  margin: 0 -0.05em;
}

/* The rarity's crest over the frame's lower edge (and a Mythical's over its top edge), on
   top of the frame as the game sets them, at the tile's scale; the stars move down under it,
   about two thirds of the crest over the frame. */
.tile.crested {
  &.rarity-epic {
    --crest-height: calc(var(--tile-width) * 0.13);
  }

  &.rarity-legendary {
    --crest-height: calc(var(--tile-width) * 0.118);
  }

  &.rarity-mythical {
    --crest-height: calc(var(--tile-width) * 0.235);
  }

  .champion-stars {
    margin-top: calc(var(--crest-height) * 0.35);
  }
}

.crest {
  pointer-events: none;
  position: absolute;
  z-index: 2;
  left: 50%;
  transform: translateX(-50%);
  width: auto;
  max-width: none;
}

.crest-top {
  top: 0;
  height: calc(var(--tile-width) * 0.14);
}

.crest-under {
  top: calc(var(--tile-width) * 182 / 140 - var(--crest-height));
  height: var(--crest-height);
}

.tile-frame {
  position: relative;
  overflow: hidden;
  aspect-ratio: 140 / 182;
  border: solid var(--rarity);
  border-width: 0.4em 0.4em 0.5em;
  background: var(--art-backdrop);
}

.tile-art {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
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
