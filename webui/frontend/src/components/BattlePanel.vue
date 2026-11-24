<script setup lang="ts">
// The battle a solve assumes (`webui/forms/request.py`'s `buff_<STAT>` and `aura` fields): the
// buffs and the leader's aura picked, as chips whose × drops them, and a picker for each, by
// stat. One buff per stat (picking the other strength replaces it) and one aura.
import { computed } from "vue";
import type {
  BattleGroup,
  BattleOption,
  BattleOptions,
} from "../types/generated/webui.service.champions";
import RemoveChip from "./RemoveChip.vue";
import StatusIcon from "./StatusIcon.vue";
import TagPicker, { type PickerGroup } from "./TagPicker.vue";

const props = defineProps<{ options: BattleOptions }>();
const fields = defineModel<Record<string, string>>("fields", { required: true });

// A picker option's value: the field and its value, as a buff's ("25") repeats across stats.
function key(option: BattleOption) {
  return `${option.field}=${option.value}`;
}

function chosen(option: BattleOption) {
  return fields.value[option.field] === option.value;
}

const every = computed(() =>
  [...props.options.buffs, ...props.options.auras].flatMap((group) => group.options),
);
const buffs = computed(() => props.options.buffs.flatMap((group) => group.options).filter(chosen));
const leader = computed(() => props.options.auras.flatMap((group) => group.options).find(chosen));
// A saved run's leader the account no longer offers: shown, so it can be dropped.
const lostLeader = computed(() => Boolean(fields.value.aura) && !leader.value);

function groups(from: BattleGroup[]): PickerGroup[] {
  return from.map((group) => ({
    title: group.title,
    options: group.options
      .filter((option) => !chosen(option))
      .map((option) => ({
        value: key(option),
        label: option.label,
        note: option.note,
        icons: option.icons,
      })),
  }));
}

function pick(value: string) {
  const option = every.value.find((each) => key(each) === value);
  if (option) fields.value[option.field] = option.value;
}

function drop(field: string) {
  delete fields.value[field];
}
</script>

<template>
  <div class="stack" style="--space: var(--space-m)">
    <div class="cluster" style="--space: var(--space-xs)">
      <RemoveChip
        v-for="buff in buffs"
        :key="buff.field"
        :title="`Stop assuming ${buff.label}`"
        kind="buff"
        @remove="drop(buff.field)"
      >
        <StatusIcon :url="buff.icons[0]?.url ?? null" :label="buff.label" size="small" />{{
          buff.label
        }}
      </RemoveChip>
      <RemoveChip
        v-if="leader"
        class="assumed"
        :title="`Stop assuming ${leader.label}'s aura`"
        kind="gear"
        @remove="drop('aura')"
      >
        <StatusIcon :url="leader.icons[0]?.url ?? null" :label="leader.label" size="small" />{{
          leader.label
        }}: {{ leader.note }}
      </RemoveChip>
      <RemoveChip
        v-else-if="lostLeader"
        class="assumed"
        title="Drop it: that leader's aura no longer reaches this champion"
        kind="gear"
        @remove="drop('aura')"
      >
        A leader no longer offered
      </RemoveChip>
      <small v-if="!buffs.length && !fields.aura" class="muted">No buffs, no aura</small>
    </div>
    <TagPicker
      :groups="groups(options.buffs)"
      placeholder="Add a buff…"
      label="Add a buff to assume"
      @pick="pick"
    />
    <TagPicker
      :groups="groups(options.auras)"
      :placeholder="leader ? 'Another leader…' : 'Lead with an aura…'"
      label="Pick a leader's aura to assume"
      @pick="pick"
    />
    <small class="note">
      Every row of the results is in this battle, the gear worn now too. An aura's area isn't
      checked: one for Arena counts against any target.
    </small>
  </div>
</template>
