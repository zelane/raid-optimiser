<script setup lang="ts">
// A saved team picker: a button naming the team picked over a dropdown of teams, each its
// name over its champions' tiles. Only the teams saved in `list`
// (the saved-team list the opponent's team screen offers) unless "Show all" is on: then every
// list, the opponent's first. Arrow keys move between the teams; Escape closes.
import { computed, nextTick, ref } from "vue";
import type { TeamOption } from "../types/generated/webui.service.sims";
import ChampionTile from "./ChampionTile.vue";

const props = defineProps<{ teams: TeamOption[]; list: string }>();
const team = defineModel<string>({ required: true });

const id = `teams-${Math.random().toString(36).slice(2)}`;
const root = ref<HTMLElement>();
const open = ref(false);
const showAll = ref(false);

const chosen = computed(() => props.teams.find((option) => String(option.id) === team.value));

// The teams by list, the opponent's first; only its own unless all are shown.
const groups = computed(() => {
  const byList = new Map<string, TeamOption[]>([[props.list, []]]);
  for (const option of props.teams)
    if (showAll.value || option.area === props.list)
      byList.set(option.area, [...(byList.get(option.area) ?? []), option]);
  return [...byList.entries()].filter(([, options]) => options.length);
});

function pick(option: TeamOption) {
  team.value = String(option.id);
  open.value = false;
  root.value?.querySelector<HTMLButtonElement>(".team-button")?.focus();
}

function options() {
  return [...(root.value?.querySelectorAll<HTMLButtonElement>(".team-option") ?? [])];
}

async function openList() {
  open.value = true;
  await nextTick();
  (options().find((o) => o.getAttribute("aria-selected") === "true") ?? options()[0])?.focus();
}

function step(event: KeyboardEvent, by: number) {
  const all = options();
  all[all.indexOf(event.target as HTMLButtonElement) + by]?.focus();
}

function leave(event: FocusEvent) {
  if (!root.value?.contains(event.relatedTarget as Node)) open.value = false;
}
</script>

<template>
  <div ref="root" class="team-picker" @focusout="leave" @keydown.esc="open = false">
    <button
      type="button"
      class="team-button"
      aria-haspopup="listbox"
      :aria-expanded="open"
      :aria-controls="id"
      @click="open ? (open = false) : openList()"
      @keydown.down.prevent="openList"
    >
      <span v-if="chosen" class="team-name">{{ chosen.name }}</span>
      <span v-else class="muted">Pick a team…</span>
      <span class="chevron" aria-hidden="true">▾</span>
    </button>

    <div v-show="open" :id="id" class="team-list">
      <label class="show-all">
        <input v-model="showAll" type="checkbox" role="switch" />
        <span>Show all saved teams</span>
      </label>
      <div role="listbox" aria-label="Saved teams">
        <div v-for="[list, members] in groups" :key="list" role="group" :aria-label="list">
          <div class="team-group caps">
            {{ list === props.list ? `${list} · this stage's` : list }}
          </div>
          <button
            v-for="option in members"
            :key="option.id"
            type="button"
            class="team-option"
            role="option"
            :aria-selected="String(option.id) === team"
            @click="pick(option)"
            @keydown.down.prevent="step($event, 1)"
            @keydown.up.prevent="step($event, -1)"
          >
            <span class="team">
              <span class="team-name">{{ option.name }}</span>
              <span class="team-tiles">
                <ChampionTile
                  v-for="slot in option.slots"
                  :key="slot.champion.id"
                  :champion="slot.champion"
                />
              </span>
            </span>
          </button>
        </div>
      </div>
      <p v-if="!groups.length" class="team-empty muted">
        No teams saved for {{ list }}: show all to pick another.
      </p>
    </div>
  </div>
</template>

<style scoped>
/* A saved team picker: the picked team's button over a dropdown of teams, each its name over
   its champions' tiles. */
.team-picker {
  position: relative;
  inline-size: min(32rem, calc(100vw - 4rem));
}

/* The button and the options are buttons: the button look is undone, then their own. */
.team-button {
  &,
  &:is(:hover, :active, :focus) {
    display: flex;
    gap: var(--space-s);
    align-items: center;
    width: 100%;
    margin: 0;
    padding: var(--space-2xs) var(--space-s);
    border: 1px solid var(--outline-variant);
    border-radius: var(--radius);
    font-weight: 400;
    color: var(--on-surface);
    text-align: left;
    background: var(--surface-container-lowest);
    box-shadow: none;
  }

  &:hover {
    border-color: var(--outline);
  }

  &[aria-expanded="true"] {
    border-color: var(--primary);
  }
}

.chevron {
  margin-inline-start: auto;
  color: var(--on-surface-variant);
}

.team-name {
  font-weight: 600;
}

.team {
  display: grid;
  gap: var(--space-2xs);
}

.team-tiles {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
}

/* Tiles a size down from the collection's: ChampionTile sets its own width. */
.team-tiles :deep(.tile) {
  --tile-width: 3.75rem;
}

.team-list {
  position: absolute;
  z-index: 20;
  inset-inline: 0;
  top: calc(100% + var(--space-2xs));
  overflow-y: auto;
  max-height: 26rem;
  padding: var(--space-xs);
  border: 1px solid var(--outline-variant);
  border-radius: var(--radius-l);
  color: var(--on-surface);
  background: var(--surface-container-low);
}

.show-all {
  display: flex;
  gap: var(--space-xs);
  align-items: center;
  padding: var(--space-2xs) var(--space-s) var(--space-xs);
  border-bottom: 1px solid var(--outline-variant);
  font-size: var(--text-s);
}

.team-group {
  padding: var(--space-s) var(--space-s) var(--space-2xs);
  font-size: var(--text-2xs);
}

.team-option {
  &,
  &:is(:hover, :active, :focus) {
    display: flex;
    gap: var(--space-s);
    align-items: center;
    width: 100%;
    margin: 0;
    padding: var(--space-xs) var(--space-s);
    border: 0;
    border-radius: var(--radius);
    font-size: var(--text-s);
    font-weight: 400;
    line-height: 1.3;
    color: inherit;
    text-align: left;
    background: none;
    box-shadow: none;
  }

  &:is(:hover, :focus-visible) {
    background: var(--surface-container-lowest);
    outline: none;
  }

  &[aria-selected="true"] {
    background: var(--surface-container-high);
  }
}

.team-empty {
  margin: 0;
  padding: var(--space-s);
}
</style>
