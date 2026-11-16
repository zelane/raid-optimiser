<script setup lang="ts" generic="Key extends string | number">
// The ledger: the stats worn now, then a build a row, each change beside its value. A row's
// heading is the `head` slot's; `pickable` rows are picked by a click anywhere on them.
import type { StatCell } from "../types/generated/webui.service.results";

defineProps<{
  current: StatCell[];
  rows: { key: Key; picked: boolean; stats: StatCell[] }[];
  pickable?: boolean;
}>();
const emit = defineEmits<{ pick: [key: Key] }>();
defineSlots<{ head(props: { key: Key }): unknown }>();
</script>

<template>
  <table class="ledger">
    <thead>
      <tr>
        <th></th>
        <th v-for="now in current" :key="now.label" scope="col">{{ now.label }}</th>
      </tr>
    </thead>
    <tbody>
      <tr class="now">
        <th scope="row">Now</th>
        <td v-for="now in current" :key="now.label">{{ now.text }}</td>
      </tr>
      <tr
        v-for="row in rows"
        :key="row.key"
        :class="{ 'build-row': pickable, picked: row.picked }"
        @click="pickable && emit('pick', row.key)"
      >
        <th scope="row"><slot name="head" :key="row.key" /></th>
        <td v-for="cell in row.stats" :key="cell.label">
          {{ cell.text
          }}<small :class="cell.change ? (cell.better ? 'up' : 'down') : ''">{{
            cell.change ?? ""
          }}</small>
        </td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
/* The ledger: a build a row, so it grows down, not across. Each change sits in a fixed slot
   after its value, so columns read straight down; the headings and the Now row leave the same
   room. The picked build gets a brass rail; its pieces fill the width under the ledger. */
table.ledger {
  --change-width: 3.25rem;
  --change-slot: calc(var(--change-width) + var(--space-xs));

  th,
  td {
    text-align: right;
    white-space: nowrap;
  }

  thead th {
    background: var(--surface-container-low);
  }

  tbody th {
    width: 1%;
    text-align: left;
  }

  td small {
    display: inline-block;
    width: var(--change-width);
    margin-left: var(--space-xs);
    font-size: var(--text-2xs);
    text-align: left;
  }

  thead th:not(:first-child),
  tr.now td {
    padding-right: calc(var(--space-s) + var(--change-slot));
  }

  tr.now > * {
    font-weight: 600;
    color: var(--on-surface-variant);
  }

  tr.now th {
    padding-left: calc(var(--space-s) + 3px);
  }

  tr.build-row {
    cursor: pointer;

    &:hover > * {
      background: color-mix(in srgb, var(--on-surface) 4%, transparent);
    }

    > th {
      border-left: 3px solid transparent;
    }
  }

  tr.picked {
    > * {
      font-weight: 700;
      background: color-mix(in srgb, var(--primary) 8%, transparent);
    }

    > th {
      border-left-color: var(--primary);
    }
  }
}
</style>
