// Small text and tone helpers the components share: a count with its noun, a score's tone, and
// what a changed field holds.

// "1 build", "3 builds"; `many` for a plural that isn't the noun plus "s" ("copies").
export function plural(count: number, noun: string, many = `${noun}s`) {
  return `${count} ${count === 1 ? noun : many}`;
}

// A score (%) by how far it can be counted on.
export function scoreTone(score: number) {
  return score >= 75 ? "good" : score >= 45 ? "mid" : "bad";
}

// The value of the field an input or change event came from.
export function valueOf(event: Event) {
  return (event.target as HTMLInputElement | HTMLSelectElement).value;
}

// Whether the checkbox an event came from is ticked.
export function checkedOf(event: Event) {
  return (event.target as HTMLInputElement).checked;
}
