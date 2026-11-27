<script setup lang="ts">
// A build's details: what's still to do for it, the buttons that send it to the game, and its
// pieces. `champion` wears it; `title` heads it (default "Build <n>"); `gear` the gear rules it
// was found under and `team` its teammates, sent with Equip to be checked against the account now.
import { computed, ref } from "vue";
import { plural } from "../composables/format";
import { equipInGame, type Sent } from "../composables/send";
import type { BuildView } from "../types/generated/webui.service.results";
import type { ChampionRow } from "../types/generated/webui.service.views";
import PieceCard from "./PieceCard.vue";
import SentNote from "./SentNote.vue";

const SLOTS = [
  "Weapon",
  "Helmet",
  "Shield",
  "Gloves",
  "Chest",
  "Boots",
  "Ring",
  "Amulet",
  "Banner",
];

const props = defineProps<{
  build: BuildView;
  champion: ChampionRow;
  title?: string;
  gear?: Record<string, string>;
  team?: number[];
}>();
const heading = computed(() => props.title ?? `Build ${props.build.number}`);

const notes = computed(() => {
  const { equipped, from_others } = props.build;
  return [
    ...(equipped ? [`${equipped} already equipped`] : []),
    ...(from_others ? [`${from_others} worn by others`] : []),
  ].join(", ");
});

const todo = computed(() => {
  const { to_level, to_ascend, glyphs_to_apply } = props.build;
  const glyphs = `${plural(glyphs_to_apply, "glyph")} to apply`;
  return [
    ...(to_level ? [`${to_level} to level`] : []),
    ...(to_ascend ? [`${to_ascend} to ascend`] : []),
    ...(glyphs_to_apply ? [glyphs] : []),
  ].join(", ");
});

const sending = ref(false);
const sent = ref<Sent | null>(null);
const sentAction = ref<"preview" | "equip">("preview");

async function send(action: "preview" | "equip") {
  const { from_others } = props.build;

  if (action === "equip") {
    const taken = from_others
      ? ` ${plural(from_others, "piece")} will be taken off other champions.`
      : "";
    if (!confirm(`Equip ${heading.value} on ${props.champion.name} in game?${taken}`)) return;
  }

  sending.value = true;
  sent.value = await equipInGame(
    props.champion.id,
    props.build.artifact_ids,
    action,
    props.gear,
    props.team,
  );
  sentAction.value = action;
  sending.value = false;
}
</script>

<template>
  <section class="build-detail">
    <div class="build-head cluster" style="--space: var(--space-s) var(--space-l)">
      <h3>{{ heading }}</h3>
      <p class="build-notes note">
        {{ notes }}<template v-if="notes && todo">; </template>
        <span v-if="todo" class="planned">{{ todo }}</span>
      </p>
      <div class="equip">
        <button class="quiet" :disabled="sending" @click="send('preview')">Preview in game</button>
        <button :disabled="sending" @click="send('equip')">Equip in game</button>
        <span class="equip-result">
          <SentNote
            :sent="sent"
            :done="sentAction === 'equip' ? 'Equipped and synced.' : 'Previewing in game.'"
          />
        </span>
      </div>
    </div>
    <div class="pieces">
      <template v-for="(piece, n) in build.slots" :key="n">
        <PieceCard v-if="piece" :piece="piece" :champion="champion" />
        <article v-else class="piece slot empty">
          <small>{{ SLOTS[n] }}: empty</small>
        </article>
      </template>
    </div>
  </section>
</template>

<style scoped>
.build-head {
  margin-bottom: var(--space-l);

  h3 {
    margin: 0;
    font-size: var(--text-xl);
  }
}

.build-notes {
  flex: 1 1 14rem;

  &:not(:empty)::before {
    content: "◆";
    margin-right: var(--space-s);
    font-size: 0.75em;
    color: var(--primary);
  }

  &:empty {
    display: none;
  }
}

.equip {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-m);
  align-items: center;
}

/* Three across, as the game lays out gear: weapon, helmet, shield; gloves, chest, boots; ring,
   amulet, banner. One a row when the build's own width is short of three. Each a card: the
   art glowing in its rarity, slot, stars and main stat; the substats two a row on the slab;
   the set and rank at the foot. */
.build-detail {
  container: build / inline-size;
}

.pieces {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-l);
  margin-bottom: var(--space-3xl);
}

@container build (min-width: 40rem) {
  .pieces {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

.piece.slot.empty {
  min-height: 9rem;
}
</style>
