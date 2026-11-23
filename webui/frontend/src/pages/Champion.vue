<script setup lang="ts">
// A champion's optimiser: the target across the top; then the champion and their run history,
// the stat targets, the sets and the search; the run shown under all three. Its form is the
// run's when one is shown (the latest, or one picked from the history), else the defaults.
import { Head, router } from "@inertiajs/vue3";
import { computed, onUnmounted, ref, watch } from "vue";
import BattlePanel from "../components/BattlePanel.vue";
import ChampionFinder from "../components/ChampionFinder.vue";
import ChampionTile from "../components/ChampionTile.vue";
import RunHistory from "../components/RunHistory.vue";
import RunResults from "../components/RunResults.vue";
import TargetPicker from "../components/TargetPicker.vue";
import { checkedOf } from "../composables/format";
import { stopSolve } from "../composables/send";
import type { ChampionPage, FormView } from "../types/generated/webui.service.champions";
import type { RunView } from "../types/generated/webui.service.runs";
import type { EnemyCard, TargetPicker as Picker } from "../types/generated/webui.service.targets";

const props = defineProps<{ page: ChampionPage; run: RunView | null; picker: Picker }>();

// The form as `webui/forms/request.py` reads it: a field per name (a ticked box is present,
// "on"), the sets apart (posted as `set_<n>`/`pieces_<n>`), the damage skill per form.
const CHECKBOXES = /^(exclude_.*|locked|unworn_only)$/;
type Fields = Record<string, string>;
interface SetRow {
  id: number;
  set: string;
  pieces: string;
}

// The rate goals' rows: what each ranks, against which of the opponent's stats, and the
// minimum it can take (`webui/forms/request.py`).
const rates = [
  {
    rank: "LANDS",
    label: "Debuffs land",
    opponent: "RES",
    opponentField: "enemy_res",
    limitLabel: "lands at least",
    limitField: "min_landing",
  },
  {
    rank: "RESISTS",
    label: "Resist debuffs",
    opponent: "ACC",
    opponentField: "enemy_acc",
    limitLabel: "resists at least",
    limitField: "min_resisting",
  },
];

const fields = ref<Fields>({});
const sets = ref<SetRow[]>([]);
const skills = ref<Record<string, string>>({});
const target = ref(props.picker.target);
// The picked enemy's stats the form fills in (DEF for damage, RES and ACC for the rates).
const targetStats = ref(enemyStats(props.picker.picked));
let setsAdded = 0;

function firstSkill(form: FormView) {
  return String((form.skills.find((skill) => skill.supported) ?? form.skills[0])?.id ?? "");
}

function enemyStats(enemy: EnemyCard) {
  return { enemy_def: enemy.defence, enemy_res: enemy.resistance, enemy_acc: enemy.accuracy };
}

function defaults(): Fields {
  const excluded = props.page.options.rules.map((rule) => [`exclude_${rule.key}`, "on"]);
  return {
    form: "0",
    enemy_def: "6000",
    enemy_res: String(props.picker.picked.resistance),
    enemy_acc: String(props.picker.picked.accuracy),
    slack: "1",
    builds: "3",
    above_level: "8",
    lock_level: String(props.page.options.lock_levels[0] ?? 0),
    ...Object.fromEntries(excluded),
  };
}

// Back to the defaults, then the saved form's values over them: every box as saved (only
// ticked ones were), and its set rows (rows left empty, from runs when there were always
// three, are skipped).
function restore(saved: Record<string, string> | null) {
  const restored = defaults();
  skills.value = Object.fromEntries(
    props.page.forms.map((form) => [String(form.number), firstSkill(form)]),
  );
  sets.value = [];

  for (const name of Object.keys(restored)) {
    if (saved && CHECKBOXES.test(name) && !(name in saved)) delete restored[name];
  }

  for (const [name, value] of Object.entries(saved ?? {})) {
    const row = name.match(/^set_(\d+)$/)?.[1];

    if (row !== undefined) {
      if (value)
        sets.value.push({ id: setsAdded++, set: value, pieces: saved?.[`pieces_${row}`] ?? "4" });
    } else if (!/^pieces_\d+$/.test(name) && name !== "damage_skill" && name !== "target") {
      restored[name] = value;
    }
  }

  if (saved?.damage_skill) skills.value[restored.form ?? "0"] = saved.damage_skill;
  fields.value = restored;
}

restore(props.run?.form ?? null);

watch(
  () => props.run?.entry.id,
  () => restore(props.run?.form ?? null),
);

