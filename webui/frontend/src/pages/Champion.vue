<script setup lang="ts">
// A champion's optimiser: the target across the top; then the champion and their run history,
// the stat targets, the sets and the search; the run shown under all three. Its form is the
// run's when one is shown (the latest, or one picked from the history), else the defaults.
import { Head, router } from "@inertiajs/vue3";
import { computed, onUnmounted, ref, watch } from "vue";
import ChampionFinder from "../components/ChampionFinder.vue";
import ChampionTile from "../components/ChampionTile.vue";
import RunHistory from "../components/RunHistory.vue";
import RunResults from "../components/RunResults.vue";
import TargetPicker from "../components/TargetPicker.vue";
import type { ChampionPage, FormView } from "../types/generated/webui.service.champions";
import type { RunView } from "../types/generated/webui.service.runs";
import type { TargetPicker as Picker } from "../types/generated/webui.service.targets";

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

const fields = ref<Fields>({});
const sets = ref<SetRow[]>([]);
const skills = ref<Record<string, string>>({});
const target = ref(props.picker.target);
const targetDefence = ref(props.picker.picked.defence);
let setsAdded = 0;

function firstSkill(form: FormView) {
  return String((form.skills.find((skill) => skill.supported) ?? form.skills[0])?.id ?? "");
}

function defaults(): Fields {
  const excluded = props.page.options.rules.map((rule) => [`exclude_${rule.key}`, "on"]);
  return {
    form: "0",
    enemy_def: "6000",
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
    targetDefence.value = picker.picked.defence;
  },
);

const form = computed(
  () =>
    props.page.forms.find((view) => String(view.number) === fields.value.form) ??
    props.page.forms[0],
);
const detached = computed(() => Number(fields.value.enemy_def) !== targetDefence.value);

function picked(defence: number, picked: string) {
  target.value = picked;
  targetDefence.value = defence;
  fields.value.enemy_def = String(defence);
}

function checked(name: string) {
  return name in fields.value;
}

function tick(name: string, event: Event) {
  if ((event.target as HTMLInputElement).checked) fields.value[name] = "on";
  else delete fields.value[name];
}

function addSet() {
  sets.value.push({ id: setsAdded++, set: "", pieces: "4" });
}

function setIcon(id: string) {
  return props.page.options.sets.find((option) => String(option.id) === id)?.icon_url ?? null;
}

// Solving: the form posted, the run it keeps shown (the page's URL names it); timed while it
// runs, which can take minutes.
const solving = ref(false);
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

const finder = ref<InstanceType<typeof ChampionFinder>>();
</script>

<template>
  <Head :title="page.champion.name" />
  <div class="champion-page">
    <section class="target-section" aria-label="Target">
      <TargetPicker
        :picker="picker"
        :detached="detached"
        @picked="(enemy, key) => picked(enemy.defence, key)"
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
            <div class="damage-pick cluster" style="--space: var(--space-s) var(--space-m)">
              <span class="caps">Damage</span>
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
                  type="number"
                  min="1"
                  max="9"
                  placeholder="—"
                  aria-label="Damage priority"
                />
              </label>
            </div>
            <small class="note">
              Damage ranks the skill's critical hit against that much enemy DEF (the target's, once
              one is picked above): pair it with C.RATE at least 100.
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
            <span v-if="solving" class="note solving" aria-busy="true">
              Solving… {{ elapsed.toFixed(1) }}s
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
