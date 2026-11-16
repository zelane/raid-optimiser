<script setup lang="ts">
// A piece's art: its picture in its rarity's rim, its level on it (the assumed one if it's to
// be levelled).
import type { PieceView } from "../types/generated/webui.service.results";

defineProps<{ piece: PieceView; size?: string }>();
</script>

<template>
  <div
    class="piece-art"
    :class="[size, `rarity-${piece.rarity.toLowerCase()}`]"
    :title="`${piece.set_name}, ${piece.rarity}`"
  >
    <img v-if="piece.image_url" :src="piece.image_url" :alt="`${piece.set_name} ${piece.slot}`" />
    <span
      v-if="piece.planned_level"
      class="piece-level planned"
      :title="`to level (now +${piece.level})`"
    >
      +{{ piece.planned_level }}
    </span>
    <span v-else class="piece-level" title="level">+{{ piece.level }}</span>
  </div>
</template>

<style scoped>
.piece-art {
  position: relative;
  overflow: hidden;
  flex: none;
  width: 3.5rem;
  height: 3.5rem;
  border: 2px solid var(--rarity);
  border-radius: var(--radius);
  background: var(--art-backdrop);
  box-shadow: 0 0 14px color-mix(in srgb, var(--rarity) 35%, transparent);

  img {
    display: block;
    width: 100%;
    height: 100%;
  }

  &.small {
    width: 2.75rem;
    height: 2.75rem;
  }

  &.small .piece-level {
    font-size: 0.7em;
  }
}

.piece-level {
  position: absolute;
  right: 0.15em;
  bottom: 0.05em;
  font-size: 0.85em;
  font-weight: 800;
  line-height: 1;
  color: var(--on-art);
  text-shadow:
    0 0 2px var(--art-backdrop),
    0 0 2px var(--art-backdrop),
    1px 1px 1px var(--art-backdrop);

  &.planned {
    border: 0;
    color: var(--stat-up);
  }
}
</style>
