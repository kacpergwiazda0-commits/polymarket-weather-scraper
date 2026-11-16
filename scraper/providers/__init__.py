from __future__ import annotations

from typing import Dict, List

from .accuweather import AccuWeatherProvider
from .aerisweather import AerisWeatherProvider
from .apple_weather import AppleWeatherProvider
from .base import WeatherProvider
from .foreca import ForecaProvider
from .meteoblue import MeteoblueProvider
from .msn_weather import MSNWeatherProvider
from .open_meteo import OpenMeteoProvider
from .uk_met_office import UKMetOfficeProvider
from .weather_com import WeatherComProvider
from .weatherbit import WeatherbitProvider
from .yr_no import YrNoProvider

ALL_PROVIDERS: List[WeatherProvider] = [
    MSNWeatherProvider(),       # 1. Microsoft Weather (MSN Weather)
    WeatherComProvider(),       # 2. The Weather Channel (weather.com)
    ForecaProvider(),           # 3. Foreca (foreca.com)
    AccuWeatherProvider(),      # 4. AccuWeather (accuweather.com)
    MeteoblueProvider(),        # 5. meteoblue (meteoblue.com)
    AerisWeatherProvider(),     # 6. AerisWeather / Xweather (aerisweather.com)
    WeatherbitProvider(),       # 7. Weatherbit (weatherbit.io)
    OpenMeteoProvider(),        # 8. Open-Meteo (open-meteo.com)
    YrNoProvider(),             # 9. Yr.no (yr.no / MET Norway)
    UKMetOfficeProvider(),      # 10. UK Met Office (metoffice.gov.uk)
    AppleWeatherProvider(),     # 11. Apple Weather (WeatherKit)
]

PROVIDERS_BY_ID: Dict[str, WeatherProvider] = {p.website_id: p for p in ALL_PROVIDERS}
