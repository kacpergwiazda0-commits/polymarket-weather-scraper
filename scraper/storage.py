from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List, Tuple

from .models import ScrapeResult


def load_previous_high_history(
    output_root: Path, city_slug: str, website_id: str
) -> Dict[str, Tuple[int, int, str]]:
    """
    Read the existing latest.json for <city_slug>/<website_id> so we can track
    how many consecutive hourly scrapes have predicted the same daily high.
    Returns: {date_str: (highest_temperature, consecutive_scrapes_count, first_predicted_at_utc)}
    """
    latest_path = output_root / city_slug / website_id / "latest.json"
    if not latest_path.exists():
        return {}
    try:
        data = json.loads(latest_path.read_text(encoding="utf-8"))
        out: Dict[str, Tuple[int, int, str]] = {}
        for day in data.get("daily_7day_summary", []):
            dt = day.get("date")
            hi = day.get("highest_temperature")
            cnt = int(day.get("consecutive_scrapes_with_same_high", 1))
            first_utc = day.get("high_first_predicted_at_utc") or data.get("scraped_at_utc", "")
            if dt is not None and hi is not None:
                out[str(dt)] = (int(hi), cnt, str(first_utc))
        return out
    except Exception:
        return {}


def save_scrape_result(output_root: Path, result: ScrapeResult) -> Path:
    """
    Save the scrape result into:
      <output_root>/<city_slug>/<website_id>/<timestamp>.json
      <output_root>/<city_slug>/<website_id>/latest.json
      <output_root>/<city_slug>/<website_id>/daily_summary.csv   (appends each hourly run)
      <output_root>/<city_slug>/<website_id>/hourly_forecast.csv (latest 7-day hourly table)
    """
    provider_dir = output_root / result.city_slug / result.website_id
    provider_dir.mkdir(parents=True, exist_ok=True)

    safe_ts = result.scraped_at_utc.replace(":", "-")
    ts_json_path = provider_dir / f"{safe_ts}.json"
    latest_json_path = provider_dir / "latest.json"

    payload = json.dumps(result.to_dict(), indent=2, ensure_ascii=False)
    ts_json_path.write_text(payload, encoding="utf-8")

    if not result.success or not result.daily_7day_summary:
        if not latest_json_path.exists():
            latest_json_path.write_text(payload, encoding="utf-8")
        return provider_dir

    latest_json_path.write_text(payload, encoding="utf-8")

    # 1. Append to cumulative daily_summary.csv
    daily_csv_path = provider_dir / "daily_summary.csv"
    daily_headers = [
        "scraped_at_utc",
        "city",
        "station_icao",
        "website",
        "date",
        "unit",
        "highest_temperature",
        "highest_temperature_duration_hours",
        "highest_temperature_hours",
        "highest_temperature_max_consecutive_hours",
        "highest_temperature_exact",
        "highest_temperature_c",
        "highest_temperature_f",
        "consecutive_scrapes_with_same_high",
        "high_first_predicted_at_utc",
        "lowest_temperature",
        "lowest_temperature_duration_hours",
        "lowest_temperature_hours",
        "avg_temperature",
        "max_feels_like",
        "min_feels_like",
        "avg_humidity_pct",
        "max_precip_prob_pct",
        "total_precip_mm",
        "max_wind_speed_kmh",
        "max_wind_gust_kmh",
        "avg_cloud_cover_pct",
        "avg_pressure_hpa",
        "max_uv_index",
        "dominant_condition",
        "hours_analyzed",
        "source_mode",
    ]
    write_header = not daily_csv_path.exists()
    with daily_csv_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(daily_headers)
        for d in result.daily_7day_summary:
            writer.writerow([
                result.scraped_at_utc,
                result.city,
                result.station_icao,
                result.website_id,
                d.date,
                d.unit,
                d.highest_temperature,
                d.highest_temperature_duration_hours,
                "|".join(d.highest_temperature_hours),
                d.highest_temperature_max_consecutive_hours,
                d.highest_temperature_exact,
                d.highest_temperature_c,
                d.highest_temperature_f,
                d.consecutive_scrapes_with_same_high,
                d.high_first_predicted_at_utc,
                d.lowest_temperature,
                d.lowest_temperature_duration_hours,
                "|".join(d.lowest_temperature_hours),
                d.avg_temperature,
                d.max_feels_like,
                d.min_feels_like,
                d.avg_humidity_pct,
                d.max_precip_prob_pct,
                d.total_precip_mm,
                d.max_wind_speed_kmh,
                d.max_wind_gust_kmh,
                d.avg_cloud_cover_pct,
                d.avg_pressure_hpa,
                d.max_uv_index,
                d.dominant_condition,
                d.hours_analyzed,
                result.source_mode,
            ])

    # 2. Write latest 7-day hourly_forecast.csv
    hourly_csv_path = provider_dir / "hourly_forecast.csv"
    daily_lookup = {d.date: d for d in result.daily_7day_summary}
    hourly_headers = [
        "scraped_at_utc",
        "city",
        "station_icao",
        "website",
        "date_local",
        "hour_local",
        "time_local",
        "time_utc",
        "unit",
        "temperature_market",
        "is_daily_high_hour",
        "daily_highest_temperature",
        "daily_highest_temperature_duration_hours",
        "temperature_market_raw",
        "temperature_c",
        "temperature_f",
        "feels_like_market",
        "feels_like_c",
        "feels_like_f",
        "dew_point_c",
        "dew_point_f",
        "humidity_pct",
        "precip_prob_pct",
        "precip_mm",
        "rain_mm",
        "snow_cm",
        "wind_speed_kmh",
        "wind_speed_mph",
        "wind_gust_kmh",
        "wind_gust_mph",
        "wind_direction_deg",
        "wind_direction_cardinal",
        "cloud_cover_pct",
        "pressure_hpa",
        "visibility_km",
        "uv_index",
        "air_quality_index",
        "condition",
    ]
    with hourly_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(hourly_headers)
        for p in result.hourly_7day_forecast:
            day_info = daily_lookup.get(p.date_local)
            writer.writerow([
                result.scraped_at_utc,
                result.city,
                result.station_icao,
                result.website_id,
                p.date_local,
                p.hour_local,
                p.time_local,
                p.time_utc,
                result.polymarket_unit,
                p.temperature_market,
                p.is_daily_high_hour,
                day_info.highest_temperature if day_info else None,
                day_info.highest_temperature_duration_hours if day_info else None,
                p.temperature_market_raw,
                p.temperature_c,
                p.temperature_f,
                p.feels_like_market,
                p.feels_like_c,
                p.feels_like_f,
                p.dew_point_c,
                p.dew_point_f,
                p.humidity_pct,
                p.precip_prob_pct,
                p.precip_mm,
                p.rain_mm,
                p.snow_cm,
                p.wind_speed_kmh,
                p.wind_speed_mph,
                p.wind_gust_kmh,
                p.wind_gust_mph,
                p.wind_direction_deg,
                p.wind_direction_cardinal,
                p.cloud_cover_pct,
                p.pressure_hpa,
                p.visibility_km,
                p.uv_index,
                p.air_quality_index,
                p.condition,
            ])

    return provider_dir


