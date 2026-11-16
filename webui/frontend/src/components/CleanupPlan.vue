<script setup lang="ts">
// The clean-up: the inventory and mailbox in figures, the spaces to leave free, what each set
// loses, then the pieces to sell (ticked ones selected in the game's sell screen; the user
// confirms the sale there) and those to leave in the mailbox. Keep protects a piece.
import { Link } from "@inertiajs/vue3";
import { computed, ref, watch } from "vue";
import { checkedOf } from "../composables/format";
import { save } from "../composables/save";
import { sendToGame, type Sent } from "../composables/send";
import type { CleanupView } from "../types/generated/webui.service.accessories";
import DropTable from "./DropTable.vue";
import SentNote from "./SentNote.vue";

const props = defineProps<{ plan: CleanupView }>();

const targetFree = ref(String(props.plan.target_free));
const ticked = ref<Set<number>>(new Set());
const selling = ref(false);
const sold = ref<Sent | null>(null);

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
            @change="checkedOf($event) ? tickAll() : (ticked = new Set())"
          />
          All
        </label>
        <SentNote :sent="sold" done="Selected in game: check them and confirm the sale there." />
      </div>
      <DropTable :rows="plan.to_sell" :ticked="ticked" @tick="tick" />
    </form>
    <p v-else>Nothing to sell.</p>

    <h2>Leave in the mailbox</h2>
    <template v-if="plan.leave_unclaimed.length">
      <p class="note">
        Not worth a space: claim everything else in the mailbox once the sale is done.
      </p>
      <DropTable :rows="plan.leave_unclaimed" />
    </template>
    <p v-else>Claim the whole mailbox.</p>
  </div>
</template>
