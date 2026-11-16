<script setup lang="ts">
// A link to one of the app's pages: an Inertia visit if Inertia serves it (the layout's
// `inertia_pages`), else a full load. Any other attributes (class, title) go on the link.
import { Link, usePage } from "@inertiajs/vue3";
import { computed } from "vue";

const props = defineProps<{ href: string; current?: boolean }>();
const page = usePage();

const inertia = computed(() => {
  const path = new URL(props.href, window.location.origin).pathname;
  return page.props.layout.inertia_pages.some((pattern) => new RegExp(pattern).test(path));
});
</script>

<template>
  <Link v-if="inertia" :href="href" :aria-current="current ? 'page' : undefined"><slot /></Link>
  <a v-else :href="href" :aria-current="current ? 'page' : undefined"><slot /></a>
</template>
