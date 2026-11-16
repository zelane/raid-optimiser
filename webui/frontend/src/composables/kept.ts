// Values kept in this browser (localStorage) under a key: read back as they were saved, or
// nothing when storage is unavailable or the saved value isn't the shape asked for.

export function readKept<Name extends string>(
  key: string,
  names: readonly Name[],
): Partial<Record<Name, string>> {
  let saved: unknown = null;

  try {
    saved = JSON.parse(localStorage.getItem(key) ?? "null");
  } catch {
    return {};
  }

  if (typeof saved !== "object" || saved === null) return {};
  const values = saved as Record<string, unknown>;
  const kept: Partial<Record<Name, string>> = {};

  for (const name of names) {
    const value = values[name];
    if (typeof value === "string") kept[name] = value;
  }

  return kept;
}

export function writeKept(key: string, values: Record<string, string>) {
  try {
    localStorage.setItem(key, JSON.stringify(values));
  } catch {
    // Storage is off: nothing is remembered, nothing breaks.
  }
}
