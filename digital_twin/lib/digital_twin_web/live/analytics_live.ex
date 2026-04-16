defmodule DigitalTwinWeb.AnalyticsLive do
  use DigitalTwinWeb, :live_view

  alias DigitalTwin.TrafficState

  @intersections [
    {"TRiia_Kalevi", "Riia × Kalevi"},
    {"TRiia_Turu", "Riia × Turu"},
    {"TTuru_Soola", "Turu × Soola"},
    {"TTuru_Aida", "Turu × Aida"}
  ]

  @impl true
  def mount(_params, _session, socket) do
    if connected?(socket) do
      TrafficState.subscribe()
    end

    state = TrafficState.get_state()
    default_int = "TRiia_Kalevi"

    {:ok,
     socket
     |> assign(:intersections, @intersections)
     |> assign(:selected_intersection, default_int)
     |> assign(:metrics, state.metrics)
     |> assign(:traffic_lights, state.traffic_lights)
     |> assign(:per_intersection_metrics, state.per_intersection_metrics)
     |> assign(:per_intersection_history, state.per_intersection_history)
     |> assign(:vehicles, state.vehicles)
     |> assign(:sim_time, state.metrics["time"] || 0)
     |> assign_intersection_data(default_int, state)}
  end

  @impl true
  def handle_info({:traffic_update, state}, socket) do
    selected = socket.assigns.selected_intersection

    socket =
      socket
      |> assign(:metrics, state.metrics)
      |> assign(:traffic_lights, state.traffic_lights)
      |> assign(:per_intersection_metrics, state.per_intersection_metrics)
      |> assign(:per_intersection_history, state.per_intersection_history)
      |> assign(:vehicles, state.vehicles)
      |> assign(:sim_time, state.metrics["time"] || 0)
      |> assign_intersection_data(selected, state)
      |> push_intersection_update(selected, state)

    {:noreply, socket}
  end

  @impl true
  def handle_event("select_intersection", %{"id" => int_id}, socket) do
    state = TrafficState.get_state()

    socket =
      socket
      |> assign(:selected_intersection, int_id)
      |> assign_intersection_data(int_id, state)
      |> push_intersection_update(int_id, state)

    {:noreply, socket}
  end

  # Compute intersection-specific assigns for the template
  defp assign_intersection_data(socket, int_id, state) do
    int_metrics = get_in(state.per_intersection_metrics, [int_id]) ||
      %{"vehicle_count" => 0, "avg_speed" => 0, "congestion_index" => 0, "stopped" => 0}

    # Get the TL state for this intersection
    tl_state = Enum.find(state.traffic_lights, fn tl -> tl["id"] == int_id end)

    # Compute speed distribution for vehicles at this intersection only
    int_vehicles = get_intersection_vehicles(state.vehicles, int_id)
    int_speed_dist = compute_speed_distribution(int_vehicles)

    socket
    |> assign(:int_metrics, int_metrics)
    |> assign(:int_tl_state, tl_state)
    |> assign(:int_speed_dist, int_speed_dist)
  end

  # Push chart data to the JS hook
  defp push_intersection_update(socket, int_id, state) do
    history = Map.get(state.per_intersection_history, int_id, [])
    int_metrics = get_in(state.per_intersection_metrics, [int_id]) ||
      %{"vehicle_count" => 0, "avg_speed" => 0, "congestion_index" => 0, "stopped" => 0}

    int_vehicles = get_intersection_vehicles(state.vehicles, int_id)
    int_speed_dist = compute_speed_distribution(int_vehicles)

    # Per-intersection current counts for the bar chart comparison
    all_counts = Enum.map(["TRiia_Kalevi", "TRiia_Turu", "TTuru_Soola", "TTuru_Aida"], fn id ->
      m = Map.get(state.per_intersection_metrics, id, %{})
      m["vehicle_count"] || 0
    end)

    push_event(socket, "analytics_update", %{
      history: history,
      metrics: int_metrics,
      speed_distribution: int_speed_dist,
      all_intersection_counts: all_counts,
      selected: int_id
    })
  end

  # Filter vehicles belonging to a specific intersection
  defp get_intersection_vehicles(vehicles, int_id) do
    edges = get_intersection_edges(int_id)

    Enum.filter(vehicles, fn v ->
      lane = v["lane"] || ""
      edge = lane |> String.split("_") |> Enum.drop(-1) |> Enum.join("_")
      edge in edges or (String.starts_with?(lane, ":") and String.starts_with?(String.trim_leading(lane, ":"), int_id))
    end)
  end

  defp get_intersection_edges("TRiia_Kalevi"), do: [
    "RiiaN_RiiaKalevi", "RiiaKalevi_RiiaN",
    "UlikW_RiiaKalevi", "RiiaKalevi_UlikW",
    "KaleviE_RiiaKalevi", "RiiaKalevi_KaleviE",
    "RiiaKalevi_RiiaTuru", "RiiaTuru_RiiaKalevi"
  ]
  defp get_intersection_edges("TRiia_Turu"), do: [
    "RiiaKalevi_RiiaTuru", "RiiaTuru_RiiaKalevi",
    "RiiaS_RiiaTuru", "RiiaTuru_RiiaS",
    "TuruW_RiiaTuru", "RiiaTuru_TuruW",
    "RiiaTuru_TuruSoola", "TuruSoola_RiiaTuru"
  ]
  defp get_intersection_edges("TTuru_Soola"), do: [
    "RiiaTuru_TuruSoola", "TuruSoola_RiiaTuru",
    "SoolaN_TuruSoola", "TuruSoola_SoolaN",
    "SoolaS_TuruSoola", "TuruSoola_SoolaS",
    "TuruSoola_TuruAida", "TuruAida_TuruSoola"
  ]
  defp get_intersection_edges("TTuru_Aida"), do: [
    "TuruSoola_TuruAida", "TuruAida_TuruSoola",
    "AidaE_TuruAida", "TuruAida_AidaE",
    "AidaN_TuruAida", "TuruAida_AidaN",
    "AidaS_TuruAida", "TuruAida_AidaS"
  ]
  defp get_intersection_edges(_), do: []

  defp compute_speed_distribution(vehicles) do
    Enum.reduce(vehicles, %{"stopped" => 0, "slow" => 0, "medium" => 0, "fast" => 0}, fn v, acc ->
      speed = v["speed"] || 0
      cond do
        speed < 0.5  -> Map.update!(acc, "stopped", &(&1 + 1))
        speed < 5.0  -> Map.update!(acc, "slow", &(&1 + 1))
        speed < 10.0 -> Map.update!(acc, "medium", &(&1 + 1))
        true         -> Map.update!(acc, "fast", &(&1 + 1))
      end
    end)
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
          <span class="subtitle">Riia–Turu Corridor • Per-Intersection Statistics</span>
        </div>
        <div class="header-right">
          <div class="sim-time">
            <span class="label">SIM TIME</span>
            <span class="value"><%= format_time(@sim_time) %></span>
          </div>
        </div>
      </header>

      <!-- Intersection Selector -->
      <div class="intersection-selector">
        <span class="selector-label">🚦 Select Intersection:</span>
        <div class="selector-pills">
          <%= for {id, label} <- @intersections do %>
            <button
              class={"selector-pill #{if @selected_intersection == id, do: "pill-active", else: ""}"}
              phx-click="select_intersection"
              phx-value-id={id}
            >
              <%= label %>
            </button>
          <% end %>
        </div>
      </div>

      <!-- Intersection Summary Cards -->
      <div class="analytics-summary">
        <div class="analytics-summary-card">
          <div class="summary-icon">🚗</div>
          <div class="summary-body">
            <span class="summary-value"><%= @int_metrics["vehicle_count"] || 0 %></span>
            <span class="summary-label">Vehicles at Intersection</span>
          </div>
        </div>
        <div class="analytics-summary-card">
          <div class="summary-icon">⚡</div>
          <div class="summary-body">
            <span class="summary-value"><%= format_speed(@int_metrics["avg_speed"]) %></span>
            <span class="summary-label">Avg Speed (m/s)</span>
          </div>
        </div>
        <div class="analytics-summary-card">
          <div class="summary-icon">📈</div>
          <div class="summary-body">
            <span class="summary-value"><%= format_percent(@int_metrics["congestion_index"]) %></span>
            <span class="summary-label">Congestion Index</span>
          </div>
        </div>
        <div class="analytics-summary-card">
          <div class="summary-icon">🛑</div>
          <div class="summary-body">
            <span class="summary-value"><%= @int_metrics["stopped"] || 0 %></span>
            <span class="summary-label">Stopped Vehicles</span>
          </div>
        </div>
        <div class="analytics-summary-card">
          <div class="summary-icon">🚦</div>
          <div class="summary-body">
            <%= if @int_tl_state do %>
              <div class="tl-state-inline">
                <%= for {char, i} <- Enum.with_index(String.graphemes(@int_tl_state["state"] || "")) do %>
                  <span class={"tl-light tl-#{char}"} title={"Link #{i}"}></span>
                <% end %>
              </div>
              <span class="summary-label">Phase <%= @int_tl_state["phase"] %></span>
            <% else %>
              <span class="summary-value">—</span>
              <span class="summary-label">Traffic Light</span>
            <% end %>
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

        <!-- Row 2: Distribution + Bar + Stopped -->
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
            <h3>🚦 All Intersections Compare</h3>
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
