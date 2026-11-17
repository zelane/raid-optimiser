<script setup lang="ts">
// Team gear: up to five champions geared at once against one target, each a row (sets, SPD,
// ACC, RES and C.RATE minimums, what it ranks), slot order its priority. The page's state is
// its query, kept in this browser (less `run`, which solves); the rows are edited here and
// sent with the next change (a slot, a rank, a target) or with Find gear.
import { Head, router } from "@inertiajs/vue3";
import { computed, ref, watch } from "vue";
import BuildDetail from "../components/BuildDetail.vue";
import Ledger from "../components/Ledger.vue";
import PageHead from "../components/PageHead.vue";
import TargetPicker from "../components/TargetPicker.vue";
import TeamSlots from "../components/TeamSlots.vue";
import { useKeptQuery } from "../composables/keptQuery";
import { stopSolve } from "../composables/send";
import { trimmed } from "../composables/teamQuery";
import type { OnlyView } from "../types/generated/webui.service.finder";
import type { TargetPicker as Picker } from "../types/generated/webui.service.targets";
import type { RowFields } from "../types/generated/webui.forms.team_gear";
import type { GearPage, RowView } from "../types/generated/webui.service.team_gear";

const props = defineProps<{ page: GearPage; picker: Picker; only: OnlyView | null }>();
useKeptQuery("team-gear", ["run"]);

interface RowEdit {
  fields: RowFields;
  sets: { set: string; pieces: string }[];
  minimums: Record<string, string>;
  rank: string;
  skill: string;
}

function rowEdit(row: RowView): RowEdit {
  return {
    fields: row.fields,
    sets: row.sets.map((pick) => ({
      set: pick.set_id === null ? "" : String(pick.set_id),
      pieces: pick.pieces === null ? "" : String(pick.pieces),
    })),
    minimums: Object.fromEntries(row.minimums.map((minimum) => [minimum.field, minimum.value])),
    rank: row.rank,
    skill: row.skill === null ? "" : String(row.skill),
  };
}

const rows = ref<RowEdit[]>([]);
const excluded = ref<Record<string, boolean>>({}); // by the rule's switch's field
const unwornOnly = ref(false);

function reset() {
  rows.value = props.page.rows.map(rowEdit);
  excluded.value = Object.fromEntries(props.page.rules.map((rule) => [rule.field, rule.on]));
  unwornOnly.value = props.page.unworn_only;
}

reset();
watch(() => props.page, reset);

// The page's query as its form sent it, by the names the page is given (`forms.team_gear`): the
// target and the RES its ACC defaults came from, the slots, each row's fields, the gear filters.
function query(slots: string[], target: string, run: boolean): URLSearchParams {
  const names = props.page.fields;
  const fields = new URLSearchParams([
    [names.target, target],
    [names.res, String(props.page.resistance)],
  ]);
  for (const choice of trimmed(slots)) fields.append(names.slot, choice);

  for (const row of rows.value) {
    for (const pick of row.sets) {
      fields.append(row.fields.sets, pick.set);
      fields.append(row.fields.pieces, pick.pieces);
    }
    for (const [name, value] of Object.entries(row.minimums)) fields.append(name, value);
    fields.append(row.fields.rank, row.rank);
    if (row.rank === props.page.damage_rank) fields.append(row.fields.skill, row.skill);
  }

  if (rows.value.length) {
    fields.append(names.filters, "1");
    for (const [field, on] of Object.entries(excluded.value)) if (on) fields.append(field, "on");
    if (unwornOnly.value) fields.append(names.unworn_only, "on");
  }

  if (run) fields.append(names.run, "true");
  return fields;
}

const solving = ref(false);
const stopping = ref(false);

function stop() {
  stopping.value = true;
  stopSolve();
}

function send(changes: { slots?: string[]; target?: string; run?: boolean } = {}) {
  const slots = changes.slots ?? props.page.slots.map((slot) => slot.choice);
  const fields = query(slots, changes.target ?? props.picker.target, changes.run ?? false);
  router.get(
    `/team-gear?${fields}`,
    {},
    {
      preserveState: true,
      preserveScroll: true,
      onStart: () => {
        solving.value = Boolean(changes.run);
        stopping.value = false;
      },
      onFinish: () => (solving.value = false),
    },
  );
}

