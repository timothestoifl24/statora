// Image reference inputs (admin/_macros.html: image_ref_input): upload, Font Awesome picker, clear.
(function () {
  var csrf = document.querySelector('meta[name="csrf-token"]')?.content;
  var index = null; // [[name, style, terms], ...] from icons-index.json, loaded on first use
  var STYLE_CLASS = { solid: "fa-solid", regular: "fa-regular", brands: "fa-brands" };
  var LIMIT = 120;

  var FA_REF = /^fa:(solid|regular|brands):([a-z0-9-]+)$/;
  var MEDIA_REF = /^media:[0-9a-f]{64}$/;

  function showPreview(box, el) {
    var target = box.querySelector(".ref-preview");
    target.querySelectorAll(":scope > :not(.ref-empty)").forEach(function (old) { old.remove(); });
    target.classList.toggle("has-icon", !!el);
    if (el) target.prepend(el);
  }

  // Font Awesome icons are drawn here; anything else is checked by the server, which answers with
  // a safe image URL (an upload or a valid https URL) or nothing. Typed text never becomes a src.
  var pending = new WeakMap();
  function preview(box, ref) {
    var fa = FA_REF.exec(ref);
    if (fa || !ref) {
      var icon = null;
      if (fa) {
        icon = document.createElement("i");
        icon.className = STYLE_CLASS[fa[1]] + " fa-" + fa[2];
      }
      showPreview(box, icon);
      return;
    }
    clearTimeout(pending.get(box));
    pending.set(box, setTimeout(function () {
      fetch("/admin/media/preview?ref=" + encodeURIComponent(ref), { headers: { Accept: "application/json" } })
        .then(function (r) { return r.ok ? r.json() : { src: null }; })
        .then(function (data) {
          if (box.querySelector(".ref-value").value.trim() !== ref) return; // typed on meanwhile
          var img = null;
          if (data.src) {
            img = document.createElement("img");
            img.alt = "";
            img.referrerPolicy = "no-referrer";
            img.src = data.src;
          }
          showPreview(box, img);
        })
        .catch(function () { showPreview(box, null); });
    }, 250));
  }

  function setValue(box, ref) {
    var input = box.querySelector(".ref-value");
    input.value = ref;
    preview(box, ref);
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function showError(box, message) {
    var err = box.querySelector(".ref-error");
    err.textContent = message || "";
    err.hidden = !message;
  }

  function upload(box, file) {
    var body = new FormData();
    body.append("file", file);
    showError(box, "");
    box.classList.add("is-uploading");
    fetch("/admin/media", { method: "POST", body: body, headers: { "X-CSRF-Token": csrf } })
      .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
      .then(function (res) {
        if (!res.ok) throw new Error(res.data.detail || "Upload failed");
        if (!MEDIA_REF.test(res.data.ref)) throw new Error("Upload failed");
        setValue(box, res.data.ref);
      })
      .catch(function (e) { showError(box, e.message); })
      .finally(function () { box.classList.remove("is-uploading"); });
  }

  function loadIndex() {
    if (index) return Promise.resolve(index);
    var src = document.documentElement.dataset.faIndex || "/static/vendor/fontawesome/icons-index.json";
    return fetch(src).then(function (r) { return r.json(); }).then(function (data) { index = data; return data; });
  }

  function renderGrid(box) {
    var grid = box.querySelector(".ref-grid");
    var hint = box.querySelector(".ref-hint");
    var words = box.querySelector(".ref-search").value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    var current = box.querySelector(".ref-value").value;
    var matches = index.filter(function (icon) {
      var hay = icon[0] + " " + icon[1] + " " + icon[2];
      return words.every(function (w) { return hay.indexOf(w) !== -1; });
    });
    grid.replaceChildren();
    matches.slice(0, LIMIT).forEach(function (icon) {
      var ref = "fa:" + icon[1] + ":" + icon[0];
      var button = document.createElement("button");
      button.type = "button";
      button.className = "ref-option";
      button.title = icon[0] + (icon[1] === "solid" ? "" : " (" + icon[1] + ")");
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", String(ref === current));
      button.dataset.ref = ref;
      var i = document.createElement("i");
      i.className = STYLE_CLASS[icon[1]] + " fa-" + icon[0];
      button.append(i);
      grid.append(button);
    });
    hint.textContent = matches.length > LIMIT
      ? "Showing " + LIMIT + " of " + matches.length + " icons. Type to narrow it down."
      : matches.length ? "" : "No icons match.";
  }

  function togglePicker(box, open) {
    var picker = box.querySelector(".ref-picker");
    var button = box.querySelector(".ref-pick");
    picker.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
    if (!open) return;
    loadIndex().then(function () { renderGrid(box); box.querySelector(".ref-search").focus(); });
  }

  document.addEventListener("change", function (event) {
    var file = event.target.closest(".ref-file");
    if (file && file.files[0]) { upload(file.closest("[data-ref-input]"), file.files[0]); file.value = ""; }
  });
  document.addEventListener("input", function (event) {
    var box = event.target.closest("[data-ref-input]");
    if (!box) return;
    if (event.target.classList.contains("ref-search")) renderGrid(box);
    if (event.target.classList.contains("ref-value")) { showError(box, ""); preview(box, event.target.value.trim()); }
  });
  document.addEventListener("click", function (event) {
    var box = event.target.closest("[data-ref-input]");
    if (!box) return;
    if (event.target.closest(".ref-clear")) { setValue(box, ""); showError(box, ""); return; }
    if (event.target.closest(".ref-pick")) { togglePicker(box, box.querySelector(".ref-picker").hidden); return; }
    var option = event.target.closest(".ref-option");
    if (option) { setValue(box, option.dataset.ref); togglePicker(box, false); }
  });
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    var box = event.target.closest("[data-ref-input]");
    if (box && box.querySelector(".ref-picker") && !box.querySelector(".ref-picker").hidden) {
      event.preventDefault();
      event.stopPropagation(); // keep a surrounding modal open
      togglePicker(box, false);
      box.querySelector(".ref-pick").focus();
    }
  }, true);
})();
