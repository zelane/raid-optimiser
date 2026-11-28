<script setup lang="ts">
// The team a sim fights with: as many slots as the stage takes (`size`: Hydra 6, arena 4 …), each a champion's tile with Swap and × (an empty one
// adds) and their skill settings' dropdown under it, the champion finder picking who goes in. A champion swapped in comes with their skills
// and auto's defaults for each of the stage's `waves` (`/sims/slot`); one already in the team
// changes places instead.
import { ref } from "vue";
import { getJson } from "../composables/send";
import type { ListedChampion } from "../types/generated/webui.service.finder";
import type { SlotView } from "../types/generated/webui.service.sims";
import ChampionFinder from "./ChampionFinder.vue";
import ChampionTile from "./ChampionTile.vue";
import SkillPriorities from "./SkillPriorities.vue";

const props = defineProps<{ waves: number; size: number }>();
const slots = defineModel<SlotView[]>({ required: true });

const finder = ref<InstanceType<typeof ChampionFinder>>();
const editing = ref(0);
const busy = ref(false);

function choose(index: number) {
  editing.value = index;
  finder.value?.open();
}

function replace(index: number, slot: SlotView) {
  slots.value = slots.value.map((each, i) => (i === index ? slot : each));
}

function remove(index: number) {
  slots.value = slots.value.filter((_, i) => i !== index);
}

async function picked(listed: ListedChampion) {
  const index = editing.value;
  const already = slots.value.findIndex((slot) => slot.champion.id === listed.champion.id);
  const next = [...slots.value];

  if (already >= 0) {
    if (index < next.length) [next[index], next[already]] = [next[already]!, next[index]!];
    slots.value = next;
    return;
  }

  busy.value = true;
  try {
    const slot = await getJson<SlotView>(
      `/sims/slot?champion=${listed.champion.id}&waves=${props.waves}`,
    );
    if (!slot) return;
    next.splice(index, 1, slot);
    slots.value = next;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="team-slots" :class="{ busy }">
    <div v-for="(slot, index) in slots" :key="slot.champion.id" class="team-slot stack">
      <ChampionTile :champion="slot.champion" />
      <span class="slot-name" :title="slot.champion.name">{{ slot.champion.name }}</span>
      <div class="cluster" style="--space: var(--space-3xs); --justify: center">
        <button type="button" class="small quiet" @click="choose(index)">Swap</button>
        <button
          type="button"
          class="icon"
          :aria-label="`Take ${slot.champion.name} out`"
          @click="remove(index)"
        >
          ×
        </button>
      </div>
      <SkillPriorities
        :model-value="slot"
        :end="index >= 3"
        @update:model-value="(edited) => replace(index, edited)"
      />
    </div>
    <button
      v-for="index in Math.max(0, size - slots.length)"
      :key="`empty-${index}`"
      type="button"
      class="team-slot empty-slot dashed"
      @click="choose(slots.length)"
    >
      + Add
    </button>
    <ChampionFinder ref="finder" @picked="picked" />
  </div>
</template>

<style scoped>
/* Five slots in a row (wrapping on narrow screens): a tile, the name, its buttons. */
.team-slots {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-m);

  &.busy {
    opacity: 0.6;
  }
}

.team-slot {
  --space: var(--space-2xs);

  align-items: center;
  inline-size: 6.5rem;
}

.slot-name {
  overflow: hidden;
  max-inline-size: 100%;
  font-size: var(--text-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-slot {
  justify-content: center;
  min-block-size: 8rem;
}
</style>
