<script setup lang="ts">
// The Chimera's trial board for the team shown: a panel per form (its accent colour and art),
// its Easy → Normal → Hard trials across it, each lit when the team clears it, with its text,
// target and who brings what it needs.
import type { FormRow } from "../types/generated/webui.service.chimera";
import NeedItem from "./NeedItem.vue";
import NeedsPanel from "./NeedsPanel.vue";

defineProps<{ rows: FormRow[] }>();

const LEVEL_TONES: Record<string, string> = { Easy: "info", Normal: "mid" };
</script>

<template>
  <NeedsPanel
    v-for="row in rows"
    :key="row.form"
    :title="`${row.form} form`"
    :needs="row.trials"
    :glyph="row.form[0]"
    :icon-url="row.icon_url"
    :accent="`form-${row.form.toLowerCase()}`"
  >
    <div class="trial-row">
      <article
        v-for="trial in row.trials"
        :key="trial.level"
        class="trial stack"
        :class="{ met: trial.met }"
        style="--space: var(--space-s)"
      >
        <div class="cluster" style="--justify: space-between">
          <span class="badge" :class="LEVEL_TONES[trial.level] ?? 'bad'">{{ trial.level }}</span>
          <span class="trial-state" :class="trial.met ? 'up' : trial.waits_on ? 'mid' : 'down'">
            <template v-if="trial.met">Cleared</template>
            <template v-else-if="trial.waits_on">Needs {{ trial.waits_on }} first</template>
            <template v-else>Not cleared</template>
          </span>
        </div>
        <p>{{ trial.description }}</p>
        <p class="trial-target">
          <span>Target</span> <strong>{{ trial.target }}</strong>
          <template v-if="trial.damage"> damage</template>
        </p>
        <ul v-if="trial.needs.length" class="stack" style="--space: var(--space-xs)">
          <NeedItem v-for="(need, n) in trial.needs" :key="n" :need="need" />
        </ul>
        <p v-else class="note">Nothing to bring: it's down to the fight.</p>
      </article>
    </div>
  </NeedsPanel>
</template>

<style scoped>
/* A form's trials three across, a chevron between them; one under the next on a narrow page. */
.trial-row {
  --trial-gap: var(--space-2xl);

  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-m);
  align-items: start;
}

@container page (min-width: 46rem) {
  .trial-row {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--trial-gap);

    .trial + .trial::before {
      content: "›";
      position: absolute;
      top: 50%;
      left: calc(var(--trial-gap) / -2);
      transform: translate(-50%, -50%);
      font-size: var(--text-xl);
      color: color-mix(in srgb, var(--accent) 70%, var(--on-surface-variant));
    }
  }
}

.trial {
  position: relative;
  padding: var(--space-m);
  border-radius: var(--radius);
  font-size: var(--text-xs);
  line-height: 1.35;
  background: var(--surface-container-lowest);

  &.met {
    border-color: color-mix(in srgb, var(--stat-up) 55%, transparent);
    box-shadow: inset 3px 0 0 var(--stat-up);
  }
}

.trial-state {
  font-size: var(--text-2xs);
  font-weight: 700;
}

.trial-target {
  align-self: flex-start;
  padding: var(--space-3xs) var(--space-s);
  border-radius: var(--radius);
  font-size: var(--text-2xs);
  color: var(--on-surface-variant);
  background: color-mix(in srgb, var(--accent) 14%, transparent);

  strong {
    color: var(--accent);
  }
}
</style>
