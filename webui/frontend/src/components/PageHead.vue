<script setup lang="ts">
// A page's title, its lede (the `lede` slot) and what sits at the other end (`aside`).
defineProps<{ title: string; id?: string }>();
</script>

<template>
  <header class="page-head">
    <div>
      <h1 :id="id">{{ title }}</h1>
      <p v-if="$slots.lede" class="lede"><slot name="lede" /></p>
    </div>
    <slot name="aside" />
  </header>
</template>
