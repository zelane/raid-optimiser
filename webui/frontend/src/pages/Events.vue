<script setup lang="ts">
// The events page: the events and tournaments on in the game (running, coming up, ended with
// prizes to claim), refreshed every 15 s, a panel each: its kind, time left and title, then (open
// for those running with a milestone left, folded for the rest) the account's points and place
// over its milestones (and for one scoring summons, level-ups, dungeon runs or upgrades, what
// each milestone takes: `ShardPlan`, `BrewPlan`, `FightPlan`, `UpgradePlan`), and what earns
// points folded away.
import { Head, usePoll } from "@inertiajs/vue3";
import { computed, ref } from "vue";
import PageHead from "../components/PageHead.vue";
import BrewPlan from "../components/BrewPlan.vue";
import FightPlan from "../components/FightPlan.vue";
import ShardPlan from "../components/ShardPlan.vue";
import Stat from "../components/Stat.vue";
import UpgradePlan from "../components/UpgradePlan.vue";
import Tally from "../components/Tally.vue";
import type { EventCard, EventsPage, MilestoneRow } from "../types/generated/webui.service.events";
import { formatCount } from "../composables/format";

const POLL_MS = 15_000;

const { page } = defineProps<{ page: EventsPage | null }>();
// Under `just watch` the reader rewrites the events within seconds of a change: keep up with it.
usePoll(POLL_MS, { only: ["page", "layout"] });
// Read through `computed`: a sync reloads the page's props without remounting it.
const sections = computed(() =>
  page
    ? [
        { key: "running", title: "Running", events: page.running, empty: "Nothing running." },
        { key: "upcoming", title: "Coming up", events: page.upcoming, empty: "Nothing announced." },
        { key: "ended", title: "Ended: prizes to claim", events: page.ended, empty: "" },
      ].filter((section) => section.events.length || section.empty)
    : [],
);

// The milestone each card's shard plan aims at, by event id: one clicked, else the next not
// reached (a pick reached since falls back to it).
const picked = ref<Record<number, number>>({});

function target(event: EventCard): MilestoneRow | undefined {
  const chosen = picked.value[event.id];
  const open = event.milestones.filter((milestone) => !milestone.reached);
  return open.find((milestone) => milestone.points === chosen) ?? open[0];
}

function pickable(event: EventCard, milestone: MilestoneRow) {
  return event.plans.length > 0 && !milestone.reached;
}

function pick(event: EventCard, milestone: MilestoneRow) {
  if (pickable(event, milestone)) picked.value[event.id] = milestone.points;
}

// Every milestone reached: nothing left to play for, so its card starts folded.
function complete(event: EventCard) {
  return event.milestones.length > 0 && event.reached === event.milestones.length;
}

function progress(event: EventCard) {
  const last = event.milestones[event.milestones.length - 1];
  return last && event.points !== null ? Math.min(100, (100 * event.points) / last.points) : 0;
}
</script>

