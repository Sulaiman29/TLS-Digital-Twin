defmodule DigitalTwinWeb.AuditLive do
  use DigitalTwinWeb, :live_view

  alias DigitalTwin.TrafficState

  @impl true
  def mount(_params, _session, socket) do
    if connected?(socket) do
      Phoenix.PubSub.subscribe(DigitalTwin.PubSub, "audit:tartu")
    end

    state = TrafficState.get_state()

    {:ok,
     socket
     |> assign(:audit_log, state.audit_log)
     |> assign(:entry_count, length(state.audit_log))}
  end

  @impl true
  def handle_info({:audit_update, audit_log}, socket) do
    {:noreply,
     socket
     |> assign(:audit_log, audit_log)
     |> assign(:entry_count, length(audit_log))}
  end

  # Ignore traffic updates (we're on a different page)
  def handle_info({:traffic_update, _state}, socket), do: {:noreply, socket}

  @impl true
  def render(assigns) do
    ~H"""
    <div class="dashboard">
      <!-- Navigation -->
      <nav class="nav-tabs">
        <a href="/" class="nav-tab">🗺️ Dashboard</a>
        <a href="/audit" class="nav-tab active">📋 Audit Trail</a>
      </nav>

      <!-- Header -->
      <header class="dashboard-header">
        <div class="header-left">
          <h1>📋 Blockchain Audit Trail</h1>
          <span class="subtitle">On-Chain Decision Log • Tamper-Proof Record</span>
        </div>
        <div class="header-right">
          <div class="sim-time">
            <span class="label">Logged Decisions</span>
            <span class="value"><%= @entry_count %></span>
          </div>
        </div>
      </header>

      <!-- Audit Table -->
      <div class="audit-section">
        <%= if @entry_count == 0 do %>
          <div class="audit-empty">
            <p>⏳ Waiting for AI agent decisions...</p>
            <p class="audit-empty-hint">Start the simulation and AI agent to see decision logs here.</p>
          </div>
        <% else %>
          <div class="audit-table-wrapper">
            <table class="audit-table">
              <thead>
                <tr>
                  <th>⏱️ Time</th>
                  <th>🚦 Intersection</th>
                  <th>⚡ Action</th>
                  <th>🔐 Input Hash</th>
                  <th>🔗 Tx Hash</th>
                </tr>
              </thead>
              <tbody>
                <%= for entry <- @audit_log do %>
                  <tr class="audit-row">
                    <td class="audit-time"><%= entry["timestamp"] || "—" %></td>
                    <td class="audit-intersection"><%= entry["intersection"] || "—" %></td>
                    <td class="audit-action"><%= entry["action"] || "—" %></td>
                    <td class="audit-hash"><code><%= entry["input_hash"] || "—" %></code></td>
                    <td class="audit-hash"><code><%= entry["tx_hash"] || "—" %></code></td>
                  </tr>
                <% end %>
              </tbody>
            </table>
          </div>
        <% end %>
      </div>
    </div>
    """
  end
end
