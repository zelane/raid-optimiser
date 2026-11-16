<script setup lang="ts">
// The team finder: what the team is for (anything, or a stage from the target picker: a
// Faction Wars challenge, the Chimera's column of trials, who the stage admits), the team's
// slots, what every team must bring besides and how, then the teams found and, for the one
// shown, its needs (the Chimera's on its trial board). The page's state is its query, kept in
// this browser.
import { Head } from "@inertiajs/vue3";
import { computed } from "vue";
import BringPanels from "../components/BringPanels.vue";
import NeedsPanel from "../components/NeedsPanel.vue";
import PageHead from "../components/PageHead.vue";
import RunBar from "../components/RunBar.vue";
import ScorePill from "../components/ScorePill.vue";
import Tally from "../components/Tally.vue";
import TargetPicker from "../components/TargetPicker.vue";
import TeamOptions from "../components/TeamOptions.vue";
import TeamSlots from "../components/TeamSlots.vue";
import TrialBoard from "../components/TrialBoard.vue";
import TrialGlance from "../components/TrialGlance.vue";
import { useKeptQuery } from "../composables/keptQuery";
import { slotEdits, teamQuery, visitWith } from "../composables/teamQuery";
import type { TeamsPage } from "../types/generated/webui.service.teams";

const { page } = defineProps<{ page: TeamsPage }>();
useKeptQuery("teams");
const edits = computed(() => slotEdits(page.links, page.ran));
const against = computed(() => page.against);
const chimera = computed(() => page.against?.chimera ?? null);
const column = computed(() =>
  chimera.value?.columns.find((each) => each.part === chimera.value?.column),
);
const trials = computed(() => page.unit === "trials");
const scoreTitle = computed(
  () => `Team score: how far it can count on what ${trials.value ? "the trials need" : "is asked"}`,
);

function change(name: string, value: string) {
  const query = teamQuery(page.links, page.ran);
  query.set(name, value);
  if (name === "base" && !value) for (const field of ["target", "column"]) query.delete(field);
  visitWith(query);
}
</script>

