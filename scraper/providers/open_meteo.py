from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from ..analyzer import make_hourly_point
from ..cities import CityConfig
from ..models import HourlyForecastPoint
from .base import WMO_CODE_MAP, WeatherProvider, http_get_json

HOURLY_VARS = (
    "temperature_2m,relative_humidity_2m,dew_point_2m,apparent_temperature,"
    "precipitation_probability,precipitation,rain,snowfall,weather_code,"
    "pressure_msl,cloud_cover,visibility,wind_speed_10m,wind_direction_10m,"
    "wind_gusts_10m,uv_index"
)


def parse_open_meteo_response(
    city: CityConfig, data: Dict[str, Any]
) -> List[HourlyForecastPoint]:
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    feels = hourly.get("apparent_temperature", [])
    dews = hourly.get("dew_point_2m", [])
    hums = hourly.get("relative_humidity_2m", [])
    pprobs = hourly.get("precipitation_probability", [])
    precips = hourly.get("precipitation", [])
    rains = hourly.get("rain", [])
    snows = hourly.get("snowfall", [])
    wcodes = hourly.get("weather_code", [])
    press = hourly.get("pressure_msl", [])
    clouds = hourly.get("cloud_cover", [])
    vis = hourly.get("visibility", [])
    wspds = hourly.get("wind_speed_10m", [])
    wdirs = hourly.get("wind_direction_10m", [])
    wgsts = hourly.get("wind_gusts_10m", [])
    uvs = hourly.get("uv_index", [])

    def _at(arr: List[Any], idx: int) -> Any:
        return arr[idx] if arr and idx < len(arr) else None

    points: List[HourlyForecastPoint] = []
    for i, t_loc in enumerate(times):
        temp_c = _at(temps, i)
        if temp_c is None:
            continue
        wcode = _at(wcodes, i)
        cond = WMO_CODE_MAP.get(int(wcode), f"WMO {wcode}") if wcode is not None else None
        vis_m = _at(vis, i)
        vis_km = round(float(vis_m) / 1000.0, 2) if vis_m is not None else None

        points.append(
            make_hourly_point(
                city=city,
                time_local=t_loc[:16],
                temp_c=temp_c,
                feels_c=_at(feels, i),
                dew_c=_at(dews, i),
                humidity_pct=_at(hums, i),
                precip_prob_pct=_at(pprobs, i),
                precip_mm=_at(precips, i),
                rain_mm=_at(rains, i),
                snow_cm=_at(snows, i),
                wind_speed_kmh=_at(wspds, i),
                wind_gust_kmh=_at(wgsts, i),
                wind_direction_deg=_at(wdirs, i),
                cloud_cover_pct=_at(clouds, i),
                pressure_hpa=_at(press, i),
                visibility_km=vis_km,
                uv_index=_at(uvs, i),
                condition=cond,
            )
        )
    return points


class OpenMeteoProvider(WeatherProvider):
    """Fetches 7-day (168-hour) best-match forecasts from Open-Meteo (open-meteo.com)."""

    website_id = "open_meteo"
    website_name = "Open-Meteo"

    def fetch_hourly(
        self, city: CityConfig
    ) -> Tuple[List[HourlyForecastPoint], str, str, Dict[str, Any]]:
        tz_enc = urllib.parse.quote(city.timezone)
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={city.latitude}&longitude={city.longitude}"
            f"&hourly={HOURLY_VARS}&timezone={tz_enc}&forecast_days=8"
        )
        data = http_get_json(url, timeout=15)
        points = parse_open_meteo_response(city, data)
        meta = {
            "elevation_m": data.get("elevation"),
            "generationtime_ms": data.get("generationtime_ms"),
            "model": "best_match",
        }
        return points, url, "live_official_api", meta
