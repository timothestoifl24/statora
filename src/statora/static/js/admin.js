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
