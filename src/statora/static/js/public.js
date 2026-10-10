// Show timestamps in the visitor's local time zone.
function localizeTimes(root) {
  var fmt = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
  root.querySelectorAll("time[datetime]").forEach(function (el) {
    var date = new Date(el.getAttribute("datetime"));
    if (isNaN(date)) return;
    el.title = date.toISOString();
    if (el.hasAttribute("data-relative")) {
      el.textContent = date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
    } else {
      el.textContent = fmt.format(date);
    }
  });
}
localizeTimes(document);

// Keep expanded groups open across the periodic HTMX refresh.
var openGroups = new Set();
document.body.addEventListener("htmx:beforeSwap", function (event) {
  openGroups = new Set(Array.from(event.target.querySelectorAll("details.members[open]"), function (d) {
    return d.dataset.key;
  }));
});
document.body.addEventListener("htmx:afterSwap", function (event) {
  localizeTimes(event.target);
  event.target.querySelectorAll("details.members").forEach(function (d) {
    if (openGroups.has(d.dataset.key)) d.open = true;
  });
});

// Light/dark toggle; the choice is shared with the admin panel ("statora-theme").
(function () {
  var button = document.getElementById("theme-toggle");
  if (!button) return;
  button.hidden = false;
  button.addEventListener("click", function () {
    var root = document.documentElement;
    var current = root.getAttribute("data-theme") ||
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    var next = current === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("statora-theme", next); } catch (e) {}
  });
})();
