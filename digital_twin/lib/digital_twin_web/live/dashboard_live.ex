defmodule DigitalTwinWeb.DashboardLive do
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
     |> assign(:vehicles, state.vehicles)
     |> assign(:traffic_lights, state.traffic_lights)
     |> assign(:vehicle_count, length(state.vehicles))
     |> assign(:sim_time, state.metrics["time"] || 0)}
  end

  @impl true
  def handle_info({:traffic_update, state}, socket) do
    # Push vehicle positions and TL states to the JS hook
    socket =
      socket
      |> assign(:metrics, state.metrics)
      |> assign(:vehicles, state.vehicles)
      |> assign(:traffic_lights, state.traffic_lights)
      |> assign(:vehicle_count, length(state.vehicles))
      |> assign(:sim_time, state.metrics["time"] || 0)
      |> push_event("traffic_update", %{
        vehicles: state.vehicles,
        traffic_lights: state.traffic_lights,
        metrics: state.metrics
      })

    {:noreply, socket}
  end

  @impl true
  def render(assigns) do
    ~H"""
    <div class="dashboard">
      <!-- Header -->
      <header class="dashboard-header">
        <div class="header-left">
          <h1>🏙️ Tartu Digital Twin</h1>
          <span class="subtitle">Riia–Turu Corridor • Real-Time Traffic Visualization</span>
        </div>
        <div class="header-right">
          <div class="sim-time">
            <span class="label">SIM TIME</span>
            <span class="value"><%= format_time(@sim_time) %></span>
          </div>
        </div>
      </header>

      <!-- Metrics Row -->
      <div class="metrics-row">
        <div class="metric-card">
          <div class="metric-icon">🚗</div>
          <div class="metric-body">
            <span class="metric-value"><%= @metrics["vehicle_count"] || 0 %></span>
            <span class="metric-label">Active Vehicles</span>
          </div>
        </div>
        <div class="metric-card">
          <div class="metric-icon">⚡</div>
          <div class="metric-body">
            <span class="metric-value"><%= format_speed(@metrics["avg_speed"]) %></span>
            <span class="metric-label">Avg Speed (m/s)</span>
          </div>
        </div>
        <div class="metric-card congestion">
          <div class="metric-icon">🔴</div>
          <div class="metric-body">
            <span class="metric-value"><%= format_percent(@metrics["congestion_index"]) %></span>
            <span class="metric-label">Congestion Index</span>
          </div>
        </div>
        <div class="metric-card">
          <div class="metric-icon">🛑</div>
          <div class="metric-body">
            <span class="metric-value"><%= @metrics["stopped"] || 0 %></span>
            <span class="metric-label">Stopped Vehicles</span>
          </div>
        </div>
      </div>

      <!-- Map + Sidebar -->
      <div class="main-content">
        <div id="traffic-map" phx-hook="TrafficMap" phx-update="ignore" class="map-container">
        </div>

        <!-- Traffic Light Sidebar -->
        <div class="tl-sidebar">
          <h3>🚦 Traffic Lights</h3>
          <div class="tl-list">
            <%= for tl <- @traffic_lights do %>
              <div class="tl-card">
                <div class="tl-name"><%= tl["id"] %></div>
                <div class="tl-state">
                  <%= for {char, i} <- Enum.with_index(String.graphemes(tl["state"] || "")) do %>
                    <span class={"tl-light tl-#{char}"} title={"Link #{i}"}></span>
                  <% end %>
                </div>
                <div class="tl-phase">Phase <%= tl["phase"] %></div>
              </div>
            <% end %>
          </div>
        </div>
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
