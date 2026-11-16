<script setup lang="ts">
// Pieces the clean-up drops, a row each: the piece and its scores, its group (red when over its
// quota), and Keep, which protects it at once. With `ticked`, a first column ticks pieces for the
// sale (`tick` says which and how).
import { save } from "../composables/save";
import { checkedOf } from "../composables/format";
import type { AccessoryRow, DropRow } from "../types/generated/webui.service.accessories";
import AccessoryCells from "./AccessoryCells.vue";
import ScoreHeads from "./ScoreHeads.vue";

defineProps<{ rows: DropRow[]; ticked?: Set<number> }>();
const emit = defineEmits<{ tick: [id: number, on: boolean] }>();

function protect(row: AccessoryRow, on: boolean) {
  save(`/accessories/${row.piece.id}/protect`, on ? { on: "1" } : {});
}
</script>

<template>
  <div class="table-well">
    <table>
      <thead>
        <tr>
          <th v-if="ticked"></th>
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
        <tr v-for="drop in rows" :key="drop.row.piece.id">
          <td v-if="ticked">
            <input
              type="checkbox"
              :checked="ticked.has(drop.row.piece.id)"
              :aria-label="`Sell ${drop.row.piece.set_name} ${drop.row.piece.slot}`"
              @change="emit('tick', drop.row.piece.id, checkedOf($event))"
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
                @change="protect(drop.row, checkedOf($event))"
              />
              Keep
            </label>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
