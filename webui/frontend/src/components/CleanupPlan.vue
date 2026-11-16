<script setup lang="ts">
// The clean-up: the inventory and mailbox in figures, the spaces to leave free, what each set
// loses, then the pieces to sell (ticked ones selected in the game's sell screen; the user
// confirms the sale there) and those to leave in the mailbox. Keep protects a piece.
import { Link } from "@inertiajs/vue3";
import { computed, ref, watch } from "vue";
import { save } from "../composables/save";
import { sendToGame } from "../composables/send";
import type { AccessoryRow, CleanupView } from "../types/generated/webui.service.accessories";
import AccessoryCells from "./AccessoryCells.vue";
import ScoreHeads from "./ScoreHeads.vue";

const props = defineProps<{ plan: CleanupView }>();

const targetFree = ref(String(props.plan.target_free));
const ticked = ref<Set<number>>(new Set());
const selling = ref(false);
const sold = ref<{ error: string | null } | null>(null);

function tickAll() {
  ticked.value = new Set(props.plan.to_sell.map((drop) => drop.row.piece.id));
}

tickAll();
watch(
  () => props.plan,
  (plan) => {
    targetFree.value = String(plan.target_free);
    tickAll();
  },
);

const all = computed(() => ticked.value.size === props.plan.to_sell.length);

function tick(id: number, on: boolean) {
  const next = new Set(ticked.value);
  if (on) next.add(id);
  else next.delete(id);
  ticked.value = next;
}

function protect(row: AccessoryRow, on: boolean) {
  save(`/accessories/${row.piece.id}/protect`, on ? { on: "1" } : {});
}

async function sell() {
  if (
    !confirm(
      "Select the ticked pieces in the game's sell screen? Nothing is sold until you confirm there.",
    )
  )
    return;
  const fields = new URLSearchParams();
  for (const id of ticked.value) fields.append("artifact_id", String(id));
  selling.value = true;
  sold.value = await sendToGame("/accessories/sell", fields);
  selling.value = false;
}

const freeNote = computed(() =>
  props.plan.short
    ? `${props.plan.short} short: the rest are kept by rule`
    : `${props.plan.worn} worn, never moved`,
);
const sellNote = computed(() => {
  const after = props.plan.sold_after_swaps ? `+${props.plan.sold_after_swaps} after swaps · ` : "";
  return `${after}${props.plan.kept} loose kept`;
});
const keptByRule = computed(() =>
  Object.entries(props.plan.keep_reasons)
    .map(([reason, count]) => `${reason} ${count}`)
    .join(", "),
);
</script>

