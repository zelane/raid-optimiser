// Accessory clean-up: the "All" box ticks or unticks every piece, and the button counts the
// ticked ones. Delegated, since the list is swapped in again whenever a weight changes.
document.addEventListener("change", (event) => {
  const form = event.target.closest("form.sell");
  if (!form) return;

  const boxes = form.querySelectorAll("input[name=artifact_id]");
  if (event.target.matches(".sell-all")) boxes.forEach((box) => (box.checked = event.target.checked));

  const ticked = [...boxes].filter((box) => box.checked).length;
  form.querySelector(".sell-count").textContent = ticked;
  form.querySelector(".sell-all").checked = ticked === boxes.length;
});
