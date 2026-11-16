from __future__ import annotations

import json
import os
import re
import urllib.parse
from typing import Any, Dict, List, Tuple

from ..analyzer import make_hourly_point
from ..cities import CityConfig
from ..models import HourlyForecastPoint
from .base import WeatherProvider, http_get_json, http_get_text, utc_iso_to_local
from .open_meteo import HOURLY_VARS, parse_open_meteo_response


class AppleWeatherProvider(WeatherProvider):
    """
    Fetches 10-day (238-hour) Apple Weather (WeatherKit) hourly forecasts via
    DuckDuckGo's Apple WeatherKit endpoint (or direct APPLE_WEATHERKIT_BEARER_TOKEN if set in .env),
    with automatic ECMWF+GFS fallback.
    """

    website_id = "apple_weather"
    website_name = "Apple Weather (WeatherKit)"

    def _parse_weatherkit_payload(
        self, city: CityConfig, payload: Dict[str, Any]
    ) -> List[HourlyForecastPoint]:
        hours = payload.get("forecastHourly", {}).get("hours", [])
        points: List[HourlyForecastPoint] = []
        for hr in hours:
            t_start = hr.get("forecastStart")
            temp_c = hr.get("temperature")
            if not t_start or temp_c is None:
                continue
            time_local, time_utc = utc_iso_to_local(t_start, city.timezone)
            hum_raw = hr.get("humidity")
            hum_pct = float(hum_raw) * 100.0 if hum_raw is not None and float(hum_raw) <= 1.0 else hum_raw
            pprob_raw = hr.get("precipitationChance")
            pprob_pct = (
                float(pprob_raw) * 100.0
                if pprob_raw is not None and float(pprob_raw) <= 1.0
                else pprob_raw
            )
            cloud_raw = hr.get("cloudCover")
            cloud_pct = (
                float(cloud_raw) * 100.0
                if cloud_raw is not None and float(cloud_raw) <= 1.0
                else cloud_raw
            )
            vis_m = hr.get("visibility")
            vis_km = round(float(vis_m) / 1000.0, 2) if vis_m is not None else None

            points.append(
                make_hourly_point(
                    city=city,
                    time_local=time_local,
                    time_utc=time_utc,
                    temp_c=float(temp_c),
                    feels_c=hr.get("temperatureApparent"),
                    dew_c=hr.get("temperatureDewPoint"),
                    humidity_pct=hum_pct,
                    precip_prob_pct=pprob_pct,
                    precip_mm=hr.get("precipitationAmount"),
                    rain_mm=hr.get("precipitationAmount"),
                    snow_cm=(float(hr["snowfallAmount"]) / 10.0)
                    if hr.get("snowfallAmount") is not None
                    else None,
                    wind_speed_kmh=hr.get("windSpeed"),
                    wind_gust_kmh=hr.get("windGust"),
                    wind_direction_deg=hr.get("windDirection"),
                    cloud_cover_pct=cloud_pct,
                    pressure_hpa=hr.get("pressure"),
                    visibility_km=vis_km,
                    uv_index=hr.get("uvIndex"),
                    condition=hr.get("conditionCode"),
                )
            )
        return points

    def fetch_hourly(
        self, city: CityConfig
    ) -> Tuple[List[HourlyForecastPoint], str, str, Dict[str, Any]]:
        token = os.getenv("APPLE_WEATHERKIT_BEARER_TOKEN", "").strip()
        if token:
            wk_url = (
                f"https://weatherkit.apple.com/api/v1/weather/en/"
                f"{city.latitude}/{city.longitude}"
                f"?dataSets=forecastHourly,forecastDaily&timezone={urllib.parse.quote(city.timezone)}"
            )
            data = http_get_json(
                wk_url, headers={"Authorization": f"Bearer {token}"}, timeout=15
            )
            pts = self._parse_weatherkit_payload(city, data)
            if pts:
                return pts, wk_url, "live_apple_weatherkit_api", {"hours_count": len(pts)}

        # Primary keyless route: DuckDuckGo spice endpoint (returns raw Apple WeatherKit JSON)
        queries = [f"{city.name} {city.country}", city.name]
        for q in queries:
            spice_url = f"https://duckduckgo.com/js/spice/forecast/{urllib.parse.quote(q)}/en"
            try:
                body = http_get_text(spice_url, timeout=15)
                m = re.search(r"ddg_spice_forecast\(\s*(\{.*\})\s*\);?\s*$", body, re.S)
                if m:
                    payload = json.loads(m.group(1))
                    pts = self._parse_weatherkit_payload(city, payload)
                    if pts:
                        return (
                            pts,
                            spice_url,
                            "live_apple_weatherkit_feed",
                            {
                                "hours_count": len(pts),
                                "reported_location": payload.get("location"),
                            },
                        )
            except Exception:
                continue

        # Fallback: ECMWF IFS 0.25° model (core global model behind Apple Weather)
        tz_enc = urllib.parse.quote(city.timezone)
        fallback_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={city.latitude}&longitude={city.longitude}"
            f"&hourly={HOURLY_VARS}&models=ecmwf_ifs025&timezone={tz_enc}&forecast_days=8"
        )
        data = http_get_json(fallback_url, timeout=15)
        pts = parse_open_meteo_response(city, data)
        return pts, fallback_url, "ecmwf_ifs025_apple_model_fallback", {"model": "ecmwf_ifs025"}
