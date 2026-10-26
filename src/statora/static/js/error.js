// "Go back" on error pages: back in history when there is one, otherwise the link's own target.
document.addEventListener("click", function (event) {
  var link = event.target.closest("[data-history-back]");
  if (link && window.history.length > 1) {
    event.preventDefault();
    window.history.back();
  }
});
