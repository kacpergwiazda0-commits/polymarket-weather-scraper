from __future__ import annotations

import os
import urllib.parse
from typing import Any, Dict, List, Tuple

from ..analyzer import make_hourly_point
from ..cities import CityConfig
from ..models import HourlyForecastPoint
from .base import WeatherProvider, http_get_json
from .open_meteo import HOURLY_VARS, parse_open_meteo_response


class WeatherbitProvider(WeatherProvider):
    """
    Fetches 7-day (168-hour) forecasts from Weatherbit API (api.weatherbit.io/v2.0/forecast/hourly)
    when WEATHERBIT_API_KEY is set in .env, or falls back to the DWD ICON seamless hourly model
    (icon_seamless) when no API key is configured.
    """

    website_id = "weatherbit"
    website_name = "Weatherbit"

    def fetch_hourly(
        self, city: CityConfig
    ) -> Tuple[List[HourlyForecastPoint], str, str, Dict[str, Any]]:
        api_key = os.getenv("WEATHERBIT_API_KEY", "").strip()

        if api_key:
            url = (
                f"https://api.weatherbit.io/v2.0/forecast/hourly"
                f"?lat={city.latitude}&lon={city.longitude}&hours=168&key={api_key}"
            )
            data = http_get_json(url, timeout=15)
            rows = data.get("data", [])
            points: List[HourlyForecastPoint] = []
            for r in rows:
                t_loc = r.get("timestamp_local")
                if not t_loc or len(t_loc) < 16:
                    continue
                wspd_ms = r.get("wind_spd")
                wgst_ms = r.get("wind_gust_spd")
                points.append(
                    make_hourly_point(
                        city=city,
                        time_local=t_loc[:16],
                        time_utc=r.get("timestamp_utc"),
                        temp_c=r.get("temp"),
                        feels_c=r.get("app_temp"),
                        dew_c=r.get("dewpt"),
                        humidity_pct=r.get("rh"),
                        precip_prob_pct=r.get("pop"),
                        precip_mm=r.get("precip"),
                        snow_cm=(float(r["snow"]) / 10.0) if r.get("snow") is not None else None,
                        wind_speed_kmh=(float(wspd_ms) * 3.6) if wspd_ms is not None else None,
                        wind_gust_kmh=(float(wgst_ms) * 3.6) if wgst_ms is not None else None,
                        wind_direction_deg=r.get("wind_dir"),
                        wind_direction_cardinal=r.get("wind_cdir"),
                        cloud_cover_pct=r.get("clouds"),
                        pressure_hpa=r.get("slp") or r.get("pres"),
                        visibility_km=r.get("vis"),
                        uv_index=r.get("uv"),
                        condition=r.get("weather", {}).get("description")
                        if isinstance(r.get("weather"), dict)
                        else None,
                    )
                )
            sanitized_url = (
                f"https://api.weatherbit.io/v2.0/forecast/hourly"
                f"?lat={city.latitude}&lon={city.longitude}&hours=168"
            )
            return points, sanitized_url, "live_weatherbit_api", {"hours_count": len(points)}

        # Zero-key fallback: DWD ICON seamless global/regional hourly model
        tz_enc = urllib.parse.quote(city.timezone)
        fallback_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={city.latitude}&longitude={city.longitude}"
            f"&hourly={HOURLY_VARS}&models=icon_seamless&timezone={tz_enc}&forecast_days=8"
        )
        data = http_get_json(fallback_url, timeout=15)
        points = parse_open_meteo_response(city, data)
        return (
            points,
            fallback_url,
            "icon_seamless_model_fallback (set WEATHERBIT_API_KEY in .env for direct API)",
            {"model": "icon_seamless", "api_key_configured": False},
        )
