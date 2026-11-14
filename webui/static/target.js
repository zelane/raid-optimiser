// The target picker (_target_picker.html): htmx re-renders it on every change. When a render
// is the user's pick (data-fill), it announces it with a "target:picked" event, which bubbles
// from the picker; the page decides what to fill in. `showTarget` re-renders it for a saved
// target ("<stage>:<wave>:<slot>") without announcing anything.
htmx.onLoad((content) => {
  const pickers = content.matches?.(".target-picker")
    ? [content]
    : content.querySelectorAll?.(".target-picker") ?? [];

  for (const picker of pickers) {
    if (picker.dataset.fill !== "true") continue;

    picker.dispatchEvent(
      new CustomEvent("target:picked", {
        bubbles: true,
        detail: { defence: Number(picker.dataset.defence), title: picker.dataset.title },
      }),
    );
  }
});

function showTarget(target) {
  const picker = document.getElementById("target-picker");
  if (!picker || !target) return Promise.resolve();

  return htmx.ajax("GET", "/targets", { source: picker, target: picker, swap: "outerHTML", values: { target } });
}
