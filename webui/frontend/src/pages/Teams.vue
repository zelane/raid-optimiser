<script setup lang="ts">
// The team finder: base needs (none, or a Faction Wars stage's challenge), the team's slots,
// what every team must bring besides and how, then the teams found and the needs of the one
// shown. The page's state is its query, kept in this browser.
import { Head } from "@inertiajs/vue3";
import { computed } from "vue";
import BringPanels from "../components/BringPanels.vue";
import NeedsPanel from "../components/NeedsPanel.vue";
import PageHead from "../components/PageHead.vue";
import RunBar from "../components/RunBar.vue";
import ScorePill from "../components/ScorePill.vue";
import Tally from "../components/Tally.vue";
import TeamOptions from "../components/TeamOptions.vue";
import TeamSlots from "../components/TeamSlots.vue";
import { valueOf } from "../composables/format";
import { useKeptQuery } from "../composables/keptQuery";
import { slotEdits, teamQuery, visitWith } from "../composables/teamQuery";
import type { TeamsPage } from "../types/generated/webui.service.teams";

const { page } = defineProps<{ page: TeamsPage }>();
useKeptQuery("teams");
const edits = computed(() => slotEdits(page.links, page.ran));

function change(name: string, value: string) {
  const query = teamQuery(page.links, page.ran);
  query.set(name, value);
  if (name === "base" && value === "fw") query.set("stage", "1");
  visitWith(query);
}

function stages(count: number) {
  return Array.from({ length: count }, (_, n) => n + 1);
}
</script>

<template>
  <Head title="Team finder" />
  <div class="stack" style="--space: var(--space-2xl)">
    <PageHead title="Team finder">
      <template #lede>
        Teams that bring what's asked: a Faction Wars stage's challenge, and whatever you add
        (buffs, debuffs, effects, so many different ones). Judged on what their skills bring and how
        far it can be counted on; how much of it (10+ Stuns) isn't, nor damage, nor turn order.
      </template>
      <template #aside>
        <Tally
          :count="page.met"
          :total="page.needs"
          label="needs"
          :tone="page.needs && page.met === page.needs ? 'up' : 'down'"
          title="Needs the team shown meets"
        >
          <ScorePill :score="page.score" title="Team score: how far it can count on what's asked" />
        </Tally>
      </template>
    </PageHead>

    <section class="panel stack" style="--space: var(--space-m)">
      <header class="panel-head">
        <h2>Base needs <small class="muted">what the content asks</small></h2>
        <a href="/chimera" class="caps">Chimera trials →</a>
      </header>
      <fieldset class="segmented" role="radiogroup" aria-label="Base needs">
        <label>
          <input type="radio" :checked="!page.base.kind" @change="change('base', '')" />
          None
        </label>
        <label>
          <input type="radio" :checked="page.base.kind === 'fw'" @change="change('base', 'fw')" />
          Faction Wars
        </label>
      </fieldset>
      <template v-if="page.base.kind === 'fw'">
        <div class="cluster" style="--space: var(--space-m) var(--space-xl)">
          <label class="inline">
            <span class="caps">Crypt</span>
            <select
              :value="page.base.crypts.find((crypt) => crypt.selected)?.region"
              @change="change('crypt', valueOf($event))"
            >
              <option v-for="crypt in page.base.crypts" :key="crypt.region" :value="crypt.region">
                {{ crypt.name }}
              </option>
            </select>
          </label>
          <label class="inline">
            <span class="caps">{{ page.base.difficulty }} stage</span>
            <select :value="page.base.number" @change="change('stage', valueOf($event))">
              <option v-for="n in stages(page.base.stages)" :key="n" :value="n">{{ n }}</option>
            </select>
          </label>
          <img
            v-if="page.base.faction_url"
            class="faction small"
            :src="page.base.faction_url"
            alt=""
            aria-hidden="true"
          />
          <span class="note">Only {{ page.base.faction }} champions are searched.</span>
        </div>
        <p class="cluster" style="--space: var(--space-xs) var(--space-m); --align: baseline">
          <span class="caps">Challenge</span>
          <template v-if="page.base.challenge">
            <strong>{{ page.base.challenge }}</strong>
            <template v-if="!page.base.checked">
              <span class="badge">not checked</span>
              <small class="note">it's about the fight, not what the team brings</small>
            </template>
          </template>
          <span v-else class="muted">none</span>
        </p>
        <p v-if="page.base.refused.length" class="note bad">
          The crypt doesn't admit {{ page.base.refused.join(", ") }}.
        </p>
      </template>
    </section>

    <TeamSlots
      :slots="page.team.slots"
      :empty-url="page.links.empty"
      keep="teams"
      @place="edits.place"
      @wear="edits.wear"
    />
    <BringPanels
      :team="page.team"
      :links="page.links"
      :ran="page.ran"
      subtitle="every team must, besides the base"
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
          Nothing is asked yet: pick a challenge to read, or add something every team must bring.
        </p>
      </section>
      <TeamOptions
        v-else
        :options="page.options"
        :shown="page.shown"
        :total="page.needs"
        :met="(option) => option.met"
        score-title="Team score: how far it can count on what's asked"
        show-label="Show needs"
        :found="page.found"
        :complete="page.complete"
        :listed="page.listed"
        :more="page.links.more"
        :min-grade="page.min_grade"
      >
        <template #lede>
          <template v-if="page.partial">No team brings it all: these bring the most.</template>
          <template v-else-if="page.found">
            {{ page.found.toLocaleString() }}{{ page.complete ? "" : "+" }} teams bring it
            all<template v-if="!page.complete">
              (the search stops there, or after a second: put a champion in a slot to narrow
              it)</template
            >. Each lists only the champions it needs; any champion can fill its other slots. Best
            scored first.
          </template>
        </template>
      </TeamOptions>
    </template>
  </div>

  <section v-if="page.needs" class="page-section">
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
