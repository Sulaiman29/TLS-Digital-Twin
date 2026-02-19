defmodule DigitalTwinWeb.Router do
  use DigitalTwinWeb, :router

  pipeline :browser do
    plug :accepts, ["html"]
    plug :fetch_session
    plug :fetch_live_flash
    plug :put_root_layout, html: {DigitalTwinWeb.Layouts, :root}
    plug :protect_from_forgery
    plug :put_secure_browser_headers
  end

  scope "/", DigitalTwinWeb do
    pipe_through :browser

    live "/", DashboardLive
  end
end
