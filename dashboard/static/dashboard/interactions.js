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

document.getElementById("add-line")?.addEventListener("click", () => {
  const total = document.getElementById("id_lines-TOTAL_FORMS");
  const index = Number(total.value);
  const html = document.getElementById("empty-line").innerHTML.replaceAll("__prefix__", index);
  document.getElementById("rfq-lines").insertAdjacentHTML("beforeend", html);
  total.value = index + 1;
});
