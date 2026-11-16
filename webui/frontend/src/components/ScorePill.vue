<script setup lang="ts">
// A score (%) as a badge, coloured by how far it can be counted on.
import { computed } from "vue";
import { scoreTone } from "../composables/format";

const props = defineProps<{ score: number; title?: string }>();
const tone = computed(() => scoreTone(props.score));
</script>

<template>
  <span class="badge" :class="tone" :title="title">{{ score }}%</span>
</template>