<template>
  <Head title="Events" />
  <PageHead title="Events">
    <template #lede>
      The events and tournaments the game holds, with your points as read
      {{ page?.read_ago ?? "never" }} (`just watch` keeps them current). Hover a title for Plarium's
      own name for it.
      <template v-if="page?.levels">Milestones are your bracket's ({{ page.levels }}).</template>
    </template>
    <template v-if="page" #aside>
      <Tally
        :count="page.running.length"
        :total="page.running.length + page.upcoming.length"
        label="running"
        title="Running, of those running or announced"
      />
    </template>
  </PageHead>

  <p v-if="!page" class="alert">
    The last sync read no events: sync with the game running and logged in.
  </p>

  <div class="stack" style="--space: var(--space-xl)">
    <section
      v-for="section in sections"
      :key="section.key"
      class="stack"
      :aria-labelledby="`${section.key}-heading`"
    >
      <h2 :id="`${section.key}-heading`">{{ section.title }}</h2>
      <p v-if="!section.events.length" class="muted">{{ section.empty }}</p>

      <div class="event-grid">
        <article v-for="event in section.events" :key="event.id" class="panel event">
          <details :open="section.key === 'running' && !complete(event)">
            <summary class="stack" style="--space: var(--space-3xs)">
              <div class="cluster" style="--space: var(--space-xs)">
                <span class="badge" :class="{ info: event.tournament }">{{ event.kind }}</span>
                <span v-if="event.fusion" class="badge quiet">{{ event.fusion }} fusion</span>
                <strong class="when push">{{ event.when }}</strong>
              </div>
              <h3 :title="event.plarium_name">{{ event.title }}</h3>
            </summary>

            <div class="stack" style="--space: var(--space-s)">
              <div v-if="event.points !== null" class="cluster" style="--space: var(--space-l)">
                <Stat :value="formatCount(event.points)" :label="event.points_name" />
                <Stat
                  v-if="event.position !== null"
                  :value="`#${event.position}`"
                  :label="event.rating_size ? `place of ${event.rating_size}` : 'place'"
                />
                <Stat
                  v-if="event.to_next !== null"
                  :value="formatCount(event.to_next)"
                  label="to the next"
                />
              </div>
              <p v-else class="note">Not joined yet.</p>

              <span
                v-if="event.milestones.length && event.points !== null"
                class="meter"
                :class="{ good: event.to_next === null }"
              >
                <span :style="{ width: `${progress(event)}%` }"></span>
              </span>

              <div v-if="event.milestones.length" class="table-well">
                <table>
                  <thead>
                    <tr>
                      <th class="num">Points</th>
                      <th>
                        Prize
                        <small class="muted">
                          {{ event.reached }}/{{ event.milestones.length }} reached
                        </small>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="milestone in event.milestones"
                      :key="milestone.points"
                      :class="{
                        reached: milestone.reached,
                        pickable: pickable(event, milestone),
                        picked: pickable(event, milestone) && target(event) === milestone,
                      }"
                      :tabindex="pickable(event, milestone) ? 0 : undefined"
                      :title="pickable(event, milestone) ? 'Aim the plan below at it' : undefined"
                      @click="pick(event, milestone)"
                      @keydown.enter.space.prevent="pick(event, milestone)"
                    >
                      <td class="num">{{ formatCount(milestone.points) }}</td>
                      <td>
                        {{ milestone.prize }}
                        <span v-if="milestone.reached" class="good" title="Reached">✓</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p v-else-if="section.key === 'upcoming'" class="note">
                Milestones come when it starts.
              </p>

              <template v-if="target(event) && section.key === 'running'">
                <template v-for="plan in event.plans" :key="plan.kind">
                  <ShardPlan
                    v-if="plan.kind === 'shards'"
                    :plan="plan"
                    :target="target(event)!"
                    :points="event.points ?? 0"
                  />
                  <BrewPlan
                    v-else-if="plan.kind === 'brews'"
                    :plan="plan"
                    :target="target(event)!"
                    :points="event.points ?? 0"
                  />
                  <FightPlan
                    v-else-if="plan.kind === 'runs'"
                    :plan="plan"
                    :target="target(event)!"
                    :points="event.points ?? 0"
                    :per-day="event.max_points_per_day"
                  />
                  <UpgradePlan
                    v-else
                    :plan="plan"
                    :target="target(event)!"
                    :points="event.points ?? 0"
                  />
                </template>
              </template>

              <details v-if="event.points_tables.length">
                <summary>
                  Rules
                  <small v-if="event.max_points_per_day" class="muted">
                    (at most {{ formatCount(event.max_points_per_day) }} a day)
                  </small>
                </summary>
                <div class="stack" style="--space: var(--space-m)">
                  <p v-if="event.turn_scored" class="note">
                    Fights by turns: the fewer a win takes, the more points, from the least to the
                    most.
                  </p>
                  <div v-for="(table, index) in event.points_tables" :key="index" class="stack">
                    <p class="note">
                      <strong>{{ table.action }}</strong>
                      <template v-if="table.note"> · {{ table.note }}</template>
                    </p>
                    <div class="table-well">
                      <table>
                        <thead>
                          <tr>
                            <th>{{ table.side }}</th>
                            <th v-for="column in table.columns" :key="column" class="num">
                              {{ column }}
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="row in table.rows" :key="row.label">
                            <th scope="row">{{ row.label }}</th>
                            <td v-for="(cell, column) in row.cells" :key="column" class="num">
                              {{ cell }}
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </details>

              <p v-if="event.highlights.length" class="note">
                Top prizes: {{ event.highlights.join(" · ") }}
              </p>
            </div>
          </details>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* The events page: a panel per event in masonry columns of 26rem at least, each whole in one
   column; its header (kind, time left at the far end, title) the summary that folds the rest:
   its standing as big figures over a meter and its milestones. */
.event-grid {
  columns: 26rem;
  column-gap: var(--space-xl);
}

.event {
  break-inside: avoid;
  margin-bottom: var(--space-xl);

  h3 {
    margin: 0;
    font-size: var(--text-lg);
  }

  /* The header is the summary: the time left holds the corner base.css puts its chevron in. */
  > details > summary::after {
    display: none;
  }

  details details > summary {
    font-weight: 700;
  }

  details[open] > summary {
    margin-bottom: var(--space-s);
    color: inherit;
  }

  tbody th {
    font-weight: 400;
    white-space: nowrap;
  }
}

.when {
  font-size: var(--text-sm);
  color: var(--on-surface);
  white-space: nowrap;
}

.reached td {
  color: var(--on-surface-variant);
}

/* A milestone the shard plan can aim at: clickable, the one it aims at marked in brass. */
.pickable {
  cursor: pointer;

  &:hover td {
    background: var(--surface-container-high);
  }
}

.picked td {
  background: color-mix(in srgb, var(--primary) 14%, transparent);

  &:first-child {
    box-shadow: inset 2px 0 var(--primary);
  }
}
</style>
