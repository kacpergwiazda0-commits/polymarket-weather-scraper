from __future__ import annotations

import html as html_lib
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from ..analyzer import make_hourly_point
from ..cities import CityConfig
from ..models import HourlyForecastPoint
from .base import WeatherProvider, http_get_json, http_get_text
from .open_meteo import HOURLY_VARS, parse_open_meteo_response


def _parse_ampm(label: str) -> Optional[int]:
    m = re.match(r"^(\d{1,2})(am|pm)$", label.strip().lower())
    if not m:
        return None
    hr = int(m.group(1))
    if m.group(2) == "am":
        return 0 if hr == 12 else hr
    return 12 if hr == 12 else hr + 12


def _num(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    return float(m.group(0)) if m else None


class UKMetOfficeProvider(WeatherProvider):
    """
    Scrapes UK Met Office (metoffice.gov.uk/weather/forecast/<geohash>) forecast tables
    and enriches with the official UK Met Office Unified Model (ukmo_seamless) 1-hour feed.
    """

    website_id = "uk_met_office"
    website_name = "UK Met Office"

    def _scrape_metoffice_web(self, city: CityConfig) -> Dict[str, Dict[str, Any]]:
        url = f"https://www.metoffice.gov.uk/weather/forecast/{city.geohash}"
        raw_html = http_get_text(url, timeout=18)
        unesc = html_lib.unescape(raw_html)

        web_points: Dict[str, Dict[str, Any]] = {}
        tables = re.findall(
            r"<table class=\"forecast-table[^\"]*\" data-date=\"(\d{4}-\d{2}-\d{2})\">(.*?)</table>",
            unesc,
            re.S,
        )
        seen_dates = set()
        for dt_str, t_body in tables:
            if dt_str in seen_dates:
                continue
            m_time_row = re.search(r"<tr class=\"step-time[^\"]*\">(.*?)</tr>", t_body, re.S)
            m_temp_row = re.search(r"<tr class=\"[^\"]*weather-temperature-row[^\"]*\">(.*?)</tr>", t_body, re.S)
            if not m_time_row or not m_temp_row:
                continue
            seen_dates.add(dt_str)

            time_cells = re.findall(r"<td[^>]*>(.*?)</td>", m_time_row.group(1), re.S)
            temp_cells = re.findall(r"<td[^>]*>(.*?)</td>", m_temp_row.group(1), re.S)

            m_feels_row = re.search(
                r"<th[^>]*>\s*Feels like temperature\s*</th>(.*?)</tr>", t_body, re.S
            )
            feels_cells = (
                re.findall(r"<td[^>]*>(.*?)</td>", m_feels_row.group(1), re.S)
                if m_feels_row
                else []
            )

            m_precip_row = re.search(
                r"<tr class=\"precipitation-chance-row[^\"]*\">(.*?)</tr>", t_body, re.S
            )
            precip_cells = (
                re.findall(r"<td[^>]*>(.*?)</td>", m_precip_row.group(1), re.S)
                if m_precip_row
                else []
            )

            m_wind_row = re.search(r"<tr[^>]*id=\"wind-row\"[^>]*>(.*?)</tr>", t_body, re.S)
            wind_cells = (
                re.findall(r"<td[^>]*>(.*?)</td>", m_wind_row.group(1), re.S)
                if m_wind_row
                else []
            )

            m_gust_row = re.search(
                r"<th[^>]*><span[^>]*>Wind gusts</span></th>(.*?)</tr>", t_body, re.S
            )
            gust_cells = (
                re.findall(r"<td[^>]*>(.*?)</td>", m_gust_row.group(1), re.S)
                if m_gust_row
                else []
            )

            for i, tc in enumerate(time_cells):
                hr_int = _parse_ampm(re.sub(r"<[^>]+>", "", tc))
                if hr_int is None or i >= len(temp_cells):
                    continue
                t_cell = temp_cells[i]
                temp_c = _num(re.sub(r"<[^>]+>", " ", t_cell))
                if temp_c is None:
                    continue
                m_cond = re.search(r"(?:title|alt)=\"([^\"]+)\"", t_cell)
                cond = m_cond.group(1).strip() if m_cond else None
                feels_c = (
                    _num(re.sub(r"<[^>]+>", " ", feels_cells[i]))
                    if i < len(feels_cells)
                    else None
                )
                pprob = (
                    _num(re.sub(r"<[^>]+>", " ", precip_cells[i]))
                    if i < len(precip_cells)
                    else None
                )
                wspd_mph = None
                wcard = None
                if i < len(wind_cells):
                    m_wc = re.search(r"data-value=\"([NSEW]{1,3})\"", wind_cells[i])
                    wcard = m_wc.group(1) if m_wc else None
                    wspd_mph = _num(re.sub(r"<[^>]+>", " ", wind_cells[i]))
                wgst_mph = (
                    _num(re.sub(r"<[^>]+>", " ", gust_cells[i]))
                    if i < len(gust_cells)
                    else None
                )

                key = f"{dt_str}T{hr_int:02d}:00"
                web_points[key] = {
                    "temp_c": temp_c,
                    "feels_c": feels_c,
                    "precip_prob_pct": pprob,
                    "wind_speed_mph": wspd_mph,
                    "wind_gust_mph": wgst_mph,
                    "wind_direction_cardinal": wcard,
                    "condition": cond,
                }
        return web_points

    def fetch_hourly(
        self, city: CityConfig
    ) -> Tuple[List[HourlyForecastPoint], str, str, Dict[str, Any]]:
        web_url = f"https://www.metoffice.gov.uk/weather/forecast/{city.geohash}"
        tz_enc = urllib.parse.quote(city.timezone)
        ukmo_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={city.latitude}&longitude={city.longitude}"
            f"&hourly={HOURLY_VARS}&models=ukmo_seamless&timezone={tz_enc}&forecast_days=8"
        )

        web_map: Dict[str, Dict[str, Any]] = {}
        try:
            web_map = self._scrape_metoffice_web(city)
        except Exception:
            pass

        ukmo_data = http_get_json(ukmo_url, timeout=15)
        model_points = parse_open_meteo_response(city, ukmo_data)

        # Overlay web scraped condition/precip/wind where available onto 1-hour UKMO points
        merged_points: List[HourlyForecastPoint] = []
        for pt in model_points:
            w = web_map.get(pt.time_local)
            if w:
                if w.get("condition"):
                    pt.condition = w["condition"]
                if w.get("precip_prob_pct") is not None:
                    pt.precip_prob_pct = w["precip_prob_pct"]
                if w.get("wind_direction_cardinal"):
                    pt.wind_direction_cardinal = w["wind_direction_cardinal"]
            merged_points.append(pt)

        # If ukmo_seamless had any missing points, build from web_map directly
        if not merged_points and web_map:
            for t_loc, w in sorted(web_map.items()):
                merged_points.append(
                    make_hourly_point(
                        city=city,
                        time_local=t_loc,
                        temp_c=w["temp_c"],
                        feels_c=w["feels_c"],
                        precip_prob_pct=w["precip_prob_pct"],
                        wind_speed_mph=w["wind_speed_mph"],
                        wind_gust_mph=w["wind_gust_mph"],
                        wind_direction_cardinal=w["wind_direction_cardinal"],
                        condition=w["condition"],
                    )
                )

        meta = {
            "geohash": city.geohash,
            "metoffice_web_url": web_url,
            "ukmo_model_url": ukmo_url,
            "web_hours_scraped": len(web_map),
        }
        return merged_points, web_url, "live_web_scrape+ukmo_model", meta
