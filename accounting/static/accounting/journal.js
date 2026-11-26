const addLine = document.getElementById("journal-add-line");
const total = document.getElementById("id_lines-TOTAL_FORMS");
const rows = document.getElementById("journal-lines");
const template = document.getElementById("journal-empty-line");

addLine.addEventListener("click", () => {
  const index = Number(total.value);
  if (index >= 50) return;
  rows.insertAdjacentHTML("beforeend", template.innerHTML.replaceAll("__prefix__", index));
  total.value = index + 1;
  if (index + 1 === 50) addLine.disabled = true;
  rows.lastElementChild.querySelector("select").focus();
});
