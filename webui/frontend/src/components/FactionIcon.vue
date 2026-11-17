<script setup lang="ts">
// A faction's emblem (`url`, from `faction_icon_url`): one colour, the SVG drawn as a mask
// in the text's colour (muted unless the context says otherwise). `label` names it (alt and
// title); without one it's decoration. `size`: "small" beside small text.
defineProps<{ url: string; label?: string | null; size?: string }>();
</script>

<template>
  <span
    class="faction"
    :class="size"
    :style="{ '--emblem': `url(${url})` }"
    :role="label ? 'img' : undefined"
    :aria-label="label ?? undefined"
    :aria-hidden="label ? undefined : 'true'"
    :title="label ?? undefined"
  />
</template>

<style scoped>
/* The emblem: a square of the text's colour cut to the SVG's shape. `--faction-size` lets a
   context size it (a champion's name). */
.faction {
  display: inline-block;
  flex: none;
  width: var(--faction-size, 2rem);
  height: var(--faction-size, 2rem);
  color: var(--on-surface-variant);
  vertical-align: middle;
  background: currentcolor;
  mask: var(--emblem) center / contain no-repeat;

  &.small {
    --faction-size: 1.1rem;
  }
}
</style>
