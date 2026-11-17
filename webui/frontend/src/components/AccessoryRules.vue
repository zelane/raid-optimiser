<script setup lang="ts">
// The accessory rules not of a set: a row each, its name and what it does, its numbers, and its
// switch at the end where it can be switched off. Each change is saved at once, without a
// reload (a switch keeps its state here, `switched`); what it says goes to the page (`saved`).
import { ref } from "vue";
import { checkedOf, valueOf } from "../composables/format";
import { sendToGame, type Sent } from "../composables/send";
import type { RuleRow } from "../types/generated/webui.service.accessories";

defineProps<{ rows: RuleRow[] }>();
const emit = defineEmits<{ saved: [sent: Sent] }>();
const switched = ref<Record<string, boolean>>({});

function isOn(row: RuleRow) {
  return row.switch === null || (switched.value[row.switch.name] ?? row.switch.value === 1);
}

function toggle(name: string, event: Event) {
  const on = checkedOf(event);
  switched.value = { ...switched.value, [name]: on };
  store(name, on ? "1" : "0");
}

async function store(rule: string, value: string) {
  emit("saved", await sendToGame("/accessories/rule", { rule, value }));
}
</script>

<template>
  <div class="rule-rows well">
    <div v-for="row in rows" :key="row.label" class="rule-row" :class="{ off: !isOn(row) }">
      <div class="rule-name">
        <span>{{ row.label }}</span>
        <small class="note">{{ row.note }}</small>
      </div>
      <div class="cluster" style="--space: var(--space-xs) var(--space-s)">
        <label v-for="number in row.numbers" :key="number.name" class="inline">
          {{ number.label }}
          <input
            type="number"
            class="small"
            :value="number.value"
            :min="number.low ?? undefined"
            :max="number.high ?? undefined"
            :step="number.step"
            autocomplete="off"
            :aria-label="`${row.label}: ${number.label}`"
            @change="store(number.name, valueOf($event))"
          />
        </label>
      </div>
      <input
        v-if="row.switch"
        type="checkbox"
        role="switch"
        :checked="isOn(row)"
        :aria-label="row.label"
        @change="toggle(row.switch.name, $event)"
      />
    </div>
  </div>
</template>

<style scoped>
/* Settings as rows, the switch at the end; a rule switched off dims. */
.rule-rows {
  display: flex;
  flex-direction: column;
  padding-block: var(--space-3xs);
}

.rule-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto 2.5rem;
  gap: var(--space-s);
  align-items: center;
  padding: var(--space-s) 0;
  border-bottom: 1px solid var(--outline-variant);
  font-size: var(--text-s);

  &:last-child {
    border-bottom: 0;
  }

  &.off > :not([role="switch"]) {
    opacity: 0.5;
  }

  input[type="number"] {
    width: 4.5rem;
  }

  input[type="checkbox"] {
    justify-self: end;
    margin: 0;
  }
}

.rule-name {
  display: flex;
  flex-direction: column;
  gap: var(--space-3xs);
  min-width: 0;
}
</style>
