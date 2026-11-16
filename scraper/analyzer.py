from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

from .cities import CityConfig
from .models import DailyPeakAnalysis, HourlyForecastPoint


def round_half_up(val: float) -> int:
    """Round to nearest integer with half-values rounded up (matches Polymarket settlement rule)."""
    return int(math.floor(float(val) + 0.5))


def c_to_f(celsius: float) -> float:
    return round(float(celsius) * 9.0 / 5.0 + 32.0, 2)


def f_to_c(fahrenheit: float) -> float:
    return round((float(fahrenheit) - 32.0) * 5.0 / 9.0, 2)


def deg_to_cardinal(deg: Optional[float]) -> Optional[str]:
    if deg is None:
        return None
    dirs = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    ix = int(round(float(deg) / 22.5)) % 16
    return dirs[ix]


def make_hourly_point(
    *,
    city: CityConfig,
    time_local: str,
    time_utc: Optional[str] = None,
    temp_c: Optional[float] = None,
    temp_f: Optional[float] = None,
    feels_c: Optional[float] = None,
    feels_f: Optional[float] = None,
    dew_c: Optional[float] = None,
    dew_f: Optional[float] = None,
    humidity_pct: Optional[float] = None,
    precip_prob_pct: Optional[float] = None,
    precip_mm: Optional[float] = None,
    rain_mm: Optional[float] = None,
    snow_cm: Optional[float] = None,
    wind_speed_kmh: Optional[float] = None,
    wind_speed_mph: Optional[float] = None,
    wind_gust_kmh: Optional[float] = None,
    wind_gust_mph: Optional[float] = None,
    wind_direction_deg: Optional[int] = None,
    wind_direction_cardinal: Optional[str] = None,
    cloud_cover_pct: Optional[float] = None,
    pressure_hpa: Optional[float] = None,
    visibility_km: Optional[float] = None,
    uv_index: Optional[float] = None,
    air_quality_index: Optional[int] = None,
    condition: Optional[str] = None,
) -> HourlyForecastPoint:
    """Create a normalized HourlyForecastPoint with both C/F and Polymarket unit rounding."""
    if temp_c is None and temp_f is not None:
        temp_c = f_to_c(temp_f)
    elif temp_f is None and temp_c is not None:
        temp_f = c_to_f(temp_c)
    temp_c_val = round(float(temp_c or 0.0), 2)
    temp_f_val = round(float(temp_f or 32.0), 2)

    if feels_c is None and feels_f is not None:
        feels_c = f_to_c(feels_f)
    elif feels_f is None and feels_c is not None:
        feels_f = c_to_f(feels_c)

    if dew_c is None and dew_f is not None:
        dew_c = f_to_c(dew_f)
    elif dew_f is None and dew_c is not None:
        dew_f = c_to_f(dew_c)

    if wind_speed_kmh is None and wind_speed_mph is not None:
        wind_speed_kmh = round(float(wind_speed_mph) * 1.60934, 2)
    elif wind_speed_mph is None and wind_speed_kmh is not None:
        wind_speed_mph = round(float(wind_speed_kmh) / 1.60934, 2)

    if wind_gust_kmh is None and wind_gust_mph is not None:
        wind_gust_kmh = round(float(wind_gust_mph) * 1.60934, 2)
    elif wind_gust_mph is None and wind_gust_kmh is not None:
        wind_gust_mph = round(float(wind_gust_kmh) / 1.60934, 2)

    if wind_direction_cardinal is None and wind_direction_deg is not None:
        wind_direction_cardinal = deg_to_cardinal(wind_direction_deg)

    if city.unit.upper() == "F":
        market_raw = temp_f_val
        market_int = round_half_up(temp_f_val)
        feels_market = round_half_up(feels_f) if feels_f is not None else None
    else:
        market_raw = temp_c_val
        market_int = round_half_up(temp_c_val)
        feels_market = round_half_up(feels_c) if feels_c is not None else None

    date_part = time_local[:10]
    hour_part = time_local[11:16] if len(time_local) >= 16 else "00:00"

    return HourlyForecastPoint(
        time_local=f"{date_part}T{hour_part}",
        date_local=date_part,
        hour_local=hour_part,
        time_utc=time_utc,
        temperature_c=temp_c_val,
        temperature_f=temp_f_val,
        temperature_market=market_int,
        temperature_market_raw=market_raw,
        feels_like_c=round(float(feels_c), 2) if feels_c is not None else None,
        feels_like_f=round(float(feels_f), 2) if feels_f is not None else None,
        feels_like_market=feels_market,
        dew_point_c=round(float(dew_c), 2) if dew_c is not None else None,
        dew_point_f=round(float(dew_f), 2) if dew_f is not None else None,
        humidity_pct=round(float(humidity_pct), 1) if humidity_pct is not None else None,
        precip_prob_pct=round(float(precip_prob_pct), 1) if precip_prob_pct is not None else None,
        precip_mm=round(float(precip_mm), 2) if precip_mm is not None else None,
        rain_mm=round(float(rain_mm), 2) if rain_mm is not None else None,
        snow_cm=round(float(snow_cm), 2) if snow_cm is not None else None,
        wind_speed_kmh=round(float(wind_speed_kmh), 2) if wind_speed_kmh is not None else None,
        wind_speed_mph=round(float(wind_speed_mph), 2) if wind_speed_mph is not None else None,
        wind_gust_kmh=round(float(wind_gust_kmh), 2) if wind_gust_kmh is not None else None,
        wind_gust_mph=round(float(wind_gust_mph), 2) if wind_gust_mph is not None else None,
        wind_direction_deg=int(round(float(wind_direction_deg))) if wind_direction_deg is not None else None,
        wind_direction_cardinal=wind_direction_cardinal,
        cloud_cover_pct=round(float(cloud_cover_pct), 1) if cloud_cover_pct is not None else None,
        pressure_hpa=round(float(pressure_hpa), 1) if pressure_hpa is not None else None,
        visibility_km=round(float(visibility_km), 2) if visibility_km is not None else None,
        uv_index=round(float(uv_index), 1) if uv_index is not None else None,
        air_quality_index=int(air_quality_index) if air_quality_index is not None else None,
        condition=condition,
    )


