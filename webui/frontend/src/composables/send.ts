// A component's own requests, answered with JSON rather than a page. Posted: a command to the
// game (equip, preview, sync, sell) or a setting saved in place, as form data, answered with
// `error`, or null when it was done (`Sent`; `SentNote` shows it). Fetched: a view a component
// draws itself (the finder's champions, the target picker).
import { router } from "@inertiajs/vue3";

export interface Sent {
  error: string | null;
}

export async function sendToGame(
  url: string,
  fields: Record<string, string> | URLSearchParams = {},
): Promise<Sent> {
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { Accept: "application/json" },
      body: new URLSearchParams(fields),
    });
    if (!response.ok) return { error: `${response.status} ${response.statusText}` };
    return (await response.json()) as Sent;
  } catch (error) {
    return { error: String(error) };
  }
}

// Equips the pieces on the champion in game (or previews them there: nothing changes). An
// equip syncs the account, so the page's views (worn gear, stats) reload after one.
export async function equipInGame(
  championId: number,
  artifactIds: number[],
  action: "equip" | "preview" = "equip",
): Promise<Sent> {
  const fields = { artifact_ids: artifactIds.join(",") };
  const sent = await sendToGame(`/champions/${championId}/${action}`, fields);
  if (action === "equip" && !sent.error) router.reload();
  return sent;
}

// A view as JSON, or null when the server couldn't give it.
export async function getJson<View>(url: string): Promise<View | null> {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  return response.ok ? ((await response.json()) as View) : null;
}
