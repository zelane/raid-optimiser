<script setup lang="ts">
// A test page: the theme's colours and the shared components (app.css) side by side, with
// made-up content, so the palette can be judged in place. Not in the nav: /palette.
import { Head } from "@inertiajs/vue3";
import { computed, onMounted, ref } from "vue";
import ChampionCard from "../components/ChampionCard.vue";
import PageHead from "../components/PageHead.vue";
import PieceCard from "../components/PieceCard.vue";
import RemoveChip from "../components/RemoveChip.vue";
import ScorePill from "../components/ScorePill.vue";
import StatusIcon from "../components/StatusIcon.vue";
import Tally from "../components/Tally.vue";
import type { LineView, PieceView } from "../types/generated/webui.service.results";
import type { ChampionRow } from "../types/generated/webui.service.views";

defineProps<{ champions: ChampionRow[] }>();

const SWATCHES = [
  ["--primary", "--on-primary"],
  ["--secondary", "--on-secondary"],
  ["--tertiary", "--surface"],
  ["--error", "--surface"],
  ["--success", "--surface"],
  ["--warning", "--surface"],
  ["--on-surface", "--surface"],
  ["--on-surface-variant", "--surface"],
  ["--heading", "--surface"],
  ["--outline", "--on-surface"],
  ["--outline-variant", "--on-surface"],
] as const;
const SURFACES = [
  ["--surface", "The page slab."],
  ["--surface-container-lowest", "Wells, fields, tables."],
  ["--surface-container-low", "Panels, the top bar, code."],
  ["--surface-container", "Spare."],
  ["--surface-container-high", "Hovered and selected rows."],
] as const;
// Asked-for chips (`RemoveChip`), one of each kind.
const ICONS = "/static/assets/statuses";
const CHIPS = [
  { kind: "debuff", icon: `${ICONS}/IncreaseDamageTaken.png`, label: "Weaken" },
  { kind: "buff", icon: `${ICONS}/StatusIncreaseAttack.png`, label: "Increase ATK" },
  { kind: "effect", icon: `${ICONS}/IncreaseStamina.png`, label: "Fill Turn Meter" },
  { kind: "count", icon: null, label: "3 different debuffs" },
  { kind: "gear", icon: `${ICONS}/IncreasePoisoning.png`, label: "Toxic set" },
  {
    kind: "buff",
    icon: `${ICONS}/StatusCounterattack.png`,
    label: "Team: Counterattack",
    assumed: true,
  },
];

const RARITIES = ["common", "uncommon", "rare", "epic", "legendary", "mythical"];

// Each swatch's resolved value, for reading off the page.
const resolved = ref<Record<string, string>>({});
onMounted(() => {
  const style = getComputedStyle(document.documentElement);
  resolved.value = Object.fromEntries(
    SWATCHES.map(([name]) => [name, style.getPropertyValue(name).trim()]),
  );
});

// The filter bar, filtering in the page.
const FILTERED = [
  { text: "Gharol", faction: "Orcs", kind: "damage", label: "Gharol · Orcs · damage" },
  { text: "Any ATK", faction: "", kind: "damage", label: "Any ATK · any faction · damage" },
  { text: "Tormin", faction: "Dwarves", kind: "support", label: "Tormin · Dwarves · support" },
];
const filter = ref({ text: "", faction: "", kind: "" });
const filtered = computed(() =>
  FILTERED.filter(
    (item) =>
      item.text.toLowerCase().includes(filter.value.text.trim().toLowerCase()) &&
      (!filter.value.faction || !item.faction || item.faction === filter.value.faction) &&
      (!filter.value.kind || item.kind === filter.value.kind),
  ),
);

// Made-up gear.
function line(label: string, amount: string, more: Partial<LineView> = {}): LineView {
  return {
    label,
    amount,
    glyph: null,
    rolls: 0,
    optimised: true,
    planned_glyph: null,
    planned_amount: null,
    ...more,
  };
}

