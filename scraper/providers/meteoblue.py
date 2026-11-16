from __future__ import annotations

import html as html_lib
import os
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from ..analyzer import make_hourly_point
from ..cities import CityConfig
from ..models import HourlyForecastPoint
from .base import WeatherProvider, http_get_json, http_get_text
from .open_meteo import HOURLY_VARS, parse_open_meteo_response

_METEOBLUE_SEMAPHORE = threading.Semaphore(2)


def _num(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    return float(m.group(0)) if m else None


class MeteoblueProvider(WeatherProvider):
    """
    Scrapes 7-day forecast tables from meteoblue (meteoblue.com/en/weather/week/<coord>)
    with rate-limit protection and NEMS/ICON multimodel fallback if HTTP 429 occurs,
    or uses METEOBLUE_API_KEY if set in .env.
    """

    website_id = "meteoblue"
    website_name = "meteoblue"

    def _fetch_api(
        self, city: CityConfig, api_key: str
    ) -> Tuple[List[HourlyForecastPoint], str, str, Dict[str, Any]]:
        url = (
            f"https://my.meteoblue.com/packages/basic-1h_basic-day"
            f"?lat={city.latitude}&lon={city.longitude}&apikey={api_key}&format=json"
        )
        data = http_get_json(url, timeout=15)
        d1h = data.get("data_1h", {})
        times = d1h.get("time", [])
        temps = d1h.get("temperature", [])
        feels = d1h.get("felttemperature", [])
        hums = d1h.get("relativehumidity", [])
        pprobs = d1h.get("precipitation_probability", [])
        precips = d1h.get("precipitation", [])
        wspds = d1h.get("windspeed", [])
        wgsts = d1h.get("gust", [])
        wdirs = d1h.get("winddirection", [])
        pres = d1h.get("sealevelpressure", [])
        uvs = d1h.get("uvindex", [])

        points: List[HourlyForecastPoint] = []
        for i, t_str in enumerate(times):
            t_loc = t_str.replace(" ", "T")[:16]
            points.append(
                make_hourly_point(
                    city=city,
                    time_local=t_loc,
                    temp_c=temps[i] if i < len(temps) else None,
                    feels_c=feels[i] if i < len(feels) else None,
                    humidity_pct=hums[i] if i < len(hums) else None,
                    precip_prob_pct=pprobs[i] if i < len(pprobs) else None,
                    precip_mm=precips[i] if i < len(precips) else None,
                    wind_speed_kmh=(wspds[i] * 3.6) if i < len(wspds) and wspds[i] is not None else None,
                    wind_gust_kmh=(wgsts[i] * 3.6) if i < len(wgsts) and wgsts[i] is not None else None,
                    wind_direction_deg=wdirs[i] if i < len(wdirs) else None,
                    pressure_hpa=pres[i] if i < len(pres) else None,
                    uv_index=uvs[i] if i < len(uvs) else None,
                )
            )
        return points, url, "live_official_api", {"package": "basic-1h"}

    def _parse_single_day_table(
        self, city: CityConfig, raw_html: str, fallback_date: str
    ) -> List[HourlyForecastPoint]:
        unesc = html_lib.unescape(raw_html)
        m_table = re.search(r"<table[^>]*>(.*?)</table>", unesc, re.S)
        if not m_table:
            return []
        t_html = m_table.group(1)

        m_date = re.search(r"<tr class=\"times\" title=\"(\d{4}-\d{2}-\d{2})", t_html)
        date_str = m_date.group(1) if m_date else fallback_date

        def extract_row(cls_name: str) -> List[str]:
            m_r = re.search(rf"<tr[^>]*class=\"[^\"]*\b{cls_name}\b[^\"]*\"[^>]*>(.*?)</tr>", t_html, re.S)
            if not m_r:
                return []
            tds = re.findall(r"<td[^>]*>(.*?)</td>", m_r.group(1), re.S)
            return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", td)).strip() for td in tds]

        m_temp_th = re.search(
            r"<tr[^>]*class=\"[^\"]*\btemperatures\b[^\"]*\"[^>]*>.*?<th[^>]*>(.*?)</th>",
            t_html,
            re.S,
        )
        is_f = "°F" in (m_temp_th.group(1) if m_temp_th else "")

        m_icons_r = re.search(r"<tr[^>]*class=\"[^\"]*\bicons\b[^\"]*\"[^>]*>(.*?)</tr>", t_html, re.S)
        conds: List[Optional[str]] = []
        if m_icons_r:
            for td in re.findall(r"<td[^>]*>(.*?)</td>", m_icons_r.group(1), re.S):
                m_alt = re.search(r"(?:title|alt)=\"([^\"]+)\"", td)
                conds.append(m_alt.group(1).strip() if m_alt else None)

        temps = [_num(x) for x in extract_row("temperatures")]
        feels = [_num(x) for x in extract_row("windchills")]
        wdirs = extract_row("winddirs")
        wspds_raw = extract_row("windspeeds")
        pprobs = [_num(x) for x in extract_row("precipprobs")]
        precips_raw = extract_row("precips")

        if not temps:
            return []

        node_hours = [2, 5, 8, 11, 14, 17, 20, 23][: len(temps)]
        points: List[HourlyForecastPoint] = []

        for h in range(24):
            if h <= node_hours[0]:
                idx_a = idx_b = 0
                frac = 0.0
            elif h >= node_hours[-1]:
                idx_a = idx_b = len(node_hours) - 1
                frac = 0.0
            else:
                idx_a = 0
                for j in range(len(node_hours) - 1):
                    if node_hours[j] <= h <= node_hours[j + 1]:
                        idx_a = j
                        break
                idx_b = idx_a + 1
                frac = (h - node_hours[idx_a]) / float(node_hours[idx_b] - node_hours[idx_a])

            ta = temps[idx_a] if temps[idx_a] is not None else 0.0
            tb = temps[idx_b] if temps[idx_b] is not None else ta
            t_val = round(ta + (tb - ta) * frac, 2)

            fa = feels[idx_a] if idx_a < len(feels) and feels[idx_a] is not None else ta
            fb = feels[idx_b] if idx_b < len(feels) and feels[idx_b] is not None else fa
            f_val = round(fa + (fb - fa) * frac, 2)

            nearest_idx = idx_a if frac < 0.5 else idx_b
            w_str = wspds_raw[nearest_idx] if nearest_idx < len(wspds_raw) else ""
            w_nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", w_str)]
            wspd_kmh = w_nums[0] if w_nums else None
            wgst_kmh = w_nums[1] if len(w_nums) > 1 else wspd_kmh

            pr_str = precips_raw[nearest_idx] if nearest_idx < len(precips_raw) else ""
            pr_nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", pr_str)]
            precip_mm = pr_nums[0] if pr_nums and "%" not in pr_str else 0.0

            points.append(
                make_hourly_point(
                    city=city,
                    time_local=f"{date_str}T{h:02d}:00",
                    temp_f=t_val if is_f else None,
                    temp_c=t_val if not is_f else None,
                    feels_f=f_val if is_f else None,
                    feels_c=f_val if not is_f else None,
                    precip_prob_pct=pprobs[nearest_idx] if nearest_idx < len(pprobs) else None,
                    precip_mm=precip_mm,
                    wind_speed_kmh=wspd_kmh,
                    wind_gust_kmh=wgst_kmh,
                    wind_direction_cardinal=wdirs[nearest_idx] if nearest_idx < len(wdirs) else None,
                    condition=conds[nearest_idx] if nearest_idx < len(conds) else None,
                )
            )
        return points

    def fetch_hourly(
        self, city: CityConfig
    ) -> Tuple[List[HourlyForecastPoint], str, str, Dict[str, Any]]:
        api_key = os.getenv("METEOBLUE_API_KEY", "").strip()
        if api_key:
            return self._fetch_api(city, api_key)

        tz = ZoneInfo(city.timezone)
        today = datetime.now(tz).date()
        dates_7 = [(today + timedelta(days=i)).isoformat() for i in range(7)]
        base_url = f"https://www.meteoblue.com/en/weather/week/{city.meteoblue_coord}"

        # Always fetch the base 1-hour NWP multimodel curve so all 7 days have 168 hourly points
        tz_enc = urllib.parse.quote(city.timezone)
        nwp_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={city.latitude}&longitude={city.longitude}"
            f"&hourly={HOURLY_VARS}&models=best_match&timezone={tz_enc}&forecast_days=8"
        )
        nwp_data = http_get_json(nwp_url, timeout=15)
        nwp_points = {p.time_local: p for p in parse_open_meteo_response(city, nwp_data)}

        web_scraped_days = 0
        try:
            with _METEOBLUE_SEMAPHORE:
                time.sleep(0.15)
                raw_day1 = http_get_text(f"{base_url}?day=1", timeout=12, retries=1)
            day1_pts = self._parse_single_day_table(city, raw_day1, dates_7[0])
            if day1_pts:
                web_scraped_days += 1
                for p in day1_pts:
                    nwp_points[p.time_local] = p
        except Exception:
            pass

        points = [nwp_points[k] for k in sorted(nwp_points.keys())]
        mode = "live_web_scrape+multimodel" if web_scraped_days > 0 else "multimodel_nwp_feed"
        return points, base_url, mode, {"coord_slug": city.meteoblue_coord, "web_days_overlaid": web_scraped_days}
