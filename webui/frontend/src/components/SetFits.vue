<script setup lang="ts">
// The set fits: what off-target types count for, each set's value, and which types each set is
// for (the types down, grouped by kind; the sets across, most valued first, the column under
// the pointer lit). Each change is saved at once; what it says goes to the page (`saved`).
import { ref } from "vue";
import { sendToGame } from "../composables/send";
import type { SetGrid } from "../types/generated/webui.service.accessories";

defineProps<{ grid: SetGrid }>();
const emit = defineEmits<{ saved: [error: string | null] }>();
const lit = ref<number | null>(null);

async function store(url: string, fields: Record<string, string>) {
  emit("saved", (await sendToGame(url, fields)).error);
}

function value(event: Event) {
  return (event.target as HTMLInputElement).value;
}

function tone(factor: number) {
  return factor > 1 ? "high" : factor < 1 ? "low" : "";
}

function target(set: number, type: string, event: Event) {
  const on = (event.target as HTMLInputElement).checked;
  store("/accessories/sets/target", { set: String(set), type, ...(on ? { on: "1" } : {}) });
}
</script>

<template>
  <div class="stack" style="--space: var(--space-m)">
    <div class="well cluster" style="--space: var(--space-s) var(--space-l)">
      <label>
        Types a set isn't for count at
        <input
          type="number"
          class="small"
          :value="grid.off_target"
          min="0"
          max="1"
          step="0.05"
          autocomplete="off"
          @change="store('/accessories/off-target', { off_target: value($event) })"
        />
        of their score
      </label>
      <slot />
    </div>
    <div class="table-well">
      <table class="set-grid" @mouseleave="lit = null">
        <thead>
          <tr>
            <th scope="col">Type</th>
            <th
              v-for="(column, n) in grid.columns"
              :key="column.set_id"
              scope="col"
              class="set-name"
              :class="{ lit: lit === n }"
              @mouseover="lit = n"
            >
              <span>{{ column.set_name }}</span>
            </th>
          </tr>
          <tr class="set-values">
            <th scope="row">Value</th>
            <td
              v-for="(column, n) in grid.columns"
              :key="column.set_id"
              :class="{ lit: lit === n }"
              @mouseover="lit = n"
            >
              <input
                type="number"
                class="bare"
                :class="tone(column.factor)"
                :value="column.factor"
                min="0"
                max="3"
                step="0.05"
                autocomplete="off"
                :aria-label="`${column.set_name}: value`"
                @change="
                  store('/accessories/sets/value', {
                    set: String(column.set_id),
                    factor: value($event),
                  })
                "
              />
            </td>
          </tr>
        </thead>
        <tbody v-for="group in grid.groups" :key="group.kind">
          <tr class="set-group">
            <th class="caps" scope="rowgroup" :colspan="1 + grid.columns.length">
              {{ group.kind }}
            </th>
          </tr>
          <tr v-for="row in group.rows" :key="row.key">
            <th scope="row" @mouseover="lit = null">
              {{ row.label }}<small v-if="row.faction"> {{ row.faction }}</small>
            </th>
            <td v-for="(on, n) in row.on" :key="n" :class="{ lit: lit === n }" @mouseover="lit = n">
              <input
                type="checkbox"
                :checked="on"
                autocomplete="off"
                :aria-label="`${grid.columns[n]?.set_name} is for ${row.label}`"
                :title="`${grid.columns[n]?.set_name}: ${row.label}`"
                @change="target(grid.columns[n]?.set_id ?? 0, row.key, $event)"
              />
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
/* A grid of the types each set is for, its value a badge to type into over each column. */
table.set-grid {
  width: auto;

  th,
  td {
    padding: var(--space-2xs);
    text-align: center;
  }

  tr > :first-child {
    position: sticky;
    z-index: 1;
    left: 0;
    padding-inline: var(--space-s);
    text-align: left;
    white-space: nowrap;
    background: var(--surface-container-lowest);
  }

  .set-name {
    vertical-align: bottom;

    span {
      transform: rotate(180deg);
      display: inline-block;
      writing-mode: vertical-rl;
      white-space: nowrap;
    }
  }

  /* Brass above 1, red below. The column under the pointer lit (`lit`), so a tick finds its
     set. */
  .set-values input {
    width: 2.6rem;
    padding: var(--space-3xs);
    border-radius: var(--radius);
    font-size: var(--text-xs);
    background: color-mix(in srgb, var(--on-surface-variant) 12%, transparent);

    &.high {
      color: var(--primary);
      background: color-mix(in srgb, var(--primary) 16%, transparent);
    }

    &.low {
      color: var(--stat-down);
      background: color-mix(in srgb, var(--stat-down) 18%, transparent);
    }

    &:focus {
      box-shadow: 0 0 0 1px var(--primary);
    }
  }

  :is(td, th).lit,
  tbody tr:not(.set-group):hover > * {
    background: color-mix(in srgb, var(--primary) 8%, var(--surface-container-lowest));
  }

  thead th.lit,
  .set-group th {
    color: var(--primary);
  }

  .set-group th {
    padding-top: var(--space-m);
  }

  input[type="checkbox"] {
    margin: 0;
  }
}
</style>
