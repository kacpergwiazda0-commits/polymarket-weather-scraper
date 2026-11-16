from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..analyzer import make_hourly_point
from ..cities import CityConfig
from ..models import HourlyForecastPoint
from .base import WeatherProvider, http_get_json


def _idx(arr: Optional[List[Any]], i: int) -> Any:
    if not arr or i >= len(arr):
        return None
    return arr[i]


class WeatherComProvider(WeatherProvider):
    """Scrapes 15-day (360-hour) hourly forecasts from The Weather Channel (weather.com)."""

    website_id = "weather_com"
    website_name = "The Weather Channel (weather.com)"

    DEFAULT_WEB_API_KEY = "71f92ea9dd2f4790b92ea9dd2f779061"

    def fetch_hourly(
        self, city: CityConfig
    ) -> Tuple[List[HourlyForecastPoint], str, str, Dict[str, Any]]:
        api_key = os.getenv("TWC_API_KEY", "").strip() or self.DEFAULT_WEB_API_KEY
        is_fahrenheit = city.unit.upper() == "F"
        units = "e" if is_fahrenheit else "m"

        api_url = (
            f"https://api.weather.com/v3/wx/forecast/hourly/15day"
            f"?geocode={city.latitude},{city.longitude}"
            f"&format=json&units={units}&language=en-US&apiKey={api_key}"
        )
        page_url = f"https://weather.com/weather/hourbyhour/l/{city.latitude},{city.longitude}"
        data = http_get_json(api_url, timeout=15)

        times_local = data.get("validTimeLocal", [])
        times_utc = data.get("validTimeUtc", [])
        temps = data.get("temperature", [])
        feels = data.get("temperatureFeelsLike", [])
        dews = data.get("temperatureDewPoint", [])
        hums = data.get("relativeHumidity", [])
        pprobs = data.get("precipChance", [])
        qpfs = data.get("qpf", [])
        qpf_snows = data.get("qpfSnow", [])
        wspds = data.get("windSpeed", [])
        wgsts = data.get("windGust", [])
        wdirs = data.get("windDirection", [])
        wcards = data.get("windDirectionCardinal", [])
        clouds = data.get("cloudCover", [])
        pressures = data.get("pressureMeanSeaLevel", [])
        vis_list = data.get("visibility", [])
        uvs = data.get("uvIndex", [])
        phrases = data.get("wxPhraseLong", [])

        points: List[HourlyForecastPoint] = []
        for i, t_loc in enumerate(times_local):
            if not t_loc or len(t_loc) < 16:
                continue
            time_local = t_loc[:16]
            utc_ts = _idx(times_utc, i)
            time_utc = (
                datetime.fromtimestamp(int(utc_ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                if utc_ts is not None
                else None
            )

            temp_val = _idx(temps, i)
            if temp_val is None:
                continue
            feels_val = _idx(feels, i)
            dew_val = _idx(dews, i)
            qpf_val = _idx(qpfs, i)
            snow_val = _idx(qpf_snows, i)
            wspd_val = _idx(wspds, i)
            wgst_val = _idx(wgsts, i)
            pres_val = _idx(pressures, i)
            vis_val = _idx(vis_list, i)

            if is_fahrenheit:
                precip_mm = round(float(qpf_val) * 25.4, 2) if qpf_val is not None else None
                snow_cm = round(float(snow_val) * 2.54, 2) if snow_val is not None else None
                pres_hpa = round(float(pres_val) * 33.8639, 1) if pres_val is not None else None
                vis_km = round(float(vis_val) * 1.60934, 2) if vis_val is not None else None
            else:
                precip_mm = float(qpf_val) if qpf_val is not None else None
                snow_cm = float(snow_val) if snow_val is not None else None
                pres_hpa = float(pres_val) if pres_val is not None else None
                vis_km = float(vis_val) if vis_val is not None else None

            points.append(
                make_hourly_point(
                    city=city,
                    time_local=time_local,
                    time_utc=time_utc,
                    temp_f=float(temp_val) if is_fahrenheit else None,
                    temp_c=float(temp_val) if not is_fahrenheit else None,
                    feels_f=float(feels_val) if (is_fahrenheit and feels_val is not None) else None,
                    feels_c=float(feels_val) if (not is_fahrenheit and feels_val is not None) else None,
                    dew_f=float(dew_val) if (is_fahrenheit and dew_val is not None) else None,
                    dew_c=float(dew_val) if (not is_fahrenheit and dew_val is not None) else None,
                    humidity_pct=_idx(hums, i),
                    precip_prob_pct=_idx(pprobs, i),
                    precip_mm=precip_mm,
                    rain_mm=precip_mm,
                    snow_cm=snow_cm,
                    wind_speed_mph=float(wspd_val) if (is_fahrenheit and wspd_val is not None) else None,
                    wind_speed_kmh=float(wspd_val) if (not is_fahrenheit and wspd_val is not None) else None,
                    wind_gust_mph=float(wgst_val) if (is_fahrenheit and wgst_val is not None) else None,
                    wind_gust_kmh=float(wgst_val) if (not is_fahrenheit and wgst_val is not None) else None,
                    wind_direction_deg=_idx(wdirs, i),
                    wind_direction_cardinal=_idx(wcards, i),
                    cloud_cover_pct=_idx(clouds, i),
                    pressure_hpa=pres_hpa,
                    visibility_km=vis_km,
                    uv_index=_idx(uvs, i),
                    condition=_idx(phrases, i),
                )
            )

        return points, page_url, "live_web_api", {"units_queried": units, "total_hours_fetched": len(points)}
