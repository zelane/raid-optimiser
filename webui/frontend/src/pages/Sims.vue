<script setup lang="ts">
// The sim page: a saved team against a stage (the target picker's), fought many times on the
// game's own battle engine, and the last sim's results: how often it cleared, the turns a win
// took, the damage, each champion's result-screen rows on average.
import { Head, router } from "@inertiajs/vue3";
import { computed, ref } from "vue";
import PageHead from "../components/PageHead.vue";
import SentNote from "../components/SentNote.vue";
import Stat from "../components/Stat.vue";
import TargetPicker from "../components/TargetPicker.vue";
import { type Sent, sendToGame } from "../composables/send";
import type { SimPage } from "../types/generated/webui.service.sims";
import type { TargetPicker as Picker } from "../types/generated/webui.service.targets";

const props = defineProps<{ page: SimPage; picker: Picker }>();

const team = ref(props.page.team === null ? "" : String(props.page.team));
const runs = ref(String(props.page.seeds));
const running = ref(false);
const sent = ref<Sent | null>(null);

// The saved teams by area, for the dropdown's groups.
const areas = computed(() => {
  const groups = new Map<string, typeof props.page.teams>();
  for (const option of props.page.teams)
    groups.set(option.area, [...(groups.get(option.area) ?? []), option]);
  return [...groups.entries()];
});
const chosen = computed(() => props.page.teams.find((option) => String(option.id) === team.value));
const result = computed(() => props.page.result);

function fields(target: string): Record<string, string> {
  return { team: team.value, runs: runs.value, target };
}

// The page's state rides in its URL: a target, team or run count changed visits it again.
function visit(target = props.picker.target) {
  const query = new URLSearchParams(fields(target));
  router.get(`/sims?${query}`, {}, { preserveState: true, preserveScroll: true });
}

async function run() {
  running.value = true;
  sent.value = null;
  sent.value = await sendToGame("/sims/run", fields(props.picker.target));
  running.value = false;
  if (!sent.value.error) router.reload({ only: ["page"] });
}

const number = (value: number) => value.toLocaleString("en-GB");
</script>

<template>
  <Head title="Sim" />
  <div class="stack" style="--space: var(--space-2xl)">
    <PageHead title="Sim">
      <template #lede>
        A saved team against a stage, fought many times on the game's own battle engine, as auto
        plays it with the team's skill settings: how often it clears, and how fast.
      </template>
    </PageHead>

    <section class="target-section" aria-label="Opponent">
      <TargetPicker :picker="picker" @picked="(_, target) => visit(target)" />
    </section>

    <section class="stack panel" aria-label="Team">
      <div class="cluster" style="--space: var(--space-s); --align: end">
        <label class="stack" style="--space: var(--space-3xs)">
          <span class="caps">Saved team</span>
          <select v-model="team" @change="visit()">
            <option value="">Pick a team…</option>
            <optgroup v-for="[area, options] in areas" :key="area" :label="area">
              <option v-for="option in options" :key="option.id" :value="String(option.id)">
                {{ option.name }}: {{ option.champions.join(", ") }}
              </option>
            </optgroup>
          </select>
        </label>
        <label class="stack" style="--space: var(--space-3xs)">
          <span class="caps">Runs</span>
          <input v-model="runs" class="runs" type="number" min="1" max="3000" @change="visit()" />
        </label>
        <button type="button" :disabled="running || !team" @click="run">
          {{ running ? "Running…" : "Run" }}
        </button>
      </div>
      <p v-if="chosen" class="note">{{ chosen.champions.join(" · ") }}</p>
      <p v-if="running" class="note">
        About a second a fight per process, six at once: 300 runs take a minute or so.
      </p>
      <SentNote :sent="sent" done="Done." />
    </section>

    <section v-if="result" class="stack" aria-label="Last sim">
      <h2>{{ result.team }} against {{ result.title }}</h2>
      <div class="cluster" style="--space: var(--space-xl)">
        <Stat
          :value="`${result.cleared} of ${result.fights}`"
          :label="`cleared (${((100 * result.cleared) / result.fights).toFixed(1)} %)`"
        />
        <Stat
          v-if="result.turns_mean !== null"
          :value="String(result.turns_mean)"
          label="turns per win"
        >
          {{ result.turns_min }} to {{ result.turns_max }}
        </Stat>
        <Stat :value="number(result.damage_mean)" label="damage, average" />
      </div>
      <p v-if="result.lost_seeds.length" class="note bad">
        Not cleared: seeds {{ result.lost_seeds.join(", ") }}
      </p>
      <div class="table-well">
        <table>
          <thead>
            <tr>
              <th>Champion</th>
              <th class="num">Dealt</th>
              <th class="num">Taken</th>
              <th class="num">Healed</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in result.champions" :key="row.name">
              <td>{{ row.name }}</td>
              <td class="num">{{ number(row.dealt) }}</td>
              <td class="num">{{ number(row.taken) }}</td>
              <td class="num">{{ number(row.healed) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="note">
        Each champion's rows are averages over the fights, as the result screen counts them.
      </p>
    </section>
  </div>
</template>

<style scoped>
.runs {
  inline-size: 7em;
}
</style>
