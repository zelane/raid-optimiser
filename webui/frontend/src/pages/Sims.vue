<script setup lang="ts">
// The sim page: a saved team against a stage (the target picker's), fought many times on the
// game's own battle engine, and the last sim's results: how often it cleared (against a boss
// that can't die, lasted to the turn limit), the turns, the damage, the Chimera's trials
// completed, each champion's result-screen rows on average.
import { Head, router } from "@inertiajs/vue3";
import { computed, ref, watch } from "vue";
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
const target = ref(props.picker.target);
const running = ref(false);
const sent = ref<Sent | null>(null);

const teamList = ref(props.picker.team_list);

// The saved teams by list, for the dropdown's groups: first the one the opponent's team screen
// offers (as the game picks it), then the rest.
const lists = computed(() => {
  const groups = new Map<string, typeof props.page.teams>([[teamList.value, []]]);
  for (const option of props.page.teams)
    groups.set(option.area, [...(groups.get(option.area) ?? []), option]);
  return [...groups.entries()]
    .filter(([, options]) => options.length)
    .map(
      ([list, options]) =>
        [list === teamList.value ? `${list} (this stage's)` : list, options] as const,
    );
});

function picked(pick: string, view: Picker) {
  target.value = pick;
  teamList.value = view.team_list;
}
const chosen = computed(() => props.page.teams.find((option) => String(option.id) === team.value));
const result = computed(() => props.page.result);

function fields(): Record<string, string> {
  return { team: team.value, runs: runs.value, target: target.value };
}

// Choices stay on the page (only Run asks the server for anything), kept in the address bar
// so a reload keeps them: the history entry is replaced in place, Inertia's page state with it.
watch([team, runs, target], () => {
  const url = `/sims?${new URLSearchParams(fields())}`;
  window.history.replaceState(window.history.state, "", url);
});

async function run() {
  running.value = true;
  sent.value = null;
  sent.value = await sendToGame("/sims/run", fields());
  running.value = false;
  if (!sent.value.error) router.reload({ only: ["page"] });
}

const number = (value: number) => value.toLocaleString("en-GB");

// The fights not cleared, the first dozen by seed, with how each ended.
const uncleared = computed(() => {
  const misses = props.page.result?.uncleared ?? [];
  const shown = misses.slice(0, 12).map((f) => `${f.seed} (${f.ending}, ${f.turns} turns)`);
  return shown.join(", ") + (misses.length > 12 ? ` and ${misses.length - 12} more` : "");
});
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
      <TargetPicker :picker="picker" @picked="(_, pick, view) => picked(pick, view)" />
    </section>

    <section class="stack panel" aria-label="Team">
      <div class="cluster" style="--space: var(--space-s); --align: end">
        <label class="stack" style="--space: var(--space-3xs)">
          <span class="caps">Saved team</span>
          <select v-model="team">
            <option value="">Pick a team…</option>
            <optgroup v-for="[list, options] in lists" :key="list" :label="list">
              <option v-for="option in options" :key="option.id" :value="String(option.id)">
                {{ option.name }}: {{ option.champions.join(", ") }}
              </option>
            </optgroup>
          </select>
        </label>
        <label class="stack" style="--space: var(--space-3xs)">
          <span class="caps">Runs</span>
          <input v-model="runs" class="runs" type="number" min="1" max="3000" />
        </label>
        <button type="button" :disabled="running || !team" @click="run">
          {{ running ? "Running…" : "Run" }}
        </button>
      </div>
      <p v-if="chosen" class="note">{{ chosen.champions.join(" · ") }}</p>
      <p v-if="running" class="note">
        Six fights at once: 300 dungeon runs take a minute or so; a Chimera fight is about 15 s, so
        100 of them take about 4 minutes.
      </p>
      <SentNote :sent="sent" done="Done." />
    </section>

    <section v-if="result" class="stack" aria-label="Last sim">
      <h2>{{ result.team }} against {{ result.title }}</h2>
      <div class="cluster" style="--space: var(--space-xl)">
        <Stat
          :value="`${result.cleared} of ${result.fights}`"
          :label="`${result.unkillable ? 'lasted to the turn limit' : 'cleared'} (${((100 * result.cleared) / result.fights).toFixed(1)} %)`"
        />
        <Stat
          v-if="result.trials_count"
          :value="`${result.trials_mean} of ${result.trials_count}`"
          label="trials a fight"
        />
        <Stat
          v-if="result.turns_mean !== null"
          :value="String(result.turns_mean)"
          :label="result.unkillable ? 'turns' : 'turns per win'"
        >
          {{ result.turns_min }} to {{ result.turns_max }}
        </Stat>
        <Stat :value="number(result.damage_mean)" label="damage, average" />
      </div>
      <p v-if="result.uncleared.length" class="note bad">Not cleared, by seed: {{ uncleared }}</p>
      <p v-if="result.unkillable" class="note">
        The boss can't die: the game ends the fight at its turn limit and calls it a defeat. Here
        that's a clear; a fight ends short of it when the team is defeated.
      </p>
      <div v-if="result.trials_count" class="table-well">
        <table>
          <thead>
            <tr>
              <th>Trial completed</th>
              <th class="num">Fights</th>
              <th class="num">Boss turn, average</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="trial in result.trials" :key="trial.name">
              <td>{{ trial.name }}</td>
              <td class="num">{{ trial.completed }} of {{ result.fights }}</td>
              <td class="num">{{ trial.boss_turn }}</td>
            </tr>
            <tr v-if="!result.trials.length">
              <td colspan="3" class="note">None completed in any fight.</td>
            </tr>
          </tbody>
        </table>
      </div>
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
