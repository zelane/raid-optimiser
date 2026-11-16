<script setup lang="ts">
// The champion's runs as cards, newest first: when, what it found, what was asked and the gear
// it left out. Picking one shows it (and its form) in place; `current` is the one shown.
import { router } from "@inertiajs/vue3";
import type { RunEntryView } from "../types/generated/webui.service.runs";

const props = defineProps<{ history: RunEntryView[]; championId: number; current?: number }>();

function show(id: number) {
  router.get(
    `/champions/${props.championId}`,
    { run: id },
    { only: ["run", "picker"], preserveState: true, preserveScroll: true },
  );
}

function forget(id: number) {
  router.delete(`/champions/${props.championId}/runs/${id}`, {
    only: ["page", "run", "picker"],
    preserveState: true,
    preserveScroll: true,
  });
}
</script>

<template>
  <section class="panel">
    <header class="panel-head">
      <h2>History</h2>
      <small class="caps">{{ history.length }} run{{ history.length !== 1 ? "s" : "" }}</small>
    </header>
    <ul v-if="history.length" class="history stack" style="--space: var(--space-s)">
      <li v-for="entry in history" :key="entry.id" :class="{ current: entry.id === current }">
        <a
          class="run-link stack"
          style="--space: var(--space-2xs)"
          :href="`/champions/${championId}?run=${entry.id}`"
          @click.prevent="show(entry.id)"
        >
          <span class="run-meta">
            <time>{{ entry.ran_at }}</time>
            <span class="badge" :class="{ bad: !entry.found }">{{ entry.note }}</span>
          </span>
          <strong class="run-summary">{{ entry.summary }}</strong>
          <small v-if="entry.gear" class="note">{{ entry.gear }}</small>
        </a>
        <button
          class="icon"
          title="Delete this run"
          aria-label="Delete this run"
          @click="forget(entry.id)"
        >
          ✕
        </button>
      </li>
    </ul>
    <p v-else class="note">No runs yet: what you solve for is kept here.</p>
  </section>
</template>
