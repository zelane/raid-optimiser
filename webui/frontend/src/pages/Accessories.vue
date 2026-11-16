<script setup lang="ts">
// Accessories, in the workflow's order: swaps, rolling, reworking, the clean-up, then the
// weights the scores come from. The steps are the page's own tabs, each with what it holds.
import { Head, Link, router } from "@inertiajs/vue3";
import { computed, ref } from "vue";
import CandidateTable from "../components/CandidateTable.vue";
import ChampionCard from "../components/ChampionCard.vue";
import CleanupPlan from "../components/CleanupPlan.vue";
import GearCard from "../components/GearCard.vue";
import PageHead from "../components/PageHead.vue";
import SetFits from "../components/SetFits.vue";
import TypeCard from "../components/TypeCard.vue";
import { sendToGame } from "../composables/send";
import { usePageSubnav } from "../composables/subnav";
import type { AccessoriesPage, SwapGroup } from "../types/generated/webui.service.accessories";

const props = defineProps<{ page: AccessoriesPage }>();
usePageSubnav();

// The steps, each with what it holds (the enhance lists stop at `shown`: a full one may hold
// more, "+").
const steps = computed(() => {
  const { swaps, enhance, cleanup } = props.page;
  const full = (list: unknown[]) => list.length >= enhance.shown;
  const rollMore = full(enhance.roll) || full(enhance.finish) ? "+" : "";
  return [
    {
      key: "swaps",
      label: "1. Swaps",
      count: `${swaps.flatMap((group) => group.swaps).length}`,
      what: "ready",
      tone: "",
    },
    {
      key: "roll",
      label: "2. Roll",
      count: `${enhance.roll.length + enhance.finish.length}${rollMore}`,
      what: "to roll",
      tone: "",
    },
    {
      key: "rework",
      label: "3. Rework",
      count: `${enhance.rework.length}${full(enhance.rework) ? "+" : ""}`,
      what: "to rework",
      tone: "",
    },
    {
      key: "cleanup",
      label: "4. Clean up",
      count: `${cleanup.to_sell.length}`,
      what: "to sell",
      tone: "bad",
    },
    { key: "weights", label: "Weights", count: null, what: "", tone: "" },
  ];
});

// Swaps: each champion's swaps equipped together.
const equipping = ref<number | null>(null);
const equipped = ref<Record<number, string | null>>({});

async function equip(group: SwapGroup) {
  const count = group.swaps.length;
  if (!confirm(`Equip ${count} piece${count > 1 ? "s" : ""} on ${group.champion.name}?`)) return;
  equipping.value = group.champion.id;
  const sent = await sendToGame(`/champions/${group.champion.id}/equip`, {
    artifact_ids: group.artifact_ids,
  });
  equipping.value = null;
  equipped.value = { ...equipped.value, [group.champion.id]: sent.error };
  if (!sent.error) router.reload();
}

// Weights: the types filtered in the page (by name or champion, faction, kind).
const filter = ref({ text: "", faction: "", kind: "" });
const weights = computed(() => props.page.weights);
const shownTypes = computed(() => {
  const text = filter.value.text.trim().toLowerCase();
  return weights.value.rows.filter(
    (row) =>
      `${row.label} ${row.champions.join(" ")}`.toLowerCase().includes(text) &&
      (!filter.value.faction || !row.faction || row.faction === filter.value.faction) &&
      (!filter.value.kind || row.kind === filter.value.kind),
  );
});

const typeSaved = ref<string | null | undefined>(undefined);
const setSaved = ref<string | null | undefined>(undefined);

function addType() {
  router.post("/accessories/types/add");
}
</script>

