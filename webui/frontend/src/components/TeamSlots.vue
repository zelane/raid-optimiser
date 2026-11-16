<script setup lang="ts">
// The team's slots: a champion the user put there (Change, ×, and the relic they wear: what's
// worn unless picked), or an open slot (+). The finder fills a slot; each change visits the
// page with it (`teamQuery`).
import { Link } from "@inertiajs/vue3";
import { computed, ref } from "vue";
import { forgetKept } from "../composables/keptQuery";
import { setAt, teamQuery, visitWith } from "../composables/teamQuery";
import type { ListedChampion } from "../types/generated/webui.service.finder";
import type { TeamLinks, TeamView } from "../types/generated/webui.service.team";
import ChampionCard from "./ChampionCard.vue";
import ChampionFinder from "./ChampionFinder.vue";

const props = defineProps<{
  team: TeamView;
  links: TeamLinks;
  ran: boolean;
  keep: string;
  only?: [string, string][];
}>();

const placed = computed(() => props.team.slots.filter((slot) => slot.champion).length);
const finder = ref<InstanceType<typeof ChampionFinder>>();
let filling = 0;

function find(index: number) {
  filling = index;
  finder.value?.open();
}

function place(slot: number, choice: string) {
  const query = teamQuery(props.links, props.ran);
  setAt(query, "slot", slot, choice);
  setAt(query, "relic", slot, "");
  visitWith(query);
}

function wear(slot: number, relic: string) {
  const query = teamQuery(props.links, props.ran);
  setAt(query, "relic", slot, relic);
  visitWith(query);
}

function picked(listed: ListedChampion) {
  place(filling, listed.choice);
}
</script>

<template>
  <section class="panel">
    <header class="panel-head">
      <h2>
        Your champions
        <span class="badge"> {{ placed }} placed · {{ team.slots.length - placed }} open </span>
      </h2>
      <Link :href="links.empty" class="caps" preserve-scroll @click="forgetKept(keep)">
        Empty all
      </Link>
    </header>
    <div class="grid" style="--min: 11rem; --space: var(--space-m)">
      <div
        v-for="(slot, n) in team.slots"
        :key="n"
        class="slot stack team-slot"
        :class="{ suggested: slot.suggested, empty: !slot.champion }"
      >
        <span class="caps"
          >Slot {{ n + 1 }}<template v-if="slot.suggested"> · suggested</template></span
        >
        <ChampionCard v-if="slot.champion" :champion="slot.champion" size="small" />
        <select
          v-if="slot.relics.length"
          class="small"
          :aria-label="`Relic for slot ${n + 1}`"
          :value="slot.relic"
          @change="wear(n, ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="option in slot.relics" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
        <template v-if="!slot.champion">
          <button
            type="button"
            class="slot-plus"
            :aria-label="`Find a champion for slot ${n + 1}`"
            title="Find a champion"
            @click="find(n)"
          >
            +
          </button>
          <small v-if="slot.problem" class="note bad"
            >“{{ slot.choice }}”: {{ slot.problem }}</small
          >
        </template>
        <div
          v-if="slot.choice"
          class="cluster push"
          style="--space: var(--space-xs); --justify: center"
        >
          <button v-if="slot.champion" type="button" class="quiet small" @click="find(n)">
            Change
          </button>
          <button
            type="button"
            class="quiet small"
            title="Empty this slot"
            :aria-label="`Empty slot ${n + 1}`"
            @click="place(n, '')"
          >
            ×
          </button>
        </div>
      </div>
    </div>
    <ChampionFinder ref="finder" :only="only" @picked="picked" />
  </section>
</template>
