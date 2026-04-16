defmodule DigitalTwin.TrafficState do
  @moduledoc """
  GenServer holding the live state of the Tartu traffic network.
  Receives updates from the MQTT handler and broadcasts to PubSub
  so LiveView clients get real-time pushes.
  """
  use GenServer

  @pubsub DigitalTwin.PubSub
  @topic "traffic:tartu"
  @history_size 600

  # Edges whose lanes feed INTO or OUT OF each intersection (from edges.edg.xml).
  # SUMO lane IDs follow the format: "edgeId_laneIndex"
  @intersection_edges %{
    "TRiia_Kalevi" => [
      "RiiaN_RiiaKalevi", "RiiaKalevi_RiiaN",
      "UlikW_RiiaKalevi", "RiiaKalevi_UlikW",
      "KaleviE_RiiaKalevi", "RiiaKalevi_KaleviE",
      "RiiaKalevi_RiiaTuru", "RiiaTuru_RiiaKalevi"
    ],
    "TRiia_Turu" => [
      "RiiaKalevi_RiiaTuru", "RiiaTuru_RiiaKalevi",
      "RiiaS_RiiaTuru", "RiiaTuru_RiiaS",
      "TuruW_RiiaTuru", "RiiaTuru_TuruW",
      "RiiaTuru_TuruSoola", "TuruSoola_RiiaTuru"
    ],
    "TTuru_Soola" => [
      "RiiaTuru_TuruSoola", "TuruSoola_RiiaTuru",
      "SoolaN_TuruSoola", "TuruSoola_SoolaN",
      "SoolaS_TuruSoola", "TuruSoola_SoolaS",
      "TuruSoola_TuruAida", "TuruAida_TuruSoola"
    ],
    "TTuru_Aida" => [
      "TuruSoola_TuruAida", "TuruAida_TuruSoola",
      "AidaE_TuruAida", "TuruAida_AidaE",
      "AidaN_TuruAida", "TuruAida_AidaN",
      "AidaS_TuruAida", "TuruAida_AidaS"
    ]
  }

  @intersection_ids Map.keys(@intersection_edges)

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
    empty_int_history = Enum.into(@intersection_ids, %{}, &{&1, []})

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
      per_intersection_history: empty_int_history,
      per_intersection_metrics: Enum.into(@intersection_ids, %{}, fn id ->
        {id, %{"vehicle_count" => 0, "avg_speed" => 0, "congestion_index" => 0, "stopped" => 0}}
      end),
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
    # Append to global rolling history
    point = %{
      "time" => metrics["time"] || 0,
      "vehicle_count" => metrics["vehicle_count"] || 0,
      "avg_speed" => metrics["avg_speed"] || 0,
      "congestion_index" => metrics["congestion_index"] || 0,
      "stopped" => metrics["stopped"] || 0
    }

    history = append_to_history(state.metrics_history, point)
    sim_time = metrics["time"] || 0

    # Append per-intersection metrics to their histories
    per_int_history =
      Enum.into(@intersection_ids, %{}, fn int_id ->
        int_metrics = Map.get(state.per_intersection_metrics, int_id, %{})
        int_point = Map.put(int_metrics, "time", sim_time)
        prev = Map.get(state.per_intersection_history, int_id, [])
        {int_id, append_to_history(prev, int_point)}
      end)

    new_state = %{state |
      metrics: metrics,
      metrics_history: history,
      per_intersection_history: per_int_history,
      last_update: DateTime.utc_now()
    }
    broadcast(new_state)
    {:noreply, new_state}
  end

  @impl true
  def handle_cast({:vehicles, payload}, state) do
    vehicles = Map.get(payload, "vehicles", [])

    # Group vehicles by intersection
    grouped = group_vehicles_by_intersection(vehicles)

    # Compute per-intersection metrics
    per_int_metrics =
      Enum.into(@intersection_ids, %{}, fn int_id ->
        int_vehicles = Map.get(grouped, int_id, [])
        {int_id, compute_intersection_metrics(int_vehicles)}
      end)

    # Compute per-intersection speed distributions
    speed_dist = compute_speed_distribution(vehicles)
    int_counts = Enum.into(@intersection_ids, %{}, fn int_id ->
      {int_id, length(Map.get(grouped, int_id, []))}
    end)

    new_state = %{state |
      vehicles: vehicles,
      per_intersection_metrics: per_int_metrics,
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

  # Append a point to a capped history list (newest at end)
  defp append_to_history(history, point) do
    (history ++ [point])
    |> Enum.take(-@history_size)
  end

  # Group vehicles by their nearest intersection based on lane → edge mapping
  defp group_vehicles_by_intersection(vehicles) do
    # Pre-compute edge → intersection lookup
    edge_lookup =
      Enum.flat_map(@intersection_edges, fn {int_id, edges} ->
        Enum.map(edges, fn edge -> {edge, int_id} end)
      end)

    Enum.reduce(vehicles, %{}, fn v, acc ->
      lane = v["lane"] || ""
      # Extract edge from lane ID: "edgeId_laneIndex" → "edgeId"
      edge = lane |> String.split("_") |> Enum.drop(-1) |> Enum.join("_")

      case Enum.find(edge_lookup, fn {e, _} -> e == edge end) do
        {_, int_id} ->
          Map.update(acc, int_id, [v], &[v | &1])
        nil ->
          # Also try matching internal edges (SUMO uses ":nodeId_..." for internal)
          int_id = find_internal_edge_intersection(lane)
          if int_id do
            Map.update(acc, int_id, [v], &[v | &1])
          else
            acc
          end
      end
    end)
  end

  # SUMO internal lanes follow pattern ":TRiia_Kalevi_0_0" → intersection "TRiia_Kalevi"
  defp find_internal_edge_intersection(lane) do
    if String.starts_with?(lane, ":") do
      # Strip leading ":" and try to match intersection IDs
      stripped = String.trim_leading(lane, ":")
      Enum.find(@intersection_ids, fn int_id -> String.starts_with?(stripped, int_id) end)
    else
      nil
    end
  end

  # Compute metrics for vehicles at a specific intersection
  defp compute_intersection_metrics([]) do
    %{"vehicle_count" => 0, "avg_speed" => 0.0, "congestion_index" => 0.0, "stopped" => 0}
  end

  defp compute_intersection_metrics(vehicles) do
    count = length(vehicles)
    speeds = Enum.map(vehicles, fn v -> v["speed"] || 0 end)
    stopped = Enum.count(speeds, &(&1 < 0.5))
    avg_speed = if count > 0, do: Float.round(Enum.sum(speeds) / count, 2), else: 0.0
    congestion = if count > 0, do: Float.round(stopped / count, 2), else: 0.0

    %{
      "vehicle_count" => count,
      "avg_speed" => avg_speed,
      "congestion_index" => congestion,
      "stopped" => stopped
    }
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
end
