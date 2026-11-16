// Shapes the components share across the generated views.
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
  crest_url?: string | null;
  crest_top_url?: string | null;
}
