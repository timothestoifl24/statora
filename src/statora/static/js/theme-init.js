// Applies the saved light/dark theme before the first paint. Loaded without defer in <head>.
// Admin and sign-in pages (Tabler) use data-bs-theme and fall back to the system setting;
// public status pages use data-theme and leave it unset so their CSS follows the system.
(function () {
  var root = document.documentElement;
  var publicPage = document.currentScript && document.currentScript.dataset.page === "public";
  var theme = null;
  try { theme = localStorage.getItem("statora-theme"); } catch (e) {}
  if (publicPage) {
    if (theme) root.setAttribute("data-theme", theme);
    return;
  }
  if (!theme) theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  root.setAttribute("data-bs-theme", theme);
})();
