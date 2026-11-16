<script setup lang="ts">
// Pieces to roll or rework, best first: the piece, its score before and `afterLabel`, its
// priority (shortage counted) and what it's best for. `shown`: the most a list holds.
import type { CandidateRow } from "../types/generated/webui.service.accessories";
import AccessoryCells from "./AccessoryCells.vue";

defineProps<{ rows: CandidateRow[]; afterLabel: string; shown: number }>();
</script>

<template>
  <div v-if="rows.length" class="stack" style="--space: var(--space-xs)">
    <div class="table-well">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th></th>
            <th>Piece</th>
            <th>Main</th>
            <th>Substats</th>
            <th class="num">Now</th>
            <th class="num">{{ afterLabel }}</th>
            <th class="num" title="shortage counted">Priority</th>
            <th>Best for</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(candidate, n) in rows" :key="candidate.row.piece.id">
            <td class="num muted">{{ n + 1 }}</td>
            <AccessoryCells :row="candidate.row" />
            <td class="num">{{ candidate.before }}</td>
            <td class="num">{{ candidate.after }}</td>
            <td class="num">
              <strong>{{ candidate.priority }}</strong>
              <small class="muted">{{ candidate.row.scarcity }}</small>
            </td>
            <td>
              <small>{{ candidate.row.fit ?? "–" }}</small>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="rows.length >= shown" class="note">The first {{ shown }} shown.</p>
  </div>
  <p v-else>Nothing to list.</p>
</template>
