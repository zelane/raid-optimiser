<script setup lang="ts">
// The search bar: the champions searched from, what the last search covered, Find.
import { teamQuery, visitWith } from "../composables/teamQuery";
import type { TeamLinks } from "../types/generated/webui.service.team";

const props = defineProps<{
  links: TeamLinks;
  ran: boolean;
  grades: number[];
  minGrade: number;
  candidates: number;
  searched: boolean;
}>();

function search(grade: number) {
  const query = teamQuery(props.links, true);
  query.set("min_grade", String(grade));
  visitWith(query);
}

function regrade(grade: string) {
  const query = teamQuery(props.links, props.ran);
  query.set("min_grade", grade);
  visitWith(query);
}
</script>

<template>
  <div class="panel cluster" style="--space: var(--space-m) var(--space-2xl)">
    <label class="inline">
      <span class="caps">Search from</span>
      <select :value="minGrade" @change="regrade(($event.target as HTMLSelectElement).value)">
        <option v-for="grade in grades" :key="grade" :value="grade">
          Champions at {{ grade }}★ and up
        </option>
      </select>
    </label>
    <span v-if="searched" class="note"
      >Searched {{ candidates }} champions (the best copy of each)</span
    >
    <button type="button" class="cta push" @click="search(minGrade)">Find teams</button>
  </div>
</template>