<template>
  <div class="stack" style="--space: var(--space-l)">
    <div class="grid" style="--min: 9rem; --space: var(--space-m)">
      <article
        v-for="[label, figure, note, tone] in [
          ['Inventory', plan.inventory, `of ${plan.space} spaces`, ''],
          [
            'Mailbox',
            plan.mailbox,
            `claim ${plan.to_claim}, leave ${plan.leave_unclaimed.length}`,
            '',
          ],
          ['To sell', plan.to_sell.length, sellNote, 'down'],
          [
            'Free after',
            plan.free_after,
            freeNote,
            plan.free_after >= plan.target_free ? 'up' : 'down',
          ],
        ]"
        :key="label"
        class="stack"
        style="--space: var(--space-3xs)"
      >
        <small class="caps">{{ label }}</small>
        <strong class="figure" :class="tone">{{ figure }}</strong>
        <small class="note">{{ note }}</small>
      </article>
    </div>

    <form
      class="panel cluster"
      style="--space: var(--space-s) var(--space-2xl)"
      @submit.prevent="save('/accessories/target', { target_free: targetFree })"
    >
      <label class="inline">
        Leave
        <input
          v-model="targetFree"
          type="number"
          class="small"
          min="0"
          max="2200"
          step="10"
          @change="save('/accessories/target', { target_free: targetFree })"
        />
        spaces free
      </label>
      <small class="note">Kept by rule: {{ keptByRule }}</small>
    </form>

    <details>
      <summary>By set</summary>
      <div class="table-well">
        <table>
          <thead>
            <tr>
              <th>Set</th>
              <th>Role</th>
              <th class="num">Loose</th>
              <th class="num">Sell</th>
              <th class="num">Leave in mailbox</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in plan.sets" :key="row.set_name">
              <td>{{ row.set_name }}</td>
              <td>{{ row.role }}</td>
              <td class="num">{{ row.loose }}</td>
              <td class="num">{{ row.to_sell }}</td>
              <td class="num">{{ row.leave_unclaimed }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>

    <p v-if="plan.swaps" class="note">
      Planned with the {{ plan.swaps }} <Link href="/accessories?tab=swaps">swaps</Link> done:
      {{ plan.sold_after_swaps }} of the pieces coming off
      {{ plan.sold_after_swaps === 1 ? "is" : "are" }} sold too, once
      {{ plan.sold_after_swaps === 1 ? "it's" : "they're" }} off and the next sync has
      {{ plan.sold_after_swaps === 1 ? "it" : "them" }} in the inventory.
    </p>

    <h2>To sell</h2>
    <form
      v-if="plan.to_sell.length"
      class="stack"
      style="--space: var(--space-m)"
      @submit.prevent="sell"
    >
      <div class="cluster" style="--space: var(--space-l)">
        <button type="submit" class="cta danger" :disabled="selling || !ticked.size">
          Select {{ ticked.size }} in game
        </button>
        <label class="inline">
          <input
            type="checkbox"
            :checked="all"
            @change="($event.target as HTMLInputElement).checked ? tickAll() : (ticked = new Set())"
          />
          All
        </label>
        <small v-if="sold?.error" class="down">Failed: {{ sold.error }}</small>
        <small v-else-if="sold" class="up">
          Selected in game: check them and confirm the sale there.
        </small>
      </div>
      <div class="table-well">
        <table>
          <thead>
            <tr>
              <th></th>
              <th></th>
              <th>Piece</th>
              <th>Main</th>
              <th>Substats</th>
              <ScoreHeads />
              <th>Group</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="drop in plan.to_sell" :key="drop.row.piece.id">
              <td>
                <input
                  type="checkbox"
                  :checked="ticked.has(drop.row.piece.id)"
                  :aria-label="`Sell ${drop.row.piece.set_name} ${drop.row.piece.slot}`"
                  @change="tick(drop.row.piece.id, ($event.target as HTMLInputElement).checked)"
                />
              </td>
              <AccessoryCells :row="drop.row" scores />
              <td class="nowrap">
                <small :class="{ down: drop.surplus }">{{ drop.group }}</small>
              </td>
              <td>
                <label class="inline" title="Never drop this piece">
                  <input
                    type="checkbox"
                    :checked="drop.row.protected"
                    @change="protect(drop.row, ($event.target as HTMLInputElement).checked)"
                  />
                  Keep
                </label>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </form>
    <p v-else>Nothing to sell.</p>

    <h2>Leave in the mailbox</h2>
    <template v-if="plan.leave_unclaimed.length">
      <p class="note">
        Not worth a space: claim everything else in the mailbox once the sale is done.
      </p>
      <div class="table-well">
        <table>
          <thead>
            <tr>
              <th></th>
              <th>Piece</th>
              <th>Main</th>
              <th>Substats</th>
              <ScoreHeads />
              <th>Group</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="drop in plan.leave_unclaimed" :key="drop.row.piece.id">
              <AccessoryCells :row="drop.row" scores />
              <td class="nowrap">
                <small :class="{ down: drop.surplus }">{{ drop.group }}</small>
              </td>
              <td>
                <label class="inline" title="Never drop this piece">
                  <input
                    type="checkbox"
                    :checked="drop.row.protected"
                    @change="protect(drop.row, ($event.target as HTMLInputElement).checked)"
                  />
                  Keep
                </label>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
    <p v-else>Claim the whole mailbox.</p>
  </div>
</template>
