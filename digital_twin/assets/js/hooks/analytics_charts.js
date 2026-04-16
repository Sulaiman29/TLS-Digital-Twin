/**
 * AnalyticsCharts — Chart.js hook for per-intersection analytics
 *
 * Creates and live-updates 6 charts filtered by the selected intersection.
 * Receives data from the AnalyticsLive server push events.
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

function hexToRgba(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// Intersection name map for the bar chart
const INT_LABELS = {
  TRiia_Kalevi: "Riia×Kalevi",
  TRiia_Turu: "Riia×Turu",
  TTuru_Soola: "Turu×Soola",
  TTuru_Aida: "Turu×Aida",
};
const INT_IDS = ["TRiia_Kalevi", "TRiia_Turu", "TTuru_Soola", "TTuru_Aida"];
const INT_COLORS = [COLORS.blue, COLORS.purple, COLORS.cyan, COLORS.green];

// --- Tooltip config ---
const TOOLTIP_CONFIG = {
  backgroundColor: COLORS.cardBg,
  titleColor: COLORS.textPrimary,
  bodyColor: COLORS.textSecondary,
  borderColor: COLORS.purple,
  borderWidth: 1,
  cornerRadius: 8,
  padding: 10,
};

// --- Common line options ---
const COMMON_LINE_OPTIONS = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 0 },
  interaction: { mode: "index", intersect: false },
  plugins: {
    legend: { display: false },
    tooltip: TOOLTIP_CONFIG,
  },
  scales: {
    x: {
      grid: { color: COLORS.gridColor },
      ticks: {
        color: COLORS.textSecondary,
        maxTicksLimit: 12,
        font: { size: 10 },
        autoSkip: true,
        maxRotation: 0,
      },
    },
    y: {
      grid: { color: COLORS.gridColor },
      ticks: { color: COLORS.textSecondary, font: { size: 10 } },
      beginAtZero: true,
    },
  },
};

// --- Format time label from sim second ---
function formatTimeLabel(t) {
  const m = Math.floor(t / 60);
  const s = t % 60;
  return `${String(m).padStart(2, "0")}:${String(Math.floor(s)).padStart(2, "0")}`;
}

// --- Downsample history for display (show max ~120 points) ---
function downsample(arr, maxPoints = 120) {
  if (arr.length <= maxPoints) return arr;
  const step = Math.ceil(arr.length / maxPoints);
  return arr.filter((_, i) => i % step === 0 || i === arr.length - 1);
}

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
    // 1. Vehicle Count at Intersection — Area chart
    this.charts.vehicleCount = new Chart(
      document.getElementById("vehicleCountChart").getContext("2d"),
      {
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
              tension: 0.3,
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
              title: { display: true, text: "Count", color: COLORS.textSecondary, font: { size: 10 } },
            },
          },
        },
      }
    );

    // 2. Average Speed at Intersection — Line chart
    this.charts.avgSpeed = new Chart(
      document.getElementById("avgSpeedChart").getContext("2d"),
      {
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
              tension: 0.3,
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
              title: { display: true, text: "m/s", color: COLORS.textSecondary, font: { size: 10 } },
            },
          },
        },
      }
    );

    // 3. Congestion Index at Intersection — Line chart
    this.charts.congestion = new Chart(
      document.getElementById("congestionChart").getContext("2d"),
      {
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
              tension: 0.3,
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
      }
    );

    // 4. Speed Distribution at Intersection — Doughnut
    this.charts.speedDist = new Chart(
      document.getElementById("speedDistChart").getContext("2d"),
      {
        type: "doughnut",
        data: {
          labels: ["Stopped", "Slow (<5 m/s)", "Medium (<10 m/s)", "Fast (≥10 m/s)"],
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
          animation: { duration: 0 },
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
              ...TOOLTIP_CONFIG,
              callbacks: {
                label: (ctx) => ` ${ctx.label}: ${ctx.raw} vehicles`,
              },
            },
          },
        },
      }
    );

    // 5. All Intersections Comparison — Bar chart (stays cross-intersection)
    this.charts.intersection = new Chart(
      document.getElementById("intersectionChart").getContext("2d"),
      {
        type: "bar",
        data: {
          labels: INT_IDS.map((id) => INT_LABELS[id]),
          datasets: [
            {
              label: "Vehicles",
              data: [0, 0, 0, 0],
              backgroundColor: INT_IDS.map((_, i) => hexToRgba(INT_COLORS[i], 0.7)),
              borderColor: INT_COLORS,
              borderWidth: 1,
              borderRadius: 6,
              barPercentage: 0.6,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: { duration: 0 },
          plugins: {
            legend: { display: false },
            tooltip: TOOLTIP_CONFIG,
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
      }
    );

    // 6. Stopped Vehicles at Intersection — Line chart
    this.charts.stopped = new Chart(
      document.getElementById("stoppedChart").getContext("2d"),
      {
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
              tension: 0.3,
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
              title: { display: true, text: "Count", color: COLORS.textSecondary, font: { size: 10 } },
            },
          },
        },
      }
    );
  },

  updateCharts(data) {
    const history = downsample(data.history || []);
    const labels = history.map((h) => formatTimeLabel(h.time || 0));

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

    // 4. Speed Distribution (at selected intersection)
    const sd = data.speed_distribution || {};
    this.charts.speedDist.data.datasets[0].data = [
      sd.stopped || 0,
      sd.slow || 0,
      sd.medium || 0,
      sd.fast || 0,
    ];
    this.charts.speedDist.update("none");

    // 5. All Intersections comparison bar
    const counts = data.all_intersection_counts || [0, 0, 0, 0];
    this.charts.intersection.data.datasets[0].data = counts;

    // Highlight the selected intersection bar
    const selectedIdx = INT_IDS.indexOf(data.selected);
    this.charts.intersection.data.datasets[0].backgroundColor = INT_IDS.map((_, i) =>
      i === selectedIdx ? hexToRgba(INT_COLORS[i], 1.0) : hexToRgba(INT_COLORS[i], 0.3)
    );
    this.charts.intersection.data.datasets[0].borderWidth = INT_IDS.map((_, i) =>
      i === selectedIdx ? 2 : 1
    );
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
