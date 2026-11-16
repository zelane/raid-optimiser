// Shapes the components share across the generated views.
import type { SlotView } from "./generated/webui.service.team";
import type { StarView } from "./generated/webui.service.views";

// Anything drawn as a champion's tile: a champion (`ChampionRow`), or an enemy of the target
// picker (`EnemyCard`: no level or stars).
export interface TileView {
  name: string;
  rarity: string;
  portrait_url: string | null;
  affinity: string;
  affinity_icon_url: string | null;
  level?: number;
  grade?: number;
  ascension?: number;
  awakening?: number;
  empower?: number;
  stars?: StarView[];
}

// A team a search found, as the team finder's and the Chimera page's options both have it.
export interface TeamOptionView {
  number: number;
  slots: SlotView[];
  score: number;
  show_url: string;
  use_url: string;
  gear_url: string;
}