def _summary_row_from_dict(r: Dict, d: Dict, consensus_info: Dict | None = None) -> List:
    base_row = [
        r.get("scraped_at_utc"),
        r.get("city"),
        r.get("city_slug"),
        r.get("station_icao"),
        r.get("website_id"),
        r.get("website_name"),
        d.get("date"),
        d.get("unit"),
        d.get("highest_temperature"),
        d.get("highest_temperature_duration_hours"),
        "|".join(d.get("highest_temperature_hours", [])),
        d.get("highest_temperature_max_consecutive_hours"),
        d.get("highest_temperature_exact"),
        d.get("highest_temperature_c"),
        d.get("highest_temperature_f"),
        d.get("consecutive_scrapes_with_same_high"),
        d.get("high_first_predicted_at_utc") or r.get("scraped_at_utc"),
        d.get("lowest_temperature"),
        d.get("lowest_temperature_duration_hours"),
        d.get("avg_temperature"),
        d.get("max_precip_prob_pct"),
        d.get("total_precip_mm"),
        d.get("max_wind_speed_kmh"),
        d.get("avg_humidity_pct"),
        d.get("dominant_condition"),
        d.get("hours_analyzed"),
        r.get("source_mode"),
    ]
    if consensus_info is not None:
        base_row.extend([
            consensus_info.get("all_websites_agree", False),
            consensus_info.get("consensus_high"),
            consensus_info.get("agree_count"),
            consensus_info.get("total_websites"),
            consensus_info.get("agreement_pct"),
            consensus_info.get("temp_spread"),
        ])
    return base_row


