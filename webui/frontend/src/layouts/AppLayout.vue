<script setup lang="ts">
// The app's frame, as base.html draws it: the bar (menu, Sync), the band of the current
// section's pages when it has several, then the page.
import { Link, router, usePage } from "@inertiajs/vue3";
import { computed, ref } from "vue";
import { sendToGame } from "../composables/send";
import { providePageSubnav } from "../composables/subnav";

const page = usePage();
const ownSubnav = providePageSubnav();
const layout = computed(() => page.props.layout);
const open = computed(() =>
  layout.value.sections.find((section) => section.tabs.some((tab) => tab.current)),
);

const syncing = ref(false);
const syncFailed = ref<string | null>(null);

// Reads the account from the running game; on success the page's props reload with it.
async function sync() {
  syncing.value = true;
  syncFailed.value = null;

  const outcome = await sendToGame("/sync");
  syncing.value = false;
  syncFailed.value = outcome.error;
  if (!outcome.error) router.reload();
}
</script>

<template>
  <header class="topbar">
    <nav class="container">
      <ul>
        <li>
          <Link href="/" class="wordmark">Raid optimiser</Link>
        </li>
      </ul>
      <ul class="menu">
        <li v-for="section in layout.sections" :key="section.label">
          <Link
            :href="section.link"
            :aria-current="section.tabs.some((tab) => tab.current) ? 'page' : undefined"
          >
            {{ section.label }}
          </Link>
        </li>
      </ul>
      <ul class="tools">
        <li class="cluster" style="--space: var(--space-m)">
          <small v-if="syncFailed" class="sync-status down">Failed: {{ syncFailed }}</small>
          <small v-else class="sync-status caps">{{ layout.synced_ago }}</small>
          <button
            class="quiet small sync"
            :disabled="syncing"
            title="Read the account from the running game"
            @click="sync"
          >
            Sync
          </button>
        </li>
      </ul>
    </nav>
    <div v-show="ownSubnav > 0" id="page-subnav" class="subbar"></div>
    <div v-if="!ownSubnav && open && open.tabs.length > 1" class="subbar">
      <nav class="container tabs" :aria-label="open.label">
        <ul>
          <li v-for="tab in open.tabs" :key="tab.label">
            <Link :href="tab.link" :aria-current="tab.current ? 'page' : undefined">{{
              tab.label
            }}</Link>
          </li>
        </ul>
      </nav>
    </div>
  </header>
  <main class="container">
    <div v-if="page.props.errors.form" class="panel alert" role="alert">
      Couldn't save: {{ page.props.errors.form }}
    </div>
    <slot />
  </main>
</template>

<style scoped>
/* The page's width is what its layouts ask about (`@container page`), not the window's. */
main.container {
  container: page / inline-size;
}
</style>
