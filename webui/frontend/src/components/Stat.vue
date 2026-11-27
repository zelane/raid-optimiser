<script setup lang="ts">
// A number to read at a glance: big, its label in caps under it, and anything more (the slot)
// under that, small and muted.
const { value, label } = defineProps<{ value: string; label: string }>();
</script>

<template>
  <div class="stat">
    <span class="figure">{{ value }}</span>
    <span class="caps">{{ label }}</span>
    <small v-if="$slots.default" class="muted"><slot /></small>
  </div>
</template>

<style scoped>
/* One above the other. */
.stat {
  display: grid;
}
</style>
