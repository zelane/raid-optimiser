<script setup lang="ts">
// One side of a swap (`gear-pair`): `label` and the piece's score as it stands, then `note` (the
// gain, or "then sell"), over the piece's card as `champion` sees it (the worn one is theirs
// and steps back). The one to equip (`candidate`) is rimmed in gold.
import type { AccessoryRow } from "../types/generated/webui.service.accessories";
import type { ChampionRow } from "../types/generated/webui.service.views";
import PieceCard from "./PieceCard.vue";

defineProps<{
  row: AccessoryRow;
  champion: ChampionRow;
  kind: "candidate" | "worn";
  label: string;
  note?: string;
  noteTone?: string;
}>();
</script>

<template>
  <div class="gear-card stack" :class="kind" style="--space: var(--space-xs)">
    <div class="cluster" style="--justify: space-between; --align: baseline">
      <span class="caps">{{ label }}</span>
      <span class="note">
        Score <strong>{{ row.now }}</strong>
        <small v-if="note" :class="noteTone">{{ note }}</small>
      </span>
    </div>
    <PieceCard :piece="row.piece" :champion="champion" />
  </div>
</template>
