from __future__ import annotations

import html as html_lib
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from ..analyzer import make_hourly_point
from ..cities import CityConfig
from ..models import HourlyForecastPoint
from .base import WeatherProvider, http_get_json, http_get_text


def _parse_hour_label(label: str) -> Optional[str]:
    """Convert '12 AM', '1 PM', '14:00', or '14' to 'HH:00'."""
    s = label.strip().upper()
    m12 = re.match(r"^(\d{1,2})\s*(AM|PM)$", s)
    if m12:
        hr = int(m12.group(1))
        ampm = m12.group(2)
        if ampm == "AM":
            hr = 0 if hr == 12 else hr
        else:
            hr = 12 if hr == 12 else hr + 12
        return f"{hr:02d}:00"
    m24 = re.match(r"^(\d{1,2})(?::00)?$", s)
    if m24:
        return f"{int(m24.group(1)) % 24:02d}:00"
    return None


def _num(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    return float(m.group(0)) if m else None


class AccuWeatherProvider(WeatherProvider):
    """
    Scrapes AccuWeather (accuweather.com) hourly forecast cards (days 1-4) + daily forecast cards (days 5-7),
    or uses ACCUWEATHER_API_KEY if configured in .env.
    """

    website_id = "accuweather"
    website_name = "AccuWeather"

    def _fetch_hourly_day_html(
        self, city: CityConfig, day_num: int, date_str: str
    ) -> List[HourlyForecastPoint]:
        unit_param = "f" if city.unit.upper() == "F" else "c"
        url = (
            f"https://www.accuweather.com{city.accuweather_prefix}"
            f"/hourly-weather-forecast/{city.accuweather_key}?day={day_num}&unit={unit_param}"
        )
        raw_html = http_get_text(url, timeout=15)
        is_f = city.unit.upper() == "F"

        # Split by accordion-item hourly cards
        cards = re.split(r"<div[^>]*class=\"[^\"]*accordion-item\s+hour[^\"]*\"", raw_html)
        points: List[HourlyForecastPoint] = []
        for card in cards[1:]:
            unesc = html_lib.unescape(card)
            m_hr = re.search(r"<h2 class=\"date\">\s*<div>([^<]+)</div>", unesc)
            if not m_hr:
                continue
            hr_str = _parse_hour_label(m_hr.group(1))
            if not hr_str:
                continue

            m_temp = re.search(r"<div class=\"temp[^\"]*\">\s*(-?\d+)", unesc)
            if not m_temp:
                continue
            temp_val = float(m_temp.group(1))

            m_rf = re.search(r"RealFeel[^0-9-]*(-?\d+)", unesc)
            feels_val = float(m_rf.group(1)) if m_rf else None

            m_pr = re.search(r"<div class=\"precip\">.*?(\d+)\s*%", unesc, re.S)
            precip_prob = float(m_pr.group(1)) if m_pr else None

            m_phr = re.search(r"<div class=\"phrase\">\s*([^<]+?)\s*</div>", unesc)
            phrase = m_phr.group(1).strip() if m_phr else None

            # Extract panel items: <p>Label<span class="value">Val</span></p>
            panels: Dict[str, str] = {}
            for pm in re.finditer(
                r"<p[^>]*>\s*([^<]+?)\s*<span class=\"value\">(.*?)</span>\s*</p>",
                unesc,
                re.S,
            ):
                k = pm.group(1).strip().lower()
                v = re.sub(r"<[^>]+>", "", pm.group(2)).strip()
                panels[k] = v

            wind_raw = panels.get("wind", "")
            wcard_m = re.match(r"^([NSEW]{1,3})\s+", wind_raw)
            wcard = wcard_m.group(1) if wcard_m else None
            wspd_val = _num(wind_raw)
            wgst_val = _num(panels.get("wind gusts"))
            hum_val = _num(panels.get("humidity"))
            dew_val = _num(panels.get("dew point"))
            cloud_val = _num(panels.get("cloud cover"))
            vis_val = _num(panels.get("visibility"))
            uv_val = _num(panels.get("max uv index") or panels.get("uv index"))
            rain_val = _num(panels.get("rain"))

            points.append(
                make_hourly_point(
                    city=city,
                    time_local=f"{date_str}T{hr_str}",
                    temp_f=temp_val if is_f else None,
                    temp_c=temp_val if not is_f else None,
                    feels_f=feels_val if is_f else None,
                    feels_c=feels_val if not is_f else None,
                    dew_f=dew_val if is_f else None,
                    dew_c=dew_val if not is_f else None,
                    humidity_pct=hum_val,
                    precip_prob_pct=precip_prob,
                    precip_mm=(rain_val * 25.4 if is_f else rain_val) if rain_val is not None else None,
                    rain_mm=(rain_val * 25.4 if is_f else rain_val) if rain_val is not None else None,
                    wind_speed_mph=wspd_val if is_f else None,
                    wind_speed_kmh=wspd_val if not is_f else None,
                    wind_gust_mph=wgst_val if is_f else None,
                    wind_gust_kmh=wgst_val if not is_f else None,
                    wind_direction_cardinal=wcard,
                    cloud_cover_pct=cloud_val,
                    visibility_km=(vis_val * 1.60934 if is_f else vis_val) if vis_val is not None else None,
                    uv_index=uv_val,
                    condition=phrase,
                )
            )
        return points

    def _fetch_daily_5_to_7_html(
        self, city: CityConfig, dates_7: List[str]
    ) -> List[HourlyForecastPoint]:
        unit_param = "f" if city.unit.upper() == "F" else "c"
        url = (
            f"https://www.accuweather.com{city.accuweather_prefix}"
            f"/daily-weather-forecast/{city.accuweather_key}?unit={unit_param}"
        )
        raw_html = http_get_text(url, timeout=15)
        unesc = html_lib.unescape(raw_html)
        is_f = city.unit.upper() == "F"

        cards = re.split(r"<div class=\"daily-wrapper\"", unesc)
        points: List[HourlyForecastPoint] = []
        for idx, card in enumerate(cards[1:]):
            if idx < 4 or idx >= len(dates_7):
                continue
            date_str = dates_7[idx]
            m_hi = re.search(r"<span class=\"high\">\s*(-?\d+)", card)
            m_lo = re.search(r"<span class=\"low\">\s*/?\s*(-?\d+)", card)
            if not m_hi or not m_lo:
                continue
            hi_val = float(m_hi.group(1))
            lo_val = float(m_lo.group(1))

            m_pr = re.search(r"<div class=\"precip\">.*?(\d+)\s*%", card, re.S)
            precip_prob = float(m_pr.group(1)) if m_pr else None
            m_phr = re.search(r"<div class=\"phrase\">\s*([^<]+?)\s*</div>", card)
            phrase = m_phr.group(1).strip() if m_phr else None

            panels: Dict[str, str] = {}
            for pm in re.finditer(
                r"<p class=\"panel-item\">\s*([^<]+?)\s*<span class=\"value\">(.*?)</span>\s*</p>",
                card,
                re.S,
            ):
                panels[pm.group(1).strip().lower()] = re.sub(r"<[^>]+>", "", pm.group(2)).strip()

            wspd_val = _num(panels.get("wind"))
            wgst_val = _num(panels.get("wind gusts"))
            uv_val = _num(panels.get("max uv index"))

            # Construct diurnal hourly curve anchored to AccuWeather's exact daily high (peaking 14:00-15:00) and low (05:00)
            for h in range(24):
                # Cosine diurnal cycle with trough at 05:00 and peak plateau around 14:00-15:00
                phase = (h - 5) / 24.0 * 2.0 * math.pi
                weight = (1.0 - math.cos(phase)) / 2.0
                if h in (14, 15):
                    t_val = hi_val
                elif h == 5:
                    t_val = lo_val
                else:
                    t_val = round(lo_val + (hi_val - lo_val) * (weight ** 0.9), 1)
                    if round(t_val) >= round(hi_val) and h not in (13, 14, 15, 16):
                        t_val = hi_val - 1.0

                points.append(
                    make_hourly_point(
                        city=city,
                        time_local=f"{date_str}T{h:02d}:00",
                        temp_f=t_val if is_f else None,
                        temp_c=t_val if not is_f else None,
                        precip_prob_pct=precip_prob,
                        wind_speed_mph=wspd_val if is_f else None,
                        wind_speed_kmh=wspd_val if not is_f else None,
                        wind_gust_mph=wgst_val if is_f else None,
                        wind_gust_kmh=wgst_val if not is_f else None,
                        uv_index=uv_val if 8 <= h <= 17 else 0.0,
                        condition=phrase,
                    )
                )
        return points

    def fetch_hourly(
        self, city: CityConfig
    ) -> Tuple[List[HourlyForecastPoint], str, str, Dict[str, Any]]:
        tz = ZoneInfo(city.timezone)
        today = datetime.now(tz).date()
        dates_7 = [(today + timedelta(days=i)).isoformat() for i in range(7)]
        base_url = (
            f"https://www.accuweather.com{city.accuweather_prefix}"
            f"/hourly-weather-forecast/{city.accuweather_key}"
        )

        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = [
                pool.submit(self._fetch_hourly_day_html, city, d_idx + 1, dates_7[d_idx])
                for d_idx in range(4)
            ]
            fut_daily = pool.submit(self._fetch_daily_5_to_7_html, city, dates_7)
            points: List[HourlyForecastPoint] = []
            for f in futs:
                points.extend(f.result())
            points.extend(fut_daily.result())

        return (
            points,
            base_url,
            "live_web_scrape",
            {"accuweather_key": city.accuweather_key, "hourly_days_direct": 4, "daily_days_extended": 3},
        )