<template>
  <Head title="Accessories" />
  <Teleport defer to="#page-subnav">
    <nav class="container tabs" aria-label="Steps">
      <ul>
        <li v-for="step in steps" :key="step.key">
          <Link
            :href="`/accessories?tab=${step.key}`"
            :aria-current="page.tab === step.key ? 'page' : undefined"
          >
            {{ step.label }}
            <span
              v-if="step.count !== null"
              class="badge"
              :class="step.tone"
              :title="`${step.count} ${step.what}`"
            >
              {{ step.count }}
            </span>
          </Link>
        </li>
      </ul>
    </nav>
  </Teleport>

  <PageHead title="Accessories" />

  <template v-if="page.tab === 'swaps'">
    <p class="lede">
      Champions wearing an accessory that a loose one clearly beats as it is now (by 10% or more;
      not counting what rolling or a rework might make of it), of the same slot, main stat, set and
      faction, so the set bonus and main stat stay. A set-less piece gives way to any set piece of
      its slot, main stat and faction with better stats, however slightly. Only unlocked champions:
      lock a champion to leave their gear alone. Substats change, so mind speed tunes and ACC/RES
      thresholds. Equip, then roll, then clean up: the clean-up already counts these as done, and
      sells what comes off where it's not worth keeping.
    </p>
    <!-- A row per champion: who; the swaps, each the piece to equip beside the one it
         replaces; the gain and Equip. -->
    <div v-if="page.swaps.length" class="stack">
      <article v-for="group in page.swaps" :key="group.champion.id" class="swap-group">
        <ChampionCard :champion="group.champion" banner />
        <div class="stack">
          <div v-for="swap in group.swaps" :key="swap.better.piece.id" class="gear-pair">
            <GearCard
              :row="swap.better"
              :champion="group.champion"
              kind="candidate"
              :label="`Equip · ${swap.better.where === 'mailbox' ? 'in mailbox' : 'loose'}`"
              :note="swap.gain"
              note-tone="up"
            />
            <span class="gear-pair-arrow" aria-hidden="true">›</span>
            <GearCard
              :row="swap.worn"
              :champion="group.champion"
              kind="worn"
              label="In place of"
              :note="swap.then_sell ? 'then sell' : ''"
              note-tone="down"
            />
          </div>
        </div>
        <div class="stack" style="--space: var(--space-s); --align: flex-end">
          <span class="caps">Net gain</span>
          <strong class="figure up">{{ group.gain }}</strong>
          <div class="cluster" style="--justify: flex-end">
            <span class="swap-result">
              <small v-if="equipped[group.champion.id]" class="down">
                Failed: {{ equipped[group.champion.id] }}
              </small>
              <small v-else-if="group.champion.id in equipped" class="up"
                >Equipped and synced.</small
              >
            </span>
            <button type="button" class="cta" :disabled="equipping !== null" @click="equip(group)">
              Equip{{ group.swaps.length > 1 ? " all" : "" }}
            </button>
          </div>
        </div>
      </article>
    </div>
    <p v-else>No champion wears a piece with a clearly better spare.</p>
  </template>

  <template v-else-if="page.tab === 'cleanup'">
    <p class="lede">
      The inventory and the mailbox's overflow are planned together: the lowest-valued pieces go
      until {{ page.cleanup.target_free }} spaces are left. Dropped inventory pieces are sold,
      dropped mailbox pieces left unclaimed, the rest of the mailbox claimed. Worn pieces never go.
      A piece's value is the better of its potential at +16 and after a rework (75th percentile of
      how it can turn out, scored for the champion types its set is worn by), times its shortage
      factor: ×1.15 when its set, faction and slot have no good piece, down to ×0.9 with three or
      more.
    </p>
    <CleanupPlan :plan="page.cleanup" />
  </template>

  <template v-else-if="page.tab === 'roll'">
    <p class="lede">
      What to level during an enhancement event, best first: +12 is cheap and shows most of a piece,
      so pieces below it rank by their value at +12. Only pieces already good once at +16 on their
      own rolls are listed for +16. Pieces the clean-up drops aren't listed.
    </p>
    <div class="stack" style="--space: var(--space-xl)">
      <h2 class="section-title">To +12</h2>
      <CandidateTable :rows="page.enhance.roll" after-label="at +12" :shown="page.enhance.shown" />
      <h2 class="section-title">To +16</h2>
      <CandidateTable
        :rows="page.enhance.finish"
        after-label="at +16"
        :shown="page.enhance.shown"
      />
    </div>
  </template>

  <template v-else-if="page.tab === 'rework'">
    <p class="lede">
      Pieces at +12 or more that haven't been reworked, where a rework looks at least 10% better
      than their own rolls. A rework keeps each line's roll count, the set and the faction, and
      re-picks the main stat and substats, so concentrated rolls in the wrong stats and main stats
      their set has no use for come first. Ranked by the gain, shortage counted.
    </p>
    <CandidateTable
      :rows="page.enhance.rework"
      after-label="reworked"
      :shown="page.enhance.shown"
    />
  </template>

  <template v-else>
    <p class="lede">
      What each champion type values, per stat, in average 6★ rolls (flat and % together), and the
      main stats that suit it. A piece scores as the best type it suits, of any faction or its own:
      accessories are faction-locked, so a faction whose champions scale off more than one stat
      wants a type of its own. Supports that weigh both HP and DEF count the lesser of the two twice
      more. Changes save as you make them.
    </p>
    <section class="page-section">
      <header class="panel-head">
        <h2 class="section-title">Types</h2>
        <button type="button" @click="addType">Add a type</button>
      </header>
      <form class="filter-bar" aria-label="Filter the types" @submit.prevent>
        <input
          v-model="filter.text"
          type="search"
          placeholder="Type or champion"
          aria-label="Type or champion"
          autocomplete="off"
        />
        <select v-model="filter.faction" aria-label="Faction">
          <option value="">Any faction</option>
          <option v-for="choice in weights.factions" :key="choice.value" :value="choice.value">
            {{ choice.label }}
          </option>
        </select>
        <div class="segmented small" role="radiogroup" aria-label="Kind">
          <label>
            <input v-model="filter.kind" type="radio" value="" />All
            <small>{{ weights.rows.length }}</small>
          </label>
          <label v-for="choice in weights.kinds" :key="choice.value">
            <input v-model="filter.kind" type="radio" :value="choice.value" />{{ choice.label }}
            <small>{{ weights.rows.filter((row) => row.kind === choice.value).length }}</small>
          </label>
        </div>
        <span class="filter-count caps">
          {{
            shownTypes.length === weights.rows.length
              ? shownTypes.length
              : `${shownTypes.length} of ${weights.rows.length}`
          }}
          shown
        </span>
      </form>
      <p>
        <small v-if="typeSaved" class="down">Failed: {{ typeSaved }}</small>
        <small v-else-if="typeSaved === null" class="up">Saved: the lists re-plan with it.</small>
      </p>
      <div class="stack" style="--space: var(--space-s)">
        <TypeCard
          v-for="row in shownTypes"
          :key="row.key"
          :row="row"
          :kinds="weights.kinds"
          :factions="weights.factions"
          @saved="(error) => (typeSaved = error)"
        />
      </div>
    </section>

    <h2>Sets</h2>
    <p class="lede">
      A set's value multiplies what its pieces are worth: 1 is an average set. Tick the types each
      set is for. A type a set isn't for still counts, at a share of its score. A set for no damage
      type still keeps a C.DMG amulet. New types and new sets start ticked everywhere.
    </p>
    <SetFits :grid="weights.sets" @saved="(error) => (setSaved = error)">
      <p class="note">
        <small v-if="setSaved" class="down">Failed: {{ setSaved }}</small>
        <small v-else-if="setSaved === null" class="up">Saved: the lists re-plan with it.</small>
      </p>
    </SetFits>
  </template>
</template>

<style scoped>
/* Swaps: a champion to a row, three columns: who, their swaps (one gear pair under another),
   the gain and Equip; who and the gain from the top. One column on narrow screens. */
.swap-group {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-l);
  align-items: start;
}

@container page (min-width: 52rem) {
  .swap-group {
    grid-template-columns: 12rem minmax(0, 1fr) auto;
  }
}
</style>