def write_Overview_tables(output_root: Path, results: List[ScrapeResult] | None = None) -> None:
    """
    Write per-city multi-website CSVs outside the website folders (`data/<city_slug>/`):
      1. `city_websites_summary.csv`          (latest scrape summary across all 11 websites)
      2. `city_websites_all_scrapes.csv`      (all historical hourly scrapes over time across all 11 websites)
      3. `city_websites_hourly_forecasts.csv` (hour-by-hour 7-day forecast rows across all 11 websites)
    Plus root-level master CSVs in `data/`:
      - `all_cities_latest_summary.csv`                 (includes website consensus columns)
      - `all_cities_websites_agree_on_high.csv`         (extracts rows where all websites agree on highest temp)
      - `all_cities_consensus_by_city_date.csv`         (1 row per city+date showing website agreement & spread)
      - `all_cities_latest_summary_without_unanimous.csv` (latest summary with unanimous rows filtered out)
      - `all_cities_all_scrapes.csv`                    (all historical hourly scrapes across all 55 cities)
    """
    from collections import Counter

    output_root.mkdir(parents=True, exist_ok=True)
    master_latest_csv = output_root / "all_cities_latest_summary.csv"
    master_agree_csv = output_root / "all_cities_websites_agree_on_high.csv"
    master_without_unanimous_csv = output_root / "all_cities_latest_summary_without_unanimous.csv"
    master_consensus_csv = output_root / "all_cities_consensus_by_city_date.csv"
    master_all_scrapes_csv = output_root / "all_cities_all_scrapes.csv"

    summary_headers = [
        "scraped_at_utc",
        "city",
        "city_slug",
        "station_icao",
        "website_id",
        "website_name",
        "date",
        "unit",
        "highest_temperature",
        "highest_temperature_duration_hours",
        "highest_temperature_hours",
        "highest_temperature_max_consecutive_hours",
        "highest_temperature_exact",
        "highest_temperature_c",
        "highest_temperature_f",
        "consecutive_scrapes_with_same_high",
        "high_first_predicted_at_utc",
        "lowest_temperature",
        "lowest_temperature_duration_hours",
        "avg_temperature",
        "max_precip_prob_pct",
        "total_precip_mm",
        "max_wind_speed_kmh",
        "avg_humidity_pct",
        "dominant_condition",
        "hours_analyzed",
        "source_mode",
    ]

    latest_summary_headers = summary_headers + [
        "all_websites_agree_on_high",
        "consensus_highest_temperature",
        "websites_agreeing_count",
        "total_websites_for_date",
        "websites_agreement_pct",
        "websites_high_temp_spread",
    ]

    consensus_headers = [
        "city",
        "city_slug",
        "station_icao",
        "date",
        "unit",
        "all_websites_agree",
        "within_1_degree_all_websites",
        "consensus_highest_temperature",
        "websites_agreeing_count",
        "total_websites",
        "agreement_ratio",
        "agreement_pct",
        "min_highest_temperature",
        "max_highest_temperature",
        "temp_spread",
        "avg_duration_hours_at_high",
        "website_predictions_breakdown",
    ]

    hourly_headers = [
        "scraped_at_utc",
        "city",
        "city_slug",
        "station_icao",
        "website_id",
        "website_name",
        "date_local",
        "hour_local",
        "time_local",
        "time_utc",
        "unit",
        "temperature_market",
        "is_daily_high_hour",
        "daily_highest_temperature",
        "daily_highest_temperature_duration_hours",
        "temperature_market_raw",
        "temperature_c",
        "temperature_f",
        "feels_like_market",
        "feels_like_c",
        "feels_like_f",
        "dew_point_c",
        "dew_point_f",
        "humidity_pct",
        "precip_prob_pct",
        "precip_mm",
        "rain_mm",
        "snow_cm",
        "wind_speed_kmh",
        "wind_speed_mph",
        "wind_gust_kmh",
        "wind_gust_mph",
        "wind_direction_deg",
        "wind_direction_cardinal",
        "cloud_cover_pct",
        "pressure_hpa",
        "visibility_km",
        "uv_index",
        "air_quality_index",
        "condition",
    ]

    by_city: Dict[str, List[Dict]] = {}
    for latest_file in sorted(output_root.glob("*/*/latest.json")):
        try:
            d = json.loads(latest_file.read_text(encoding="utf-8"))
            if not (d.get("success") and d.get("daily_7day_summary")):
                # Recover from the most recent valid *Z.json in the same folder if latest.json had a transient error
                for cand in sorted(latest_file.parent.glob("*Z.json"), reverse=True):
                    try:
                        cand_d = json.loads(cand.read_text(encoding="utf-8"))
                        if cand_d.get("success") and cand_d.get("daily_7day_summary"):
                            d = cand_d
                            latest_file.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
                            break
                    except Exception:
                        continue
            if d.get("success") and d.get("daily_7day_summary"):
                by_city.setdefault(d["city_slug"], []).append(d)
        except Exception:
            continue

    # Pre-compute cross-website consensus for every (city_slug, date)
    consensus_map: Dict[Tuple[str, str], Dict] = {}
    consensus_summary_rows: List[Tuple[Tuple, List]] = []

    for city_slug, city_records in sorted(by_city.items()):
        by_date_items: Dict[str, List[Tuple[str, int, int, Dict]]] = {}
        city_name = city_records[0].get("city", city_slug) if city_records else city_slug
        station_icao = city_records[0].get("station_icao", "") if city_records else ""
        unit = city_records[0].get("polymarket_unit", "") if city_records else ""

        for r in city_records:
            w_id = r.get("website_id", "")
            for d in r.get("daily_7day_summary", []):
                dt = d.get("date")
                hi = d.get("highest_temperature")
                dur = d.get("highest_temperature_duration_hours", 0)
                if dt is not None and hi is not None:
                    by_date_items.setdefault(str(dt), []).append((str(w_id), int(hi), int(dur or 0), d))

        for dt, items in sorted(by_date_items.items()):
            temps = [t for _, t, _, _ in items]
            counts = Counter(temps)
            # Mode temperature (tie-break by highest count then temperature)
            consensus_high, agree_count = sorted(
                counts.items(), key=lambda kv: (-kv[1], kv[0])
            )[0]
            total_w = len(temps)
            min_t = min(temps)
            max_t = max(temps)
            spread = max_t - min_t
            all_agree = (spread == 0 and total_w >= 2)
            within_1 = (spread <= 1 and total_w >= 2)
            agree_pct = round(agree_count * 100.0 / total_w, 1) if total_w else 0.0

            agree_durs = [dur for _, t, dur, _ in items if t == consensus_high]
            avg_dur = round(sum(agree_durs) / len(agree_durs), 2) if agree_durs else 0.0

            breakdown = "|".join(
                f"{w}:{t}" for w, t, _, _ in sorted(items, key=lambda x: (x[1], x[0]))
            )

            info = {
                "all_websites_agree": all_agree,
                "within_1_degree": within_1,
                "consensus_high": consensus_high,
                "agree_count": agree_count,
                "total_websites": total_w,
                "agreement_pct": agree_pct,
                "min_high": min_t,
                "max_high": max_t,
                "temp_spread": spread,
                "avg_dur": avg_dur,
                "breakdown": breakdown,
            }
            consensus_map[(city_slug, dt)] = info

            sort_key = (
                0 if all_agree else (1 if within_1 else 2),
                -agree_pct,
                spread,
                city_slug,
                dt,
            )
            consensus_summary_rows.append((
                sort_key,
                [
                    city_name,
                    city_slug,
                    station_icao,
                    dt,
                    unit,
                    all_agree,
                    within_1,
                    consensus_high,
                    agree_count,
                    total_w,
                    f"{agree_count}/{total_w}",
                    agree_pct,
                    min_t,
                    max_t,
                    spread,
                    avg_dur,
                    breakdown,
                ],
            ))

    with master_consensus_csv.open("w", newline="", encoding="utf-8") as mcf:
        mcwriter = csv.writer(mcf)
        mcwriter.writerow(consensus_headers)
        for _, row in sorted(consensus_summary_rows, key=lambda x: x[0]):
            mcwriter.writerow(row)

    master_all_scrapes_csv = output_root / "all_cities_all_scrapes.csv"
    if master_all_scrapes_csv.exists():
        try:
            master_all_scrapes_csv.unlink()
        except Exception:
            pass

    agree_rows_sorted: List[Tuple[Tuple, List]] = []

    with master_latest_csv.open("w", newline="", encoding="utf-8") as mf, \
         master_without_unanimous_csv.open("w", newline="", encoding="utf-8") as mwof:
        mwriter = csv.writer(mf)
        mwriter.writerow(latest_summary_headers)
        mwowriter = csv.writer(mwof)
        mwowriter.writerow(latest_summary_headers)

        for city_slug, city_records in sorted(by_city.items()):
            city_dir = output_root / city_slug
            city_dir.mkdir(parents=True, exist_ok=True)

            # 1. Latest summary across all websites for this city
            city_csv = city_dir / "city_websites_summary.csv"
            with city_csv.open("w", newline="", encoding="utf-8") as cf:
                cwriter = csv.writer(cf)
                cwriter.writerow(latest_summary_headers)
                for r in city_records:
                    for d in r.get("daily_7day_summary", []):
                        dt = str(d.get("date"))
                        cinfo = consensus_map.get((city_slug, dt), {})
                        row = _summary_row_from_dict(r, d, cinfo)
                        cwriter.writerow(row)
                        mwriter.writerow(row)
                        if (
                            cinfo.get("all_websites_agree")
                            or cinfo.get("within_1_degree")
                            or (cinfo.get("agreement_pct", 0.0) >= 75.0)
                        ):
                            skey = (
                                0 if cinfo.get("all_websites_agree") else 1,
                                -float(cinfo.get("agreement_pct", 0.0)),
                                int(cinfo.get("temp_spread", 99)),
                                city_slug,
                                dt,
                                str(r.get("website_id", "")),
                            )
                            agree_rows_sorted.append((skey, row))
                        if not cinfo.get("all_websites_agree"):
                            mwowriter.writerow(row)

            # 2. Hour-by-hour 7-day forecasts across all websites for this city (outside website folders)
            city_hourly_csv = city_dir / "city_websites_hourly_forecasts.csv"
            with city_hourly_csv.open("w", newline="", encoding="utf-8") as chf:
                chwriter = csv.writer(chf)
                chwriter.writerow(hourly_headers)
                for r in city_records:
                    daily_lookup = {d.get("date"): d for d in r.get("daily_7day_summary", [])}
                    for p in r.get("hourly_7day_forecast", []):
                        day_info = daily_lookup.get(p.get("date_local")) or {}
                        chwriter.writerow([
                            r.get("scraped_at_utc"),
                            r.get("city"),
                            r.get("city_slug"),
                            r.get("station_icao"),
                            r.get("website_id"),
                            r.get("website_name"),
                            p.get("date_local"),
                            p.get("hour_local"),
                            p.get("time_local"),
                            p.get("time_utc"),
                            r.get("polymarket_unit"),
                            p.get("temperature_market"),
                            p.get("is_daily_high_hour"),
                            day_info.get("highest_temperature"),
                            day_info.get("highest_temperature_duration_hours"),
                            p.get("temperature_market_raw"),
                            p.get("temperature_c"),
                            p.get("temperature_f"),
                            p.get("feels_like_market"),
                            p.get("feels_like_c"),
                            p.get("feels_like_f"),
                            p.get("dew_point_c"),
                            p.get("dew_point_f"),
                            p.get("humidity_pct"),
                            p.get("precip_prob_pct"),
                            p.get("precip_mm"),
                            p.get("rain_mm"),
                            p.get("snow_cm"),
                            p.get("wind_speed_kmh"),
                            p.get("wind_speed_mph"),
                            p.get("wind_gust_kmh"),
                            p.get("wind_gust_mph"),
                            p.get("wind_direction_deg"),
                            p.get("wind_direction_cardinal"),
                            p.get("cloud_cover_pct"),
                            p.get("pressure_hpa"),
                            p.get("visibility_km"),
                            p.get("uv_index"),
                            p.get("air_quality_index"),
                            p.get("condition"),
                        ])

            # 3. All historical hourly scrapes across all websites for this city (outside website folders)
            city_all_scrapes_csv = city_dir / "city_websites_all_scrapes.csv"
            existing_rows: Dict[Tuple[str, str, str], List] = {}
            if city_all_scrapes_csv.exists():
                try:
                    with city_all_scrapes_csv.open("r", newline="", encoding="utf-8") as rf:
                        reader = csv.reader(rf)
                        header = next(reader, None)
                        if header == summary_headers:
                            for row in reader:
                                if len(row) >= 7:
                                    key = (row[0], row[4], row[6])  # (scraped_at_utc, website_id, date)
                                    existing_rows[key] = row
                except Exception:
                    existing_rows = {}

            if not existing_rows:
                # Backfill from all timestamped JSON snapshots (*Z.json) in all website folders for this city
                for ts_file in sorted(city_dir.glob("*/*Z.json")):
                    try:
                        snap = json.loads(ts_file.read_text(encoding="utf-8"))
                        if snap.get("success") and snap.get("daily_7day_summary"):
                            for d in snap.get("daily_7day_summary", []):
                                row = _summary_row_from_dict(snap, d)
                                key = (str(row[0]), str(row[4]), str(row[6]))
                                existing_rows[key] = row
                    except Exception:
                        continue
            else:
                # Merge the latest records into existing_rows
                for r in city_records:
                    for d in r.get("daily_7day_summary", []):
                        row = _summary_row_from_dict(r, d)
                        key = (str(row[0]), str(row[4]), str(row[6]))
                        existing_rows[key] = row

            sorted_rows = [
                existing_rows[k]
                for k in sorted(existing_rows.keys(), key=lambda x: (x[0], x[1], x[2]))
            ]
            # Keep under 250,000 rows (~55 MB) per city file so no file can ever exceed GitHub's 100 MB limit
            if len(sorted_rows) > 250000:
                sorted_rows = sorted_rows[-250000:]
            with city_all_scrapes_csv.open("w", newline="", encoding="utf-8") as caf:
                cawriter = csv.writer(caf)
                cawriter.writerow(summary_headers)
                for row in sorted_rows:
                    cawriter.writerow(row)

    with master_agree_csv.open("w", newline="", encoding="utf-8") as magf:
        magwriter = csv.writer(magf)
        magwriter.writerow(latest_summary_headers)
        for _, row in sorted(agree_rows_sorted, key=lambda x: x[0]):
            magwriter.writerow(row)


