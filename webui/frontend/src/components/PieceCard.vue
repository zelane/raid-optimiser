<script setup lang="ts">
// A piece as a card: its art, slot, stars and main stat (with its ascension bonus), who wears
// it, and its substats beside (rows for substats not rolled yet keep the cards level).
// `champion`: whose build it is (older runs didn't save their portrait on their own pieces).
import { computed } from "vue";
import type { PieceView } from "../types/generated/webui.service.results";
import type { ChampionRow } from "../types/generated/webui.service.views";
import PieceArt from "./PieceArt.vue";
import Portrait from "./Portrait.vue";
import Stars from "./Stars.vue";

const props = defineProps<{ piece: PieceView; champion: ChampionRow }>();
const wearer = computed(() => props.piece.worn_by ?? props.champion.name);
const wearerPortrait = computed(
  () => props.piece.worn_by_portrait ?? (props.piece.equipped ? props.champion.portrait_url : null),
);
const starsTitle = computed(() => {
  const { rank, ascend_level } = props.piece;
  return `${rank} stars${ascend_level ? `, ascended ${ascend_level}` : ""}`;
});
const ascensionTitle = computed(() => {
  const { ascension, planned_ascend_level, ascend_level } = props.piece;
  return ascension?.planned_amount
    ? `to ascend ${planned_ascend_level}★ (now ${ascension.amount} at ${ascend_level}★)`
    : "ascension bonus";
});
</script>

<template>
  <article class="piece" :class="{ 'is-equipped': piece.equipped }">
    <div class="piece-body">
      <header>
        <div class="piece-id">
          <PieceArt :piece="piece" />
          <div class="piece-title">
            <strong>{{ piece.slot }}</strong>
            <Stars :count="piece.rank" :art="piece.stars" :title="starsTitle" kind="piece-stars" />
            <span class="piece-main">
              <span :class="{ ignored: !piece.primary.optimised }">{{ piece.primary.label }}</span>
              <span
                v-if="piece.primary.planned_amount"
                class="planned"
                :title="`assumed (now ${piece.primary.amount})`"
              >
                {{ piece.primary.planned_amount }}
              </span>
              <span v-else>{{ piece.primary.amount }}</span>
              <span
                v-if="piece.ascension"
                class="ascension"
                :class="{ planned: piece.ascension.planned_amount }"
                :title="ascensionTitle"
              >
                {{ piece.ascension.label }}
                {{ piece.ascension.planned_amount ?? piece.ascension.amount }}
              </span>
            </span>
          </div>
        </div>
        <span
          v-if="piece.worn_by || piece.equipped"
          class="owner"
          :class="{ equipped: piece.equipped }"
          :title="`on ${wearer}`"
        >
          <Portrait v-if="wearerPortrait" :url="wearerPortrait" :name="wearer" size="small" />
          on {{ wearer }}
        </span>
        <span v-else class="owner muted">Unequipped</span>
      </header>
      <table class="piece-stats">
        <tbody>
          <tr v-for="(line, n) in piece.substats" :key="n">
            <th scope="row" class="stat-name" :class="{ ignored: !line.optimised }">
              {{ line.label }}
            </th>
            <td class="stat-value">
              <span
                v-if="line.planned_amount"
                class="planned"
                :class="{ ignored: !line.optimised }"
                :title="`assumed (now ${line.amount})`"
              >
                {{ line.planned_amount }}
              </span>
              <span v-else :class="{ ignored: !line.optimised }">{{ line.amount }}</span>
              <template v-if="line.planned_glyph">
                {{ " " }}
                <span
                  class="glyph planned"
                  :title="`glyph to apply${line.glyph ? ` (now ${line.glyph})` : ''}`"
                >
                  {{ line.planned_glyph }}
                </span>
              </template>
              <template v-else-if="line.glyph">
                {{ " " }}<span class="glyph" title="glyph">{{ line.glyph }}</span>
              </template>
            </td>
          </tr>
          <tr
            v-for="n in Math.max(0, 4 - piece.substats.length)"
            :key="`open-${n}`"
            class="stat-open"
            aria-hidden="true"
          >
            <th scope="row">–</th>
            <td></td>
          </tr>
        </tbody>
      </table>
    </div>
  </article>
</template>
