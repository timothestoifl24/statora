// Latency chart on the monitor detail page (admin/monitor_detail.html); data comes from #latency-data.
(function () {
  var chart = null, chartEl = null;
  // (Re)draws the chart after the first load and after every refresh of #monitor-live.
  function render() {
    var el = document.getElementById("latency-chart");
    var data = document.getElementById("latency-data");
    if (chart && chartEl !== el) { chart.destroy(); chart = null; }
    if (!el || !data || chart) return;
    var dark = document.documentElement.getAttribute("data-bs-theme") === "dark";
    chartEl = el;
    chart = new ApexCharts(el, {
      chart: { type: "area", height: 260, toolbar: { show: false }, animations: { enabled: false },
               background: "transparent", fontFamily: "inherit" },
      theme: { mode: dark ? "dark" : "light" },
      series: [{ name: "Latency (ms)", data: JSON.parse(data.textContent) }],
      xaxis: { type: "datetime", labels: { datetimeUTC: false } },
      yaxis: { labels: { formatter: function (v) { return v == null ? "" : Math.round(v) + " ms"; } } },
      stroke: { width: 2, curve: "smooth" },
      fill: { type: "gradient", gradient: { opacityFrom: 0.35, opacityTo: 0.05 } },
      dataLabels: { enabled: false },
      colors: ["#1f6feb"],
      tooltip: { x: { format: "HH:mm:ss" } },
      grid: { strokeDashArray: 4 }
    });
    chart.render();
  }
  document.addEventListener("DOMContentLoaded", render);
  document.addEventListener("htmx:afterSettle", render);
})();
