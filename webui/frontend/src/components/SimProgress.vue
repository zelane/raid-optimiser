<script setup lang="ts">
// How far the sim under way has got, asked of `/sims/progress` every second while it's shown:
// building the team's slots, then a bar of the fights done, the time so far and, from the fights'
// pace, about how long is left, then summing their results up. `finished` once no sim is running (one picked up after a reload
// has no request of the page's to end it).
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { getJson } from "../composables/send";
import type { SimProgress } from "../types/generated/webui.service.sims";

const POLL_MS = 1000;

const emit = defineEmits<{ finished: [] }>();
const progress = ref<SimProgress | null>(null);
const fightingSince = ref<number | null>(null); // the elapsed seconds when the fights began
let timer: number | undefined;
let seenRunning = false; // a Run's first poll may come before the server has started it
let polls = 0;

async function poll() {
  const seen = await getJson<SimProgress>("/sims/progress");
  if (!seen) return;
  polls += 1;
  if (!seen.running) {
    if (!seenRunning && polls < 3) return;
    window.clearInterval(timer);
    emit("finished");
    return;
  }
  seenRunning = true;
  if (seen.fighting && fightingSince.value === null) fightingSince.value = seen.elapsed;
  progress.value = seen;
}

onMounted(() => {
  poll();
  timer = window.setInterval(poll, POLL_MS);
});
onBeforeUnmount(() => window.clearInterval(timer));

const share = computed(() =>
  progress.value?.total ? Math.min(1, progress.value.done / progress.value.total) : 0,
);

// From the pace so far, once a few fights are in.
const left = computed(() => {
  const seen = progress.value;
  if (!seen?.fighting || seen.done < 6 || fightingSince.value === null) return null;
  const perFight = (seen.elapsed - fightingSince.value) / seen.done;
  return perFight * (seen.total - seen.done);
});

function duration(seconds: number): string {
  const whole = Math.round(seconds);
  return whole < 60 ? `${whole} s` : `${Math.floor(whole / 60)} min ${whole % 60} s`;
}
</script>

<template>
  <div class="sim-progress stack" style="--space: var(--space-2xs)" role="status">
    <span
      class="meter"
      :class="{ building: !progress?.fighting || progress.summing }"
      role="progressbar"
      :aria-valuenow="progress?.done ?? 0"
      :aria-valuemax="progress?.total ?? 0"
    >
      <span :style="{ width: `${100 * share}%` }"></span>
    </span>
    <p class="note">
      <template v-if="progress?.summing">
        Summing up the fights · {{ duration(progress.elapsed) }}…
      </template>
      <template v-else-if="progress?.fighting">
        {{ progress.done }} of {{ progress.total }} fights · {{ duration(progress.elapsed) }}
        <template v-if="left !== null"> · about {{ duration(left) }} left</template>
      </template>
      <template v-else>
        Building the team's slots{{ progress ? ` · ${duration(progress.elapsed)}` : "" }}…
      </template>
    </p>
  </div>
</template>

<style scoped>
/* The shared meter, taller; while the team is built, a band sweeping across it. */
.meter {
  height: 0.5rem;

  > span {
    transition: width var(--transition);
  }

  &.building > span {
    width: 30% !important;
    animation: sweep 1.2s ease-in-out infinite alternate;
  }
}

@keyframes sweep {
  from {
    transform: translateX(0);
  }

  to {
    transform: translateX(233%);
  }
}
</style>
