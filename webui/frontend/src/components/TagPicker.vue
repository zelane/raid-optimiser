<script setup lang="ts">
// A search box over a dropdown of options in groups: typing narrows it to the options whose
// text holds it; a pick is announced. Arrow keys move between the shown options; Enter picks
// the focused one, or in the search box the only one left; Escape closes.
import { computed, nextTick, ref } from "vue";
import type { IconView } from "../types/generated/webui.service.team";
import StatusIcon from "./StatusIcon.vue";

export interface PickerOption {
  value: string;
  label: string;
  note?: string | null;
  title?: string;
  icons: IconView[];
}

export interface PickerGroup {
  title: string;
  options: PickerOption[];
}

const props = defineProps<{ groups: PickerGroup[]; placeholder: string; label: string }>();
const emit = defineEmits<{ pick: [value: string] }>();

const id = `picker-${Math.random().toString(36).slice(2)}`;
const root = ref<HTMLElement>();
const text = ref("");
const open = ref(false);

const shown = computed(() => {
  const wanted = text.value.trim().toLowerCase();
  return props.groups
    .map((group) => ({
      ...group,
      options: group.options.filter(
        (option) =>
          !wanted || `${option.label} ${option.note ?? ""}`.toLowerCase().includes(wanted),
      ),
    }))
    .filter((group) => group.options.length);
});
const flat = computed(() => shown.value.flatMap((group) => group.options));

function pick(option: PickerOption) {
  open.value = false;
  text.value = "";
  emit("pick", option.value);
}

function buttons() {
  return [...(root.value?.querySelectorAll<HTMLButtonElement>(".picker-option") ?? [])];
}

async function focusFirst() {
  open.value = true;
  await nextTick();
  buttons()[0]?.focus();
}

function step(event: KeyboardEvent, by: number) {
  const all = buttons();
  const next = all[all.indexOf(event.target as HTMLButtonElement) + by];
  if (next) next.focus();
  else if (by < 0) root.value?.querySelector<HTMLInputElement>(".picker-search")?.focus();
}

function enter() {
  const only = flat.value.length === 1 ? flat.value[0] : undefined;
  if (only) pick(only);
}

function leave(event: FocusEvent) {
  if (!root.value?.contains(event.relatedTarget as Node)) open.value = false;
}
</script>

<template>
  <div ref="root" class="picker" @focusout="leave">
    <input
      v-model="text"
      type="search"
      class="picker-search"
      role="combobox"
      :aria-expanded="open"
      :aria-controls="id"
      aria-autocomplete="list"
      :placeholder="placeholder"
      :aria-label="label"
      autocomplete="off"
      @focus="open = true"
      @click="open = true"
      @input="open = true"
      @keydown.down.prevent="focusFirst"
      @keydown.enter.prevent="enter"
      @keydown.esc="open = false"
    />
    <div v-show="open" :id="id" class="picker-options" role="listbox" :aria-label="label">
      <div v-for="group in shown" :key="group.title" class="picker-group">
        <div class="picker-group-title caps">{{ group.title }}</div>
        <button
          v-for="option in group.options"
          :key="option.value"
          type="button"
          class="picker-option"
          role="option"
          :title="option.title ?? option.label"
          @click="pick(option)"
          @keydown.down.prevent="step($event, 1)"
          @keydown.up.prevent="step($event, -1)"
          @keydown.esc="open = false"
        >
          <span v-if="option.icons.length > 1" class="icons">
            <StatusIcon
              v-for="icon in option.icons"
              :key="icon.label"
              :url="icon.url"
              :label="icon.label"
              size="small"
            />
          </span>
          <StatusIcon
            v-else-if="option.icons[0]"
            :url="option.icons[0].url"
            :label="option.icons[0].label"
            size="small"
          />
          <span>
            {{ option.label }}
            <small v-if="option.note" class="muted">{{ option.note }}</small>
          </span>
        </button>
      </div>
      <p v-if="!flat.length" class="picker-empty muted">Nothing matches</p>
    </div>
  </div>
</template>
