<script setup lang="ts">
// A piece as a list's row, in cells: its art; slot and stars (and what the slot adds beside
// them), set and faction, who wears it; its main stat; its substats.
import type { PieceView } from "../types/generated/webui.service.results";
import PieceArt from "./PieceArt.vue";
import Stars from "./Stars.vue";

defineProps<{ piece: PieceView }>();
</script>

<template>
  <td><PieceArt :piece="piece" size="small" /></td>
  <td>
    <strong>{{ piece.slot }}</strong>
    {{ " " }}<Stars :count="piece.rank" :art="piece.stars" kind="piece-stars" />
    <slot />
    <br />
    <small>{{ piece.set_name }}</small>
    {{ " "
    }}<img
      v-if="piece.faction_icon_url"
      class="faction small"
      :src="piece.faction_icon_url"
      :alt="piece.faction_label ?? ''"
      :title="piece.faction_label ?? ''"
    />
    <small v-else-if="piece.faction">· {{ piece.faction_label ?? piece.faction }}</small>
    <template v-if="piece.worn_by">
      <br /><small class="muted">on {{ piece.worn_by }}</small>
    </template>
  </td>
  <td>
    <strong>{{ piece.primary.label }}</strong>
  </td>
  <td>
    <small>
      <template v-for="(line, n) in piece.substats" :key="n">
        <span class="nowrap">
          {{ line.label }} {{ line.amount
          }}<template v-if="line.glyph"> ({{ line.glyph }})</template>
        </span>
        <template v-if="n < piece.substats.length - 1"> · </template>
      </template>
    </small>
  </td>
</template>
