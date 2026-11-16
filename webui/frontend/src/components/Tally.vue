<script setup lang="ts">
// `count` of `total` as a big figure in its `tone`, a caps `label`, and what the slot adds.
defineProps<{ count: number; total: number; label: string; tone?: string; title?: string }>();
</script>

<template>
  <div class="tally" :title="title">
    <strong class="figure" :class="tone"
      >{{ count }}<small>/{{ total }}</small></strong
    >
    <span class="caps">{{ label }}</span>
    <slot />
  </div>
</template>