function piece(more: Partial<PieceView>): PieceView {
  return {
    id: 0,
    slot: "Gloves",
    set_name: "Speed",
    set_icon_url: null,
    image_url: null,
    rank: 6,
    rarity: "Legendary",
    level: 16,
    primary: line("ATK%", "50%"),
    substats: [],
    ascension: null,
    faction: null,
    worn_by: null,
    worn_by_portrait: null,
    equipped: false,
    stars: [],
    ascend_level: 0,
    planned_level: null,
    planned_ascend_level: null,
    reserved_by: [],
    faction_icon_url: null,
    faction_label: null,
    ...more,
  };
}

const speed = line("SPD", "16", { glyph: "4" });
const critRate = line("C.RATE", "9%", { planned_amount: "15%" });
const attack = line("ATK%", "5%", { optimised: false });
const legend = piece({
  image_url: "/static/assets/pieces/4_gloves.png",
  ascend_level: 2,
  ascension: line("ATK", "41"),
  substats: [speed, critRate, attack],
});
const epic = piece({
  rarity: "Epic",
  set_name: "Lifesteal",
  slot: "Boots",
  image_url: "/static/assets/pieces/2_boots.png",
  level: 12,
  planned_level: 16,
  primary: line("SPD", "40", { planned_amount: "45" }),
  substats: [speed, attack],
  worn_by: "Someone",
});
const someone = {
  id: 0,
  name: "Champion",
  portrait_url: null,
  rarity: "Epic",
} as ChampionRow;
</script>

