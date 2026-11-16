<script setup lang="ts">
// The Chimera's trials: one team clearing a whole column (Easy → Hard, all three forms) in one
// Ultra Nightmare fight. The rotation, the team's slots, what it must bring besides and how,
// the teams found, then the trial board for the one shown. The state is the query, kept in
// this browser.
import { Head } from "@inertiajs/vue3";
import { computed } from "vue";
import BringPanels from "../components/BringPanels.vue";
import NeedItem from "../components/NeedItem.vue";
import NeedsPanel from "../components/NeedsPanel.vue";
import PageHead from "../components/PageHead.vue";
import RunBar from "../components/RunBar.vue";
import ScorePill from "../components/ScorePill.vue";
import Tally from "../components/Tally.vue";
import TeamOptions from "../components/TeamOptions.vue";
import TeamSlots from "../components/TeamSlots.vue";
import { useKeptQuery } from "../composables/keptQuery";
import { slotEdits, teamQuery, visitWith } from "../composables/teamQuery";
import type { ChimeraPage } from "../types/generated/webui.service.chimera";

const { page } = defineProps<{ page: ChimeraPage }>();
useKeptQuery("chimera");

const LEVELS = ["Easy", "Normal", "Hard"];
const LEVEL_TONES: Record<string, string> = { Easy: "info", Normal: "mid" };
const column = computed(() => page.columns.find((each) => each.part === page.column));
const edits = computed(() => slotEdits(page.links, page.ran));

function pickColumn(part: string) {
  const query = teamQuery(page.links, page.ran);
  query.set("column", part);
  visitWith(query);
}
</script>

