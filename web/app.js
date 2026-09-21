"use strict";
const papers = [...document.querySelectorAll(".paper")];
const search = document.querySelector("#search");
const source = document.querySelector("#source");
const flag = document.querySelector("#flag");
const bucket = document.querySelector("#bucket");
function applyFilters() {
  const terms = search.value.toLowerCase().trim().split(/\s+/).filter(Boolean);
  let visible = 0;
  for (const paper of papers) {
    const show = terms.every(term => paper.dataset.search.includes(term)) &&
      (!source.value || paper.dataset.sources.split(" ").includes(source.value)) &&
      (!flag.value || paper.dataset.flags.split(" ").includes(flag.value)) &&
      (!bucket.value || paper.dataset.buckets.split(" ").includes(bucket.value));
    paper.hidden = !show;
    if (show) visible++;
  }
  document.querySelector("#count").textContent = `${visible} of ${papers.length} articles`;
  document.querySelector("#empty").hidden = visible !== 0;
}
for (const control of [search, source, flag, bucket]) control.addEventListener("input", applyFilters);
document.querySelector("#reset").addEventListener("click", () => {
  for (const control of [search, source, flag, bucket]) control.value = "";
  applyFilters();
});
const updated = document.querySelector("#updated");
const stamp = new Date(updated.dateTime);
if (!Number.isNaN(stamp.getTime())) {
  updated.textContent = stamp.toLocaleString(undefined, {dateStyle: "medium", timeStyle: "short"});
  document.querySelector("#stale").hidden = Date.now() - stamp.getTime() < 36 * 60 * 60 * 1000;
}
applyFilters();
