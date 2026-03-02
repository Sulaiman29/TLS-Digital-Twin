defmodule DigitalTwin.MqttHandler do
  @moduledoc """
  Tortoise311 MQTT handler that subscribes to the Tartu simulation topics
  and feeds decoded JSON into the TrafficState GenServer.

  Topics consumed:
    - simulation/tartu/metrics/live
    - simulation/tartu/vehicles/live
    - simulation/tartu/tl/live
  """
  require Logger
  use Tortoise311.Handler

  alias DigitalTwin.TrafficState

  @impl true
  def init(_opts) do
    Logger.info("[MqttHandler] Handler initialized")
    {:ok, %{}}
  end

  @impl true
  def connection(:up, state) do
    Logger.info("[MqttHandler] Connected to MQTT broker")
    {:ok, state}
  end

  def connection(:down, state) do
    Logger.warning("[MqttHandler] Disconnected from MQTT broker")
    {:ok, state}
  end

  def connection(:terminating, state) do
    Logger.warning("[MqttHandler] MQTT connection terminating")
    {:ok, state}
  end

  @impl true
  def subscription(:up, topic, state) do
    Logger.info("[MqttHandler] Subscribed to #{topic}")
    {:ok, state}
  end

  def subscription({:warn, flags}, topic, state) do
    Logger.warning("[MqttHandler] Subscription warning on #{topic}: #{inspect(flags)}")
    {:ok, state}
  end

  def subscription({:error, reason}, topic, state) do
    Logger.error("[MqttHandler] Subscription error on #{topic}: #{inspect(reason)}")
    {:ok, state}
  end

  @impl true
  def handle_message(["simulation", "tartu", "metrics", "live"], payload, state) do
    case Jason.decode(payload) do
      {:ok, data} ->
        TrafficState.update_metrics(data)
        {:ok, state}

      {:error, _reason} ->
        {:ok, state}
    end
  end

  def handle_message(["simulation", "tartu", "vehicles", "live"], payload, state) do
    case Jason.decode(payload) do
      {:ok, data} ->
        TrafficState.update_vehicles(data)
        {:ok, state}

      {:error, _reason} ->
        {:ok, state}
    end
  end

  def handle_message(["simulation", "tartu", "tl", "live"], payload, state) do
    case Jason.decode(payload) do
      {:ok, data} ->
        TrafficState.update_traffic_lights(data)
        {:ok, state}

      {:error, _reason} ->
        {:ok, state}
    end
  end

  def handle_message(["simulation", "tartu", "blockchain", "live"], payload, state) do
    case Jason.decode(payload) do
      {:ok, data} ->
        TrafficState.update_blockchain(data)
        {:ok, state}

      {:error, _reason} ->
        {:ok, state}
    end
  end

  def handle_message(topic, _payload, state) do
    Logger.debug("[MqttHandler] Unhandled topic: #{Enum.join(topic, "/")}")
    {:ok, state}
  end

  @impl true
  def terminate(_reason, _state) do
    :ok
  end
end