def _max_consecutive_streak(flags: Iterable[bool]) -> int:
    best = 0
    curr = 0
    for f in flags:
        if f:
            curr += 1
            if curr > best:
                best = curr
        else:
            curr = 0
    return best


def get_target_7_dates(city: CityConfig) -> List[str]:
    """Return the 7 local YYYY-MM-DD dates starting from today in the city's timezone."""
    tz = ZoneInfo(city.timezone)
    now_local = datetime.now(tz)
    return [(now_local.date() + timedelta(days=i)).isoformat() for i in range(7)]


def analyze_7day_forecast(
    city: CityConfig,
    hourly_points: List[HourlyForecastPoint],
    scraped_at_utc: str,
    previous_high_history: Optional[Dict[str, Tuple[int, int, str]]] = None,
) -> Tuple[List[DailyPeakAnalysis], List[HourlyForecastPoint]]:
    """
    Filter and analyze hourly forecast points across the next 7 local days.

    Computes for each day:
    - highest_temperature (whole-degree rounded in Polymarket unit)
    - highest_temperature_duration_hours (count of hours where temperature == highest_temperature,
      e.g. if 17 degrees occurred at 14:00, 15:00, and 16:00 -> 3)
    - highest_temperature_hours (list of HH:MM strings at highest_temperature)
    - highest_temperature_max_consecutive_hours (longest unbroken streak at highest_temperature)
    - lowest_temperature & its duration/hours
    - cross-run streak tracking (consecutive_scrapes_with_same_high)
    """
    target_dates = set(get_target_7_dates(city))

    # Deduplicate by time_local and sort chronologically
    dedup: Dict[str, HourlyForecastPoint] = {}
    for pt in hourly_points:
        if pt.date_local in target_dates:
            dedup[pt.time_local] = pt

    sorted_points = [dedup[k] for k in sorted(dedup.keys())]

    by_date: Dict[str, List[HourlyForecastPoint]] = defaultdict(list)
    for pt in sorted_points:
        by_date[pt.date_local].append(pt)

    daily_summaries: List[DailyPeakAnalysis] = []

    for date_str in sorted(target_dates):
        pts = by_date.get(date_str, [])
        if not pts:
            continue

        max_temp_int = max(p.temperature_market for p in pts)
        min_temp_int = min(p.temperature_market for p in pts)
        max_temp_raw = max(p.temperature_market_raw for p in pts)
        min_temp_raw = min(p.temperature_market_raw for p in pts)
        max_temp_c = max(p.temperature_c for p in pts)
        max_temp_f = max(p.temperature_f for p in pts)

        high_hours: List[str] = []
        low_hours: List[str] = []
        exact_high_hours: List[str] = []
        high_flags: List[bool] = []

        for p in pts:
            is_hi = p.temperature_market == max_temp_int
            is_lo = p.temperature_market == min_temp_int
            p.is_daily_high_hour = is_hi
            p.is_daily_low_hour = is_lo
            high_flags.append(is_hi)
            if is_hi:
                high_hours.append(p.hour_local)
            if is_lo:
                low_hours.append(p.hour_local)
            if abs(p.temperature_market_raw - max_temp_raw) < 1e-6:
                exact_high_hours.append(p.hour_local)

        max_consec = _max_consecutive_streak(high_flags)

        # Cross-run persistence tracking
        consec_scrapes = 1
        first_seen_utc = scraped_at_utc
        if previous_high_history and date_str in previous_high_history:
            prev_high, prev_count, prev_first_utc = previous_high_history[date_str]
            if prev_high == max_temp_int:
                consec_scrapes = prev_count + 1
                first_seen_utc = prev_first_utc or scraped_at_utc

        feels_vals = [p.feels_like_market for p in pts if p.feels_like_market is not None]
        hum_vals = [p.humidity_pct for p in pts if p.humidity_pct is not None]
        pprob_vals = [p.precip_prob_pct for p in pts if p.precip_prob_pct is not None]
        precip_vals = [p.precip_mm for p in pts if p.precip_mm is not None]
        rain_vals = [p.rain_mm for p in pts if p.rain_mm is not None]
        snow_vals = [p.snow_cm for p in pts if p.snow_cm is not None]
        wspd_kmh = [p.wind_speed_kmh for p in pts if p.wind_speed_kmh is not None]
        wspd_mph = [p.wind_speed_mph for p in pts if p.wind_speed_mph is not None]
        wgst_kmh = [p.wind_gust_kmh for p in pts if p.wind_gust_kmh is not None]
        wgst_mph = [p.wind_gust_mph for p in pts if p.wind_gust_mph is not None]
        cloud_vals = [p.cloud_cover_pct for p in pts if p.cloud_cover_pct is not None]
        pres_vals = [p.pressure_hpa for p in pts if p.pressure_hpa is not None]
        uv_vals = [p.uv_index for p in pts if p.uv_index is not None]
        cond_vals = [p.condition for p in pts if p.condition]

        dom_cond = Counter(cond_vals).most_common(1)[0][0] if cond_vals else None

        daily_summaries.append(
            DailyPeakAnalysis(
                date=date_str,
                unit=city.unit,
                highest_temperature=max_temp_int,
                highest_temperature_duration_hours=len(high_hours),
                highest_temperature_hours=high_hours,
                highest_temperature_max_consecutive_hours=max_consec,
                highest_temperature_exact=round(max_temp_raw, 2),
                highest_temperature_exact_hours=exact_high_hours,
                highest_temperature_c=round(max_temp_c, 2),
                highest_temperature_f=round(max_temp_f, 2),
                consecutive_scrapes_with_same_high=consec_scrapes,
                high_first_predicted_at_utc=first_seen_utc,
                lowest_temperature=min_temp_int,
                lowest_temperature_duration_hours=len(low_hours),
                lowest_temperature_hours=low_hours,
                lowest_temperature_exact=round(min_temp_raw, 2),
                avg_temperature=round(sum(p.temperature_market_raw for p in pts) / len(pts), 2),
                max_feels_like=max(feels_vals) if feels_vals else None,
                min_feels_like=min(feels_vals) if feels_vals else None,
                max_humidity_pct=round(max(hum_vals), 1) if hum_vals else None,
                min_humidity_pct=round(min(hum_vals), 1) if hum_vals else None,
                avg_humidity_pct=round(sum(hum_vals) / len(hum_vals), 1) if hum_vals else None,
                max_precip_prob_pct=round(max(pprob_vals), 1) if pprob_vals else None,
                total_precip_mm=round(sum(precip_vals), 2) if precip_vals else None,
                total_rain_mm=round(sum(rain_vals), 2) if rain_vals else None,
                total_snow_cm=round(sum(snow_vals), 2) if snow_vals else None,
                max_wind_speed_kmh=round(max(wspd_kmh), 2) if wspd_kmh else None,
                max_wind_speed_mph=round(max(wspd_mph), 2) if wspd_mph else None,
                max_wind_gust_kmh=round(max(wgst_kmh), 2) if wgst_kmh else None,
                max_wind_gust_mph=round(max(wgst_mph), 2) if wgst_mph else None,
                avg_cloud_cover_pct=round(sum(cloud_vals) / len(cloud_vals), 1) if cloud_vals else None,
                avg_pressure_hpa=round(sum(pres_vals) / len(pres_vals), 1) if pres_vals else None,
                max_uv_index=round(max(uv_vals), 1) if uv_vals else None,
                dominant_condition=dom_cond,
                hours_analyzed=len(pts),
            )
        )

    return daily_summaries, sorted_points
