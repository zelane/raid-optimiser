<script setup lang="ts">
// The champions an event scoring level-ups (Champion Training) takes brewed to reach the
// milestone picked in the card's table (the next not reached by default), folded away like the
// card's rules: per grade, a new champion brewed from level 1 to half its top level with brews
// of its own affinity, what that earns, and how many of them (all of that grade) the rest takes.
import { computed } from "vue";
import type { MilestoneRow } from "../types/generated/webui.service.events";
import type { BrewPlan } from "../types/generated/webui.service.training";

const { plan, target, points } = defineProps<{
  plan: BrewPlan;
  target: MilestoneRow;
  points: number;
}>();

const short = computed(() => target.points - points);

function champions(each: number) {
  return Math.ceil(short.value / each);
}

function count(value: number) {
  return value.toLocaleString();
}
</script>

<template>
  <details class="brew-plan">
    <summary>
      Brews
      <small class="muted">to reach {{ count(target.points) }}: {{ target.prize }}</small>
    </summary>

    <div class="stack" style="--space: var(--space-s)">
      <p class="note">
        <strong>{{ count(short) }} to go</strong>
      </p>

      <div class="table-well">
        <table>
          <thead>
            <tr>
              <th>Champion</th>
              <th class="num" title="Brews of its own affinity, and the level they take it to">
                Brews
              </th>
              <th class="num" title="Points one champion brewed that far earns">Each</th>
              <th class="num" title="Champions of this grade the rest takes">Needed</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in plan.rows" :key="row.stars">
              <th scope="row">{{ row.stars }}★</th>
              <td class="num">
                {{ row.brews }}
                <small class="muted level">to level {{ row.level }}</small>
              </td>
              <td class="num">
                {{ count(row.points) }}
                <small class="muted level">{{ row.per_brew }} a brew</small>
              </td>
              <td class="num">
                <strong>{{ count(champions(row.points)) }}</strong>
                <small class="muted level"
                  >{{ count(champions(row.points) * row.brews) }} brews</small
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="note">
        New champions to half their top level, with brews of their own affinity ({{
          count(plan.matching)
        }}
        XP; {{ count(plan.brew) }} otherwise, so about half as many again). The first brew earns the
        most: levels cost more XP as they climb.
      </p>
    </div>
  </details>
</template>

<style scoped>
/* Folded like the card's rules, the milestone aimed at in its summary; a row per grade, each
   count with what it comes to under it. */
.brew-plan {
  > summary {
    font-weight: 700;
  }

  &[open] > summary {
    margin-bottom: var(--space-s);
    color: inherit;
  }

  tbody th {
    font-weight: 400;
    white-space: nowrap;
  }
}

.level {
  display: block;
  white-space: nowrap;
}
</style>
