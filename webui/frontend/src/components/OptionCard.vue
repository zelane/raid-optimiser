<script setup lang="ts">
// A team found: its score and how much it meets (`met` of `total`), its members (any champion
// where it needs none), what the default slot adds (a glance), then a link showing its needs
// below and one using it.
import { Link } from "@inertiajs/vue3";
import type { SlotView } from "../types/generated/webui.service.team";
import ChampionCard from "./ChampionCard.vue";
import ScorePill from "./ScorePill.vue";

defineProps<{
  option: { number: number; slots: SlotView[]; score: number; show_url: string; use_url: string };
  shown: boolean;
  met: number;
  total: number;
  scoreTitle: string;
  showLabel: string;
}>();
</script>

<template>
  <article
    :id="`option-${option.number}`"
    class="stack team-option"
    :class="{ shown }"
    style="--space: var(--space-m)"
  >
    <div class="cluster" style="--justify: space-between">
      <strong>Option {{ option.number }}</strong>
      <span class="cluster">
        <ScorePill :score="option.score" :title="scoreTitle" />
        <strong :class="met === total ? 'up' : 'down'">{{ met }} / {{ total }}</strong>
      </span>
    </div>
    <div class="team-members">
      <template v-for="(slot, n) in option.slots" :key="n">
        <span v-if="!slot.champion" class="champion small muted" title="Any champion">
          <span class="free-slot">any</span>
          <span class="champion-name">Any champion</span>
        </span>
        <ChampionCard
          v-else
          :champion="slot.champion"
          size="small"
          :class="{ suggested: slot.suggested }"
          :title="`${slot.champion.name}${slot.suggested ? ' (suggested)' : ''}${slot.needed ? '' : ', not needed'}`"
        />
      </template>
    </div>
    <slot />
    <div class="cluster push">
      <Link
        :href="option.show_url"
        class="quiet small grow"
        role="button"
        :aria-current="shown ? 'true' : undefined"
        preserve-scroll
        preserve-state
      >
        {{ showLabel }}
      </Link>
      <Link :href="option.use_url" class="small grow" role="button" preserve-scroll preserve-state>
        Use this team
      </Link>
    </div>
  </article>
</template>

<style scoped>
/* The options found: a card each, its members across (any champion where it needs none), a
   glance at what it clears, and its buttons. The one the needs below show has the brass rail. */
.team-option.shown {
  border-color: var(--primary);
  box-shadow: inset 3px 0 0 var(--primary);
}

.team-members {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--space-2xs);
}

.free-slot {
  display: grid;
  place-items: center;
  aspect-ratio: 1;
  width: 3.5rem;
  border: 2px dashed var(--outline-variant);
  border-radius: var(--radius-l);
  font-size: var(--text-2xs);
  color: var(--on-surface-variant);
}
</style>
