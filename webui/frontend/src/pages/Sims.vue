<script setup lang="ts">
// The sim page: a team against a stage (the target picker's), fought many times on the game's
// own battle engine: a saved team loads the configurator (champions swapped in and out, each's
// skill priorities under their tile), whose team is what runs; and the last sim's results: how often it cleared (against a boss
// that can't die, lasted to the turn limit), the turns, the damage, the Chimera's trials
// completed, each champion's result-screen rows on average.
import { Head, router } from "@inertiajs/vue3";
import { computed, ref, toRaw, watch } from "vue";
import PageHead from "../components/PageHead.vue";
import SentNote from "../components/SentNote.vue";
import SimProgress from "../components/SimProgress.vue";
import Stat from "../components/Stat.vue";
import TargetPicker from "../components/TargetPicker.vue";
import TeamConfigurator from "../components/TeamConfigurator.vue";
import TeamPicker from "../components/TeamPicker.vue";
import { type Sent, sendToGame } from "../composables/send";
import type { SimPage, SlotView } from "../types/generated/webui.service.sims";
import type { TargetPicker as Picker } from "../types/generated/webui.service.targets";

const props = defineProps<{ page: SimPage; picker: Picker }>();

const team = ref(props.page.team === null ? "" : String(props.page.team));
const runs = ref(String(props.page.seeds));
const target = ref(props.picker.target);
const running = ref(props.page.running); // a sim under way, maybe started before a reload
const stopped = ref(false);
const sent = ref<Sent | null>(null);

const teamList = ref(props.picker.team_list);
const waves = ref(props.picker.waves.length);
const teamSize = ref(props.picker.team_size);

function picked(pick: string, view: Picker) {
  target.value = pick;
  teamList.value = view.team_list;
  waves.value = view.waves.length;
  teamSize.value = view.team_size;
}

// The team as the configurator has it: the saved team's, loaded whenever one is picked.
const savedSlots = (id: string) =>
  structuredClone(toRaw(props.page.teams.find((option) => String(option.id) === id)?.slots ?? []));
const slots = ref<SlotView[]>(savedSlots(team.value));
watch(team, (id) => (slots.value = savedSlots(id)));

const result = computed(() => props.page.result);

function fields(): Record<string, string> {
  return { team: team.value, runs: runs.value, target: target.value };
}

function teamJson(): string {
  return JSON.stringify(
    slots.value.map((slot) => ({
      champion: slot.champion.id,
      waves: slot.waves.map(({ openers, priorities }) => ({ openers, priorities })),
    })),
  );
}

// Choices stay on the page (only Run asks the server for anything), kept in the address bar
// so a reload keeps them: the history entry is replaced in place, Inertia's page state with it.
watch([team, runs, target], () => {
  const url = `/sims?${new URLSearchParams(fields())}`;
  window.history.replaceState(window.history.state, "", url);
});

async function run() {
  running.value = true;
  stopped.value = false;
  sent.value = null;
  sent.value = await sendToGame("/sims/run", { ...fields(), slots: teamJson() });
  finished();
}

// The sim's over: its results, unless it failed.
function finished() {
  if (!running.value) return;
  running.value = false;
  if (!sent.value?.error) router.reload({ only: ["page"] });
}

// Ends the sim under way; the fights done by then are its result.
async function stop() {
  stopped.value = true;
  const outcome = await sendToGame("/sims/stop", {});
  if (outcome.error) sent.value = outcome;
}

const number = (value: number) => value.toLocaleString("en-GB");
const short = (value: number) =>
  value.toLocaleString("en-US", { notation: "compact", maximumSignificantDigits: 3 }); // 9.02M, 10.8B

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
        A team against a stage, fought many times on the game's own battle engine, as auto plays it
        with the team's skill settings: how often it clears, and how fast. Start from a saved team,
        then swap champions and change their skills.
      </template>
    </PageHead>

    <section class="target-section" aria-label="Opponent">
      <TargetPicker :picker="picker" @picked="(_, pick, view) => picked(pick, view)" />
    </section>

    <section class="stack panel" aria-label="Team">
      <div class="stack" style="--space: var(--space-3xs)">
        <span class="caps">Load a saved team</span>
        <TeamPicker v-model="team" :teams="page.teams" :list="teamList" />
      </div>
      <TeamConfigurator v-model="slots" :waves="waves" :size="teamSize" />
      <p v-if="slots.length > teamSize" class="note bad">
        This stage takes {{ teamSize }} champions: take {{ slots.length - teamSize }} out.
      </p>
      <div class="cluster" style="--space: var(--space-s); --align: end">
        <label class="stack" style="--space: var(--space-3xs)">
          <span class="caps">Runs</span>
          <input v-model="runs" class="runs" type="number" min="1" max="3000" />
        </label>
        <button
          type="button"
          :disabled="running || !slots.length || slots.length > teamSize"
          @click="run"
        >
          {{ running ? "Running…" : "Run" }}
        </button>
        <button v-if="running" type="button" class="quiet" :disabled="stopped" @click="stop">
          {{ stopped ? "Stopping…" : "Stop" }}
        </button>
      </div>
      <SimProgress v-if="running" @finished="finished" />
      <SentNote
        :sent="sent"
        :done="stopped ? 'Stopped: the fights done by then are below.' : 'Done.'"
      />
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
        <Stat :value="number(result.damage_mean)" label="damage, average">
          <span :title="`${number(result.damage_min)} to ${number(result.damage_max)}`">
            {{ short(result.damage_min) }} to {{ short(result.damage_max) }}
          </span>
        </Stat>
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
