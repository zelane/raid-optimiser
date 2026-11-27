<script setup lang="ts">
// The app's frame: the bar (menu, Sync), the band of tabs under it (the page's own, else the
// current section's pages when it has several), then the page.
import { Link, router, usePage } from "@inertiajs/vue3";
import { computed, ref } from "vue";
import { sendToGame } from "../composables/send";
import { providePageSubnav, type PageSubnav } from "../composables/subnav";

const page = usePage();
const pageSubnav = providePageSubnav();
const layout = computed(() => page.props.layout);

const subnav = computed<PageSubnav | null>(() => {
  if (pageSubnav.value) return pageSubnav.value.subnav;
  const open = layout.value.sections.find((section) => section.tabs.some((tab) => tab.current));
  if (!open || open.tabs.length < 2) return null;
  return {
    label: open.label,
    tabs: open.tabs.map((tab) => ({ href: tab.link, label: tab.label, current: tab.current })),
  };
});

const syncing = ref(false);
const syncFailed = ref<string | null>(null);

// Reads the account from the running game now; on success the page's props reload with it.
// Starting or stopping `just watch` (which reads it as it changes) reloads the frame alone.
async function send(url: string, reload: string[] | null) {
  syncing.value = true;
  syncFailed.value = null;

  const outcome = await sendToGame(url);
  syncing.value = false;
  syncFailed.value = outcome.error;
  router.reload(reload ? { only: reload } : {});
}

const sync = () => send("/sync", null);
const toggleWatch = () => send(layout.value.watching ? "/watch/stop" : "/watch/start", ["layout"]);
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
          <small
            v-else
            class="sync-status caps"
            :class="{ watching: layout.watching }"
            :title="layout.watching ? 'Watching the game: read as it changes' : undefined"
          >
            {{ layout.synced_ago }}
          </small>
          <button
            class="quiet small"
            :disabled="syncing"
            :title="
              layout.watching
                ? 'Stop reading the account as it changes'
                : 'Read the account as it changes, while the game runs (just watch)'
            "
            @click="toggleWatch"
          >
            {{ layout.watching ? "Stop watching" : "Watch" }}
          </button>
          <button
            class="quiet small sync"
            :disabled="syncing"
            title="Read the account from the running game now"
            @click="sync"
          >
            Sync
          </button>
        </li>
      </ul>
    </nav>
    <div v-if="subnav" class="subbar">
      <nav class="container tabs" :aria-label="subnav.label">
        <ul>
          <li v-for="tab in subnav.tabs" :key="tab.href">
            <Link :href="tab.href" :aria-current="tab.current ? 'page' : undefined">
              {{ tab.label }}
              <span v-if="tab.badge" class="badge" :class="tab.badge.tone" :title="tab.badge.title">
                {{ tab.badge.text }}
              </span>
            </Link>
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

/* Two rows: the wordmark, the sections and (at the end) sync; then, in a darker band of
   its own (the subbar), the open section's tabs, muted, the open one brass with a rule on the
   band's lower edge. Both wrap on a narrow screen. */
.topbar {
  margin: 0;
  padding-block: var(--panel-pad);
  border-bottom: 1px solid var(--outline-variant);
  background: var(--surface-container-low);

  nav,
  nav ul {
    flex-wrap: wrap;
  }

  nav {
    padding-block: var(--space-2xs);

    &:not(.tabs) {
      column-gap: var(--space-2xl);
    }

    ul.menu {
      margin-inline: 0 auto;
    }

    a {
      font-size: var(--text-xs);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.07em;

      &.wordmark {
        font-size: var(--text-xl);
        font-weight: 700;
        letter-spacing: 0.04em;
      }

      &[aria-current="page"] {
        color: var(--primary);
      }
    }
  }

  ul.menu a[aria-current="page"] {
    text-decoration: underline 2px;
    text-underline-offset: 0.55em;
  }

  button.sync[disabled]::after {
    content: "…";
  }

  /* The band sits on the bar's lower edge. */
  &:has(.subbar) {
    padding-bottom: 0;
  }

  nav.tabs {
    justify-content: flex-start;
    padding-block: 0;

    ul {
      gap: var(--space-2xs) var(--space-3xl);
      margin: 0;
    }

    li {
      padding: 0;
    }

    a {
      display: inline-block;
      margin: 0;
      padding: var(--space-s) 0 calc(var(--space-s) - 2px);
      border-bottom: 2px solid transparent;
      border-radius: 0;
      font-size: var(--text-2xs);
      color: var(--on-surface-variant);

      &:hover {
        color: var(--on-surface);
      }

      &[aria-current="page"] {
        border-bottom-color: var(--primary);
        color: var(--primary);
      }
    }
  }
}

.wordmark {
  display: inline-flex;
  gap: var(--space-s);
  align-items: center;
  font-family: var(--font-display);
  color: var(--heading);
  text-decoration: none;
  letter-spacing: 0.01em;
  white-space: nowrap;
}

.wordmark::before {
  content: "";
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: var(--primary);
  box-shadow: 0 0 8px var(--primary);
}

/* The dot: green and pulsing while the watcher keeps the account current. */
.sync-status {
  white-space: nowrap;

  &::before {
    content: "●";
    margin-right: var(--space-xs);
    color: var(--tertiary);
  }

  &.watching::before {
    color: var(--stat-up);
    animation: pulse 2s ease-in-out infinite;
  }
}

@keyframes pulse {
  50% {
    opacity: 0.35;
  }
}

.subbar {
  border-top: 1px solid var(--outline-variant);
  background: color-mix(in srgb, var(--surface-container-lowest) 60%, var(--surface-container-low));
}
</style>
