<script setup lang="ts">
// The teams a search found: what it found (`found`, `complete`, `partial` say how many and
// whether they bring it all), the option cards (a glance per card in the `glance` slot), and
// the link listing more.
import { Link } from "@inertiajs/vue3";
import OptionCard from "./OptionCard.vue";
import type { SlotView } from "../types/generated/webui.service.team";

type Option = {
  number: number;
  slots: SlotView[];
  score: number;
  show_url: string;
  use_url: string;
};

defineProps<{
  options: Option[];
  shown: number | null;
  total: number;
  met: (option: Option) => number;
  scoreTitle: string;
  showLabel: string;
  found: number;
  complete: boolean;
  listed: number;
  more: string | null;
  minGrade: number;
}>();

defineSlots<{ default(props: { option: Option }): unknown; lede(): unknown }>();
</script>

<template>
  <section class="stack" style="--space: var(--space-l)">
    <h2 class="section-title">Teams</h2>
    <p class="lede"><slot name="lede" /></p>
    <div class="grid" style="--min: 19rem; --space: var(--space-l); --repeat: auto-fill">
      <OptionCard
        v-for="option in options"
        :key="option.number"
        :option="option"
        :shown="option.number === shown"
        :met="met(option)"
        :total="total"
        :score-title="scoreTitle"
        :show-label="showLabel"
      >
        <slot :option="option" />
      </OptionCard>
      <p v-if="!options.length">
        No team found: no champion at {{ minGrade }}★ or above adds anything.
      </p>
    </div>
    <p v-if="more">
      <Link :href="more" role="button" class="quiet" preserve-scroll preserve-state>
        Show more ({{ listed }} of {{ found.toLocaleString() }}{{ complete ? "" : "+" }})
      </Link>
    </p>
  </section>
</template>