function place(slot: number, choice: string) {
  const slots = props.page.slots.map((each) => each.choice);
  while (slots.length <= slot) slots.push("");
  slots[slot] = choice;
  send({ slots });
}

const result = computed(() => props.page.result);
const shortfall = computed(() => props.page.shortfall);

function minimumTitle(placeholder: string) {
  return placeholder
    ? `${placeholder}: resists the target's debuffs within 0.1 points of the 97 % cap`
    : undefined;
}
</script>

<template>
  <Head title="Team gear" />
  <div class="stack" style="--space: var(--space-2xl)">
    <PageHead title="Team gear">
      <template #lede>
        Gear for a whole team at once, against one target: each champion's sets and minimums met, no
        piece worn twice. Slot order is priority: each champion gets the best of what the ones
        before left, as long as the rest can still meet theirs.
      </template>
    </PageHead>

    <section class="target-section" aria-label="Target">
      <!-- A target picked sends the page again: ACC still at the old target's RES follows. -->
      <TargetPicker :picker="picker" @picked="(_, target) => send({ target })" />
    </section>

    <p v-if="page.admits" class="note info">
      The target's stage admits only {{ page.admits }}: the champion finder lists only them.
    </p>
    <p v-else-if="page.rotating" class="note info">
      The target's stage restricts the team, but which restriction is active rotates with the
      account (Cursed City): it isn't applied.
    </p>

    <TeamSlots
      :slots="page.slots"
      empty-url="/team-gear"
      keep="team-gear"
      :only="only?.fields"
      :only-label="only?.label"
      @place="place"
    />

    <template v-if="rows.length">
      <section class="panel stack" style="--space: var(--space-m)">
        <header class="panel-head">
          <h2>
            What each needs <small class="muted">{{ page.target_note }}</small>
          </h2>
        </header>
        <div class="table-well">
          <table class="team-gear-rows">
            <thead>
              <tr>
                <th scope="col">Champion</th>
                <th scope="col">Sets, at least</th>
                <th scope="col">SPD ≥</th>
                <th scope="col">ACC ≥</th>
                <th scope="col">RES ≥</th>
                <th scope="col">C.RATE ≥ %</th>
                <th scope="col">Rank</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, n) in page.rows" :key="row.number">
                <th scope="row">
                  {{ row.champion.name }} <small>slot {{ row.number }}</small>
                  <small v-if="row.refused" class="bad">not admitted</small>
                </th>
                <td>
                  <div
                    v-if="rows[n]"
                    class="cluster"
                    style="--space: var(--space-2xs) var(--space-s)"
                  >
                    <span v-for="(pick, s) in rows[n].sets" :key="s" class="joined">
                      <select
                        v-model="pick.set"
                        class="small"
                        :aria-label="`Set ${s + 1} for ${row.champion.name}`"
                      >
                        <option value="">No set</option>
                        <option v-for="[id, name] in page.sets" :key="id" :value="String(id)">
                          {{ name }}
                        </option>
                      </select>
                      <input
                        v-model="pick.pieces"
                        type="number"
                        class="small bare"
                        min="1"
                        max="9"
                        placeholder="pcs"
                        aria-label="Pieces"
                      />
                    </span>
                  </div>
                </td>
                <td v-for="minimum in row.minimums" :key="minimum.field">
                  <input
                    v-if="rows[n]"
                    v-model="rows[n].minimums[minimum.field]"
                    type="number"
                    class="small bare"
                    min="0"
                    step="any"
                    :placeholder="minimum.placeholder || undefined"
                    :title="minimumTitle(minimum.placeholder)"
                    :aria-label="`${minimum.label} at least for ${row.champion.name}`"
                  />
                  <small v-if="minimum.note">{{ minimum.note }}</small>
                </td>
                <td>
                  <div
                    v-if="rows[n]"
                    class="cluster"
                    style="--space: var(--space-2xs) var(--space-s)"
                  >
                    <select
                      v-model="rows[n].rank"
                      class="small"
                      :aria-label="`What ${row.champion.name} ranks`"
                      @change="send()"
                    >
                      <template v-for="[value, label] in page.ranks" :key="value">
                        <option
                          v-if="value !== page.damage_rank || row.skills.length"
                          :value="value"
                        >
                          {{ label }}
                        </option>
                      </template>
                    </select>
                    <select
                      v-if="row.rank === page.damage_rank"
                      v-model="rows[n].skill"
                      class="small"
                      :aria-label="`Skill whose damage ${row.champion.name} ranks`"
                    >
                      <option v-for="[id, name] in row.skills" :key="id" :value="String(id)">
                        {{ name }}
                      </option>
                    </select>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <small class="note">
          Empty: no minimum. A debuff is resisted at least 3 % of the time however high ACC is: ACC
          starts where that's within 0.1 points (the target's RES + 64) for champions who place
          debuffs. RES has no default: the greyed number resists the target's debuffs within 0.1
          points of the 97 % most (its ACC + 247). C.RATE starts at 100 % for one ranking damage
          (their skill's crit against the target's DEF).
        </small>
      </section>

      <section class="panel stack" style="--space: var(--space-xs)">
        <p class="caps">Leave out gear from</p>
        <div
          class="switch-rows well"
          title="Gear the solve may not take; the team's own is always allowed"
        >
          <label v-for="rule in page.rules" :key="rule.key">
            <input v-model="excluded[rule.field]" type="checkbox" role="switch" />
            <span class="row-name">{{ rule.label }}</span>
          </label>
          <label>
            <input v-model="unwornOnly" type="checkbox" role="switch" />
            <span class="row-name">Any champion outside the team (unequipped gear only)</span>
          </label>
        </div>
      </section>

      <div class="panel cluster" style="--space: var(--space-m) var(--space-2xl)">
        <span class="note">
          {{
            stopping
              ? "Stopping…"
              : solving
                ? "Solving…"
                : page.stopped
                  ? "Stopped before the team was geared."
                  : "Solving takes a few seconds per champion."
          }}
        </span>
        <button
          v-if="solving"
          type="button"
          class="quiet cta push"
          :disabled="stopping"
          @click="stop"
        >
          Stop
        </button>
        <button v-else type="button" class="cta push" @click="send({ run: true })">
          Find gear
        </button>
      </div>
    </template>

    <section v-if="result" class="stack" style="--space: var(--space-xl)">
      <p class="cluster note" style="--space: var(--space-xs) var(--space-l)">
        <span class="badge info">
          Geared {{ result.members.length }} in {{ result.seconds.toFixed(1) }}s
        </span>
        <span>Equip each in turn: no piece is in two builds.</span>
      </p>
      <section
        v-for="member in result.members"
        :key="member.champion.id"
        class="panel stack team-gear-member"
        style="--space: var(--space-m)"
      >
        <div class="table-well">
          <Ledger
            :current="member.current"
            :rows="[{ key: 'build', picked: true, stats: member.build.stats }]"
          >
            <template #head>Build</template>
          </Ledger>
        </div>
        <small class="note">
          The target resists its debuffs {{ member.resisted }} of the time; it resists the target's
          {{ member.resists }}.<template v-if="member.damage">
            The DMG column is {{ member.damage }}.</template
          >
        </small>
        <BuildDetail
          :build="member.build"
          :champion="member.champion"
          :title="member.champion.name"
        />
      </section>
    </section>
    <section v-else-if="shortfall" class="panel stack alert" style="--space: var(--space-s)">
      <p v-if="shortfall.clash">
        Each champion can meet their minimums alone, but not all of them together: the same pieces
        are wanted twice. Ease a minimum, or a set.
      </p>
      <template v-else>
        <p>Not every champion can meet their minimums, even alone:</p>
        <div v-for="[champion, lines] in shortfall.members" :key="champion.id">
          <strong>{{ champion.name }}</strong>
          <ul>
            <li v-for="line in lines" :key="line">{{ line }}</li>
          </ul>
        </div>
      </template>
    </section>
  </div>
</template>
