<script setup lang="ts">
// The masteries page: the 6★ champions without a last-row mastery (Helmsmasher's row), those
// holding the scrolls to reach it, then those still to farm for (the fewest Divine short first),
// each with every kind of scroll they've had (held and spent) against what reaching it takes.
import { Head } from "@inertiajs/vue3";
import { computed } from "vue";
import ChampionCard from "../components/ChampionCard.vue";
import PageHead from "../components/PageHead.vue";
import Tally from "../components/Tally.vue";
import { plural } from "../composables/format";
import type { MasteriesPage } from "../types/generated/webui.service.masteries";

const { page } = defineProps<{ page: MasteriesPage }>();
// Read through `computed`: a sync reloads the page's props without remounting it.
const sections = computed(() => [
  {
    key: "ready",
    title: "Enough to unlock",
    items: page.ready,
    lede: "They hold the scrolls for the rest of a tree, last row included: spend them in game.",
    empty: "None yet.",
  },
  {
    key: "farming",
    title: "Still to farm",
    items: page.farming,
    lede: "Those fewest Divine scrolls short first, then Advanced, then Basic.",
    empty: "None: every champion short of the last row holds enough for it.",
  },
]);
</script>

<template>
  <Head title="Masteries" />
  <PageHead title="Masteries">
    <template #lede>
      6★ champions without a mastery in a tree's last row (Warmaster, Helmsmasher, Giant Slayer, …),
      as the game held them at the last sync. Each kind of scroll shows what they've had, held and
      spent, against what reaching the last row takes from their furthest row: 550 Divine with one
      row 5 mastery.
    </template>
    <template #aside>
      <Tally
        :count="page.farming.length"
        :total="page.top_grade"
        label="6★ champions to farm for"
        title="Short of the scrolls for a last-row mastery"
      />
    </template>
  </PageHead>

  <section v-for="section in sections" :key="section.key" class="stack">
    <h2>{{ section.title }} ({{ section.items.length }})</h2>
    <p class="lede">{{ section.lede }}</p>
    <div v-if="section.items.length" class="champion-grid">
      <ChampionCard
        v-for="item in section.items"
        :key="item.champion.id"
        :champion="item.champion"
        banner
        card
      >
        <div class="cluster" style="--space: var(--space-2xs)">
          <span
            v-for="count in item.scrolls"
            :key="count.kind"
            class="badge"
            :class="count.short ? 'bad' : 'good'"
            :title="
              count.short ? `${count.short} ${count.kind} scrolls to farm` : `Enough ${count.kind}`
            "
          >
            {{ count.have }}/{{ count.need }} {{ count.kind }}
          </span>
        </div>
        <small class="note">
          <template v-if="item.row">
            row {{ item.row }} of {{ page.last_row }} ·
            {{ plural(item.count, "mastery", "masteries") }}
          </template>
          <template v-else>no masteries</template>
        </small>
      </ChampionCard>
    </div>
    <p v-else>{{ section.empty }}</p>
  </section>
</template>
