defmodule DigitalTwinWeb.PageController do
  use DigitalTwinWeb, :controller

  def home(conn, _params) do
    render(conn, :home)
  end
end
