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
