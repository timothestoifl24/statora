// Two-column picker for <select multiple data-dual-list>: "Available" on the left, "Selected" on the
// right; clicking an entry moves it across. The original <select> stays in the form (hidden) and
// remains the source of truth, so form submission and server code are unchanged.
(function () {
  "use strict";

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function buildPane(title, actionLabel, emptyText, icon) {
    var pane = el("div", "dual-pane card");
    var head = el("div", "card-header dual-head");
    var heading = el("h4", "card-title", title);
    var count = el("span", "badge bg-secondary-lt ms-2", "0");
    heading.appendChild(count);
    var bulk = el("button", "btn btn-sm btn-ghost-primary ms-auto", actionLabel);
    bulk.type = "button";
    head.append(heading, bulk);

    var search = el("input", "form-control form-control-sm");
    search.type = "search";
    search.placeholder = "Filter…";
    search.setAttribute("aria-label", "Filter " + title.toLowerCase());
    var searchWrap = el("div", "dual-search");
    searchWrap.appendChild(search);

    var list = el("div", "list-group list-group-flush dual-items");
    list.setAttribute("role", "list");
    list.setAttribute("aria-label", title);
    pane.append(head, searchWrap, list);
    return { pane: pane, list: list, count: count, bulk: bulk, search: search, emptyText: emptyText, icon: icon };
  }

  function init(select) {
    if (select.dataset.dualReady) return;
    select.dataset.dualReady = "1";
    var noun = select.dataset.noun || "items";
    var left = buildPane(select.dataset.availableLabel || "Available", "Add all", "All " + noun + " selected.", "fa-solid fa-plus");
    var right = buildPane(select.dataset.selectedLabel || "Selected", "Remove all", "Nothing selected yet.", "fa-solid fa-xmark");
    var wrapper = el("div", "dual-list");
    wrapper.append(left.pane, right.pane);
    select.hidden = true;
    select.after(wrapper);

    // Clicking the field's <label> focuses the left filter.
    if (select.id) {
      var label = document.querySelector('label[for="' + select.id + '"]');
      if (label) label.htmlFor = (left.search.id = select.id + "-filter");
    }

    function matches(option, query) {
      return !query || option.text.toLowerCase().indexOf(query) !== -1;
    }

    function fill(side, selected) {
      var query = side.search.value.trim().toLowerCase();
      side.list.replaceChildren();
      var total = 0;
      Array.prototype.forEach.call(select.options, function (option) {
        if (option.selected !== selected) return;
        total += 1;
        if (!matches(option, query)) return;
        var item = el("button", "list-group-item list-group-item-action dual-item");
        item.type = "button";
        item.title = (selected ? "Remove " : "Add ") + option.text;
        item.append(el("span", "text-truncate", option.text), el("i", side.icon + " ms-auto"));
        item.addEventListener("click", function () {
          option.selected = !selected;
          render();
          select.dispatchEvent(new Event("change", { bubbles: true }));
        });
        side.list.appendChild(item);
      });
      side.count.textContent = total;
      if (!side.list.children.length) {
        side.list.appendChild(el("div", "dual-empty text-secondary small", total ? "No matches." : side.emptyText));
      }
      side.bulk.disabled = total === 0;
    }

    function render() {
      fill(left, false);
      fill(right, true);
    }

    function moveVisible(fromSelected) {
      var query = (fromSelected ? right : left).search.value.trim().toLowerCase();
      Array.prototype.forEach.call(select.options, function (option) {
        if (option.selected === fromSelected && matches(option, query)) option.selected = !fromSelected;
      });
      render();
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    left.bulk.addEventListener("click", function () { moveVisible(false); });
    right.bulk.addEventListener("click", function () { moveVisible(true); });
    left.search.addEventListener("input", render);
    right.search.addEventListener("input", render);
    render();
  }

  function scan(root) {
    if (!root || !root.querySelectorAll) return;
    if (root.matches && root.matches("select[data-dual-list]")) init(root);
    root.querySelectorAll("select[data-dual-list]").forEach(init);
  }

  scan(document);
  // Content swapped in by HTMX (e.g. the group settings when choosing the monitor type).
  document.addEventListener("htmx:load", function (event) { scan(event.detail.elt); });
})();
