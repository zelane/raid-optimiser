<script setup lang="ts">
// A champion type, saved whole on each change (`forms.settings.parse_champion_type`): its name,
// kind and faction, a weight per stat (a zero dimmed), the main stats that suit it per slot.
// Copy adds a copy; Delete asks first. What a save says goes to the page (`saved`).
import { router } from "@inertiajs/vue3";
import { ref, watch } from "vue";
import { sendToGame } from "../composables/send";
import type { TypeRow } from "../types/generated/webui.service.accessories";
import type { Choice } from "../types/generated/webui.service.views";

const props = defineProps<{ row: TypeRow; kinds: Choice[]; factions: Choice[] }>();
const emit = defineEmits<{ saved: [error: string | null] }>();

function edits(row: TypeRow) {
  return {
    label: row.label,
    kind: row.kind,
    faction: row.faction,
    weights: Object.fromEntries(row.cells.map((cell) => [cell.field, String(cell.value)])),
    mains: Object.fromEntries(
      row.mains.flatMap((slot) => slot.options.map((option) => [option.field, option.on])),
    ),
  };
}

const edit = ref(edits(props.row));
watch(
  () => props.row,
  (row) => (edit.value = edits(row)),
);

async function store() {
  const { label, kind, faction, weights, mains } = edit.value;
  const fields = new URLSearchParams({ type: props.row.key, label, kind, faction });
  for (const [field, value] of Object.entries(weights)) fields.append(field, value);
  for (const [field, on] of Object.entries(mains)) if (on) fields.append(field, "on");
  emit("saved", (await sendToGame("/accessories/types", fields)).error);
}

function copy() {
  router.post(`/accessories/types/${props.row.key}/copy`);
}

function remove() {
  if (confirm(`Delete ${props.row.label}?`))
    router.post(`/accessories/types/${props.row.key}/delete`);
}
</script>

<template>
  <form class="type-card panel" :class="row.kind" @change="store" @submit.prevent>
    <div class="stack" style="--space: var(--space-xs)">
      <input
        v-model="edit.label"
        type="text"
        class="type-name"
        required
        autocomplete="off"
        aria-label="Type name"
      />
      <div class="cluster" style="--space: var(--space-xs)">
        <div class="segmented small type-kind" role="radiogroup" :aria-label="`${row.label}: kind`">
          <label v-for="choice in kinds" :key="choice.value">
            <input v-model="edit.kind" type="radio" :value="choice.value" />{{ choice.label }}
          </label>
        </div>
        <select v-model="edit.faction" class="small" :aria-label="`${row.label}: faction`">
          <option value="">Any faction</option>
          <option v-for="choice in factions" :key="choice.value" :value="choice.value">
            {{ choice.label }}
          </option>
        </select>
      </div>
      <p v-if="row.champions.length" class="note">from {{ row.champions.join(", ") }}</p>
    </div>
    <div class="stat-tiles edit">
      <label
        v-for="cell in row.cells"
        :key="cell.field"
        :class="{ zero: Number(edit.weights[cell.field]) === 0 }"
      >
        <span class="caps">{{ cell.label }}</span>
        <input
          v-model="edit.weights[cell.field]"
          type="number"
          class="bare"
          autocomplete="off"
          min="0"
          max="10"
          step="0.5"
          :aria-label="`${row.label}: ${cell.label}`"
        />
      </label>
    </div>
    <div class="type-mains">
      <template v-for="slot in row.mains" :key="slot.slot">
        <span class="caps">{{ slot.slot }}</span>
        <div class="segmented small">
          <label v-for="option in slot.options" :key="option.field">
            <input
              v-model="edit.mains[option.field]"
              type="checkbox"
              :aria-label="`${row.label}: ${slot.slot} ${option.label}`"
            />{{ option.label }}
          </label>
        </div>
      </template>
    </div>
    <div class="type-actions">
      <button type="button" class="quiet small" :title="`Add a copy of ${row.label}`" @click="copy">
        Copy
      </button>
      <button
        type="button"
        class="quiet small danger"
        :title="`Delete ${row.label}`"
        @click="remove"
      >
        Delete
      </button>
    </div>
  </form>
</template>

<style scoped>
/* A card a champion type, in four zones: who (name, kind, faction, who it came from), its stat
   weights as tiles, the main stats it suits a slot a row, then copy and delete. Its kind on the
   rail. One under another on narrow screens. */
.type-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-m) var(--space-xl);
  align-items: center;
  padding: var(--space-m) var(--space-l);
  border-left: 3px solid var(--primary);

  &.support {
    border-left-color: var(--tertiary);

    .type-kind label:has(:checked) {
      background: var(--tertiary);
    }
  }

  .stat-tiles {
    grid-template-columns: repeat(7, minmax(3rem, 1fr));
  }
}

input.type-name {
  height: auto;
  margin-inline: calc(var(--space-2xs) * -1);
  padding: var(--space-3xs) var(--space-2xs);
  border-color: transparent;
  font-family: var(--font-display);
  font-size: var(--text-l);
  font-weight: 700;
  color: var(--heading);
  background: none;

  &:is(:hover, :focus) {
    border-color: var(--outline-variant);
    background: var(--surface-container-lowest);
  }
}

.type-mains {
  display: grid;
  grid-template-columns: auto auto;
  gap: var(--space-2xs) var(--space-s);
  place-items: center start;
  justify-content: start;
}

.type-actions {
  display: flex;
  gap: var(--space-2xs);

  button {
    flex: 1;
  }
}

@container page (min-width: 62rem) {
  .type-card {
    grid-template-columns: minmax(12rem, 15rem) minmax(0, 1fr) auto auto;
  }

  .type-actions {
    flex-direction: column;
  }
}
</style>
