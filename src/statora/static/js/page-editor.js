// Status page components editor (admin/page_form.html): groups, items, drag and drop.
// The page passes its data as JSON in #groups' data-monitors and data-groups attributes.
(function () {
  var container = document.getElementById("groups");
  var monitors = JSON.parse(container.dataset.monitors);
  var initial = JSON.parse(container.dataset.groups);
  var byId = {};
  monitors.forEach(function (m) { byId[m.id] = m; });

  function move(el, dir) {
    if (dir < 0 && el.previousElementSibling) el.parentNode.insertBefore(el, el.previousElementSibling);
    if (dir > 0 && el.nextElementSibling) el.parentNode.insertBefore(el.nextElementSibling, el);
  }

  // Drag and drop: an element is draggable only while its handle is held, so text in the
  // inputs can still be selected. Monitors can also be dropped into another group.
  var dragged = null;

  function draggable(el) {
    el.querySelector(".drag-handle").addEventListener("mousedown", function () { el.draggable = true; });
    el.addEventListener("dragstart", function (e) {
      if (!el.draggable) return;
      e.stopPropagation(); // dragging a monitor must not drag its group
      dragged = el;
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", "");
      setTimeout(function () { el.classList.add("dragging"); });
    });
    el.addEventListener("dragend", function (e) {
      e.stopPropagation();
      el.draggable = false;
      el.classList.remove("dragging");
      dragged = null;
    });
  }

  function sortable(list, kind) {
    list.addEventListener("dragover", function (e) {
      if (!dragged || !dragged.classList.contains(kind)) return;
      e.preventDefault();
      e.stopPropagation();
      var before = Array.from(list.children).find(function (child) {
        var box = child.getBoundingClientRect();
        return child !== dragged && child.classList.contains(kind) && e.clientY < box.top + box.height / 2;
      });
      if (before) { if (before.previousElementSibling !== dragged) list.insertBefore(dragged, before); }
      else if (list.lastElementChild !== dragged) list.appendChild(dragged);
    });
    list.addEventListener("drop", function (e) {
      if (dragged && dragged.classList.contains(kind)) e.preventDefault();
    });
  }

  document.addEventListener("mouseup", function () {
    container.querySelectorAll("[draggable=true]").forEach(function (el) { if (el !== dragged) el.draggable = false; });
  });
  sortable(container, "group-card");

  function addItem(groupEl, item) {
    var m = byId[item.monitor_id];
    if (!m) return;
    var el = document.getElementById("item-template").content.firstElementChild.cloneNode(true);
    el.dataset.monitorId = m.id;
    el.querySelector(".item-type").textContent = m.type.toUpperCase();
    el.querySelector(".item-monitor").textContent = m.name;
    el.querySelector(".item-label").value = item.display_name || "";
    el.querySelector(".item-label").placeholder = m.name;
    el.querySelector(".item-up").onclick = function () { move(el, -1); };
    el.querySelector(".item-down").onclick = function () { move(el, 1); };
    el.querySelector(".item-remove").onclick = function () { el.remove(); };
    draggable(el);
    groupEl.querySelector(".items").appendChild(el);
  }

  function addGroup(group) {
    var el = document.getElementById("group-template").content.firstElementChild.cloneNode(true);
    el.querySelector(".group-name").value = group.name || "";
    var select = el.querySelector(".add-item");
    monitors.forEach(function (m) {
      var opt = document.createElement("option");
      opt.value = m.id; opt.textContent = m.name + " (" + m.type.toUpperCase() + ")";
      select.appendChild(opt);
    });
    select.onchange = function () {
      if (select.value) addItem(el, { monitor_id: Number(select.value) });
      select.value = "";
    };
    el.querySelector(".move-up").onclick = function () { move(el, -1); };
    el.querySelector(".move-down").onclick = function () { move(el, 1); };
    el.querySelector(".remove").onclick = function () { el.remove(); };
    draggable(el);
    sortable(el.querySelector(".items"), "group-item");
    (group.items || []).forEach(function (item) { addItem(el, item); });
    container.appendChild(el);
  }

  document.getElementById("add-group").onclick = function () { addGroup({ name: "", items: [] }); };
  initial.forEach(addGroup);
  if (!initial.length) addGroup({ name: "Services", items: [] });

  document.getElementById("page-form").addEventListener("submit", function () {
    var groups = Array.from(container.querySelectorAll(".group-card")).map(function (g) {
      return {
        name: g.querySelector(".group-name").value.trim(),
        items: Array.from(g.querySelectorAll(".group-item")).map(function (i) {
          var label = i.querySelector(".item-label").value.trim();
          return { monitor_id: Number(i.dataset.monitorId), display_name: label || null };
        })
      };
    });
    document.getElementById("groups_json").value = JSON.stringify(groups);
  });
})();
