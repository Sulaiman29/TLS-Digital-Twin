defmodule DigitalTwin.TrafficState do
  @moduledoc """
  GenServer holding the live state of the Tartu traffic network.
  Receives updates from the MQTT handler and broadcasts to PubSub
  so LiveView clients get real-time pushes.
  """
  use GenServer

  @pubsub DigitalTwin.PubSub
  @topic "traffic:tartu"
  @history_size 60

  # Lane prefixes that map to each intersection
  @intersection_lane_prefixes %{
    "TRiia_Kalevi" => ["Riia_south", "Kalevi", "Ulikooli", "Riia_north_in"],
    "TRiia_Turu" => ["Riia_mid", "Turu_west", "Kaubamaja", "Riia_center"],
    "TTuru_Soola" => ["Turu_mid", "Soola", "Turu_east_in"],
    "TTuru_Aida" => ["Turu_east", "Aida", "Turu_out"]
  }

  # --- Client API ---

  def start_link(_opts) do
    GenServer.start_link(__MODULE__, %{}, name: __MODULE__)
  end

  def get_state do
    GenServer.call(__MODULE__, :get_state)
  end

  def update_metrics(metrics) do
    GenServer.cast(__MODULE__, {:metrics, metrics})
  end

  def update_vehicles(vehicles_payload) do
    GenServer.cast(__MODULE__, {:vehicles, vehicles_payload})
  end

  def update_traffic_lights(tl_payload) do
    GenServer.cast(__MODULE__, {:traffic_lights, tl_payload})
  end

  def update_blockchain(bc_payload) do
    GenServer.cast(__MODULE__, {:blockchain, bc_payload})
  end

  def add_audit_entry(entry) do
    GenServer.cast(__MODULE__, {:audit, entry})
  end

  @doc "Subscribe to real-time traffic updates"
  def subscribe do
    Phoenix.PubSub.subscribe(@pubsub, @topic)
  end

  # --- Server Callbacks ---

  @impl true
  def init(_) do
    state = %{
      metrics: %{
        "time" => 0,
        "vehicle_count" => 0,
        "avg_speed" => 0,
        "congestion_index" => 0,
        "stopped" => 0
      },
      vehicles: [],
      traffic_lights: [],
      blockchain: %{
        "connected" => false,
        "data_anchored" => false,
        "anchor_count" => 0,
        "block_number" => 0,
        "last_tx_hash" => nil,
        "access_control_active" => false
      },
      audit_log: [],
      metrics_history: [],
      speed_distribution: %{"stopped" => 0, "slow" => 0, "medium" => 0, "fast" => 0},
      intersection_counts: %{},
      last_update: nil
    }

    {:ok, state}
  end

  @impl true
  def handle_call(:get_state, _from, state) do
    {:reply, state, state}
  end

  @impl true
  def handle_cast({:metrics, metrics}, state) do
    # Append to rolling history
    point = %{
      "time" => metrics["time"] || 0,
      "vehicle_count" => metrics["vehicle_count"] || 0,
      "avg_speed" => metrics["avg_speed"] || 0,
      "congestion_index" => metrics["congestion_index"] || 0,
      "stopped" => metrics["stopped"] || 0
    }

    history = Enum.take([point | state.metrics_history], @history_size) |> Enum.reverse()

    new_state = %{state | metrics: metrics, metrics_history: history, last_update: DateTime.utc_now()}
    broadcast(new_state)
    {:noreply, new_state}
  end

  @impl true
  def handle_cast({:vehicles, payload}, state) do
    vehicles = Map.get(payload, "vehicles", [])

    # Compute speed distribution
    speed_dist = compute_speed_distribution(vehicles)

    # Compute per-intersection vehicle counts
    int_counts = compute_intersection_counts(vehicles)

    new_state = %{state |
      vehicles: vehicles,
      speed_distribution: speed_dist,
      intersection_counts: int_counts,
      last_update: DateTime.utc_now()
    }
    broadcast(new_state)
    {:noreply, new_state}
  end

  @impl true
  def handle_cast({:traffic_lights, payload}, state) do
    lights = Map.get(payload, "lights", [])
    new_state = %{state | traffic_lights: lights, last_update: DateTime.utc_now()}
    broadcast(new_state)
    {:noreply, new_state}
  end

  @impl true
  def handle_cast({:blockchain, payload}, state) do
    new_state = %{state | blockchain: payload, last_update: DateTime.utc_now()}
    broadcast(new_state)
    {:noreply, new_state}
  end

  @impl true
  def handle_cast({:audit, entry}, state) do
    updated_log = [entry | state.audit_log] |> Enum.take(50)
    new_state = %{state | audit_log: updated_log}
    Phoenix.PubSub.broadcast(@pubsub, "audit:tartu", {:audit_update, updated_log})
    {:noreply, new_state}
  end

  defp broadcast(state) do
    Phoenix.PubSub.broadcast(@pubsub, @topic, {:traffic_update, state})
  end

  # Categorize vehicles into speed buckets
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

  # Count vehicles near each intersection based on lane ID prefix
  defp compute_intersection_counts(vehicles) do
    # Build a flat lookup: [{prefix, intersection_id}, ...]
    prefix_lookup =
      Enum.flat_map(@intersection_lane_prefixes, fn {int_id, prefixes} ->
        Enum.map(prefixes, fn pfx -> {pfx, int_id} end)
      end)

    base = Map.keys(@intersection_lane_prefixes) |> Enum.into(%{}, &{&1, 0})

    Enum.reduce(vehicles, base, fn v, acc ->
      lane = v["lane"] || ""
      case Enum.find(prefix_lookup, fn {pfx, _} -> String.starts_with?(lane, pfx) end) do
        {_, int_id} -> Map.update!(acc, int_id, &(&1 + 1))
        nil -> acc
      end
    end)
  end
end