<template>
  <Head title="Chimera trials" />
  <div class="stack" style="--space: var(--space-2xl)">
    <PageHead title="Chimera trials">
      <template #lede>
        Teams that clear a whole column of Ultra Nightmare trials in one fight, judged on the buffs,
        debuffs and effects their skills bring against each trial's rules and each form's
        immunities. Damage, skill chances, turn order and gear (bar the Toxic set) aren't checked.
      </template>
      <template #aside>
        <div class="stack" style="--space: var(--space-xs); --align: flex-start">
          <span class="caps">Mythical materials in</span>
          <fieldset class="segmented" role="radiogroup" aria-label="Rotation">
            <label
              v-for="each in page.columns"
              :key="each.part"
              :title="`Its Easy Ram trial: ${each.hint}`"
            >
              <input
                type="radio"
                :checked="each.part === page.column"
                @change="pickColumn(each.part)"
              />
              {{ each.part }}
              <span v-if="each.mythical" class="badge">this raid</span>
            </label>
          </fieldset>
          <small v-if="column" class="note">Easy Ram: {{ column.hint }}</small>
        </div>
        <Tally
          :count="page.cleared"
          :total="9"
          label="trials"
          :tone="page.cleared === 9 ? 'up' : 'down'"
          title="Trials the team shown clears"
        >
          <ScorePill
            :score="page.score"
            title="Team score: how far it can count on what the trials need"
          />
        </Tally>
      </template>
    </PageHead>

    <article v-if="page.problems.length" class="alert">
      <strong>The trial rules no longer match the game's data</strong> (a game update?): these
      trials may be judged wrongly.
      <ul>
        <li v-for="problem in page.problems" :key="problem">{{ problem }}</li>
      </ul>
    </article>

    <TeamSlots
      :slots="page.team.slots"
      :empty-url="page.links.empty"
      keep="chimera"
      @place="edits.place"
      @wear="edits.wear"
    />
    <BringPanels
      :team="page.team"
      :links="page.links"
      :ran="page.ran"
      subtitle="every team must, besides the trials"
    />
    <RunBar
      :links="page.links"
      :ran="page.ran"
      :grades="page.grades"
      :min-grade="page.min_grade"
      :candidates="page.candidates"
      :searched="page.ran"
    />

    <TeamOptions
      v-if="page.ran"
      :options="page.options"
      :shown="page.shown"
      :total="9"
      :met="(option) => option.cleared"
      score-title="Team score: how far it can count on what the trials need"
      show-label="Show trials"
      :found="page.found"
      :complete="page.complete"
      :listed="page.listed"
      :more="page.links.more"
      :min-grade="page.min_grade"
    >
      <template #lede>
        <template v-if="page.partial"
          >No team clears all nine trials: these clear the most.</template
        >
        <template v-else-if="page.found">
          {{ page.found.toLocaleString() }}{{ page.complete ? "" : "+" }} teams clear all nine
          trials<template v-if="!page.complete">
            (the search stops there, or after a second: put a champion in a slot to narrow it; the
            order is among those found)</template
          >. Each lists only the champions it needs; any champion can fill its other slots. Best
          scored first: how far a team can count on what the trials need (each effect's uptime ×
          reliability × reach, from your champions' skills and books).
        </template>
      </template>
      <template #default="{ option }">
        <table class="glance" aria-label="Trials cleared">
          <tbody>
            <tr v-for="[form, hits] in option.glance" :key="form">
              <th scope="row">{{ form }}</th>
              <td v-for="(hit, n) in hits" :key="n" :class="hit ? 'up' : 'down'" :title="LEVELS[n]">
                {{ hit ? "✓" : "✗" }}
              </td>
            </tr>
          </tbody>
        </table>
      </template>
    </TeamOptions>
  </div>

  <section class="page-section">
    <h2 class="section-title">
      Trials<template v-if="page.shown">: option {{ page.shown }}</template>
      <span class="badge" :class="page.cleared === 9 ? 'good' : 'bad'">
        {{ page.cleared }} / 9 cleared
      </span>
    </h2>
    <!-- A row per form (its accent colour), Easy → Normal → Hard across it. -->
    <div class="stack" style="--space: var(--space-2xl)">
      <NeedsPanel
        v-for="row in page.rows"
        :key="row.form"
        :title="`${row.form} form`"
        :needs="row.trials"
        :glyph="row.form[0]"
        :icon-url="row.icon_url"
        :accent="`form-${row.form.toLowerCase()}`"
      >
        <div class="trial-row">
          <article
            v-for="trial in row.trials"
            :key="trial.level"
            class="trial stack"
            :class="{ met: trial.met }"
            style="--space: var(--space-s)"
          >
            <div class="cluster" style="--justify: space-between">
              <span class="badge" :class="LEVEL_TONES[trial.level] ?? 'bad'">{{
                trial.level
              }}</span>
              <span class="trial-state" :class="trial.met ? 'up' : trial.waits_on ? 'mid' : 'down'">
                <template v-if="trial.met">Cleared</template>
                <template v-else-if="trial.waits_on">Needs {{ trial.waits_on }} first</template>
                <template v-else>Not cleared</template>
              </span>
            </div>
            <p>{{ trial.description }}</p>
            <p class="trial-target">
              <span>Target</span> <strong>{{ trial.target }}</strong>
              <template v-if="trial.damage"> damage</template>
            </p>
            <ul v-if="trial.needs.length" class="stack" style="--space: var(--space-xs)">
              <NeedItem v-for="(need, n) in trial.needs" :key="n" :need="need" />
            </ul>
            <p v-else class="note">Nothing to bring: it's down to the fight.</p>
          </article>
        </div>
      </NeedsPanel>
      <NeedsPanel v-if="page.extras.length" title="Also bringing" :needs="page.extras" />
    </div>
  </section>
</template>

<style scoped>
table.glance {
  width: auto;
  margin: 0;
  font-size: var(--text-xs);

  th,
  td {
    padding: var(--space-3xs) var(--space-s);
    border: 0;
    text-align: center;
  }

  th {
    text-align: left;
  }
}

/* A form's trials three across, a chevron between them; one under the next on a narrow page. */
.trial-row {
  --trial-gap: var(--space-2xl);

  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-m);
  align-items: start;
}

@container page (min-width: 46rem) {
  .trial-row {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--trial-gap);

    .trial + .trial::before {
      content: "›";
      position: absolute;
      top: 50%;
      left: calc(var(--trial-gap) / -2);
      transform: translate(-50%, -50%);
      font-size: var(--text-xl);
      color: color-mix(in srgb, var(--accent) 70%, var(--on-surface-variant));
    }
  }
}

.trial {
  position: relative;
  padding: var(--space-m);
  border-radius: var(--radius);
  font-size: var(--text-xs);
  line-height: 1.35;
  background: var(--surface-container-lowest);

  &.met {
    border-color: color-mix(in srgb, var(--stat-up) 55%, transparent);
    box-shadow: inset 3px 0 0 var(--stat-up);
  }
}

.trial-state {
  font-size: var(--text-2xs);
  font-weight: 700;
}

.trial-target {
  align-self: flex-start;
  padding: var(--space-3xs) var(--space-s);
  border-radius: var(--radius);
  font-size: var(--text-2xs);
  color: var(--on-surface-variant);
  background: color-mix(in srgb, var(--accent) 14%, transparent);

  strong {
    color: var(--accent);
  }
}
</style>
