<script setup lang="ts">
// The empower page, for one rarity: copies safe to feed, champions with fodder, those fully
// empowered and every one left to empower.
import { Head, Link } from "@inertiajs/vue3";
import ChampionCard from "../components/ChampionCard.vue";
import PageHead from "../components/PageHead.vue";
import type { EmpowerPage } from "../types/generated/webui.service.empower";

const { page } = defineProps<{ page: EmpowerPage }>();

function copies(count: number) {
  return `${count} cop${count === 1 ? "y" : "ies"}`;
}
</script>

<template>
  <Head title="Empower" />
  <PageHead title="Empower">
    <template #aside>
      <nav class="page-tabs" aria-label="Rarity">
        <Link
          v-for="rarity in page.rarities"
          :key="rarity"
          :href="`/empower?rarity=${rarity}`"
          :aria-current="page.rarity === rarity ? 'page' : undefined"
        >
          {{ rarity }}
        </Link>
      </nav>
    </template>
  </PageHead>

  <h2>Safe to feed ({{ page.spare.reduce((sum, group) => sum + group.count, 0) }})</h2>
  <p class="lede">
    Spare copies of {{ page.rarity }} champions you already have at +{{ page.max_empower }}, with
    how many there are. Mind any you've levelled, geared or empowered, and any marked as feeding a
    champion you can only get once.
  </p>
  <div v-if="page.spare.length" class="champion-grid">
    <ChampionCard
      v-for="group in page.spare"
      :key="group.copy.id"
      :champion="group.copy"
      banner
      card
    >
      <strong>×{{ group.count }}</strong>
      <small v-if="group.needed_by.length" class="note">
        feeds {{ group.needed_by.join(", ") }}
      </small>
    </ChampionCard>
  </div>
  <p v-else>None: no fully empowered {{ page.rarity }} champion has a second copy.</p>

  <h2>Not fully empowered, with fodder ({{ page.with_fodder.length }})</h2>
  <p class="lede">
    {{ page.rarity }} champions below +{{ page.max_empower }} you can feed: the most empowered copy,
    then the other copies that aren't empowered themselves. A champion you can only get once is
    empowered with copies of another champion instead, shown under its name.
  </p>
  <div
    v-if="page.with_fodder.length"
    class="grid"
    style="--min: 17rem; --space: var(--space-l); --repeat: auto-fill; --align: start"
  >
    <article
      v-for="group in page.with_fodder"
      :key="group.champion.id"
      class="cluster"
      style="--space: var(--space-l); --align: flex-start"
    >
      <ChampionCard :champion="group.champion" banner />
      <div class="stack" style="--space: var(--space-s)">
        <div v-if="group.copies.length" class="cluster">
          <ChampionCard
            v-for="copy in group.copies"
            :key="copy.id"
            :champion="copy"
            size="small"
            :name="false"
          />
        </div>
        <template v-if="group.substitutes.length">
          <small class="note">With {{ group.substitute }}:</small>
          <div class="cluster">
            <ChampionCard
              v-for="copy in group.substitutes"
              :key="copy.id"
              :champion="copy"
              size="small"
              :name="false"
            />
          </div>
        </template>
      </div>
    </article>
  </div>
  <p v-else>None: no {{ page.rarity }} champion below +{{ page.max_empower }} has fodder.</p>

  <details v-if="page.full.length" class="section">
    <summary>
      <h2>Fully empowered ({{ page.full.length }})</h2>
    </summary>
    <div class="champion-grid">
      <ChampionCard
        v-for="champion in page.full"
        :key="champion.id"
        :champion="champion"
        banner
        card
      />
    </div>
  </details>
  <template v-else>
    <h2>Fully empowered (0)</h2>
    <p>No {{ page.rarity }} champion is at +{{ page.max_empower }} yet.</p>
  </template>

  <details v-if="page.left.length" class="section">
    <summary>
      <h2>Left to empower ({{ page.left.length }})</h2>
    </summary>
    <p class="lede">
      Every {{ page.rarity }} champion below +{{ page.max_empower }}, with the copies you have to
      feed them. One you can only get once takes copies of the champion named.
    </p>
    <div class="champion-grid">
      <ChampionCard
        v-for="item in page.left"
        :key="item.champion.id"
        :champion="item.champion"
        banner
        card
      >
        <small class="note">
          <template v-if="item.substitute"
            >with {{ item.substitute }}: {{ item.fodder }} owned</template
          >
          <template v-else-if="item.fodder">{{ copies(item.fodder) }} to feed</template>
          <template v-else>no duplicate</template>
        </small>
      </ChampionCard>
    </div>
  </details>
  <template v-else>
    <h2>Left to empower (0)</h2>
    <p>Every {{ page.rarity }} champion you have is at +{{ page.max_empower }}.</p>
  </template>
</template>