<template>
  <Head title="Team finder" />
  <div class="stack" style="--space: var(--space-2xl)">
    <PageHead title="Team finder">
      <template #lede>
        Teams that bring what's asked: what a stage asks (a Faction Wars challenge, a column of
        Chimera trials in one fight), and whatever you add (buffs, debuffs, effects, so many
        different ones). Judged on what their skills bring and how far it can be counted on; how
        much of it (10+ Stuns) isn't, nor damage, nor turn order, nor ACC against RES.
      </template>
      <template #aside>
        <Tally
          :count="page.met"
          :total="page.needs"
          :label="page.unit"
          :tone="page.needs && page.met === page.needs ? 'up' : 'down'"
          :title="`${trials ? 'Trials' : 'Needs'} the team shown ${trials ? 'clears' : 'meets'}`"
        >
          <ScorePill :score="page.score" :title="scoreTitle" />
        </Tally>
      </template>
    </PageHead>

    <section class="panel stack" style="--space: var(--space-m)">
      <header class="panel-head">
        <h2>Against <small class="muted">what the content asks</small></h2>
      </header>
      <fieldset class="segmented" role="radiogroup" aria-label="Against">
        <label>
          <input type="radio" :checked="!against" @change="change('base', '')" />
          Anything
        </label>
        <label>
          <input type="radio" :checked="Boolean(against)" @change="change('base', 'stage')" />
          A stage
        </label>
      </fieldset>

      <template v-if="against">
        <TargetPicker :picker="against.picker" @picked="(_, target) => change('target', target)" />

        <p
          v-if="against.challenge"
          class="cluster"
          style="--space: var(--space-xs) var(--space-m); --align: baseline"
        >
          <span class="caps">Challenge</span>
          <template v-if="against.challenge.text">
            <strong>{{ against.challenge.text }}</strong>
            <template v-if="!against.challenge.checked">
              <span class="badge">not checked</span>
              <small class="note">it's about the fight, not what the team brings</small>
            </template>
          </template>
          <span v-else class="muted">none</span>
        </p>

        <template v-if="chimera">
          <div class="cluster" style="--space: var(--space-xs) var(--space-m)">
            <span class="caps">Trials: the column</span>
            <fieldset class="segmented" role="radiogroup" aria-label="Trial column">
              <label
                v-for="each in chimera.columns"
                :key="each.part"
                :title="`Its Easy Ram trial: ${each.hint}`"
              >
                <input
                  type="radio"
                  :checked="each.part === chimera.column"
                  @change="change('column', each.part)"
                />
                {{ each.part }}
                <span v-if="each.mythical" class="badge">mythical this raid</span>
              </label>
            </fieldset>
            <small v-if="column" class="note">Easy Ram: {{ column.hint }}</small>
          </div>
          <p class="note">
            One team clearing the column's nine trials, Easy → Hard in each form, in one fight: the
            rewards only count for trials cleared in the same fight. Targets are shown, not checked.
          </p>
          <article v-if="chimera.problems.length" class="alert">
            <strong>The trial rules no longer match the game's data</strong> (a game update?): these
            trials may be judged wrongly.
            <ul>
              <li v-for="problem in chimera.problems" :key="problem">{{ problem }}</li>
            </ul>
          </article>
        </template>

        <p v-if="against.admits" class="cluster note" style="--space: var(--space-xs)">
          <img
            v-if="against.faction_url"
            class="faction small"
            :src="against.faction_url"
            alt=""
            aria-hidden="true"
          />
          Only {{ against.admits }} are searched.
        </p>
        <p v-else-if="against.rotating" class="note info">
          The stage restricts the team, but which restriction is active rotates with the account
          (Cursed City): it isn't applied.
        </p>
        <p v-if="against.refused.length" class="note bad">
          The stage doesn't admit {{ against.refused.join(", ") }}.
        </p>
      </template>
    </section>

    <TeamSlots
      :slots="page.team.slots"
      :empty-url="page.links.empty"
      keep="teams"
      :only="against?.only?.fields"
      :only-label="against?.only?.label"
      @place="edits.place"
      @wear="edits.wear"
    />
    <BringPanels
      :team="page.team"
      :links="page.links"
      :ran="page.ran"
      subtitle="every team must, besides what the stage asks"
    />
    <RunBar
      :links="page.links"
      :ran="page.ran"
      :grades="page.grades"
      :min-grade="page.min_grade"
      :candidates="page.candidates"
      :searched="page.ran && page.asked"
    />

    <template v-if="page.ran">
      <section v-if="!page.asked" class="stack" style="--space: var(--space-l)">
        <h2 class="section-title">Teams</h2>
        <p class="lede">
          Nothing is asked yet: pick a stage that asks something, or add something every team must
          bring.
        </p>
      </section>
      <TeamOptions
        v-else
        :options="page.options"
        :shown="page.shown"
        :total="page.needs"
        :met="(option) => option.met"
        :score-title="scoreTitle"
        :show-label="trials ? 'Show trials' : 'Show needs'"
        :found="page.found"
        :complete="page.complete"
        :listed="page.listed"
        :more="page.links.more"
        :min-grade="page.min_grade"
      >
        <template #lede>
          <template v-if="page.partial">
            {{
              trials
                ? "No team clears all nine trials: these clear the most."
                : "No team brings it all: these bring the most."
            }}
          </template>
          <template v-else-if="page.found">
            {{ page.found.toLocaleString() }}{{ page.complete ? "" : "+" }} teams
            {{ trials ? "clear all nine trials" : "bring it all"
            }}<template v-if="!page.complete">
              (the search stops there, or after a second: put a champion in a slot to narrow it; the
              order is among those found)</template
            >. Each lists only the champions it needs; any champion can fill its other slots. Best
            scored first: how far a team can count on what's asked (each effect's uptime ×
            reliability × reach, from your champions' skills and books).
          </template>
        </template>
        <template #default="{ option }">
          <TrialGlance v-if="option.glance.length" :glance="option.glance" />
        </template>
      </TeamOptions>
    </template>
  </div>

  <section v-if="page.rows.length" class="page-section">
    <h2 class="section-title">
      Trials<template v-if="page.shown">: option {{ page.shown }}</template>
      <span class="badge" :class="page.met === page.needs ? 'good' : 'bad'">
        {{ page.met }} / {{ page.needs }} cleared
      </span>
    </h2>
    <div class="stack" style="--space: var(--space-2xl)">
      <TrialBoard :rows="page.rows" />
      <NeedsPanel v-if="page.extras.length" title="Also bringing" :needs="page.extras" />
    </div>
  </section>
  <section v-else-if="page.needs" class="page-section">
    <h2 class="section-title">
      Needs<template v-if="page.shown">: option {{ page.shown }}</template>
      <span class="badge" :class="page.met === page.needs ? 'good' : 'bad'">
        {{ page.met }} / {{ page.needs }} met
      </span>
    </h2>
    <div
      class="grid"
      style="--min: 26rem; --space: var(--space-l); --align: start; --repeat: auto-fill"
    >
      <NeedsPanel
        v-if="page.base_needs.length"
        title="The challenge"
        :needs="page.base_needs"
        glyph="★"
      />
      <NeedsPanel v-if="page.extras.length" title="Also bringing" :needs="page.extras" />
    </div>
  </section>
</template>
