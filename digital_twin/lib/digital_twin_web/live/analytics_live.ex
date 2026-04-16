defmodule DigitalTwinWeb.AnalyticsLive do
  use DigitalTwinWeb, :live_view

  alias DigitalTwin.TrafficState

  @impl true
  def mount(_params, _session, socket) do
    if connected?(socket) do
      TrafficState.subscribe()
    end

    state = TrafficState.get_state()

    {:ok,
     socket
     |> assign(:metrics, state.metrics)
     |> assign(:metrics_history, state.metrics_history)
     |> assign(:speed_distribution, state.speed_distribution)
     |> assign(:intersection_counts, state.intersection_counts)
     |> assign(:vehicle_count, state.metrics["vehicle_count"] || 0)
     |> assign(:sim_time, state.metrics["time"] || 0)}
  end

  @impl true
  def handle_info({:traffic_update, state}, socket) do
    socket =
      socket
      |> assign(:metrics, state.metrics)
      |> assign(:metrics_history, state.metrics_history)
      |> assign(:speed_distribution, state.speed_distribution)
      |> assign(:intersection_counts, state.intersection_counts)
      |> assign(:vehicle_count, state.metrics["vehicle_count"] || 0)
      |> assign(:sim_time, state.metrics["time"] || 0)
      |> push_event("analytics_update", %{
        metrics: state.metrics,
        history: state.metrics_history,
        speed_distribution: state.speed_distribution,
        intersection_counts: state.intersection_counts
      })

    {:noreply, socket}
  end

  @impl true
  def render(assigns) do
    ~H"""
    <div class="dashboard">
      <!-- Navigation -->
      <nav class="nav-tabs">
        <a href="/" class="nav-tab">🗺️ Dashboard</a>
        <a href="/analytics" class="nav-tab active">📊 Analytics</a>
        <a href="/audit" class="nav-tab">📋 Audit Trail</a>
      </nav>

      <!-- Header -->
      <header class="dashboard-header">
        <div class="header-left">
          <h1>📊 Traffic Analytics</h1>
          <span class="subtitle">Riia–Turu Corridor • Real-Time Statistics for Stakeholders</span>
        </div>
        <div class="header-right">
          <div class="sim-time">
            <span class="label">SIM TIME</span>
            <span class="value"><%= format_time(@sim_time) %></span>
          </div>
        </div>
      </header>

      <!-- Summary Cards Row -->
      <div class="analytics-summary">
        <div class="analytics-summary-card">
          <div class="summary-icon">🚗</div>
          <div class="summary-body">
            <span class="summary-value"><%= @metrics["vehicle_count"] || 0 %></span>
            <span class="summary-label">Active Vehicles</span>
          </div>
        </div>
        <div class="analytics-summary-card">
          <div class="summary-icon">⚡</div>
          <div class="summary-body">
            <span class="summary-value"><%= format_speed(@metrics["avg_speed"]) %></span>
            <span class="summary-label">Avg Speed (m/s)</span>
          </div>
        </div>
        <div class="analytics-summary-card">
          <div class="summary-icon">📈</div>
          <div class="summary-body">
            <span class="summary-value"><%= format_percent(@metrics["congestion_index"]) %></span>
            <span class="summary-label">Congestion Index</span>
          </div>
        </div>
        <div class="analytics-summary-card">
          <div class="summary-icon">🛑</div>
          <div class="summary-body">
            <span class="summary-value"><%= @metrics["stopped"] || 0 %></span>
            <span class="summary-label">Stopped Vehicles</span>
          </div>
        </div>
      </div>

      <!-- Charts Grid -->
      <div
        id="analytics-charts"
        phx-hook="AnalyticsCharts"
        phx-update="ignore"
        class="analytics-grid"
      >
        <!-- Row 1: Time-series charts -->
        <div class="chart-card" id="chart-vehicle-count">
          <div class="chart-header">
            <h3>🚗 Vehicle Count</h3>
            <span class="stakeholder-badge badge-municipality">🏙️ Municipality</span>
          </div>
          <div class="chart-body">
            <canvas id="vehicleCountChart"></canvas>
          </div>
        </div>

        <div class="chart-card" id="chart-avg-speed">
          <div class="chart-header">
            <h3>⚡ Average Speed</h3>
            <span class="stakeholder-badge badge-navigation">🗺️ Navigation</span>
          </div>
          <div class="chart-body">
            <canvas id="avgSpeedChart"></canvas>
          </div>
        </div>

        <div class="chart-card" id="chart-congestion">
          <div class="chart-header">
            <h3>📈 Congestion Index</h3>
            <span class="stakeholder-badge badge-transit">🚌 Public Transport</span>
          </div>
          <div class="chart-body">
            <canvas id="congestionChart"></canvas>
          </div>
        </div>

        <!-- Row 2: Distribution + Bar charts -->
        <div class="chart-card" id="chart-speed-distribution">
          <div class="chart-header">
            <h3>🎯 Speed Distribution</h3>
            <span class="stakeholder-badge badge-rideshare">🚕 Ride Sharing</span>
          </div>
          <div class="chart-body">
            <canvas id="speedDistChart"></canvas>
          </div>
        </div>

        <div class="chart-card" id="chart-intersection">
          <div class="chart-header">
            <h3>🚦 Intersection Load</h3>
            <span class="stakeholder-badge badge-municipality">🏙️ Municipality</span>
          </div>
          <div class="chart-body">
            <canvas id="intersectionChart"></canvas>
          </div>
        </div>

        <div class="chart-card" id="chart-stopped">
          <div class="chart-header">
            <h3>🛑 Stopped Vehicles</h3>
            <span class="stakeholder-badge badge-transit">🚌 Public Transport</span>
          </div>
          <div class="chart-body">
            <canvas id="stoppedChart"></canvas>
          </div>
        </div>
      </div>

      <!-- Stakeholder Legend -->
      <div class="stakeholder-legend">
        <span class="legend-title">Stakeholder Analytics:</span>
        <span class="stakeholder-badge badge-municipality">🏙️ City Municipality</span>
        <span class="stakeholder-badge badge-transit">🚌 Public Transport</span>
        <span class="stakeholder-badge badge-rideshare">🚕 Ride Sharing</span>
        <span class="stakeholder-badge badge-navigation">🗺️ Navigation Apps</span>
      </div>
    </div>
    """
  end

  # --- Helpers ---

  defp format_time(nil), do: "00:00"
  defp format_time(seconds) when is_number(seconds) do
    m = div(trunc(seconds), 60)
    s = rem(trunc(seconds), 60)
    :io_lib.format("~2..0B:~2..0B", [m, s]) |> IO.iodata_to_binary()
  end
  defp format_time(_), do: "00:00"

  defp format_speed(nil), do: "0.0"
  defp format_speed(speed) when is_number(speed), do: :erlang.float_to_binary(speed / 1, decimals: 1)
  defp format_speed(_), do: "0.0"

  defp format_percent(nil), do: "0%"
  defp format_percent(val) when is_number(val), do: "#{trunc(val * 100)}%"
  defp format_percent(_), do: "0%"
end
