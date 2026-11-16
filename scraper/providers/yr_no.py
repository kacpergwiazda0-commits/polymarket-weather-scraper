from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ..analyzer import make_hourly_point
from ..cities import CityConfig
from ..models import HourlyForecastPoint
from .base import WeatherProvider, http_get_json, utc_iso_to_local


class YrNoProvider(WeatherProvider):
    """Fetches 7-day forecasts from Yr.no / MET Norway official API (api.met.no)."""

    website_id = "yr_no"
    website_name = "Yr.no (MET Norway)"

    def fetch_hourly(
        self, city: CityConfig
    ) -> Tuple[List[HourlyForecastPoint], str, str, Dict[str, Any]]:
        url = (
            f"https://api.met.no/weatherapi/locationforecast/2.0/complete"
            f"?lat={city.latitude:.4f}&lon={city.longitude:.4f}"
        )
        headers = {
            "User-Agent": (
                "PolymarketWeatherScraper/1.0 "
                "(https://github.com/kacpergwiazda0-commits/polymarket-weather-scraper)"
            ),
            "Accept": "application/json",
        }
        data = http_get_json(url, headers=headers, timeout=15)
        timeseries = data.get("properties", {}).get("timeseries", [])

        raw_nodes: List[Dict[str, Any]] = []
        for entry in timeseries:
            t_utc = entry.get("time")
            if not t_utc:
                continue
            time_local, time_utc = utc_iso_to_local(t_utc, city.timezone)
            dt_obj = datetime.fromisoformat(time_local)
            inst = entry.get("data", {}).get("instant", {}).get("details", {})
            n1 = entry.get("data", {}).get("next_1_hours", {})
            n6 = entry.get("data", {}).get("next_6_hours", {})

            summary_code = (
                n1.get("summary", {}).get("symbol_code")
                or n6.get("summary", {}).get("symbol_code")
            )
            n1_det = n1.get("details", {})
            n6_det = n6.get("details", {})

            precip_mm = n1_det.get("precipitation_amount")
            if precip_mm is None and n6_det.get("precipitation_amount") is not None:
                precip_mm = round(float(n6_det["precipitation_amount"]) / 6.0, 2)

            pprob = n1_det.get("probability_of_precipitation")
            if pprob is None:
                pprob = n6_det.get("probability_of_precipitation")

            wspd_ms = inst.get("wind_speed")
            wgst_ms = inst.get("wind_speed_of_gust")

            raw_nodes.append({
                "dt_local": dt_obj,
                "time_local": time_local,
                "time_utc": time_utc,
                "temp_c": inst.get("air_temperature"),
                "tmax_6h": n6_det.get("air_temperature_max"),
                "tmin_6h": n6_det.get("air_temperature_min"),
                "dew_c": inst.get("dew_point_temperature"),
                "humidity_pct": inst.get("relative_humidity"),
                "precip_prob_pct": pprob,
                "precip_mm": precip_mm,
                "wind_speed_kmh": round(float(wspd_ms) * 3.6, 2) if wspd_ms is not None else None,
                "wind_gust_kmh": round(float(wgst_ms) * 3.6, 2) if wgst_ms is not None else None,
                "wind_direction_deg": inst.get("wind_from_direction"),
                "cloud_cover_pct": inst.get("cloud_area_fraction"),
                "pressure_hpa": inst.get("air_pressure_at_sea_level"),
                "uv_index": inst.get("ultraviolet_index_clear_sky"),
                "condition": summary_code.replace("_", " ").title() if summary_code else None,
            })

        points: List[HourlyForecastPoint] = []
        for idx, node in enumerate(raw_nodes):
            if node["temp_c"] is None:
                continue
            points.append(
                make_hourly_point(
                    city=city,
                    time_local=node["time_local"],
                    time_utc=node["time_utc"],
                    temp_c=node["temp_c"],
                    dew_c=node["dew_c"],
                    humidity_pct=node["humidity_pct"],
                    precip_prob_pct=node["precip_prob_pct"],
                    precip_mm=node["precip_mm"],
                    rain_mm=node["precip_mm"],
                    wind_speed_kmh=node["wind_speed_kmh"],
                    wind_gust_kmh=node["wind_gust_kmh"],
                    wind_direction_deg=node["wind_direction_deg"],
                    cloud_cover_pct=node["cloud_cover_pct"],
                    pressure_hpa=node["pressure_hpa"],
                    uv_index=node["uv_index"],
                    condition=node["condition"],
                )
            )

            # If gap to next node is > 1 hour (e.g. 6-hour steps for days 3-7), interpolate intermediate hours
            if idx + 1 < len(raw_nodes):
                nxt = raw_nodes[idx + 1]
                gap_hours = int(round((nxt["dt_local"] - node["dt_local"]).total_seconds() / 3600.0))
                if 1 < gap_hours <= 6 and nxt["temp_c"] is not None:
                    t_start = float(node["temp_c"])
                    t_end = float(nxt["temp_c"])
                    for step in range(1, gap_hours):
                        frac = step / float(gap_hours)
                        interp_dt = node["dt_local"] + timedelta(hours=step)
                        t_interp = round(t_start + (t_end - t_start) * frac, 2)
                        points.append(
                            make_hourly_point(
                                city=city,
                                time_local=interp_dt.strftime("%Y-%m-%dT%H:%M"),
                                temp_c=t_interp,
                                dew_c=node["dew_c"],
                                humidity_pct=node["humidity_pct"],
                                precip_prob_pct=node["precip_prob_pct"],
                                precip_mm=node["precip_mm"],
                                rain_mm=node["precip_mm"],
                                wind_speed_kmh=node["wind_speed_kmh"],
                                wind_gust_kmh=node["wind_gust_kmh"],
                                wind_direction_deg=node["wind_direction_deg"],
                                cloud_cover_pct=node["cloud_cover_pct"],
                                pressure_hpa=node["pressure_hpa"],
                                uv_index=node["uv_index"],
                                condition=node["condition"],
                            )
                        )

        meta = {
            "updated_at": data.get("properties", {}).get("meta", {}).get("updated_at"),
            "yr_web_coordinates": f"{city.latitude},{city.longitude}",
        }
        return points, url, "live_official_api", meta
