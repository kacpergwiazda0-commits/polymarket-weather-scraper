from __future__ import annotations

import os
import urllib.parse
from typing import Any, Dict, List, Tuple

from ..analyzer import make_hourly_point
from ..cities import CityConfig
from ..models import HourlyForecastPoint
from .base import WeatherProvider, http_get_json
from .open_meteo import HOURLY_VARS, parse_open_meteo_response


class AerisWeatherProvider(WeatherProvider):
    """
    Fetches 7-day (168-hour) forecasts from AerisWeather / Xweather API when
    AERIS_CLIENT_ID and AERIS_CLIENT_SECRET are set in .env, or falls back to
    NOAA GFS/HRRR seamless hourly forecast (gfs_seamless) when no API key is configured.
    """

    website_id = "aerisweather"
    website_name = "AerisWeather (Xweather)"

    def fetch_hourly(
        self, city: CityConfig
    ) -> Tuple[List[HourlyForecastPoint], str, str, Dict[str, Any]]:
        client_id = os.getenv("AERIS_CLIENT_ID", "").strip()
        client_secret = os.getenv("AERIS_CLIENT_SECRET", "").strip()

        if client_id and client_secret:
            url = (
                f"https://data.api.xweather.com/forecasts/{city.latitude},{city.longitude}"
                f"?filter=1hr&limit=168&client_id={client_id}&client_secret={client_secret}"
            )
            data = http_get_json(url, timeout=15)
            responses = data.get("response", [])
            periods = responses[0].get("periods", []) if responses else []
            points: List[HourlyForecastPoint] = []
            for p in periods:
                dt_iso = p.get("dateTimeISO")
                if not dt_iso or len(dt_iso) < 16:
                    continue
                points.append(
                    make_hourly_point(
                        city=city,
                        time_local=dt_iso[:16],
                        temp_c=p.get("tempC"),
                        temp_f=p.get("tempF"),
                        feels_c=p.get("feelslikeC"),
                        feels_f=p.get("feelslikeF"),
                        dew_c=p.get("dewpointC"),
                        dew_f=p.get("dewpointF"),
                        humidity_pct=p.get("humidity"),
                        precip_prob_pct=p.get("pop"),
                        precip_mm=p.get("precipMM"),
                        snow_cm=p.get("snowCM"),
                        wind_speed_kmh=p.get("windSpeedKPH"),
                        wind_speed_mph=p.get("windSpeedMPH"),
                        wind_gust_kmh=p.get("windGustKPH"),
                        wind_gust_mph=p.get("windGustMPH"),
                        wind_direction_deg=p.get("windDirDEG"),
                        wind_direction_cardinal=p.get("windDir"),
                        cloud_cover_pct=p.get("sky"),
                        pressure_hpa=p.get("pressureMB"),
                        visibility_km=p.get("visibilityKM"),
                        uv_index=p.get("uvi"),
                        condition=p.get("weather"),
                    )
                )
            sanitized_url = (
                f"https://data.api.xweather.com/forecasts/{city.latitude},{city.longitude}"
                f"?filter=1hr&limit=168"
            )
            return points, sanitized_url, "live_aerisweather_api", {"periods_count": len(points)}

        # Zero-key fallback: NOAA GFS + HRRR seamless hourly model (core US/Global model behind Aeris)
        tz_enc = urllib.parse.quote(city.timezone)
        fallback_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={city.latitude}&longitude={city.longitude}"
            f"&hourly={HOURLY_VARS}&models=gfs_seamless&timezone={tz_enc}&forecast_days=8"
        )
        data = http_get_json(fallback_url, timeout=15)
        points = parse_open_meteo_response(city, data)
        return (
            points,
            fallback_url,
            "gfs_seamless_model_fallback (set AERIS_CLIENT_ID & AERIS_CLIENT_SECRET in .env for direct API)",
            {"model": "gfs_seamless", "api_key_configured": False},
        )
