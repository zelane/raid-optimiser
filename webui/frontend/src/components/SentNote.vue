<script setup lang="ts">
// What a command or save came to (`sent`; nothing before one): "Failed: …" in red, else `done`
// in green.
import type { Sent } from "../composables/send";

defineProps<{ sent: Sent | null | undefined; done: string }>();
</script>

<template>
  <small v-if="sent?.error" class="down">Failed: {{ sent.error }}</small>
  <small v-else-if="sent" class="up">{{ done }}</small>
</template>
