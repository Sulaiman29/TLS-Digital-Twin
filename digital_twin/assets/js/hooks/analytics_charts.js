/**
 * AnalyticsCharts — Chart.js hook for the Tartu Digital Twin Analytics page
 *
 * Creates and live-updates 6 charts from server-pushed analytics data.
 * Uses the same dark theme palette as the rest of the dashboard.
 */

import {
  Chart,
  LineController,
  BarController,
  DoughnutController,
  LineElement,
  BarElement,
  ArcElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Filler,
  Tooltip,
  Legend,
} from "chart.js";

// Register only the components we need (tree-shaking friendly)
Chart.register(
  LineController,
  BarController,
  DoughnutController,
  LineElement,
  BarElement,
  ArcElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Filler,
  Tooltip,
  Legend
);

// --- Theme colors ---
const COLORS = {
  blue: "#4dabf7",
  green: "#00e676",
  red: "#ff1744",
  yellow: "#ffea00",
  orange: "#ff9100",
  purple: "#6c5ce7",
  cyan: "#00cec9",
  textPrimary: "#e8eaf6",
  textSecondary: "#9aa0b8",
  gridColor: "rgba(255, 255, 255, 0.06)",
  cardBg: "#22253a",
};

// --- Utility: create gradient fill ---
function createGradient(ctx, color, height = 300) {
  const gradient = ctx.createLinearGradient(0, 0, 0, height);
  gradient.addColorStop(0, color.replace(")", ", 0.35)").replace("rgb", "rgba"));
  gradient.addColorStop(1, color.replace(")", ", 0.02)").replace("rgb", "rgba"));
  return gradient;
}

function hexToRgba(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// --- Common chart options ---
const COMMON_LINE_OPTIONS = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 300 },
  interaction: { mode: "index", intersect: false },
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: COLORS.cardBg,
      titleColor: COLORS.textPrimary,
      bodyColor: COLORS.textSecondary,
      borderColor: COLORS.purple,
      borderWidth: 1,
      cornerRadius: 8,
      padding: 10,
    },
  },
  scales: {
    x: {
      grid: { color: COLORS.gridColor },
      ticks: { color: COLORS.textSecondary, maxTicksLimit: 10, font: { size: 10 } },
    },
    y: {
      grid: { color: COLORS.gridColor },
      ticks: { color: COLORS.textSecondary, font: { size: 10 } },
      beginAtZero: true,
    },
  },
};

