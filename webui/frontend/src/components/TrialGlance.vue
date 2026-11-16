<script setup lang="ts">
// A found team's Chimera trials at a glance, on its option card: a row per form, ✓ or ✗ for
// each level (Easy, Normal, Hard).
defineProps<{ glance: [string, boolean[]][] }>();

const LEVELS = ["Easy", "Normal", "Hard"];
</script>

<template>
  <table class="glance" aria-label="Trials cleared">
    <tbody>
      <tr v-for="[form, hits] in glance" :key="form">
        <th scope="row">{{ form }}</th>
        <td v-for="(hit, n) in hits" :key="n" :class="hit ? 'up' : 'down'" :title="LEVELS[n]">
          {{ hit ? "✓" : "✗" }}
        </td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
table.glance {
  width: auto;
  margin: 0;
  font-size: var(--text-xs);

  th,
  td {
    padding: var(--space-3xs) var(--space-s);
    border: 0;
    text-align: center;
  }

  th {
    text-align: left;
  }
}
</style>
