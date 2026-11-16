// A command to the game (equip, preview, sync, sell) or a setting saved in place: posted as
// form data, answered with JSON: `error`, or null when it was done.

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
