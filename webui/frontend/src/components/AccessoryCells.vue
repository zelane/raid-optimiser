<script setup lang="ts">
// An accessory's cells in the lists: the piece's, marked if it's been reworked; with `scores`,
// then its scores (now, at +16, after a rework, its value with the shortage counted, best for).
import type { AccessoryRow } from "../types/generated/webui.service.accessories";
import PieceCells from "./PieceCells.vue";

defineProps<{ row: AccessoryRow; scores?: boolean }>();
</script>

<template>
  <PieceCells :piece="row.piece">
    <small v-if="row.reworked" class="badge quiet" title="reworked already: it can't be again">
      reworked
    </small>
  </PieceCells>
  <template v-if="scores">
    <td class="num">{{ row.now }}</td>
    <td class="num">{{ row.natural }}</td>
    <td class="num">{{ row.rework ?? "–" }}</td>
    <td class="num" :title="`shortage: ${row.scarcity}`">
      <strong>{{ row.value }}</strong> <small class="muted">{{ row.scarcity }}</small>
    </td>
    <td>
      <small>{{ row.fit ?? "fits nothing in its set" }}</small>
    </td>
  </template>
</template>
