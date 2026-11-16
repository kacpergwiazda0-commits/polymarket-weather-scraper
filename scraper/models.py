from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class HourlyForecastPoint:
    """Single hourly forecast observation normalized across all weather websites."""

    time_local: str  # YYYY-MM-DDTHH:MM (in city's station timezone)
    date_local: str  # YYYY-MM-DD
    hour_local: str  # HH:MM (e.g. "14:00")
    time_utc: Optional[str] = None
    temperature_c: float = 0.0  # Exact temperature in Celsius
    temperature_f: float = 0.0  # Exact temperature in Fahrenheit
    temperature_market: int = 0  # Rounded whole-degree temperature in Polymarket unit (C or F)
    temperature_market_raw: float = 0.0  # Unrounded float in Polymarket unit
    feels_like_c: Optional[float] = None
    feels_like_f: Optional[float] = None
    feels_like_market: Optional[int] = None
    dew_point_c: Optional[float] = None
    dew_point_f: Optional[float] = None
    humidity_pct: Optional[float] = None
    precip_prob_pct: Optional[float] = None
    precip_mm: Optional[float] = None
    rain_mm: Optional[float] = None
    snow_cm: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    wind_speed_mph: Optional[float] = None
    wind_gust_kmh: Optional[float] = None
    wind_gust_mph: Optional[float] = None
    wind_direction_deg: Optional[int] = None
    wind_direction_cardinal: Optional[str] = None
    cloud_cover_pct: Optional[float] = None
    pressure_hpa: Optional[float] = None
    visibility_km: Optional[float] = None
    uv_index: Optional[float] = None
    air_quality_index: Optional[int] = None
    condition: Optional[str] = None
    is_daily_high_hour: bool = False
    is_daily_low_hour: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DailyPeakAnalysis:
    """Daily 7-day forecast summary including highest temperature & duration at peak."""

    date: str  # YYYY-MM-DD in city's local timezone
    unit: str  # "F" (US cities) or "C" (international cities)
    highest_temperature: int  # Whole-degree predicted high (e.g. 17)
    highest_temperature_duration_hours: int  # Number of hours at highest_temperature (e.g. 3 for 14:00, 15:00, 16:00)
    highest_temperature_hours: List[str] = field(default_factory=list)  # e.g. ["14:00", "15:00", "16:00"]
    highest_temperature_max_consecutive_hours: int = 0  # Longest contiguous streak at highest_temperature
    highest_temperature_exact: float = 0.0  # Unrounded max temperature in settlement unit
    highest_temperature_exact_hours: List[str] = field(default_factory=list)
    highest_temperature_c: float = 0.0
    highest_temperature_f: float = 0.0
    consecutive_scrapes_with_same_high: int = 1  # How many consecutive hourly scrape runs predicted this same high
    high_first_predicted_at_utc: str = ""  # First UTC timestamp in current streak that predicted this high
    lowest_temperature: int = 0
    lowest_temperature_duration_hours: int = 0
    lowest_temperature_hours: List[str] = field(default_factory=list)
    lowest_temperature_exact: float = 0.0
    avg_temperature: float = 0.0
    max_feels_like: Optional[int] = None
    min_feels_like: Optional[int] = None
    max_humidity_pct: Optional[float] = None
    min_humidity_pct: Optional[float] = None
    avg_humidity_pct: Optional[float] = None
    max_precip_prob_pct: Optional[float] = None
    total_precip_mm: Optional[float] = None
    total_rain_mm: Optional[float] = None
    total_snow_cm: Optional[float] = None
    max_wind_speed_kmh: Optional[float] = None
    max_wind_speed_mph: Optional[float] = None
    max_wind_gust_kmh: Optional[float] = None
    max_wind_gust_mph: Optional[float] = None
    avg_cloud_cover_pct: Optional[float] = None
    avg_pressure_hpa: Optional[float] = None
    max_uv_index: Optional[float] = None
    dominant_condition: Optional[str] = None
    hours_analyzed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScrapeResult:
    """Full result of scraping one website for one city."""

    scraped_at_utc: str
    city: str
    city_slug: str
    station_icao: str
    station_name: str
    latitude: float
    longitude: float
    timezone: str
    polymarket_unit: str
    website_id: str
    website_name: str
    source_url: str
    source_mode: str  # e.g. "live_web_scrape", "live_official_api", "nwp_model_fallback"
    success: bool = True
    error: Optional[str] = None
    daily_7day_summary: List[DailyPeakAnalysis] = field(default_factory=list)
    hourly_7day_forecast: List[HourlyForecastPoint] = field(default_factory=list)
    extra_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
