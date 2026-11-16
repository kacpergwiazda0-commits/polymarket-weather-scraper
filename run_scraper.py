#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

from scraper.cities import CityConfig, POLYMARKET_CITIES, get_city
from scraper.models import ScrapeResult
from scraper.providers import ALL_PROVIDERS, PROVIDERS_BY_ID, WeatherProvider
from scraper.storage import (
    load_previous_high_history,
    save_scrape_result,
    write_Overview_tables,
)


def load_dotenv_file(dotenv_path: Path) -> None:
    """Lightweight .env loader requiring no third-party dependencies."""
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip("'").strip('"')
        if k and k not in os.environ:
            os.environ[k] = v


def _scrape_one(
    city: CityConfig,
    provider: WeatherProvider,
    output_root: Path,
    scraped_at_utc: str,
) -> ScrapeResult:
    prev_history = load_previous_high_history(output_root, city.slug, provider.website_id)
    res = provider.scrape_city(
        city=city,
        scraped_at_utc=scraped_at_utc,
        previous_high_history=prev_history,
    )
    save_scrape_result(output_root, res)
    return res


def run_once(
    cities: List[CityConfig],
    providers: List[WeatherProvider],
    output_root: Path,
    max_workers: int = 16,
) -> Tuple[int, int, List[ScrapeResult]]:
    scraped_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total_tasks = len(cities) * len(providers)
    print(
        f"[{scraped_at_utc}] Starting scrape: {len(cities)} cities x {len(providers)} websites "
        f"= {total_tasks} tasks (output -> {output_root})"
    )
    t0 = time.time()
    results: List[ScrapeResult] = []
    ok_count = 0
    err_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {
            pool.submit(_scrape_one, city, prov, output_root, scraped_at_utc): (city, prov)
            for city in cities
            for prov in providers
        }
        for idx, fut in enumerate(as_completed(future_map), 1):
            city, prov = future_map[fut]
            try:
                res = fut.result()
                results.append(res)
                if res.success:
                    ok_count += 1
                    d0 = res.daily_7day_summary[0] if res.daily_7day_summary else None
                    hi_str = (
                        f"Day0({d0.date}) High={d0.highest_temperature}°{d0.unit} "
                        f"for {d0.highest_temperature_duration_hours}h ({','.join(d0.highest_temperature_hours[:4])})"
                        if d0
                        else "no-days"
                    )
                    if idx % 25 == 0 or total_tasks <= 30:
                        print(
                            f"  [{idx}/{total_tasks}] OK   {city.slug}/{prov.website_id}: {hi_str}"
                        )
                else:
                    err_count += 1
                    print(
                        f"  [{idx}/{total_tasks}] WARN {city.slug}/{prov.website_id}: {res.error}"
                    )
            except Exception as e:
                err_count += 1
                print(f"  [{idx}/{total_tasks}] FAIL {city.slug}/{prov.website_id}: {e}")

    write_Overview_tables(output_root, results)
    elapsed = time.time() - t0
    print(
        f"[{scraped_at_utc}] Completed in {elapsed:.1f}s: {ok_count}/{total_tasks} succeeded, {err_count} failed."
    )
    return ok_count, err_count, results


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scrape 7-day hourly weather forecasts, daily highest temperatures, and "
            "hours-at-peak duration for all 55 Polymarket cities across 11 weather websites."
        )
    )
    parser.add_argument(
        "--output-dir",
        default="data",
        help="Root directory where <city>/<website>/ folders are written (default: data)",
    )
    parser.add_argument(
        "--cities",
        default="",
        help="Optional comma-separated city slugs or names (default: all 55 Polymarket cities)",
    )
    parser.add_argument(
        "--websites",
        default="",
        help=(
            "Optional comma-separated website IDs "
            f"({','.join(PROVIDERS_BY_ID.keys())}; default: all 11)"
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=16,
        help="Concurrent worker threads (default: 16)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously every --interval-seconds (default 3600s = 1 hour)",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=3600,
        help="Interval in seconds between runs when --loop is enabled (default: 3600)",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    load_dotenv_file(Path(".env"))
    args = parse_args(argv if argv is not None else sys.argv[1:])

    if args.cities.strip():
        selected_cities: List[CityConfig] = []
        for token in args.cities.split(","):
            c = get_city(token)
            if not c:
                print(f"Unknown city: {token!r}", file=sys.stderr)
                return 2
            selected_cities.append(c)
    else:
        selected_cities = list(POLYMARKET_CITIES)

    if args.websites.strip():
        selected_providers: List[WeatherProvider] = []
        for token in args.websites.split(","):
            pid = token.strip().lower()
            if pid not in PROVIDERS_BY_ID:
                print(
                    f"Unknown website ID: {pid!r}. Available: {list(PROVIDERS_BY_ID.keys())}",
                    file=sys.stderr,
                )
                return 2
            selected_providers.append(PROVIDERS_BY_ID[pid])
    else:
        selected_providers = list(ALL_PROVIDERS)

    output_root = Path(args.output_dir).resolve()

    if not args.loop:
        ok, _, _ = run_once(
            cities=selected_cities,
            providers=selected_providers,
            output_root=output_root,
            max_workers=args.workers,
        )
        return 0 if ok > 0 else 1

    print(
        f"Starting hourly daemon mode (interval={args.interval_seconds}s) for "
        f"{len(selected_cities)} cities x {len(selected_providers)} websites..."
    )
    while True:
        cycle_start = time.time()
        try:
            run_once(
                cities=selected_cities,
                providers=selected_providers,
                output_root=output_root,
                max_workers=args.workers,
            )
        except Exception as e:
            print(f"Error during scrape cycle: {e}", file=sys.stderr)
        elapsed = time.time() - cycle_start
        sleep_for = max(1.0, float(args.interval_seconds) - elapsed)
        print(f"Sleeping {sleep_for:.1f}s until next hourly scrape...")
        time.sleep(sleep_for)


if __name__ == "__main__":
    raise SystemExit(main())