<template>
  <Head title="Palette" />
  <div class="stack palette" style="--space: var(--space-3xl)">
    <PageHead title="Palette">
      <template #lede>
        Every colour in the Vault theme and every shared component, filled with made-up content. The
        theme lives in <code>static/theme.css</code>, the components in <code>static/app.css</code>.
      </template>
      <template #aside>
        <Tally :count="42" :total="50" label="tally"><span class="muted">a big figure</span></Tally>
      </template>
    </PageHead>

    <section class="page-section stack" style="--space: var(--space-m)">
      <h2>Colours</h2>
      <div class="grid" style="--min: 9.5rem; --space: var(--space-s); --repeat: auto-fill">
        <div v-for="[bg, fg] in SWATCHES" :key="bg" class="swatch stack" style="--space: 0">
          <div class="swatch-chip" :style="{ background: `var(${bg})`, color: `var(${fg})` }">
            Aa
          </div>
          <div class="swatch-meta note">
            <code>{{ bg }}</code><br /><span>{{ resolved[bg] }}</span>
          </div>
        </div>
      </div>
    </section>

    <section class="page-section stack" style="--space: var(--space-m)">
      <h2>Surfaces</h2>
      <p class="note">
        The slab, then the containers from lowest (insets: wells, fields, tables) to high (hovered
        and selected rows).
      </p>
      <div class="layers grid" style="--min: 10rem; --space: var(--space-l)">
        <div v-for="[name, use] in SURFACES" :key="name" :style="{ background: `var(${name})` }">
          <span class="caps">{{ name }}</span>
          <p>{{ use }}</p>
        </div>
      </div>
    </section>

    <section class="page-section stack" style="--space: var(--space-m)">
      <h2>Text on surfaces</h2>
      <div class="grid" style="--min: 16rem; --space: var(--space-l); --align: start">
        <div
          v-for="bg in ['--surface', '--surface-container-low', '--surface-container']"
          :key="bg"
          class="text-on stack"
          :style="{ '--space': 'var(--space-2xs)', background: `var(${bg})` }"
        >
          <span class="caps">{{ bg }}</span>
          <h3>A heading in Alegreya</h3>
          <span>Body text, the bone white of the page.</span>
          <span class="muted">Muted text.</span>
          <span class="note">A note: small and muted.</span>
          <span>
            <a href="#">A link</a> · <span class="up">+12% up</span> ·
            <span class="down">−8% down</span> · <span class="mid">mid</span> ·
            <span class="info">info</span>
          </span>
        </div>
      </div>
    </section>

    <section class="page-section stack" style="--space: var(--space-m)">
      <h2>Rarity</h2>
      <div class="rarities cluster">
        <span v-for="rarity in RARITIES" :key="rarity" :class="`rarity-${rarity}`">
          {{ rarity[0]?.toUpperCase() + rarity.slice(1) }}
        </span>
      </div>
      <div v-if="champions.length" class="champion-grid">
        <ChampionCard
          v-for="champion in champions"
          :key="champion.id"
          :champion="champion"
          banner
          card
        />
      </div>
    </section>

    <section class="page-section stack" style="--space: var(--space-m)">
      <h2>Buttons and links</h2>
      <div class="cluster">
        <button>Primary</button>
        <button class="cta">Run · CTA</button>
        <button class="quiet">Quiet</button>
        <button class="quiet danger">Quiet danger</button>
        <button class="danger">Sell 12 pieces</button>
        <button disabled>Disabled</button>
        <a href="#">A link</a>
      </div>
      <p class="note">Primary next to danger: they should never be mistaken for each other.</p>
      <div class="cluster">
        <button>Equip</button><button class="danger">Sell</button> <span class="badge">accent</span
        ><span class="badge bad">bad</span>
      </div>
    </section>

    <section class="page-section stack" style="--space: var(--space-m)">
      <h2>Badges, chips, statuses</h2>
      <div class="cluster">
        <span class="badge">default</span><span class="badge good">good</span>
        <span class="badge mid">mid</span><span class="badge bad">bad</span>
        <span class="badge info">info</span><span class="badge quiet">quiet</span>
        <span class="badge quiet bad">quiet bad</span>
        <span class="figure up">+29.9</span>
        <span class="caps">caps label</span>
        <mark>marked text</mark> <ins>inserted</ins> <del>deleted</del> <code>code</code>
      </div>
      <div class="cluster">
        <label class="chip"><input type="checkbox" />Off chip</label>
        <label class="chip on"><input type="checkbox" checked />On chip</label>
        <span class="chip assumed">Assumed</span>
        <ScorePill :score="88" /> <ScorePill :score="55" /> <ScorePill :score="20" />
        <StatusIcon url="/static/assets/statuses/BlockBuffs.png" label="Block Buffs" />
        <StatusIcon :url="null" label="No icon" />
      </div>
      <ul class="grid" style="--min: 16rem; --space: var(--space-s)">
        <li class="status met">✓ Decrease DEF on the Chimera</li>
        <li class="status missing">✗ Block Buffs: nobody brings it</li>
        <li class="status">A plain status</li>
      </ul>
      <div class="grid" style="--min: 16rem; --space: var(--space-l); --align: start">
        <div>
          <span class="caps">meter high</span
          ><span class="meter"><span style="width: 85%"></span></span>
        </div>
        <div>
          <span class="caps">meter mid</span
          ><span class="meter mid"><span style="width: 55%"></span></span>
        </div>
        <div>
          <span class="caps">meter low</span
          ><span class="meter bad"><span style="width: 20%"></span></span>
        </div>
      </div>
    </section>

    <section class="page-section stack" style="--space: var(--space-m)">
      <h2>Asked-for chips</h2>
      <div class="cluster" style="--space: var(--space-xs)">
        <RemoveChip
          v-for="chip in CHIPS"
          :key="chip.label"
          href="#"
          title="Remove"
          :kind="chip.kind"
          :class="{ assumed: chip.assumed }"
        >
          <StatusIcon v-if="chip.icon" :url="chip.icon" :label="chip.label" size="small" />
          <span v-else class="count-mark" aria-hidden="true">#</span>{{ chip.label }}
        </RemoveChip>
      </div>
    </section>

    <section class="page-section stack" style="--space: var(--space-m)">
      <h2>Forms</h2>
      <div class="grid" style="--min: 16rem; --space: var(--space-l); --align: start">
        <article class="panel stack" style="--space: var(--space-m)">
          <header class="panel-head">
            <h3>Fields</h3>
            <span class="caps">panel-head</span>
          </header>
          <div class="stack" style="--space: var(--space-s)">
            <input type="text" placeholder="Placeholder" />
            <input type="text" value="Focused field" />
            <input type="text" value="Invalid" aria-invalid="true" />
            <select>
              <option>A select</option>
            </select>
            <label><input type="checkbox" checked /> A checkbox</label>
            <label><input type="radio" checked /> A radio</label>
            <input type="range" value="60" />
          </div>
        </article>
        <article class="panel stack" style="--space: var(--space-m)">
          <header class="panel-head"><h3>Toggles</h3></header>
          <div class="segmented">
            <label><input type="radio" name="seg" checked />Easy</label>
            <label><input type="radio" name="seg" />Normal</label>
            <label><input type="radio" name="seg" />Hard</label>
          </div>
          <div class="cluster">
            <span class="caps">small, checkboxes</span>
            <div class="segmented small">
              <label><input type="checkbox" checked />ACC</label>
              <label><input type="checkbox" />RES</label>
              <label><input type="checkbox" checked />ATK</label>
              <label><input type="checkbox" />HP</label>
            </div>
          </div>
          <div class="switch-rows">
            <label>
              <span class="row-name">Reserved gear</span><span class="row-note">3 rules</span>
              <input type="checkbox" role="switch" checked />
            </label>
            <label>
              <span class="row-name">Locked champions</span>
              <select class="small">
                <option>above 3</option>
              </select>
            </label>
            <label>
              <span class="row-name">Worn by others</span><input type="checkbox" role="switch" />
            </label>
          </div>
        </article>
        <article class="panel stack" style="--space: var(--space-m)">
          <header class="panel-head"><h3>Tabs and stats</h3></header>
          <nav class="page-tabs">
            <a href="#" aria-current="page">Swaps <span class="badge">4</span></a>
            <a href="#">Roll <span class="badge">12</span></a>
            <a href="#">Clean up</a>
          </nav>
          <dl class="stat-tiles well">
            <div>
              <dt>HP</dt>
              <dd>48,210</dd>
            </div>
            <div>
              <dt>ATK</dt>
              <dd>1,544</dd>
            </div>
            <div>
              <dt>DEF</dt>
              <dd>3,902</dd>
            </div>
            <div>
              <dt>SPD</dt>
              <dd class="up">241</dd>
            </div>
            <div>
              <dt>C.RATE</dt>
              <dd>100%</dd>
            </div>
            <div>
              <dt>ACC</dt>
              <dd class="down">180</dd>
            </div>
          </dl>
          <div class="stat-tiles edit">
            <label
              ><span class="caps">SPD</span><input type="number" class="bare" value="4"
            /></label>
            <label
              ><span class="caps">ATK</span><input type="number" class="bare" value="5"
            /></label>
            <label class="zero">
              <span class="caps">HP</span><input type="number" class="bare" value="0" />
            </label>
            <label>
              <span class="caps">C.DMG</span><input type="number" class="bare" value="5" />
            </label>
          </div>
        </article>
      </div>
    </section>

    <section class="page-section stack" style="--space: var(--space-m)">
      <h2>Filter bar</h2>
      <form class="filter-bar" @submit.prevent>
        <input v-model="filter.text" type="search" placeholder="Name" aria-label="Name" />
        <select v-model="filter.faction" aria-label="Faction">
          <option value="">Any faction</option>
          <option value="Orcs">Orcs</option>
          <option value="Dwarves">Dwarves</option>
        </select>
        <div class="segmented small">
          <label><input v-model="filter.kind" type="radio" value="" />All <small>3</small></label>
          <label>
            <input v-model="filter.kind" type="radio" value="damage" />Damage <small>2</small>
          </label>
          <label>
            <input v-model="filter.kind" type="radio" value="support" />Support <small>1</small>
          </label>
        </div>
        <span class="filter-count caps">{{ filtered.length }} shown</span>
      </form>
      <ul class="cluster">
        <li v-for="item in filtered" :key="item.label" class="chip">{{ item.label }}</li>
      </ul>
    </section>

    <section class="page-section stack" style="--space: var(--space-m)">
      <h2>Containers</h2>
      <div class="grid" style="--min: 16rem; --space: var(--space-l); --align: start">
        <article class="panel stack" style="--space: var(--space-m)">
          <header class="panel-head">
            <h3>Panel</h3>
            <span class="badge info">info</span>
          </header>
          <p class="note">A note explains the panel.</p>
          <div class="well">A well, an inset back down on the slab.</div>
        </article>
        <div class="slot"><strong>A slot</strong><span class="muted">Something placed</span></div>
        <div class="slot empty">+ An empty slot</div>
        <article>
          <header>Plain article</header>
          Plain <code>&lt;article&gt;</code>.
          <footer>Footer</footer>
        </article>
      </div>
      <div class="table-well">
        <table class="striped">
          <thead>
            <tr>
              <th>Piece</th>
              <th>Set</th>
              <th>Value</th>
              <th>Change</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Weapon</td>
              <td>Speed</td>
              <td>12.4</td>
              <td class="up">+2.1</td>
            </tr>
            <tr>
              <td>Helmet</td>
              <td>Lifesteal</td>
              <td>8.9</td>
              <td class="down">−0.6</td>
            </tr>
            <tr>
              <td>Shield</td>
              <td>Mercurial</td>
              <td>10.2</td>
              <td>—</td>
            </tr>
            <tr>
              <td>Gauntlets</td>
              <td>Merciless</td>
              <td>9.7</td>
              <td class="up">+0.3</td>
            </tr>
          </tbody>
        </table>
      </div>
      <details class="section" open>
        <summary><h2>A collapsible section</h2></summary>
        <p>Its diamond turns when it opens.</p>
      </details>
    </section>

    <section class="page-section stack" style="--space: var(--space-m)">
      <h2>Gear</h2>
      <div class="gear-pair" style="container: page / inline-size">
        <div class="gear-card candidate stack" style="--space: var(--space-xs)">
          <div class="cluster" style="--justify: space-between">
            <span class="caps">Take</span><span class="note"><strong>14.2</strong> score</span>
          </div>
          <PieceCard :piece="legend" :champion="someone" />
        </div>
        <span class="gear-pair-arrow">→</span>
        <div class="gear-card worn stack" style="--space: var(--space-xs)">
          <div class="cluster" style="--justify: space-between">
            <span class="caps">Replaces</span><span class="note"><strong>9.1</strong> score</span>
          </div>
          <PieceCard :piece="epic" :champion="someone" />
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.count-mark {
  font-weight: 700;
  color: var(--warning);
}

/* The palette's own scaffolding: swatches, the surface ladder, rarity labels. */
.swatch {
  overflow: hidden;
  border: 1px solid var(--outline-variant);
  border-radius: var(--radius-panel);
}

.swatch-chip {
  display: grid;
  place-items: center;
  height: 3.25rem;
  font-weight: 700;
}

.swatch-meta {
  padding: var(--space-xs) var(--space-s);
  background: var(--surface-container-low);
}

.layers {
  padding: var(--space-l);
  border: 1px solid var(--outline-variant);
  background: var(--surface);
}

.layers > div,
.text-on {
  padding: var(--space-l);
  border: 1px solid var(--outline-variant);
  border-radius: var(--radius-panel);
}

.rarities span {
  padding: var(--space-2xs) var(--space-s);
  border: 2px solid var(--rarity);
  border-radius: var(--radius);
  font-weight: 700;
  color: var(--rarity);
}
</style>
