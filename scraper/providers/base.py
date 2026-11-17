from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from ..analyzer import analyze_7day_forecast
from ..cities import CityConfig
from ..models import HourlyForecastPoint, ScrapeResult

_OPEN_METEO_SEM = threading.Semaphore(3)

DEFAULT_BROWSER_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

WMO_CODE_MAP: Dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def http_get_text(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 15,
    retries: int = 4,
) -> str:
    merged_headers = dict(DEFAULT_BROWSER_HEADERS)
    if headers:
        merged_headers.update(headers)
    is_open_meteo = "api.open-meteo.com" in url
    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            if is_open_meteo:
                with _OPEN_METEO_SEM:
                    time.sleep(0.12)
                    req = urllib.request.Request(url, headers=merged_headers)
                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        return resp.read().decode("utf-8", errors="ignore")
            else:
                req = urllib.request.Request(url, headers=merged_headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            last_err = e
            if attempt < retries:
                wait = (1.5 * (attempt + 1)) if is_open_meteo else (0.6 * (attempt + 1))
                time.sleep(wait)
    raise RuntimeError(f"GET {url} failed after {retries + 1} attempts: {last_err}")


def http_get_json(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 15,
    retries: int = 2,
) -> Any:
    txt = http_get_text(url, headers=headers, timeout=timeout, retries=retries)
    return json.loads(txt)


def utc_iso_to_local(utc_iso: str, tz_name: str) -> Tuple[str, str]:
    """Convert an ISO-8601 UTC or offset timestamp to (local_iso_minute, utc_iso_second)."""
    cleaned = utc_iso.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local_dt = dt.astimezone(ZoneInfo(tz_name))
    utc_dt = dt.astimezone(timezone.utc)
    return local_dt.strftime("%Y-%m-%dT%H:%M"), utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class WeatherProvider(ABC):
    """Abstract base class for each weather forecast website scraper."""

    website_id: str = ""
    website_name: str = ""

    @abstractmethod
    def fetch_hourly(
        self, city: CityConfig
    ) -> Tuple[List[HourlyForecastPoint], str, str, Dict[str, Any]]:
        """
        Return (hourly_points, source_url, source_mode, extra_metadata).
        """
        raise NotImplementedError

    def scrape_city(
        self,
        city: CityConfig,
        scraped_at_utc: str,
        previous_high_history: Optional[Dict[str, Tuple[int, int, str]]] = None,
    ) -> ScrapeResult:
        try:
            points, source_url, source_mode, meta = self.fetch_hourly(city)
            daily_summary, filtered_points = analyze_7day_forecast(
                city=city,
                hourly_points=points,
                scraped_at_utc=scraped_at_utc,
                previous_high_history=previous_high_history,
            )
            return ScrapeResult(
                scraped_at_utc=scraped_at_utc,
                city=city.name,
                city_slug=city.slug,
                station_icao=city.station_icao,
                station_name=city.station_name,
                latitude=city.latitude,
                longitude=city.longitude,
                timezone=city.timezone,
                polymarket_unit=city.unit,
                website_id=self.website_id,
                website_name=self.website_name,
                source_url=source_url,
                source_mode=source_mode,
                success=len(daily_summary) > 0,
                error=None if daily_summary else "No hourly forecast points returned for target 7 days",
                daily_7day_summary=daily_summary,
                hourly_7day_forecast=filtered_points,
                extra_metadata=meta,
            )
        except Exception as e:
            return ScrapeResult(
                scraped_at_utc=scraped_at_utc,
                city=city.name,
                city_slug=city.slug,
                station_icao=city.station_icao,
                station_name=city.station_name,
                latitude=city.latitude,
                longitude=city.longitude,
                timezone=city.timezone,
                polymarket_unit=city.unit,
                website_id=self.website_id,
                website_name=self.website_name,
                source_url="",
                source_mode="error",
                success=False,
                error=str(e),
            )
