import math

BASE_LAT = 58.3780     # Tartu reference
BASE_LON = 26.7280

def xy_to_latlon(x, y):
    """
    Convert SUMO Cartesian (meters) -> Leaflet lat/lon
    using a simple local projection around a chosen base point.
    """
    # meters to degrees
    dlat = y / 111320.0
    dlon = x / (111320.0 * math.cos(math.radians(BASE_LAT)))

    lat = BASE_LAT + dlat
    lon = BASE_LON + dlon
    return lat, lon
