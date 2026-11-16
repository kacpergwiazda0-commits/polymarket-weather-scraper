from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from ..analyzer import make_hourly_point
from ..cities import CityConfig
from ..models import HourlyForecastPoint
from .base import WeatherProvider, http_get_text, utc_iso_to_local


def _clean_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    m = re.search(r"[-+]?\d+(?:\.\d+)?", str(val))
    return float(m.group(0)) if m else None


class MSNWeatherProvider(WeatherProvider):
    """Scrapes 10-day hourly forecast JSON directly from Microsoft MSN Weather."""

    website_id = "msn_weather"
    website_name = "Microsoft Weather (MSN)"

    def fetch_hourly(
        self, city: CityConfig
    ) -> Tuple[List[HourlyForecastPoint], str, str, Dict[str, Any]]:
        locale = "en-us" if city.unit.upper() == "F" else "en-gb"
        loc_slug = city.name.replace(" ", "-")
        url = (
            f"https://www.msn.com/{locale}/weather/hourlyforecast/"
            f"in-{loc_slug}?lat={city.latitude}&lon={city.longitude}"
        )
        html = http_get_text(url, timeout=18)

        state_json: Optional[Dict[str, Any]] = None
        for script_body in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S):
            stripped = script_body.strip()
            if stripped.startswith('{"SharedState"') and '"WeatherData"' in stripped:
                state_json = json.loads(stripped)
                break

        if not state_json or "WeatherData" not in state_json:
            raise RuntimeError("Could not locate embedded WeatherData state on MSN Weather page")

        wd = state_json["WeatherData"].get("_@STATE@_", {})
        forecast_days = wd.get("forecast", [])
        is_fahrenheit = locale == "en-us"

        points: List[HourlyForecastPoint] = []
        for day_obj in forecast_days:
            for hr in day_obj.get("hourly", []):
                time_info = hr.get("time", {})
                utc_iso = time_info.get("dataValue") if isinstance(time_info, dict) else None
                if not utc_iso and hr.get("timeStr"):
                    utc_iso = hr["timeStr"]
                if not utc_iso:
                    continue

                time_local, time_utc = utc_iso_to_local(utc_iso, city.timezone)
                temp_val = _clean_float(hr.get("temperature"))
                feels_val = _clean_float(hr.get("feels"))
                dew_val = _clean_float(hr.get("dewPt"))
                wspd_val = _clean_float(hr.get("windSpeed"))
                wgst_val = _clean_float(hr.get("windGust"))
                wspd_unit = str(hr.get("windSpeedUnit", "")).lower()

                wspd_mph = wspd_val if "mph" in wspd_unit or is_fahrenheit else None
                wspd_kmh = wspd_val if not wspd_mph and wspd_val is not None else None
                wgst_mph = wgst_val if "mph" in str(hr.get("windGust", "")).lower() or is_fahrenheit else None
                wgst_kmh = wgst_val if not wgst_mph and wgst_val is not None else None

                pres_val = _clean_float(hr.get("airPressure"))
                pres_unit = str(hr.get("pressureUnit", "")).lower()
                if pres_val is not None and (pres_unit == "in" or pres_val < 100):
                    pres_hpa = round(pres_val * 33.8639, 1)
                else:
                    pres_hpa = pres_val

                vis_val = _clean_float(hr.get("visibility"))
                if vis_val is not None and is_fahrenheit:
                    vis_km = round(vis_val * 1.60934, 2)
                else:
                    vis_km = vis_val

                rain_val = _clean_float(hr.get("rainAmount"))
                snow_val = _clean_float(hr.get("snowAmount"))
                if is_fahrenheit:
                    rain_mm = round(rain_val * 25.4, 2) if rain_val is not None else None
                    snow_cm = round(snow_val * 2.54, 2) if snow_val is not None else None
                else:
                    rain_mm = rain_val
                    snow_cm = snow_val

                points.append(
                    make_hourly_point(
                        city=city,
                        time_local=time_local,
                        time_utc=time_utc,
                        temp_f=temp_val if is_fahrenheit else None,
                        temp_c=temp_val if not is_fahrenheit else None,
                        feels_f=feels_val if is_fahrenheit else None,
                        feels_c=feels_val if not is_fahrenheit else None,
                        dew_f=dew_val if is_fahrenheit else None,
                        dew_c=dew_val if not is_fahrenheit else None,
                        humidity_pct=_clean_float(hr.get("humidity")),
                        precip_prob_pct=_clean_float(hr.get("precipitation")),
                        precip_mm=rain_mm,
                        rain_mm=rain_mm,
                        snow_cm=snow_cm,
                        wind_speed_kmh=wspd_kmh,
                        wind_speed_mph=wspd_mph,
                        wind_gust_kmh=wgst_kmh,
                        wind_gust_mph=wgst_mph,
                        wind_direction_deg=int(_clean_float(hr.get("windDir")))
                        if _clean_float(hr.get("windDir")) is not None
                        else None,
                        cloud_cover_pct=_clean_float(hr.get("cloudCover")),
                        pressure_hpa=pres_hpa,
                        visibility_km=vis_km,
                        uv_index=_clean_float(hr.get("uv")),
                        air_quality_index=int(_clean_float(hr.get("aqi")))
                        if _clean_float(hr.get("aqi")) is not None
                        else None,
                        condition=hr.get("cap"),
                    )
                )

        meta = {
            "provider_source": wd.get("provider") or wd.get("source") or "Foreca/Microsoft Weather",
            "last_updated": wd.get("lastUpdated"),
            "locale_used": locale,
        }
        return points, url, "live_web_scrape", meta
