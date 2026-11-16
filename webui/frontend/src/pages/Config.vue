<script setup lang="ts">
// What every solve assumes and leaves out, for all champions: assumptions, glyphs and reserved
// gear. Each change is saved at once.
import { Head } from "@inertiajs/vue3";
import { ref, watch } from "vue";
import PageHead from "../components/PageHead.vue";
import { checkedOf, valueOf } from "../composables/format";
import { save } from "../composables/save";
import type { AssumptionsPage } from "../types/generated/webui.service.assumptions";

const { page } = defineProps<{ page: AssumptionsPage }>();
const tag = ref(page.reserve.tags[0]?.key ?? "");
const team = ref(page.reserve.teams[0]?.key ?? "");

// A tag or team just added is no longer offered: pick the first that still is.
watch(
  () => page.reserve,
  (reserve) => {
    if (!reserve.tags.some((choice) => choice.key === tag.value))
      tag.value = reserve.tags[0]?.key ?? "";
    if (!reserve.teams.some((choice) => choice.key === team.value))
      team.value = reserve.teams[0]?.key ?? "";
  },
);

function flag(name: string, event: Event) {
  const on = checkedOf(event);
  save("/assumptions", on ? { flag: name, on: "1" } : { flag: name });
}

function glyph(kind: string, event: Event) {
  save("/glyphs", { kind, grade: valueOf(event) });
}

function addRule(rule: string) {
  save("/reserve", { rule, on: "1" });
}

function removeRule(rule: string) {
  save("/reserve", { rule });
}
</script>

<template>
  <Head title="Config" />
  <PageHead title="Config">
    <template #lede>What every solve assumes and leaves out, for all champions.</template>
  </PageHead>
  <!-- Three panels: what's assumed done, the glyphs assumed, the gear kept back. -->
  <div class="grid" style="--min: 22rem; --align: start">
    <section class="panel stack" style="--space: var(--space-m)">
      <header class="panel-head"><h2>Assumptions</h2></header>
      <p class="note">
        What solves take as done beyond the gear as it is now. Builds mark each assumed value, so
        you can see what still needs doing. Current stats keep the gear as it is.
      </p>
      <div class="switch-rows well">
        <label v-for="item in page.flags" :key="item.name">
          <input
            type="checkbox"
            role="switch"
            :checked="item.on"
            @change="flag(item.name, $event)"
          />
          <span class="row-name">{{ item.label }}</span>
        </label>
      </div>
    </section>

    <section class="panel stack" style="--space: var(--space-m)">
      <header class="panel-head">
        <h2>Glyphs</h2>
        <span class="caps">top roll of the grade</span>
      </header>
      <p class="note">
        Every substat of a kind chosen here is taken as carrying that glyph at its top roll, unless
        the glyph already on it is better. Gear below 6★ takes glyphs up to its own rank, so there
        it's capped at that rank's top roll. A solve only glyphs stats it wants more of: a minimum,
        a priority, or a stat the ranked skill's damage uses (and C.DMG); a stat with only a maximum
        isn't glyphed. Main stats can't be glyphed, and the game has no C.RATE or C.DMG glyphs.
      </p>
      <div class="table-well">
        <table class="glyphs">
          <thead>
            <tr>
              <th>Stat</th>
              <th>Assume</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in page.glyphs" :key="row.key">
              <th scope="row">{{ row.label }}</th>
              <td>
                <select
                  :aria-label="`${row.label} glyph`"
                  class="small"
                  :class="{ 'is-planned': row.chosen }"
                  :value="row.chosen"
                  @change="glyph(row.key, $event)"
                >
                  <option v-for="choice in row.choices" :key="choice.key" :value="choice.key">
                    {{ choice.label }}
                  </option>
                </select>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel stack" style="--space: var(--space-m)">
      <header class="panel-head">
        <h2>Reserved gear</h2>
        <span class="caps">read fresh on every sync</span>
      </header>
      <p class="note">
        Gear kept for something else. Each rule is its own switch on the champion page (on by
        default), builds that take reserved gear say so, and the accessory clean-up never sells it
        (swaps may still move it). Global presets reserve their pieces even when no one wears them.
        A champion's own gear is always theirs to use.
      </p>
      <div class="stack">
        <div v-if="page.reserve.rules.length" class="table-well">
          <table class="reserve-rules">
            <thead>
              <tr>
                <th>Reserves</th>
                <th>Pieces</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="rule in page.reserve.rules" :key="rule.key">
                <td>{{ rule.label }}</td>
                <td>{{ rule.pieces }}</td>
                <td>
                  <button class="quiet small" @click="removeRule(rule.key)">Remove</button>
                </td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td>Together</td>
                <td>{{ page.reserve.pieces }}</td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>
        <p v-else class="note">Nothing is reserved.</p>

        <div class="stack" style="--space: var(--space-m); --align: flex-start">
          <form v-if="page.reserve.tags.length" class="joined" @submit.prevent="addRule(tag)">
            <select v-model="tag" aria-label="Champion tag">
              <option v-for="choice in page.reserve.tags" :key="choice.key" :value="choice.key">
                {{ choice.label }}
              </option>
            </select>
            <button type="submit">Add tag</button>
          </form>
          <form v-if="page.reserve.teams.length" class="joined" @submit.prevent="addRule(team)">
            <select v-model="team" aria-label="Saved team">
              <option v-for="choice in page.reserve.teams" :key="choice.key" :value="choice.key">
                {{ choice.label }}
              </option>
            </select>
            <button type="submit">Add team</button>
          </form>
          <button v-if="page.reserve.global_key" @click="addRule(page.reserve.global_key)">
            Add global presets
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* A glyph assumed is outlined in brass. The reserve rules' table is only as wide as it needs. */
table.glyphs select.is-planned {
  border-color: var(--primary);
}

table.reserve-rules {
  width: auto;
}
</style>