// --- The Hook ---
const AnalyticsCharts = {
  mounted() {
    this.charts = {};
    this.initCharts();

    this.handleEvent("analytics_update", (data) => {
      this.updateCharts(data);
    });
  },

  initCharts() {
    // 1. Vehicle Count — Area chart
    const vcCtx = document.getElementById("vehicleCountChart").getContext("2d");
    this.charts.vehicleCount = new Chart(vcCtx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Vehicles",
            data: [],
            borderColor: COLORS.blue,
            backgroundColor: hexToRgba(COLORS.blue, 0.15),
            borderWidth: 2,
            fill: true,
            tension: 0.4,
            pointRadius: 0,
            pointHitRadius: 8,
          },
        ],
      },
      options: {
        ...COMMON_LINE_OPTIONS,
        scales: {
          ...COMMON_LINE_OPTIONS.scales,
          y: { ...COMMON_LINE_OPTIONS.scales.y, title: { display: true, text: "Count", color: COLORS.textSecondary, font: { size: 10 } } },
        },
      },
    });

    // 2. Average Speed — Line chart
    const asCtx = document.getElementById("avgSpeedChart").getContext("2d");
    this.charts.avgSpeed = new Chart(asCtx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Avg Speed (m/s)",
            data: [],
            borderColor: COLORS.green,
            backgroundColor: hexToRgba(COLORS.green, 0.1),
            borderWidth: 2,
            fill: true,
            tension: 0.4,
            pointRadius: 0,
            pointHitRadius: 8,
          },
        ],
      },
      options: {
        ...COMMON_LINE_OPTIONS,
        scales: {
          ...COMMON_LINE_OPTIONS.scales,
          y: { ...COMMON_LINE_OPTIONS.scales.y, title: { display: true, text: "m/s", color: COLORS.textSecondary, font: { size: 10 } } },
        },
      },
    });

    // 3. Congestion Index — Line chart with red zone
    const ciCtx = document.getElementById("congestionChart").getContext("2d");
    this.charts.congestion = new Chart(ciCtx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Congestion",
            data: [],
            borderColor: COLORS.red,
            backgroundColor: hexToRgba(COLORS.red, 0.12),
            borderWidth: 2,
            fill: true,
            tension: 0.4,
            pointRadius: 0,
            pointHitRadius: 8,
          },
        ],
      },
      options: {
        ...COMMON_LINE_OPTIONS,
        scales: {
          ...COMMON_LINE_OPTIONS.scales,
          y: {
            ...COMMON_LINE_OPTIONS.scales.y,
            max: 1,
            title: { display: true, text: "Index (0–1)", color: COLORS.textSecondary, font: { size: 10 } },
          },
        },
      },
    });

    // 4. Speed Distribution — Doughnut
    const sdCtx = document.getElementById("speedDistChart").getContext("2d");
    this.charts.speedDist = new Chart(sdCtx, {
      type: "doughnut",
      data: {
        labels: ["Stopped", "Slow (<5)", "Medium (<10)", "Fast (≥10)"],
        datasets: [
          {
            data: [0, 0, 0, 0],
            backgroundColor: [COLORS.red, COLORS.orange, COLORS.yellow, COLORS.green],
            borderColor: COLORS.cardBg,
            borderWidth: 3,
            hoverOffset: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        cutout: "55%",
        plugins: {
          legend: {
            position: "bottom",
            labels: {
              color: COLORS.textSecondary,
              padding: 14,
              usePointStyle: true,
              pointStyleWidth: 10,
              font: { size: 11 },
            },
          },
          tooltip: {
            backgroundColor: COLORS.cardBg,
            titleColor: COLORS.textPrimary,
            bodyColor: COLORS.textSecondary,
            borderColor: COLORS.purple,
            borderWidth: 1,
            cornerRadius: 8,
            callbacks: {
              label: (ctx) => ` ${ctx.label}: ${ctx.raw} vehicles`,
            },
          },
        },
      },
    });

    // 5. Intersection Throughput — Bar chart
    const itCtx = document.getElementById("intersectionChart").getContext("2d");
    this.charts.intersection = new Chart(itCtx, {
      type: "bar",
      data: {
        labels: ["Riia×Kalevi", "Riia×Turu", "Turu×Soola", "Turu×Aida"],
        datasets: [
          {
            label: "Vehicles",
            data: [0, 0, 0, 0],
            backgroundColor: [
              hexToRgba(COLORS.blue, 0.7),
              hexToRgba(COLORS.purple, 0.7),
              hexToRgba(COLORS.cyan, 0.7),
              hexToRgba(COLORS.green, 0.7),
            ],
            borderColor: [COLORS.blue, COLORS.purple, COLORS.cyan, COLORS.green],
            borderWidth: 1,
            borderRadius: 6,
            barPercentage: 0.6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: COLORS.cardBg,
            titleColor: COLORS.textPrimary,
            bodyColor: COLORS.textSecondary,
            borderColor: COLORS.purple,
            borderWidth: 1,
            cornerRadius: 8,
          },
        },
        scales: {
          x: {
            grid: { color: COLORS.gridColor },
            ticks: { color: COLORS.textSecondary, font: { size: 10 } },
          },
          y: {
            grid: { color: COLORS.gridColor },
            ticks: { color: COLORS.textSecondary, font: { size: 10 } },
            beginAtZero: true,
            title: { display: true, text: "Vehicles", color: COLORS.textSecondary, font: { size: 10 } },
          },
        },
      },
    });

    // 6. Stopped Vehicles — Line chart
    const svCtx = document.getElementById("stoppedChart").getContext("2d");
    this.charts.stopped = new Chart(svCtx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Stopped",
            data: [],
            borderColor: COLORS.orange,
            backgroundColor: hexToRgba(COLORS.orange, 0.12),
            borderWidth: 2,
            fill: true,
            tension: 0.4,
            pointRadius: 0,
            pointHitRadius: 8,
          },
        ],
      },
      options: {
        ...COMMON_LINE_OPTIONS,
        scales: {
          ...COMMON_LINE_OPTIONS.scales,
          y: { ...COMMON_LINE_OPTIONS.scales.y, title: { display: true, text: "Count", color: COLORS.textSecondary, font: { size: 10 } } },
        },
      },
    });
  },

  updateCharts(data) {
    const history = data.history || [];
    const labels = history.map((h) => {
      const t = h.time || 0;
      const m = Math.floor(t / 60);
      const s = t % 60;
      return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    });

    // 1. Vehicle Count
    this.charts.vehicleCount.data.labels = labels;
    this.charts.vehicleCount.data.datasets[0].data = history.map((h) => h.vehicle_count || 0);
    this.charts.vehicleCount.update("none");

    // 2. Average Speed
    this.charts.avgSpeed.data.labels = labels;
    this.charts.avgSpeed.data.datasets[0].data = history.map((h) => h.avg_speed || 0);
    this.charts.avgSpeed.update("none");

    // 3. Congestion
    this.charts.congestion.data.labels = labels;
    this.charts.congestion.data.datasets[0].data = history.map((h) => h.congestion_index || 0);
    this.charts.congestion.update("none");

    // 4. Speed Distribution
    const sd = data.speed_distribution || {};
    this.charts.speedDist.data.datasets[0].data = [
      sd.stopped || 0,
      sd.slow || 0,
      sd.medium || 0,
      sd.fast || 0,
    ];
    this.charts.speedDist.update("none");

    // 5. Intersection Counts
    const ic = data.intersection_counts || {};
    this.charts.intersection.data.datasets[0].data = [
      ic["TRiia_Kalevi"] || 0,
      ic["TRiia_Turu"] || 0,
      ic["TTuru_Soola"] || 0,
      ic["TTuru_Aida"] || 0,
    ];
    this.charts.intersection.update("none");

    // 6. Stopped Vehicles
    this.charts.stopped.data.labels = labels;
    this.charts.stopped.data.datasets[0].data = history.map((h) => h.stopped || 0);
    this.charts.stopped.update("none");
  },

  destroyed() {
    Object.values(this.charts).forEach((chart) => chart.destroy());
  },
};

export default AnalyticsCharts;
