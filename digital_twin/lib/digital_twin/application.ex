defmodule DigitalTwin.Application do
  @moduledoc false

  use Application

  @impl true
  def start(_type, _args) do
    mqtt_config = Application.get_env(:digital_twin, :mqtt, [])
    mqtt_host = Keyword.get(mqtt_config, :host, "localhost")
    mqtt_port = Keyword.get(mqtt_config, :port, 1883)

    children = [
      DigitalTwinWeb.Telemetry,
      {DNSCluster, query: Application.get_env(:digital_twin, :dns_cluster_query) || :ignore},
      {Phoenix.PubSub, name: DigitalTwin.PubSub},
      # TrafficState GenServer — holds live city state
      DigitalTwin.TrafficState,
      # MQTT connection via Tortoise311
      {Tortoise311.Connection,
       [
         client_id: "digital_twin_elixir",
         handler: {DigitalTwin.MqttHandler, []},
         server: {Tortoise311.Transport.Tcp, host: String.to_charlist(mqtt_host), port: mqtt_port},
         subscriptions: [
           {"simulation/tartu/metrics/live", 0},
           {"simulation/tartu/vehicles/live", 0},
           {"simulation/tartu/tl/live", 0},
           {"simulation/tartu/blockchain/live", 0},
           {"simulation/tartu/audit/live", 0}
         ]
       ]},
      # Phoenix endpoint — must be last
      DigitalTwinWeb.Endpoint
    ]

    opts = [strategy: :one_for_one, name: DigitalTwin.Supervisor]
    Supervisor.start_link(children, opts)
  end

  @impl true
  def config_change(changed, _new, removed) do
    DigitalTwinWeb.Endpoint.config_change(changed, removed)
    :ok
  end
end
