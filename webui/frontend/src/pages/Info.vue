<script setup lang="ts">
// The info page: Faction Wars, per crypt the stages still short of their stars.
import { Head } from "@inertiajs/vue3";
import PageHead from "../components/PageHead.vue";
import Stars from "../components/Stars.vue";
import Tally from "../components/Tally.vue";
import type { InfoPage } from "../types/generated/webui.service.info";

const { page } = defineProps<{ page: InfoPage }>();
const fw = page.faction_wars;
const plural = fw.open_stages !== 1 ? "s" : "";

function teamsLink(region: string, stage: number) {
  return `/teams?base=fw&crypt=${region}&difficulty=${fw.difficulty}&stage=${stage}`;
}
</script>

<template>
  <Head title="Faction Wars" />
  <section aria-labelledby="fw-heading">
    <PageHead :title="`Faction Wars ${fw.difficulty}`" id="fw-heading">
      <template #lede>
        As the game held it at the last sync. The game counts each stage's stars but not which
        challenges earned them, so a stage one star short shows both it could be missing: almost
        always its challenge, the last.
      </template>
      <template #aside>
        <Tally
          :count="fw.stars"
          :total="fw.max_stars"
          :label="`stars · ${fw.open_stages} stage${plural} short`"
          title="Stars earned"
        />
      </template>
    </PageHead>

    <div class="crypt-grid">
      <article
        v-for="crypt in fw.crypts"
        :key="crypt.region"
        class="panel stack crypt"
        style="--space: var(--space-m)"
      >
        <div class="cluster" style="--space: var(--space-m)">
          <img v-if="crypt.banner_url" class="faction" :src="crypt.banner_url" alt="" />
          <h3>{{ crypt.name }}</h3>
          <span class="badge push">{{ crypt.stars }}/{{ crypt.max_stars }} stars</span>
        </div>
        <div class="table-well">
          <table>
            <thead>
              <tr>
                <th>Stage</th>
                <th>Stars</th>
                <th>Still to do</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in crypt.rows" :key="row.number">
                <th scope="row">
                  <!-- The team finder is still a Jinja page: a full load, not an Inertia visit. -->
                  <a
                    :href="teamsLink(crypt.region, row.number)"
                    title="Find a team for its challenge"
                  >
                    {{ row.number }}
                  </a>
                </th>
                <td class="crypt-state">
                  <Stars :count="row.stars" :of="3" :title="row.state" />
                  <small v-if="row.state.startsWith('not')" class="muted">{{ row.state }}</small>
                </td>
                <td>
                  <!-- The challenge is almost always the one missing; the rest may be. -->
                  <template v-if="row.one_of">
                    {{ row.open[row.open.length - 1] }}
                    <small class="muted">(or {{ row.open.slice(0, -1).join(", or ") }})</small>
                  </template>
                  <ul v-else>
                    <li v-for="quest in row.open" :key="quest">{{ quest }}</li>
                  </ul>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </div>

    <p v-if="fw.done.length" class="muted">All stars: {{ fw.done.join(", ") }}.</p>
  </section>
</template>

<style scoped>
/* The info page. Faction Wars: a panel per crypt short of its stars, in masonry columns of
   32rem at least, each crypt whole in one (down a column, then across); a row per stage with
   the stars earned. */
.crypt-grid {
  columns: 32rem;
  column-gap: var(--space-xl);
}

.crypt {
  break-inside: avoid;
  margin-bottom: var(--space-xl);

  :is(th, td) {
    vertical-align: top;
  }

  tbody th {
    width: 3.5rem;
    font-weight: 700;
  }

  ul {
    margin: 0;
  }
}

.crypt-state {
  width: 7rem;
  white-space: nowrap;
}
</style>
