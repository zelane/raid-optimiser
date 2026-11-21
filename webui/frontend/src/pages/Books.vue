<script setup lang="ts">
// The skill books page: the champions the filter bar leaves (6★ Legendaries to start with) whose
// skills aren't all booked. The ones a single book from done first, then the rest by fewest books
// short; each card names its skills by where they sit (A1, A2 …, P1, P2 …) with the upgrades their
// books still owe on a line apiece, a mythical's two forms booked apart so those get a block each.
import { Head, router } from "@inertiajs/vue3";
import { computed, ref } from "vue";
import ChampionCard from "../components/ChampionCard.vue";
import ChampionFilters, { watchFilters, type Filters } from "../components/ChampionFilters.vue";
import PageHead from "../components/PageHead.vue";
import Tally from "../components/Tally.vue";
import type { BooksPage } from "../types/generated/webui.service.books";

const { page } = defineProps<{ page: BooksPage }>();
const filters = ref<Filters>({
  q: page.query.text,
  rarity: page.query.rarity ?? "",
  faction: page.query.faction ?? "",
  grade: page.query.min_grade ? String(page.query.min_grade) : "",
});
// Read through `computed`: a filter change reloads the page's props without remounting it.
const stars = computed(() => {
  const grade = page.query.min_grade;

  return grade === 6 ? "6★" : grade ? `${grade}★ and up` : "any stars";
});
const short = computed(() => page.single.length + page.to_book.length);
const sections = computed(() => [
  {
    key: "single",
    title: "One book away",
    items: page.single,
    lede: "One skill, one book from its top: spend it and they're fully booked.",
    empty: "None with only one book left.",
  },
  {
    key: "to_book",
    title: "Still to book",
    items: page.to_book,
    lede: "The fewest books short first, then as many as each still wants.",
    empty: "None: every champion the filters leave is fully booked.",
  },
]);

watchFilters(filters, search, null);

// The filters ride in the URL. Rarity and stars always go, "any" included: the page starts on
// Legendary 6★, so a URL without either means nobody has chosen it yet (`forms.books.ANY`).
function search() {
  const wanted: Record<string, string> = {
    rarity: filters.value.rarity || "any",
    grade: filters.value.grade || "any",
  };

  for (const [name, value] of Object.entries(filters.value)) {
    if (value) wanted[name] = value;
  }

  router.get("/books", wanted, { only: ["page"], preserveScroll: true, replace: true });
}
</script>

<template>
  <Head title="Skill books" />
  <div class="stack">
    <PageHead title="Skill books">
      <template #lede>
        Champions {{ stars }} with a skill below its top, as the game held them at the last sync. A
        skill's top is one past how many books the game defines for it, so a passive with none is
        already there; each champion takes their affinity's books, and a mythical's two forms each
        take their own.
      </template>
      <template #aside>
        <Tally
          :count="short"
          :total="page.matching"
          :label="
            page.query.min_grade
              ? `${page.query.min_grade}★ champions to book`
              : 'champions to book'
          "
          title="Short of every skill at its top, in any form"
        />
      </template>
    </PageHead>

    <ChampionFilters v-model="filters" :choices="page.choices" />

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
          <div class="stack" style="--space: var(--space-s)">
            <div
              v-for="form in item.short_forms"
              :key="form.form"
              class="stack"
              style="--space: var(--space-xs)"
            >
              <small v-if="form.forms > 1" class="caps">Form {{ form.form }}</small>

              <div
                v-for="skill in form.skills"
                :key="skill.slot"
                class="stack"
                style="--align: start; --space: var(--space-3xs)"
              >
                <span
                  class="badge"
                  :class="skill.top - skill.level > 1 ? 'bad' : 'mid'"
                  :title="`${skill.name}: level ${skill.level} of ${skill.top}`"
                >
                  {{ skill.slot }} {{ skill.level }}/{{ skill.top }}
                </span>
                <small v-for="gain in skill.gains" :key="gain" class="note">{{ gain }}</small>
              </div>
            </div>
          </div>
        </ChampionCard>
      </div>
      <p v-else>{{ section.empty }}</p>
    </section>
  </div>
</template>

<style scoped>
/* What a skill still owes hangs under its badge. */
.note {
  padding-inline-start: var(--space-s);
}
</style>