watch(
  () => props.picker,
  (picker) => {
    target.value = picker.target;
    targetStats.value = enemyStats(picker.picked);
  },
);

const form = computed(
  () =>
    props.page.forms.find((view) => String(view.number) === fields.value.form) ??
    props.page.forms[0],
);
const detached = computed(() =>
  Object.entries(targetStats.value).some(([name, value]) => Number(fields.value[name]) !== value),
);

function picked(enemy: EnemyCard, picked: string) {
  target.value = picked;
  targetStats.value = enemyStats(enemy);
  for (const [name, value] of Object.entries(targetStats.value)) fields.value[name] = String(value);
}

function checked(name: string) {
  return name in fields.value;
}

function tick(name: string, event: Event) {
  if (checkedOf(event)) fields.value[name] = "on";
  else delete fields.value[name];
}

function addSet() {
  sets.value.push({ id: setsAdded++, set: "", pieces: "4" });
}

function setIcon(id: string) {
  return props.page.options.sets.find((option) => String(option.id) === id)?.icon_url ?? null;
}

// Solving: the form posted, the run it keeps shown (the page's URL names it); timed while it
// runs, which can take minutes. Stop keeps the builds found by then.
const solving = ref(false);
const stopping = ref(false);
const elapsed = ref(0);
let ticking: ReturnType<typeof setInterval> | undefined;

function solve() {
  const posted: Fields = { ...fields.value, target: target.value };
  posted.damage_skill = skills.value[fields.value.form ?? "0"] ?? "";
  sets.value.forEach((row, n) => {
    posted[`set_${n}`] = row.set;
    posted[`pieces_${n}`] = row.pieces;
  });

  router.post(`/champions/${props.page.champion.id}/builds`, posted, {
    forceFormData: true,
    preserveScroll: true,
    preserveState: true,
    onStart: () => {
      const started = performance.now();
      solving.value = true;
      stopping.value = false;
      elapsed.value = 0;
      ticking = setInterval(() => (elapsed.value = (performance.now() - started) / 1000), 100);
    },
    onFinish: () => {
      solving.value = false;
      clearInterval(ticking);
    },
  });
}

onUnmounted(() => clearInterval(ticking));

function stop() {
  stopping.value = true;
  stopSolve();
}

const finder = ref<InstanceType<typeof ChampionFinder>>();
</script>

