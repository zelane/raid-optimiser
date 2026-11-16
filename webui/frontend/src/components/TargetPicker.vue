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

<style scoped>
/* The target picker across the top: zone…stage as a 2×2 of labelled selects, then the stage's
   last wave as portraits (the picked one lit) and the pick's stats, on the slab. When the DEF
   field no longer matches it, it dims and says so. */
.target-picker {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-l) var(--space-2xl);
  align-items: center;

  &.busy {
    opacity: 0.8;
  }

  &.off-target .target-card {
    opacity: 0.6;
  }

  &:not(.off-target) .target-detached {
    display: none;
  }
}

@container page (min-width: 60rem) {
  .target-picker {
    grid-template-columns: minmax(16rem, 2fr) minmax(0, 3fr);
  }
}

.target-levels {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-s) var(--space-m);

  label {
    margin: 0;
  }

  select {
    font-weight: 600;
  }
}

.target-card {
  padding: var(--space-m) var(--space-l);
}

.target-enemy {
  cursor: pointer;
  flex: none;
  padding: 0;
  border: 0;
  opacity: 0.55;
  background: none;
  transition: opacity var(--transition);

  .tile {
    --tile-width: 3.6rem;
  }

  &:hover,
  &:focus-visible {
    opacity: 0.85;
  }

  &:focus-visible {
    outline: 2px solid var(--primary);
    outline-offset: 2px;
  }

  &.picked {
    opacity: 1;

    .tile {
      --tile-width: 4.6rem;
    }
  }
}

.target-facts {
  flex: 1 1 18rem;
  min-width: 0;
}

/* The enemy's name, and the wave select at the line's far end. */
.target-head {
  display: flex;
  gap: var(--space-xs) var(--space-m);
  align-items: center;
  justify-content: space-between;

  .target-name {
    min-width: 0;
  }
}

.target-wave {
  flex: none;
  margin-block: 0;

  select {
    font-weight: 600;
  }
}

.target-name strong {
  font-family: var(--font-display);
  font-size: var(--text-l);
}
</style>
