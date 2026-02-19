defmodule DigitalTwin.TrafficState do
  @moduledoc """
  GenServer holding the live state of the Tartu traffic network.
  Receives updates from the MQTT handler and broadcasts to PubSub
  so LiveView clients get real-time pushes.
  """
  use GenServer

  @pubsub DigitalTwin.PubSub
  @topic "traffic:tartu"

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
    new_state = %{state | metrics: metrics, last_update: DateTime.utc_now()}
    broadcast(new_state)
    {:noreply, new_state}
  end

  @impl true
  def handle_cast({:vehicles, payload}, state) do
    vehicles = Map.get(payload, "vehicles", [])
    new_state = %{state | vehicles: vehicles, last_update: DateTime.utc_now()}
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

  defp broadcast(state) do
    Phoenix.PubSub.broadcast(@pubsub, @topic, {:traffic_update, state})
  end
end