<template>
  <Head :title="page.champion.name" />
  <div class="champion-page">
    <section class="target-section" aria-label="Target">
      <TargetPicker
        :picker="picker"
        :detached="detached"
        @picked="(enemy, key) => picked(enemy, key)"
      />
    </section>
    <div class="champion-column stack" style="--space: var(--space-2xl)">
      <article
        class="panel stack champion-profile"
        :class="`rarity-${page.champion.rarity.toLowerCase()}`"
      >
        <div class="champion-identity">
          <ChampionTile :champion="page.champion" size="large" />
          <div class="stack" style="--space: var(--space-xs)">
            <h1>{{ page.champion.name }}</h1>
            <span>
              <img
                v-if="page.champion.faction_icon_url"
                class="faction"
                :src="page.champion.faction_icon_url"
                :alt="page.champion.faction"
                :title="page.champion.faction"
              />
              <small v-else>{{ page.champion.faction }}</small>
            </span>
            <button
              type="button"
              class="quiet small"
              title="Another champion's optimiser"
              @click="finder?.open()"
            >
              ⇄ Switch champion
            </button>
          </div>
        </div>
        <div v-if="page.forms.length > 1" class="cluster" style="--justify: space-between">
          <span class="caps">Form</span>
          <div class="segmented form-switch" role="radiogroup" aria-label="Form">
            <label
              v-for="view in page.forms"
              :key="view.number"
              :title="`Form ${view.number + 1}: ${view.role}`"
            >
              <input v-model="fields.form" type="radio" :value="String(view.number)" />
              <template v-if="view.icon_url">
                <img class="form-on" :src="view.icon_url" alt="" />
                <img class="form-off" :src="view.idle_url ?? view.icon_url" alt="" />
              </template>
              <span>{{ view.role }}</span>
            </label>
          </div>
        </div>
        <dl v-if="form" class="stat-tiles well" aria-label="Stats in the gear worn now">
          <div v-for="cell in form.current" :key="cell.label">
            <dt>{{ cell.label }}</dt>
            <dd>{{ cell.text }}</dd>
          </div>
        </dl>
      </article>
      <RunHistory
        :history="page.history"
        :champion-id="page.champion.id"
        :current="run?.entry.id"
      />
    </div>
    <form class="champion-main" @submit.prevent="solve" @reset.prevent="restore(null)">
      <div class="stack" style="--space: var(--space-2xl)">
        <fieldset class="panel targets">
          <legend>Stat targets</legend>
          <div class="stack" style="--space: var(--space-m)">
            <div class="table-well">
              <table class="limits">
                <thead>
                  <tr>
                    <th>Stat</th>
                    <th>At least</th>
                    <th>At most</th>
                    <th title="1 ranks first; blank: not ranked">Priority</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="stat in page.options.stats" :key="stat.name">
                    <th>
                      {{ stat.label }}<template v-if="stat.percent"> <small>%</small></template>
                    </th>
                    <td>
                      <input
                        v-model="fields[`min_${stat.name}`]"
                        type="number"
                        step="any"
                        placeholder="—"
                        :aria-label="`${stat.label} at least`"
                      />
                    </td>
                    <td>
                      <input
                        v-model="fields[`max_${stat.name}`]"
                        type="number"
                        step="any"
                        placeholder="—"
                        :aria-label="`${stat.label} at most`"
                      />
                    </td>
                    <td class="priority">
                      <input
                        v-model="fields[`rank_${stat.name}`]"
                        type="number"
                        min="1"
                        max="9"
                        placeholder="—"
                        :aria-label="`${stat.label} priority`"
                      />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="goal-pick stack" style="--space: var(--space-2xs)">
              <span class="caps">Damage</span>
              <div class="cluster" style="--space: var(--space-xs) var(--space-m)">
                <select
                  v-if="form"
                  v-model="skills[String(form.number)]"
                  aria-label="Skill to rank damage by"
                >
                  <option
                    v-for="skill in form.skills"
                    :key="skill.id"
                    :value="String(skill.id)"
                    :disabled="!skill.supported"
                    :title="skill.note"
                  >
                    {{ skill.name }}{{ skill.supported ? "" : " (can't be ranked)" }}
                  </option>
                </select>
                <label class="inline">
                  vs DEF
                  <input v-model="fields.enemy_def" type="number" min="0" step="any" />
                </label>
                <label class="inline" title="1 ranks first; blank: not ranked">
                  Priority
                  <input
                    v-model="fields.rank_DAMAGE"
                    class="rank"
                    type="number"
                    min="1"
                    max="9"
                    placeholder="—"
                    aria-label="Damage priority"
                  />
                </label>
              </div>
            </div>
            <small class="note">
              Damage ranks the skill's critical hit against that much enemy DEF (the target's, once
              one is picked above): pair it with C.RATE at least 100.
            </small>
            <div
              v-for="rate in rates"
              :key="rate.rank"
              class="goal-pick stack"
              style="--space: var(--space-2xs)"
            >
              <span class="caps">{{ rate.label }}</span>
              <div class="cluster" style="--space: var(--space-xs) var(--space-m)">
                <label class="inline" :title="`${rate.limitLabel}: a minimum (blank: none)`">
                  <input
                    v-model="fields[rate.limitField]"
                    type="number"
                    min="3"
                    max="97"
                    step="any"
                    placeholder="—"
                    :aria-label="`${rate.label}: ${rate.limitLabel} %`"
                  />
                  %
                </label>
                <label class="inline">
                  vs {{ rate.opponent }}
                  <input v-model="fields[rate.opponentField]" type="number" min="0" step="any" />
                </label>
                <label class="inline" title="1 ranks first; blank: not ranked">
                  Priority
                  <input
                    v-model="fields[`rank_${rate.rank}`]"
                    class="rank"
                    type="number"
                    min="1"
                    max="9"
                    placeholder="—"
                    :aria-label="`${rate.label} priority`"
                  />
                </label>
              </div>
            </div>
            <small class="note">
              Each rate's % is a minimum (lands or resists at least), against an opponent's RES or
              ACC (the target's, once one is picked). Ranked, more ACC or RES counts only while it
              moves the chance: past 97 % the next priority gets the gear.
            </small>
          </div>
        </fieldset>
      </div>
      <div class="stack" style="--space: var(--space-2xl)">
        <fieldset class="panel sets">
          <legend>Sets, at least</legend>
          <div>
            <div v-for="(row, n) in sets" :key="row.id" class="set-row well">
              <span class="set-icon" aria-hidden="true">
                <img v-if="setIcon(row.set)" :src="setIcon(row.set) ?? undefined" alt="" />
              </span>
              <select v-model="row.set" aria-label="Set" required>
                <option value="">Choose a set</option>
                <option
                  v-for="option in page.options.sets"
                  :key="option.id"
                  :value="String(option.id)"
                >
                  {{ option.name }}
                </option>
              </select>
              <input v-model="row.pieces" type="number" min="1" max="9" aria-label="Pieces" />
              <button
                type="button"
                class="icon"
                aria-label="Remove set"
                title="Remove set"
                @click="sets.splice(n, 1)"
              >
                ×
              </button>
            </div>
          </div>
          <button type="button" class="dashed" @click="addSet">+ Add a set</button>
        </fieldset>
        <fieldset class="panel">
          <legend>Battle</legend>
          <BattlePanel v-model:fields="fields" :options="page.options.battle" />
        </fieldset>
        <fieldset class="panel search">
          <legend>Search</legend>
          <div class="stack" style="--space: var(--space-l)">
            <div class="settings">
              <label
                class="well"
                title="How much of its best each ranked goal may give up for the next"
              >
                <span class="caps">Slack (%)</span>
                <input v-model="fields.slack" type="number" min="0" max="50" step="any" />
              </label>
              <label class="well">
                <span class="caps">Builds</span>
                <input v-model="fields.builds" type="number" min="1" max="10" />
              </label>
              <label class="well" title="Only pieces enhanced past this level">
                <span class="caps">Above level</span>
                <input v-model="fields.above_level" type="number" min="0" max="16" />
              </label>
            </div>
            <div class="stack" style="--space: var(--space-xs)">
              <p class="caps">Leave out gear from</p>
              <div
                class="switch-rows well"
                title="Gear the solve may not take; the champion's own is always allowed"
              >
                <label v-for="rule in page.options.rules" :key="rule.key">
                  <input
                    type="checkbox"
                    role="switch"
                    :checked="checked(`exclude_${rule.key}`)"
                    @change="tick(`exclude_${rule.key}`, $event)"
                  />
                  <span class="row-name">{{ rule.label }}</span>
                  <span class="row-note">{{ rule.pieces }} pcs</span>
                </label>
                <label class="lock-filter">
                  <input
                    type="checkbox"
                    role="switch"
                    :checked="checked('locked')"
                    @change="tick('locked', $event)"
                  />
                  <span class="row-name">Champions locked above</span>
                  <select v-model="fields.lock_level" class="small" aria-label="Lock level">
                    <option
                      v-for="level in page.options.lock_levels"
                      :key="level"
                      :value="String(level)"
                    >
                      {{ level }}
                    </option>
                  </select>
                </label>
                <label>
                  <input
                    type="checkbox"
                    role="switch"
                    :checked="checked('unworn_only')"
                    @change="tick('unworn_only', $event)"
                  />
                  <span class="row-name">Any other champion (unequipped gear only)</span>
                </label>
              </div>
            </div>
            <div class="actions">
              <button type="submit" class="cta" :disabled="solving">Find builds</button>
              <button type="reset" class="quiet cta">Reset</button>
            </div>
            <span v-if="solving" class="cluster" style="--space: var(--space-s); --align: center">
              <span class="note solving" aria-busy="true">
                {{ stopping ? "Stopping…" : "Solving…" }} {{ elapsed.toFixed(1) }}s
              </span>
              <button type="button" class="quiet small" :disabled="stopping" @click="stop">
                Stop
              </button>
            </span>
          </div>
        </fieldset>
      </div>
    </form>
  </div>
  <section v-if="run" class="run page-section">
    <h2>Results</h2>
    <p v-if="run.outcome === null">
      <small>
        This run was saved by an older version and can't be shown; its inputs are restored.
      </small>
    </p>
    <RunResults v-else-if="'builds' in run.outcome" :results="run.outcome" />
    <article v-else>
      <header><strong>No build meets the request</strong></header>
      <p v-if="run.outcome.reason">{{ run.outcome.reason }}</p>
      <template v-else>
        <ul>
          <li v-for="line in run.outcome.lines" :key="line">{{ line }}</li>
        </ul>
        <p>
          <small
            >Each limit on its own, with the sets asked; together they may still conflict.</small
          >
        </p>
      </template>
    </article>
  </section>
  <ChampionFinder
    ref="finder"
    @picked="(listed) => router.visit(`/champions/${listed.champion.id}`)"
  />
</template>

<style scoped>
/* The champion: portrait with name and faction beside it, the form switch (a mythical's),
   then their stats in the gear worn now, lit faintly in their rarity's colour. */
.champion-profile {
  background:
    radial-gradient(
      ellipse 80% 60% at 15% 0%,
      color-mix(in srgb, var(--rarity) 14%, transparent),
      transparent 70%
    ),
    var(--surface-container-low);

  h1 {
    font-size: var(--text-2xl);
    line-height: 1.15;
  }

  .stat-tiles {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

/* The tile is ChampionTile's: its frame is inside it. (A :deep() only compiles right in a rule
   of its own, not nested.) */
.champion-profile :deep(.tile-frame) {
  box-shadow: 0 0 18px color-mix(in srgb, var(--rarity) 35%, transparent);
}

.champion-identity {
  display: flex;
  gap: var(--space-l);
  align-items: flex-start;

  .stack {
    align-items: flex-start;
    padding-top: var(--space-s);
  }
}

/* A mythical's form switch, after the game's: two helms in a dark pill (a `segmented`), the
   picked one gold (and named), the other white and dim. */
.segmented.form-switch {
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--surface) 70%, var(--shadow));

  label {
    padding: var(--space-2xs) var(--space-m) var(--space-2xs) var(--space-xs);
    border-radius: var(--radius-pill);
    font-size: var(--text-xs);
    font-weight: 400;
  }

  label:has(:checked) {
    color: var(--on-surface);
    background: color-mix(in srgb, var(--primary) 16%, transparent);
  }

  img {
    width: 1.6rem;
    height: 1.6rem;
    object-fit: contain;
  }

  .form-on,
  label:has(:checked) .form-off {
    display: none;
  }

  label:has(:checked) .form-on {
    display: block;
  }

  .form-off {
    opacity: 0.55;
  }

  label:hover .form-off {
    opacity: 0.85;
  }
}

/* Stat targets: a ledger on the slab, blanks as dashes; a stat with anything asked of it
   lights up. Damage, its skill and the DEF it's against, close the panel. */
table.limits {
  th,
  td {
    padding: var(--space-2xs) var(--space-s);
  }

  tbody th {
    font-size: var(--text-s);
    font-weight: 700;
    white-space: nowrap;
  }

  input {
    height: auto;
    padding-block: var(--space-2xs);
    border-color: transparent;
    background: var(--surface-container-low);

    &::placeholder {
      opacity: 0.6;
    }
  }

  td.priority {
    width: 4rem;
  }

  tr:has(input:not(:placeholder-shown)) {
    > * {
      background: color-mix(in srgb, var(--primary) 7%, transparent);
    }

    th,
    input {
      color: var(--primary);
    }
  }
}

.goal-pick {
  > .caps {
    color: var(--primary);
  }

  select {
    flex: 1 1 9rem;
    width: auto;
    min-width: 0;
  }

  label {
    font-size: var(--text-xs);
    color: var(--on-surface-variant);
  }

  input {
    width: 4.75rem;

    &.rank {
      width: 3rem;
    }
  }
}

/* Sets: a row card each (the set's icon, which set, how many pieces), then a dashed button
   for another. */
.set-row {
  display: flex;
  gap: var(--space-s);
  align-items: center;
  margin-bottom: var(--space-s);

  select {
    flex: 1 1 auto;
    min-width: 0;
    font-weight: 600;
  }

  input {
    flex: 0 0 3.5rem;
  }

  .icon {
    font-size: var(--text-l);
  }
}

.set-icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 2.25rem;
  height: 2.25rem;
  border: 1px solid color-mix(in srgb, var(--primary) 45%, transparent);
  border-radius: var(--radius);
  background: var(--shade);

  img {
    width: 85%;
    height: 85%;
    object-fit: contain;
  }
}

/* The search: its numbers as three small wells, the gear filters as rows with their switch
   at the end, then the buttons. */
.settings {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-s);

  label {
    margin: 0;
  }
}

.actions {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: var(--space-m);
}

.solving {
  color: var(--primary);
}

/* The target across the top, then three columns of panels: the champion and their run
   history; the stat targets; the sets and the search. Two columns on a middling page (the
   sets and search under the champion), one on a narrow one. The request form is
   `display: contents`: its two columns are the page grid's own. The results run full width
   under it all. */
.champion-page {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-2xl);
  align-items: start;
  margin-bottom: var(--space-4xl);
}

.champion-main {
  display: contents;
}

@container page (min-width: 46rem) {
  .champion-page {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .target-section {
    grid-column: 1 / -1;
  }
}

@container page (min-width: 68rem) {
  .champion-page {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
