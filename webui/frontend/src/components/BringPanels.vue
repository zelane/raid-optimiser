<script setup lang="ts">
// What every team must bring besides the content (wanted tags, so many different debuffs or
// buffs), and how it brings it besides skills (gear, relics, assumptions): chosen ones as
// removable chips, a picker adding one, and the count and assume forms. Two panels side by
// side where they fit. `subtitle`: what the wants are besides.
import { computed, ref } from "vue";
import { teamQuery, visitWith } from "../composables/teamQuery";
import type { TeamLinks, TeamView } from "../types/generated/webui.service.team";
import RemoveChip from "./RemoveChip.vue";
import StatusIcon from "./StatusIcon.vue";
import TagPicker, { type PickerGroup } from "./TagPicker.vue";

const props = defineProps<{ team: TeamView; links: TeamLinks; ran: boolean; subtitle: string }>();

const wantGroups = computed<PickerGroup[]>(() =>
  props.team.wants.map((group) => ({
    title: group.title,
    options: group.wants
      .filter((want) => !want.wanted)
      .map((want) => ({
        value: want.key,
        label: want.label,
        note: want.note,
        title: want.note ? `${want.label} (${want.note})` : want.label,
        icons: [{ label: want.label, url: want.icon_url }],
      })),
  })),
);

const gearGroups = computed<PickerGroup[]>(() =>
  props.team.gear.map((group) => ({
    title: group.title,
    options: group.gear
      .filter((gear) => !gear.on)
      .map((gear) => ({
        value: gear.key,
        label: gear.name,
        note: gear.faction ? `${gear.faction} only` : null,
        title: `${gear.name}: ${gear.brings.map((icon) => icon.label).join(", ")}`,
        icons: gear.brings.slice(0, 3),
      })),
  })),
);

// A chip's link: the page without what it asks.
function without(key: string) {
  return props.links.without[key] ?? props.links.current;
}

const countSide = ref("debuff");
const countN = ref("");
const assumeWho = ref("");
const assumeWhat = ref("");

function add(fields: [string, string][]) {
  const query = teamQuery(props.links, props.ran);
  for (const [name, value] of fields) query.append(name, value);
  visitWith(query);
}

function addCount() {
  add([
    ["count_side", countSide.value],
    ["count_n", countN.value],
  ]);
  countN.value = "";
}

function assume() {
  add([
    ["assume_who", assumeWho.value],
    ["assume_what", assumeWhat.value],
  ]);
  assumeWho.value = "";
  assumeWhat.value = "";
}
</script>

<template>
  <div class="grid" style="--min: 34rem; --align: start">
    <section class="panel stack" style="--space: var(--space-m)">
      <header class="panel-head">
        <h2>
          Also bring <small class="muted">{{ subtitle }}</small>
        </h2>
        <div class="cluster" style="--space: var(--space-xs)">
          <RemoveChip
            v-for="want in team.wanted"
            :key="want.key"
            :href="without(want.key)"
            :title="`Stop asking for ${want.label}`"
          >
            <StatusIcon :url="want.icon_url" :label="want.label" size="small" />{{
              want.label
            }}</RemoveChip
          >
          <RemoveChip
            v-for="count in team.counts"
            :key="count.key"
            :href="without(count.key)"
            :title="`Stop asking for ${count.label}`"
          >
            <span class="count-mark" aria-hidden="true">#</span>{{ count.label }}</RemoveChip
          >
          <small v-if="!team.wanted.length && !team.counts.length" class="muted">
            Nothing extra yet
          </small>
        </div>
      </header>
      <TagPicker
        :groups="wantGroups"
        placeholder="Add a buff, debuff or effect…"
        label="Add something to bring"
        @pick="(key) => add([['want', key]])"
      />
      <form class="cluster" @submit.prevent="addCount">
        <span class="caps">Or so many different</span>
        <select v-model="countSide" class="small" aria-label="Debuffs or buffs">
          <option value="debuff">debuffs</option>
          <option value="buff">buffs</option>
        </select>
        <input
          v-model="countN"
          type="number"
          class="small"
          min="1"
          max="10"
          placeholder="3"
          aria-label="How many"
        />
        <button type="submit" class="quiet small">Add</button>
      </form>
    </section>

    <section class="panel stack" style="--space: var(--space-m)">
      <header class="panel-head">
        <h2>
          Gear, relics &amp; assumptions
          <small class="muted">how the team brings it, besides skills</small>
        </h2>
        <div class="cluster" style="--space: var(--space-xs)">
          <RemoveChip
            v-for="gear in team.gear_on"
            :key="gear.key"
            :href="without(gear.key)"
            :title="`Stop allowing ${gear.name}`"
          >
            <StatusIcon
              v-for="icon in gear.brings.slice(0, 3)"
              :key="icon.label"
              :url="icon.url"
              :label="icon.label"
              size="small"
            />{{ gear.name }}</RemoveChip
          >
          <RemoveChip
            v-for="assumed in team.assumed"
            :key="assumed.key"
            class="assumed"
            :href="without(assumed.key)"
            title="Stop assuming it"
          >
            <StatusIcon :url="assumed.icon.url" :label="assumed.icon.label" size="small" />{{
              assumed.champion ?? "Team"
            }}: {{ assumed.label }}</RemoveChip
          >
          <small v-if="!team.gear_on.length && !team.assumed.length" class="muted">
            Skills only
          </small>
        </div>
      </header>
      <TagPicker
        :groups="gearGroups"
        placeholder="Add a set or relic…"
        label="Add gear or a relic"
        @pick="(key) => add([['gear', key]])"
      />
      <form class="stack" style="--space: var(--space-s)" @submit.prevent="assume">
        <p class="note">
          Assume: a blessing, a book to come. A champion (or the team, left empty) brings what you
          name.
        </p>
        <datalist id="team-champions">
          <option v-for="choice in team.choices" :key="choice.label" :value="choice.label" />
        </datalist>
        <div class="cluster" style="--basis: 10rem">
          <input
            v-model="assumeWho"
            type="search"
            class="grow"
            list="team-champions"
            placeholder="Champion (empty: the team)"
            autocomplete="off"
            aria-label="Who brings it"
          />
          <select v-model="assumeWhat" class="grow" aria-label="What they bring">
            <option value="">brings…</option>
            <optgroup v-for="group in team.wants" :key="group.title" :label="group.title">
              <option v-for="want in group.wants" :key="want.key" :value="want.key">
                {{ want.label }}
              </option>
            </optgroup>
          </select>
          <button type="submit" class="quiet">Assume</button>
        </div>
      </form>
    </section>
  </div>
</template>

<style scoped>
.count-mark {
  font-weight: 700;
  color: var(--primary);
}
</style>
