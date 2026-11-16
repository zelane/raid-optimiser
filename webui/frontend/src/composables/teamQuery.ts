// A team page's state is its query (`service.team.PageUrl`): a change starts from the state as
// the page's form would send it (`links.current`, plus `run` once a search ran, so it searches
// again), edits it, and visits the page with it. Repeated fields (`slot`, `relic`) are one per
// team slot.
import { router } from "@inertiajs/vue3";
import type { TeamLinks } from "../types/generated/webui.service.team";

export const TEAM_SIZE = 5;

export function teamQuery(links: TeamLinks, ran: boolean): URLSearchParams {
  const query = new URL(links.current, window.location.origin).searchParams;
  if (ran) query.set("run", "true");
  return query;
}

export function setAt(query: URLSearchParams, name: string, index: number, value: string) {
  const values = query.getAll(name);
  while (values.length < TEAM_SIZE) values.push("");
  values[index] = value;
  query.delete(name);
  for (const each of values) query.append(name, each);
}

export function visitWith(query: URLSearchParams) {
  visitTeamPage(`${window.location.pathname}?${query}`);
}

export function visitTeamPage(url: string) {
  router.get(url, {}, { preserveState: true, preserveScroll: true });
}

// The slots' changes on a team page: a champion placed in a slot (its relic back to what they
// wear), or a slot's relic picked; the search runs again if it ran.
export function slotEdits(links: TeamLinks, ran: boolean) {
  return {
    place(slot: number, choice: string) {
      const query = teamQuery(links, ran);
      setAt(query, "slot", slot, choice);
      setAt(query, "relic", slot, "");
      visitWith(query);
    },
    wear(slot: number, relic: string) {
      const query = teamQuery(links, ran);
      setAt(query, "relic", slot, relic);
      visitWith(query);
    },
  };
}
