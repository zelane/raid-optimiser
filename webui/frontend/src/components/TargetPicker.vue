<script setup lang="ts">
// The target picker: zone, group, difficulty and stage, then one enemy of a wave (the last
// unless picked), with its stats. Each change asks `/targets` for the picker again (the levels
// under the one changed go back to their defaults); a pick of the user's is announced
// (`picked`) for the page to fill in what it wants. `detached`: the page no longer uses the
// pick (its DEF was typed over), so the card dims and says so.
import { ref, watch } from "vue";
import type { EnemyCard, TargetPicker } from "../types/generated/webui.service.targets";
import ChampionTile from "./ChampionTile.vue";

const props = defineProps<{ picker: TargetPicker; detached?: boolean }>();
const emit = defineEmits<{ picked: [enemy: EnemyCard, target: string] }>();

const shown = ref(props.picker);
const busy = ref(false);

watch(
  () => props.picker,
  (picker) => (shown.value = picker),
);

type Level = "zone" | "group" | "difficulty" | "stage" | "wave" | "enemy";

function selected(options: { value: string; selected: boolean }[]) {
  return options.find((option) => option.selected)?.value ?? "";
}

async function change(level: Level, value: string) {
  const view = shown.value;
  const query = new URLSearchParams({
    zone: selected(view.zones),
    group: selected(view.groups),
    difficulty: selected(view.difficulties),
    stage: selected(view.stages),
    wave: selected(view.waves),
    enemy: view.picked.key,
    changed: level,
  });
  query.set(level, value);
  busy.value = true;

  try {
    const response = await fetch(`/targets?${query}`, { headers: { Accept: "application/json" } });
    if (!response.ok) return;
    shown.value = (await response.json()) as TargetPicker;
    emit("picked", shown.value.picked, shown.value.target);
  } finally {
    busy.value = false;
  }
}

const levels = [
  ["zone", "Zone", "zones"],
  ["group", "Group", "groups"],
  ["difficulty", "Difficulty", "difficulties"],
  ["stage", "Stage", "stages"],
] as const;
</script>

<template>
  <div class="panel target-picker" :class="{ busy, 'off-target': detached }">
    <div class="target-levels">
      <label v-for="[level, label, list] in levels" :key="level">
        <span class="caps">{{ label }}</span>
        <select
          :value="selected(shown[list])"
          @change="change(level, ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="option in shown[list]" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>
    </div>
    <div class="target-card well cluster" style="--space: var(--space-l) var(--space-2xl)">
      <div class="cluster" style="--space: var(--space-xs)" role="radiogroup" aria-label="Enemy">
        <button
          v-for="enemy in shown.enemies"
          :key="enemy.key"
          type="button"
          role="radio"
          :aria-checked="enemy.picked"
          class="target-enemy"
          :class="{ picked: enemy.picked, boss: enemy.boss }"
          :title="`${enemy.name}${enemy.boss ? ' (boss)' : ''}`"
          @click="change('enemy', enemy.key)"
        >
          <ChampionTile :champion="enemy" />
        </button>
      </div>
      <div class="target-facts stack" style="--space: var(--space-s)">
        <div class="target-head">
          <p class="target-name cluster" style="--space: var(--space-2xs) var(--space-s)">
            <strong>{{ shown.picked.name }}</strong>
            <small v-if="shown.picked.boss" class="badge">Boss</small>
            <small class="muted">{{ shown.title }} · {{ shown.picked.affinity }}</small>
          </p>
          <label v-if="shown.waves.length > 1" class="target-wave inline">
            <span class="caps">Wave</span>
            <select
              class="small"
              :value="selected(shown.waves)"
              @change="change('wave', ($event.target as HTMLSelectElement).value)"
            >
              <option v-for="option in shown.waves" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </label>
        </div>
        <dl class="stat-tiles target-stats">
          <div v-for="stat in shown.picked.stats" :key="stat.label">
            <dt>{{ stat.label }}</dt>
            <dd>{{ stat.text }}</dd>
          </div>
        </dl>
        <small class="target-detached note">
          Not in use: damage ranks against the DEF typed in below.
        </small>
      </div>
    </div>
  </div>
</template>
