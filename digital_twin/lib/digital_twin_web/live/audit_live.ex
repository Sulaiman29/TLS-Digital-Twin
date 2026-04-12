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
     |> assign(:audit_log, add_ids(state.audit_log))
     |> assign(:entry_count, length(state.audit_log))
     |> assign(:selected, nil)}
  end

  @impl true
  def handle_info({:audit_update, audit_log}, socket) do
    {:noreply,
     socket
     |> assign(:audit_log, add_ids(audit_log))
     |> assign(:entry_count, length(audit_log))}
  end

  # Ignore traffic updates (we're on a different page)
  def handle_info({:traffic_update, _state}, socket), do: {:noreply, socket}

  @impl true
  def handle_event("select_entry", %{"idx" => idx_str}, socket) do
    idx = String.to_integer(idx_str)
    entry = Enum.at(socket.assigns.audit_log, idx)

    selected =
      if socket.assigns.selected && socket.assigns.selected["_idx"] == idx,
        do: nil,
        else: entry

    {:noreply, assign(socket, :selected, selected)}
  end

  def handle_event("close_detail", _params, socket) do
    {:noreply, assign(socket, :selected, nil)}
  end

  # Add index to each entry for identification
  defp add_ids(log) do
    log
    |> Enum.with_index()
    |> Enum.map(fn {entry, idx} -> Map.put(entry, "_idx", idx) end)
  end

  defp truncate_hash(nil), do: "—"
  defp truncate_hash(hash) when byte_size(hash) > 16, do: String.slice(hash, 0, 16) <> "..."
  defp truncate_hash(hash), do: hash

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
          <span class="subtitle">On-Chain Decision Log • Click any row to view AI reasoning</span>
        </div>
        <div class="header-right">
          <div class="sim-time">
            <span class="label">Logged Decisions</span>
            <span class="value"><%= @entry_count %></span>
          </div>
        </div>
      </header>

      <div class="audit-layout">
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
                    <tr
                      class={"audit-row #{if @selected && @selected["_idx"] == entry["_idx"], do: "audit-row-selected", else: ""}"}
                      phx-click="select_entry"
                      phx-value-idx={entry["_idx"]}
                      style="cursor: pointer;"
                    >
                      <td class="audit-time"><%= entry["timestamp"] || "—" %></td>
                      <td class="audit-intersection"><%= entry["intersection"] || "—" %></td>
                      <td class="audit-action"><%= entry["action"] || "—" %></td>
                      <td class="audit-hash"><code><%= truncate_hash(entry["input_hash"]) %></code></td>
                      <td class="audit-hash"><code><%= truncate_hash(entry["tx_hash"]) %></code></td>
                    </tr>
                  <% end %>
                </tbody>
              </table>
            </div>
          <% end %>
        </div>

        <!-- Detail Panel (shown when a row is selected) -->
        <%= if @selected do %>
          <div class="audit-detail">
            <div class="audit-detail-header">
              <h2>🔍 Decision Details</h2>
              <button class="audit-detail-close" phx-click="close_detail">✕</button>
            </div>

            <div class="audit-detail-body">
              <!-- Summary -->
              <div class="detail-section">
                <h3>📌 Summary</h3>
                <div class="detail-grid">
                  <div class="detail-item">
                    <span class="detail-label">Intersection</span>
                    <span class="detail-value highlight"><%= @selected["intersection"] %></span>
                  </div>
                  <div class="detail-item">
                    <span class="detail-label">Direction</span>
                    <span class="detail-value"><%= @selected["direction"] || "—" %></span>
                  </div>
                  <div class="detail-item">
                    <span class="detail-label">Phase</span>
                    <span class="detail-value"><%= @selected["phase"] || "—" %></span>
                  </div>
                  <div class="detail-item">
                    <span class="detail-label">Duration</span>
                    <span class="detail-value"><%= @selected["duration"] || "—" %>s</span>
                  </div>
                  <div class="detail-item">
                    <span class="detail-label">Time</span>
                    <span class="detail-value"><%= @selected["timestamp"] %></span>
                  </div>
                </div>
              </div>

              <!-- Queue State -->
              <div class="detail-section">
                <h3>🚗 Queue State at Decision</h3>
                <%= if @selected["queues"] do %>
                  <div class="detail-queues">
                    <%= for {dir, count} <- @selected["queues"] do %>
                      <div class={"queue-badge #{if count > 5, do: "queue-high", else: if count > 0, do: "queue-mid", else: "queue-empty"}"}>
                        <span class="queue-dir"><%= dir %></span>
                        <span class="queue-count"><%= count %></span>
                      </div>
                    <% end %>
                  </div>
                <% else %>
                  <p class="detail-muted">Queue data not available.</p>
                <% end %>
              </div>

              <!-- AI Reasoning -->
              <div class="detail-section">
                <h3>🤖 AI Reasoning</h3>
                <%= if @selected["reasoning"] do %>
                  <div class="detail-reasoning">
                    <%= @selected["reasoning"] %>
                  </div>
                <% else %>
                  <p class="detail-muted">Reasoning not available for this entry.</p>
                <% end %>
              </div>

              <!-- Blockchain Verification -->
              <div class="detail-section">
                <h3>🔗 Blockchain Verification</h3>
                <div class="detail-hashes">
                  <div class="hash-row">
                    <span class="hash-label">Input Hash</span>
                    <code class="hash-value-full"><%= @selected["input_hash"] || "—" %></code>
                  </div>
                  <div class="hash-row">
                    <span class="hash-label">Tx Hash</span>
                    <code class="hash-value-full"><%= @selected["tx_hash"] || "—" %></code>
                  </div>
                </div>
              </div>
            </div>
          </div>
        <% end %>
      </div>
    </div>
    """
  end
end
