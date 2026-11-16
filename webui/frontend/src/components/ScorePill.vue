<script setup lang="ts">
// A score (%) as a badge, coloured by how far it can be counted on.
import { computed } from "vue";

const props = defineProps<{ score: number; title?: string }>();
const tone = computed(() => (props.score >= 75 ? "good" : props.score >= 45 ? "mid" : "bad"));
</script>

<template>
  <span class="badge" :class="tone" :title="title">{{ score }}%</span>
</template>
