<script setup lang="ts">
// The champion's runs as cards, newest first: when, what it found, what was asked and the gear
// it left out. Picking one shows it (and its form) in place; `current` is the one shown.
import { Link, router } from "@inertiajs/vue3";
import { plural } from "../composables/format";
import type { RunEntryView } from "../types/generated/webui.service.runs";

const props = defineProps<{ history: RunEntryView[]; championId: number; current?: number }>();

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
      <small class="caps">{{ plural(history.length, "run") }}</small>
    </header>
    <ul v-if="history.length" class="history stack" style="--space: var(--space-s)">
      <li v-for="entry in history" :key="entry.id" :class="{ current: entry.id === current }">
        <Link
          class="run-link stack"
          style="--space: var(--space-2xs)"
          :href="`/champions/${championId}?run=${entry.id}`"
          :only="['run', 'picker']"
          preserve-state
          preserve-scroll
        >
          <span class="run-meta">
            <time>{{ entry.ran_at }}</time>
            <span class="badge" :class="{ bad: !entry.found }">{{ entry.note }}</span>
          </span>
          <strong class="run-summary">{{ entry.summary }}</strong>
          <small v-if="entry.gear" class="note">{{ entry.gear }}</small>
        </Link>
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

<style scoped>
/* History: a card a run, newest first; the one the results show has the brass rail. Under the
   champion, it scrolls on its own past a few runs. */
ul.history {
  overflow-y: auto;
  max-height: 22rem;
  margin: 0;
  padding: 0 var(--space-2xs) 0 0;

  li {
    position: relative;
    border: 1px solid var(--outline-variant);
    border-left: 3px solid transparent;
    border-radius: var(--radius);
    list-style: none;
    background: var(--surface-container-lowest);

    &:hover {
      border-color: color-mix(in srgb, var(--secondary) 50%, transparent);
      border-left-color: transparent;
    }

    &.current {
      border-left-color: var(--primary);
      background: color-mix(in srgb, var(--primary) 7%, var(--surface-container-lowest));
    }
  }

  .icon {
    position: absolute;
    top: var(--space-s);
    right: var(--space-xs);
    font-size: var(--text-2xs);
  }
}

.run-link {
  padding: var(--space-s) var(--space-3xl) var(--space-s) var(--space-m);
  color: inherit;
  text-decoration: none;
}

.run-meta {
  display: flex;
  gap: var(--space-s);
  align-items: center;
  justify-content: space-between;

  time {
    font-size: var(--text-2xs);
    font-weight: 700;
    color: var(--on-surface-variant);
    letter-spacing: 0.04em;
  }
}

li.current .run-meta time {
  color: var(--primary);
}

.run-summary {
  font-size: var(--text-s);
  font-weight: 600;
  line-height: 1.35;
}
</style>
