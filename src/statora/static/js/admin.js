// Theme toggle (persisted per browser).
document.getElementById("theme-toggle")?.addEventListener("click", function () {
  var root = document.documentElement;
  var next = root.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
  root.setAttribute("data-bs-theme", next);
  try { localStorage.setItem("statora-theme", next); } catch (e) {}
});

// Confirm destructive actions: <form data-confirm="Delete this?">.
document.addEventListener("submit", function (event) {
  var message = event.target.getAttribute("data-confirm");
  if (message && !window.confirm(message)) event.preventDefault();
});

// Copy buttons: <button data-copy="#element-id">.
document.addEventListener("click", function (event) {
  var button = event.target.closest("[data-copy]");
  if (!button) return;
  var el = document.querySelector(button.getAttribute("data-copy"));
  if (!el) return;
  navigator.clipboard.writeText(el.value || el.textContent.trim()).then(function () {
    var label = button.innerHTML;
    button.innerHTML = '<i class="fa-solid fa-check"></i> Copied';
    setTimeout(function () { button.innerHTML = label; }, 1500);
  });
});

// Monitor list: search, filter chips and expanded groups. The rows are replaced by the
// 15s HTMX refresh, so the state lives here and is re-applied after every swap.
(function () {
  var search = document.getElementById("monitor-search");
  if (!search) return;
  var STORE = "statora-monitor-filter";
  var state = { filter: "all", open: [] };
  try { Object.assign(state, JSON.parse(localStorage.getItem(STORE)) || {}); } catch (e) {}

  function save() {
    try { localStorage.setItem(STORE, JSON.stringify({ filter: state.filter, open: state.open })); } catch (e) {}
  }

  function matches(row, query) {
    var status = row.dataset.status, type = row.dataset.type;
    if (state.filter === "problems" && status !== "down" && status !== "degraded") return false;
    if (state.filter !== "all" && state.filter !== "problems" && type !== state.filter) return false;
    return !query || row.dataset.name.indexOf(query) !== -1;
  }

  function apply() {
    var query = search.value.trim().toLowerCase();
    var shown = 0;
    document.querySelectorAll(".filter-chip").forEach(function (chip) {
      chip.setAttribute("aria-pressed", String(chip.dataset.filter === state.filter));
    });
    document.querySelectorAll("[data-status][data-name]").forEach(function (row) {
      var visible = matches(row, query);
      row.hidden = !visible;
      if (visible) shown++;
    });
    document.querySelectorAll(".group-toggle").forEach(function (button) {
      var id = button.dataset.group;
      var open = state.open.indexOf(id) !== -1;
      var parentRow = button.closest("[data-status]");
      button.setAttribute("aria-expanded", String(open));
      document.querySelectorAll('.member-row[data-parent="' + id + '"]').forEach(function (row) {
        row.hidden = !open || parentRow.hidden;
      });
    });
    var empty = document.querySelector(".filter-empty");
    if (empty) empty.hidden = shown > 0;
  }

  search.addEventListener("input", apply);
  document.addEventListener("click", function (event) {
    var chip = event.target.closest(".filter-chip");
    if (chip) {
      state.filter = chip.dataset.filter;
      save();
      apply();
      return;
    }
    var toggle = event.target.closest(".group-toggle");
    if (toggle) {
      var id = toggle.dataset.group;
      var at = state.open.indexOf(id);
      if (at === -1) state.open.push(id); else state.open.splice(at, 1);
      save();
      apply();
    }
  });
  document.body.addEventListener("htmx:afterSwap", apply);

  // Shortcuts: "/" focuses the search, "n" opens the new-monitor form.
  document.addEventListener("keydown", function (event) {
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    var target = event.target;
    if (target.closest("input, textarea, select, [contenteditable]")) {
      if (event.key === "Escape" && target === search) { search.value = ""; apply(); search.blur(); }
      return;
    }
    if (event.key === "/") { event.preventDefault(); search.focus(); }
    var link = document.querySelector('[data-shortcut="' + event.key + '"]');
    if (link) { event.preventDefault(); link.click(); }
  });

  apply();
})();

// Status page settings modal: HTMX loads the form into #page-modal-content, then we show it.
document.body.addEventListener("htmx:afterSwap", function (event) {
  if (event.detail.target.id !== "page-modal-content") return;
  var modal = document.getElementById("page-modal");
  var Modal = (window.tabler || window.bootstrap).Modal; // Tabler bundles Bootstrap's components
  Modal.getOrCreateInstance(modal).show();
  modal.addEventListener("shown.bs.modal", function () {
    modal.querySelector("input:not([type=hidden])")?.focus();
  }, { once: true });
});

// New page: fill the slug from the title until the slug is edited by hand.
document.addEventListener("input", function (event) {
  var form = event.target.closest("form");
  if (!form) return;
  var slug = form.querySelector("[data-slug-target]");
  if (!slug) return;
  if (event.target === slug) { slug.dataset.touched = "1"; return; }
  if (event.target.matches("[data-slug-source]") && !slug.dataset.touched) {
    slug.value = event.target.value.toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "")
      .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 100);
  }
});
