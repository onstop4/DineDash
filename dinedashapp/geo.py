from geopy.distance import geodesic
from geopy.geocoders import Nominatim

geolocator = Nominatim(user_agent="DineDash")


def get_coordinates(location):
    location = geolocator.geocode(location)
    return [location.latitude, location.longitude]


def get_distance_in_miles(coordinate_1, coordinate_2):
    return geodesic(coordinate_1, coordinate_2).miles
