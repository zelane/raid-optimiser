<script setup lang="ts">
// A panel of needs in its accent colour (`accent`: a form's class), headed by its icon or
// glyph and how many are met. The default slot is the body; else the needs as a grid.
import { computed } from "vue";
import type { NeedView } from "../types/generated/webui.service.team";
import NeedItem from "./NeedItem.vue";

const props = withDefaults(
  defineProps<{
    title: string;
    needs: { met: boolean }[];
    glyph?: string;
    iconUrl?: string | null;
    accent?: string;
  }>(),
  { glyph: "+", iconUrl: null, accent: "" },
);
const met = computed(() => props.needs.filter((need) => need.met).length);
</script>

<template>
  <section class="panel stack accent-panel" :class="accent" style="--space: var(--space-m)">
    <header class="cluster" style="--space: var(--space-s)">
      <img v-if="iconUrl" class="form-icon" :src="iconUrl" alt="" aria-hidden="true" />
      <span v-else class="form-glyph" aria-hidden="true">{{ glyph }}</span>
      <h3>{{ title }}</h3>
      <span class="badge push" :class="met === needs.length ? 'good' : 'bad'">
        {{ met }} / {{ needs.length }}
      </span>
    </header>
    <slot>
      <ul class="grid" style="--min: 18rem; --space: var(--space-s)">
        <NeedItem v-for="(need, n) in needs as NeedView[]" :key="n" :need="need" />
      </ul>
    </slot>
  </section>
</template>

<style scoped>
/* A panel in its own colour (`--accent`): a Chimera form's (theme.css), else the extras'. */
.accent-panel {
  --accent: var(--form-any);

  border-top: 2px solid color-mix(in srgb, var(--accent) 70%, transparent);
  background: linear-gradient(
    135deg,
    color-mix(in srgb, var(--accent) 8%, var(--surface-container-low)),
    var(--surface-container-low) 50%
  );

  h3 {
    font-size: var(--text-l);
    color: var(--accent);
  }
}

.form-ram {
  --accent: var(--form-ram);
}

.form-lion {
  --accent: var(--form-lion);
}

.form-snake {
  --accent: var(--form-snake);
}

.form-icon {
  width: 2.4rem;
  height: 2.4rem;
  object-fit: contain;
  filter: drop-shadow(0 0 6px color-mix(in srgb, var(--accent) 45%, transparent));
}

.form-glyph {
  display: grid;
  place-items: center;
  width: 2.1rem;
  height: 2.1rem;
  border-radius: 50%;
  font-family: var(--font-display);
  font-size: var(--text-l);
  font-weight: 700;
  color: var(--surface);
  background: var(--accent);
}
</style>
