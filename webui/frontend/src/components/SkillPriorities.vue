<script setup lang="ts">
// One champion's skill settings, as the game's auto plays them, in a dropdown under their tile:
// a "Skills" button opens it. Each wave's (a wave picker when there's more than one) active
// skills, by form for a mythical, each with its priority (the game's: Default, priority 1 to 3,
// don't use) and its place among the openers (the skills used first, in order: click to add,
// again to take out). `end`: it opens towards the left, for slots at the row's end. Escape or
// clicking away closes it.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import type { SlotView, WaveSettings } from "../types/generated/webui.service.sims";

const PRIORITIES: [string, string][] = [
  ["Default", "Default"],
  ["First", "Priority 1"],
  ["Second", "Priority 2"],
  ["Third", "Priority 3"],
  ["NotUsed", "Don't use"],
];

defineProps<{ end?: boolean }>();
const slot = defineModel<SlotView>({ required: true });

const id = `skills-${Math.random().toString(36).slice(2)}`;
const root = ref<HTMLElement>();
const open = ref(false);
const wave = ref(0);

const shown = computed(() => Math.min(wave.value, slot.value.waves.length - 1));
const settings = computed(() => slot.value.waves[shown.value]!);

// Settings left as auto plays them, for the button's mark.
const changed = computed(() =>
  slot.value.waves.some(
    (w) => w.openers.length || Object.values(w.priorities).some((p) => p !== "Default"),
  ),
);

function change(edit: (settings: WaveSettings) => WaveSettings) {
  const waves = slot.value.waves.map((each, i) => (i === shown.value ? edit(each) : each));
  slot.value = { ...slot.value, waves };
}

function setPriority(skill: number, priority: string) {
  change((each) => ({ ...each, priorities: { ...each.priorities, [String(skill)]: priority } }));
}

function toggleOpener(skill: number) {
  change((each) => ({
    ...each,
    openers: each.openers.includes(skill)
      ? each.openers.filter((other) => other !== skill)
      : [...each.openers, skill],
  }));
}

function leave(event: FocusEvent) {
  if (!root.value?.contains(event.relatedTarget as Node)) open.value = false;
}

// A click anywhere else closes it too (not every browser moves focus to a clicked button).
function clickedAway(event: PointerEvent) {
  if (!root.value?.contains(event.target as Node)) open.value = false;
}

onMounted(() => document.addEventListener("pointerdown", clickedAway));
onBeforeUnmount(() => document.removeEventListener("pointerdown", clickedAway));

const ordinal = (n: number) => `${n}${["st", "nd", "rd"][n - 1] ?? "th"}`;
</script>

<template>
  <div ref="root" class="skill-priorities" @focusout="leave" @keydown.esc="open = false">
    <button
      type="button"
      class="small quiet skills-button"
      :aria-expanded="open"
      :aria-controls="id"
      :title="changed ? 'Skill settings set' : 'Skill settings: auto’s defaults'"
      @click="open = !open"
    >
      Skills <span v-if="changed" class="set-mark" aria-hidden="true">●</span> ▾
    </button>

    <div
      v-show="open"
      :id="id"
      class="skills-panel stack"
      :class="{ end }"
      style="--space: var(--space-s)"
      tabindex="-1"
    >
      <div class="cluster" style="--space: var(--space-s); --justify: space-between">
        <strong>{{ slot.champion.name }}</strong>
        <fieldset
          v-if="slot.waves.length > 1"
          class="segmented small"
          role="radiogroup"
          :aria-label="`${slot.champion.name}'s wave`"
        >
          <label v-for="(_, w) in slot.waves" :key="w">
            <input type="radio" :name="`${id}-wave`" :checked="shown === w" @change="wave = w" />
            Wave {{ w + 1 }}
          </label>
        </fieldset>
      </div>

      <div v-for="(form, f) in slot.forms" :key="f" class="table-well">
        <table>
          <thead>
            <tr>
              <th>{{ slot.forms.length > 1 ? `Form ${f + 1} · ${form.role}` : "Skill" }}</th>
              <th>Priority</th>
              <th>Opener</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="skill in form.skills" :key="skill.id">
              <td :title="skill.cooldown ? `${skill.cooldown}-turn cooldown` : 'no cooldown'">
                <span class="badge quiet">{{ skill.slot }}</span>
                {{ skill.name }}
              </td>
              <td>
                <select
                  class="small"
                  :value="settings.priorities[String(skill.id)] ?? 'Default'"
                  @change="setPriority(skill.id, ($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="[value, label] in PRIORITIES" :key="value" :value="value">
                    {{ label }}
                  </option>
                </select>
              </td>
              <td>
                <button
                  type="button"
                  class="small"
                  :class="{ quiet: !settings.openers.includes(skill.id) }"
                  @click="toggleOpener(skill.id)"
                >
                  {{
                    settings.openers.includes(skill.id)
                      ? ordinal(settings.openers.indexOf(skill.id) + 1)
                      : "—"
                  }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* A "Skills" button under a champion's tile, its dropdown over what's below. */
.skill-priorities {
  position: relative;
}

.set-mark {
  color: var(--primary);
}

.skills-panel {
  position: absolute;
  z-index: 20;
  inset-inline-start: 0;
  top: calc(100% + var(--space-2xs));
  inline-size: min(30rem, calc(100vw - 2rem));
  padding: var(--space-s);
  border: 1px solid var(--outline-variant);
  border-radius: var(--radius-l);
  color: var(--on-surface);
  text-align: start;
  background: var(--surface-container-low);

  &.end {
    inset-inline: auto 0;
  }
}

td .badge {
  margin-inline-end: var(--space-2xs);
}

/* The same columns in each form's table, so they line up. */
table {
  table-layout: fixed;
}

th:nth-child(2) {
  inline-size: 8.5rem;
}

th:nth-child(3) {
  inline-size: 5rem;
}
</style>
