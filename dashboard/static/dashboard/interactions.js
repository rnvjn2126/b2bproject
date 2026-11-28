const menus = document.querySelectorAll(".topbar details");

document.addEventListener("keydown", event => {
  if (event.key !== "Escape") return;
  for (const menu of menus) {
    if (menu.open) {
      menu.open = false;
      menu.querySelector("summary").focus();
    }
  }
});

document.addEventListener("click", event => {
  for (const menu of menus) {
    if (!menu.contains(event.target)) menu.open = false;
  }
});

// Keep the submitter enabled so Django receives the selected action.
document.addEventListener("submit", event => {
  if (!event.defaultPrevented) event.target.setAttribute("aria-busy", "true");
});
window.addEventListener("pageshow", () => {
  document.querySelectorAll('form[aria-busy]').forEach(form => form.removeAttribute("aria-busy"));
});

function addFormRows(buttonId, totalId, templateId, listId) {
  const button = document.getElementById(buttonId);
  if (!button) return;
  const total = document.getElementById(totalId);
  const maximum = Number(button.dataset.max || Infinity);
  button.disabled = Number(total.value) >= maximum;
  button.addEventListener("click", () => {
    const index = Number(total.value);
    if (index >= maximum) return;
    const html = document.getElementById(templateId).innerHTML.replaceAll("__prefix__", index);
    document.getElementById(listId).insertAdjacentHTML("beforeend", html);
    total.value = index + 1;
    button.disabled = Number(total.value) >= maximum;
  });
}

addFormRows("add-line", "id_lines-TOTAL_FORMS", "empty-line", "rfq-lines");
addFormRows("add-output", "id_outputs-TOTAL_FORMS", "empty-output", "cut-outputs");
