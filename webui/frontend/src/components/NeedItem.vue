<script setup lang="ts">
// A need: met or not, what would do (icons), and who brings it (portraits) or what else does.
import { computed } from "vue";
import { scoreTone } from "../composables/format";
import type { NeedView } from "../types/generated/webui.service.team";
import Portrait from "./Portrait.vue";
import ScorePill from "./ScorePill.vue";
import StatusIcon from "./StatusIcon.vue";

const props = defineProps<{ need: NeedView }>();
const tone = computed(() => scoreTone(props.need.score));
</script>

<template>
  <li class="status" :class="need.met ? 'met' : 'missing'">
    <span
      class="need-mark"
      :class="need.met ? 'up' : 'down'"
      :aria-label="need.met ? 'met' : 'not met'"
    >
      {{ need.met ? "✓" : "✗" }}
    </span>
    <div class="need-body stack" style="--space: var(--space-2xs)">
      <span class="cluster" style="--space: var(--space-xs)">
        <span v-if="need.asks.length" class="icons">
          <StatusIcon
            v-for="icon in need.asks"
            :key="icon.label"
            :url="icon.url"
            :label="icon.label"
          />
        </span>
        <span>{{ need.label }}</span>
        <ScorePill
          v-if="need.met"
          :score="need.score"
          title="How far the team can count on it: uptime × reliability × reach"
          class="push"
        />
      </span>
      <span v-if="need.met" class="meter" :class="tone" aria-hidden="true">
        <span :style="{ width: `${need.score}%` }"></span>
      </span>
      <div
        v-if="need.contributors.length || need.notes.length || need.brought.length"
        class="cluster"
        style="--space: var(--space-2xs)"
      >
        <Portrait
          v-for="contributor in need.contributors"
          :key="contributor.champion.id"
          :href="`/champions/${contributor.champion.id}`"
          :url="contributor.champion.portrait_url"
          :name="contributor.champion.name"
          :rarity="contributor.champion.rarity"
          :title="`${contributor.champion.name}: ${contributor.score}% (${contributor.detail})`"
        />
        <span
          v-if="need.brought.length"
          class="icons need-brought"
          title="What the team brings toward it"
        >
          <StatusIcon
            v-for="icon in need.brought"
            :key="icon.label"
            :url="icon.url"
            :label="icon.label"
            size="small"
          />
        </span>
        <span v-for="note in need.notes" :key="note" class="badge quiet">{{ note }}</span>
      </div>
      <div v-else-if="!need.met" class="cluster">
        <span class="badge bad">nobody brings it</span>
      </div>
    </div>
  </li>
</template>

<style scoped>
/* A need: met or not, what would do, how far it can be counted on, who brings it. */
.need-mark {
  flex: none;
  font-weight: 700;
}

.need-body {
  flex: 1;
}

.need-brought {
  padding: var(--space-3xs) var(--space-2xs);
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--outline-variant) 30%, transparent);
}
</style>
