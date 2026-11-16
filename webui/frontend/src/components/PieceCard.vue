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
            <Stars
              :count="piece.rank"
              :colours="piece.stars"
              :title="starsTitle"
              kind="piece-stars"
            />
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

<style scoped>
.piece {
  header {
    display: flex;
    flex-direction: column;
    flex-grow: 1;
    gap: var(--space-s);
    align-self: stretch;
    min-width: 0;

    .owner {
      display: inline-flex;
      gap: var(--space-xs);
      align-items: center;
      min-width: 0;
      margin-top: auto;
      font-size: var(--text-xs);

      &.equipped {
        color: var(--primary);
      }
    }
  }

  .glyph {
    color: var(--stat-up);
  }

  .ascension {
    color: var(--rarity-epic);
  }

  .ignored {
    color: var(--on-surface-variant);
    opacity: 0.8;
  }
}

/* The piece and its substats side by side, both from the top; the header runs the body's height
   so who wears the piece sits at its bottom. */
.piece-body {
  display: flex;
  gap: var(--space-m);
  align-items: flex-start;
}

.piece-id {
  display: flex;
  gap: var(--space-s);
  align-items: center;
  min-width: 0;
}

.piece-title {
  display: flex;
  flex-direction: column;
  gap: var(--space-3xs);
  align-items: flex-start;
  align-self: center;
  min-width: 0;
  line-height: 1.2;

  strong {
    font-family: var(--font-display);
    font-size: var(--text-l);
  }
}

.piece-main {
  display: flex;
  flex-wrap: wrap;
  gap: 0 var(--space-xs);
  align-items: baseline;
  font-weight: 700;
  color: var(--primary);

  /* The ascension bonus always on a line of its own, under the main stat. */
  .ascension {
    flex-basis: 100%;
    font-size: 0.85em;
    font-weight: 600;
    white-space: nowrap;
  }
}

table.piece-stats {
  display: block;
  flex-shrink: 1;
  width: 50%;
  margin: 0;
  padding: var(--space-xs) var(--space-m);
  border-radius: var(--radius);
  background: var(--surface-container-lowest);

  /* Two columns, 40/60: the stat, then its value and glyph, both from the left. The rows are only
   their cells (`contents`), so every row shares the columns. */
  tbody {
    display: grid;
    grid-template-columns: minmax(0, 2fr) minmax(0, 3fr);
    gap: var(--space-3xs) var(--space-m);
    align-items: baseline;
  }

  tr {
    display: contents;
  }

  th,
  td {
    padding: 0;
    border: 0;
    text-align: left;
    white-space: nowrap;
  }

  th {
    font-weight: 500;
    color: var(--on-surface-variant);
  }

  td.stat-value {
    font-weight: 600;
  }

  .glyph {
    font-size: 0.85em;
  }

  tr.stat-open th {
    opacity: 0.4;
  }
}

/* Already on the champion: nothing to do for it, so it steps back. */
.piece.is-equipped {
  opacity: 0.6;
  filter: saturate(0.4);
}
</style>
