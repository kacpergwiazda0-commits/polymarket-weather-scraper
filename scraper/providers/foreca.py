from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from ..analyzer import make_hourly_point
from ..cities import CityConfig
from ..models import HourlyForecastPoint
from .base import WeatherProvider, http_get_text


def _num(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except Exception:
        return None


class ForecaProvider(WeatherProvider):
    """Scrapes 7-day hourly forecast JSON embedded in Foreca (foreca.com) hourly pages."""

    website_id = "foreca"
    website_name = "Foreca"

    def _fetch_day(self, city: CityConfig, day_idx: int) -> List[Dict[str, Any]]:
        slug_url = city.name.replace(" ", "-")
        url = f"https://www.foreca.com/{city.foreca_id}/{slug_url}/hourly?day={day_idx}"
        html = http_get_text(url, timeout=15)
        idx = html.find("renderHourly")
        if idx < 0:
            return []
        end_idx = html.find("});", idx)
        segment = html[idx : end_idx + 2] if end_idx > idx else html[idx : idx + 35000]
        m = re.search(r"data:\s*(\[\{\"time\":.*?\])\s*(?:,|\})", segment, re.S)
        if not m:
            return []
        return json.loads(m.group(1))

    def fetch_hourly(
        self, city: CityConfig
    ) -> Tuple[List[HourlyForecastPoint], str, str, Dict[str, Any]]:
        slug_url = city.name.replace(" ", "-")
        base_url = f"https://www.foreca.com/{city.foreca_id}/{slug_url}/hourly"

        with ThreadPoolExecutor(max_workers=4) as pool:
            day_lists = list(pool.map(lambda d: self._fetch_day(city, d), range(7)))

        points: List[HourlyForecastPoint] = []
        for rows in day_lists:
            for r in rows:
                t_loc = r.get("time")
                if not t_loc or len(t_loc) < 16:
                    continue
                points.append(
                    make_hourly_point(
                        city=city,
                        time_local=t_loc[:16],
                        time_utc=r.get("dateObject"),
                        temp_c=_num(r.get("temp")),
                        temp_f=_num(r.get("tempf")),
                        feels_c=_num(r.get("flike")),
                        feels_f=_num(r.get("flikef")),
                        dew_c=_num(r.get("dewp")),
                        dew_f=_num(r.get("dewpf")),
                        humidity_pct=_num(r.get("rhum")),
                        precip_prob_pct=_num(r.get("rainp")),
                        precip_mm=_num(r.get("rain")),
                        rain_mm=_num(r.get("rain")),
                        snow_cm=(_num(r.get("snowff")) / 10.0) if _num(r.get("snowff")) is not None else None,
                        wind_speed_kmh=_num(r.get("windskmh")),
                        wind_speed_mph=_num(r.get("windsmph")),
                        wind_gust_kmh=_num(r.get("maxwindkmh")),
                        wind_gust_mph=_num(r.get("maxwindmph")),
                        wind_direction_deg=int(_num(r.get("windd"))) if _num(r.get("windd")) is not None else None,
                        wind_direction_cardinal=r.get("windCardinal"),
                        cloud_cover_pct=_num(r.get("cloud")),
                        pressure_hpa=_num(r.get("pres")),
                        uv_index=_num(r.get("uvi")),
                        air_quality_index=int(_num(r.get("aqi"))) if _num(r.get("aqi")) is not None else None,
                        condition=r.get("wx"),
                    )
                )

        return points, base_url, "live_web_scrape", {"foreca_location_id": city.foreca_id}
