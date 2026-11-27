<script setup lang="ts">
// The dungeon runs an event scoring them (by their turns: Turn Attack; by the gear they drop:
// Ice Golem's) takes to reach the milestone picked in the card's table (the next not reached by
// default), folded away like the card's rules: the count of runs, big, from a stage (the hardest
// by default) and, scored by turns, the turns a run usually takes; what one earns under it and,
// under a daily cap, how many days.
import { computed, ref, watch } from "vue";
import type { MilestoneRow } from "../types/generated/webui.service.events";
import type { FightPlan } from "../types/generated/webui.service.fights";

const DEFAULT_TURNS = 30;
const SUPER_RAID_KEY = "events-super-raid"; // remembered in the browser: how the player runs

const { plan, target, points, perDay } = defineProps<{
  plan: FightPlan;
  target: MilestoneRow;
  points: number;
  perDay: number | null;
}>();

const stage = ref(0);
const turns = ref<number | "">(DEFAULT_TURNS);
const superRaid = ref(remembered());

watch(superRaid, (on) => {
  try {
    localStorage.setItem(SUPER_RAID_KEY, on ? "1" : "");
  } catch {
    // storage blocked: the choice lasts the visit
  }
});

function remembered() {
  try {
    return localStorage.getItem(SUPER_RAID_KEY) === "1";
  } catch {
    return false;
  }
}

const short = computed(() => target.points - points);
const each = computed(() => {
  const table = plan.stages[stage.value]?.points ?? [];
  if (!plan.by_turns) return table[0] ?? 0;
  const count = Math.min(Math.max(Math.round(Number(turns.value) || 1), 1), table.length);
  return table[count - 1] ?? 0;
});
// A super raid is two runs in one.
const perRaid = computed(() => each.value * (superRaid.value ? 2 : 1));
const runs = computed(() => (perRaid.value ? Math.ceil(short.value / perRaid.value) : null));
const days = computed(() => (perDay ? Math.ceil(short.value / perDay) : null));

function count(value: number) {
  return value.toLocaleString();
}
</script>

<template>
  <details class="fight-plan">
    <summary>
      Runs
      <small class="muted">to reach {{ count(target.points) }}: {{ target.prize }}</small>
    </summary>

    <div class="cluster" style="--space: var(--space-m); --align: end">
      <div>
        <span class="figure">{{ runs === null ? "–" : count(runs) }}</span>
        <span class="caps">
          {{ superRaid ? "super raid" : "run" }}{{ runs === 1 ? "" : "s" }}
        </span>
        <small class="muted detail">
          {{ count(perRaid) }} a {{ superRaid ? "super raid" : "run"
          }}<template v-if="!plan.by_turns"> on average</template
          ><template v-if="days && days > 1">
            · {{ days }} days at {{ count(perDay!) }} a day</template
          >
        </small>
      </div>

      <div class="cluster push" style="--space: var(--space-s)">
        <label class="inline" title="Two runs in one, for twice the energy">
          <input v-model="superRaid" type="checkbox" />
          Super raid
        </label>
        <label class="inline">
          Stage
          <select v-model.number="stage" class="small">
            <option v-for="(choice, index) in plan.stages" :key="choice.label" :value="index">
              {{ choice.label }}
            </option>
          </select>
        </label>
        <label
          v-if="plan.by_turns"
          class="inline"
          title="The turns a run usually takes, as the result screen counts them"
        >
          ~Turns
          <input
            v-model.number="turns"
            class="small"
            type="number"
            min="1"
            :max="plan.stages[0]?.points.length"
          />
        </label>
      </div>
    </div>
  </details>
</template>

<style scoped>
/* Folded like the card's rules, the milestone aimed at in its summary; the count of fights as a
   big figure, what one earns under it, the stage and turns beside it. */
.fight-plan {
  > summary {
    font-weight: 700;
  }

  &[open] > summary {
    margin-bottom: var(--space-s);
    color: inherit;
  }

  input[type="number"] {
    width: 4.5em;
  }
}

.caps,
.detail {
  display: block;
}
</style>
