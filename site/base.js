// Shared page behaviour. v1.0.0
// Copy buttons: <button class="btn btn-small copy" data-copy="element-id">Copy</button>
document.querySelectorAll("[data-copy]").forEach((button) => {
  const label = button.textContent;
  button.addEventListener("click", async () => {
    const source = document.getElementById(button.dataset.copy);
    if (!source) return;
    try {
      await navigator.clipboard.writeText(source.innerText);
      button.textContent = "Copied";
    } catch {
      button.textContent = "Copy failed, select the text";
    }
    setTimeout(() => {
      button.textContent = label;
    }, 1500);
  });
});
