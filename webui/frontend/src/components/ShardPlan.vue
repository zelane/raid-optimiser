<script setup lang="ts">
// The shards an event scoring summons takes (Champion Chase) to reach the milestone picked in
// the card's table (the next not reached by default), folded away like the card's rules: champions counted by hand first (fused,
// or summoned since the last read: a box per rarity, marked in its colour, Void by a triangle,
// the void symbol), whose points come off what's still to earn;
// then for each shard type the shards the rest takes, typically and nine times in ten, beside
// those held and what they'd earn. At today's odds, boosts included, and from no mercy built up
// (the game doesn't keep the account's count): a guide, not a promise. The page brings the
// counts for its first target; another shortfall asks the server (`plan.shards_url`).
import { computed, reactive, ref, watch } from "vue";
import { getJson } from "../composables/send";
import type { MilestoneRow } from "../types/generated/webui.service.events";
import type { ShardRow, SummonPlan } from "../types/generated/webui.service.summons";
import { formatCount } from "../composables/format";
import PlanPanel from "./PlanPanel.vue";

const ASK_AFTER_MS = 250; // typing settles before the server is asked

const { plan, target, points } = defineProps<{
  plan: SummonPlan;
  target: MilestoneRow;
  points: number;
}>();

const counted = reactive<Record<string, number>>({});
const byHand = computed(() =>
  plan.kinds.reduce((sum, kind) => sum + (counted[kind.key] || 0) * kind.points, 0),
);
const short = computed(() => target.points - points - byHand.value);

const rows = ref<ShardRow[]>(plan.rows);
const asking = ref(false);
let pending: ReturnType<typeof setTimeout> | undefined;

// The page's own counts while they fit (its first target, nothing counted by hand); else ask.
watch(
  [() => plan, short],
  () => {
    clearTimeout(pending);

    if (short.value === plan.target - points && target.points === plan.target) {
      rows.value = plan.rows;
      return;
    }

    if (short.value <= 0) return;

    asking.value = true;
    pending = setTimeout(async () => {
      const found = await getJson<ShardRow[]>(`${plan.shards_url}?short=${short.value}`);
      asking.value = false;
      if (found) rows.value = found;
    }, ASK_AFTER_MS);
  },
  { immediate: true },
);
</script>

<template>
  <PlanPanel title="Shards" :target="target">
    <div class="stack" style="--space: var(--space-s)">
      <div class="cluster" style="--space: var(--space-s)">
        <label
          v-for="kind in plan.kinds"
          :key="kind.key"
          class="inline"
          :title="`${kind.label}: ${formatCount(kind.points)} points each`"
        >
          <span
            class="mark"
            :style="{ color: `var(--rarity-${kind.rarity.toLowerCase()})` }"
            :aria-label="kind.label"
            >{{ kind.void ? "▲" : "●" }}</span
          >
          <input
            v-model.number="counted[kind.key]"
            class="small"
            type="number"
            min="0"
            placeholder="0"
          />
        </label>
      </div>

      <p class="note">
        <template v-if="byHand">
          {{ formatCount(target.points - points) }} to go, {{ formatCount(byHand) }} counted by
          hand:
        </template>
        <strong v-if="short > 0">{{ formatCount(short) }} to earn from shards</strong>
        <strong v-else class="good">reached with those</strong>
      </p>

      <div v-if="short > 0" class="table-well" :class="{ asking }">
        <table>
          <thead>
            <tr>
              <th>Shard</th>
              <th class="num" title="Points one shard earns on average">Each</th>
              <th class="num" title="Shards needed: typically, and nine times in ten">Needed</th>
              <th class="num" title="Held, and what they would earn on average">Held</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="shard in rows" :key="shard.name">
              <th scope="row">
                {{ shard.name.replace(/ Shard$/, "") }}
                <span v-if="shard.boost" class="badge good" :title="shard.boost">boosted</span>
              </th>
              <td class="num">{{ formatCount(shard.per_shard) }}</td>
              <td class="num">
                <template v-if="shard.reach">
                  <strong :class="{ good: shard.held >= shard.reach.typical }">
                    ~{{ formatCount(shard.reach.typical) }}
                  </strong>
                  <small class="muted"> ≤ {{ formatCount(shard.reach.likely) }}</small>
                </template>
                <small v-else class="muted">out of reach</small>
              </td>
              <td class="num">
                {{ formatCount(shard.held) }}
                <small class="muted earns">≈ {{ formatCount(shard.held_earns) }} pts</small>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="note">
        One type alone, from no mercy built up (the game doesn't keep your count), at today's odds:
        boosted while a summon event runs.
      </p>
    </div>
  </PlanPanel>
</template>

<style scoped>
/* A row of counts by hand, then a table of shard types; a count the held shards cover in green,
   what those held would earn under their count. The table dims while new counts are asked for. */
tbody th {
  font-weight: 400;
  white-space: nowrap;
}

input {
  width: 4.5em;
}

/* A kind's mark: its rarity's colour; a triangle for Void, a dot for the rest. */
.mark {
  font-size: var(--text-lg);
  line-height: 1;
}

.earns {
  display: block;
  white-space: nowrap;
}

.asking {
  opacity: 0.5;
  transition: opacity var(--transition);
}
</style>
