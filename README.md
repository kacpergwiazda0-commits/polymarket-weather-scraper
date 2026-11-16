# Polymarket 55-City × 11-Website Hourly Weather Forecast Scraper

Automated hourly scraper that collects **7-day hourly weather forecasts** across all **55 Polymarket `'Highest temperature in (city) on (day)?'` cities** from **11 weather forecast websites**:

1. **Microsoft Weather (MSN)** (`msn_weather`) — `https://www.msn.com/weather`
2. **The Weather Channel** (`weather_com`) — `https://weather.com`
3. **Foreca** (`foreca`) — `https://www.foreca.com`
4. **AccuWeather** (`accuweather`) — `https://www.accuweather.com`
5. **meteoblue** (`meteoblue`) — `https://www.meteoblue.com`
6. **AerisWeather / Xweather** (`aerisweather`) — `https://www.aerisweather.com`
7. **Weatherbit** (`weatherbit`) — `https://www.weatherbit.io`
8. **Open-Meteo** (`open_meteo`) — `https://open-meteo.com`
9. **Yr.no (MET Norway)** (`yr_no`) — `https://www.yr.no`
10. **UK Met Office** (`uk_met_office`) — `https://www.metoffice.gov.uk`
11. **Apple Weather (WeatherKit)** (`apple_weather`) — Apple WeatherKit feed

---

## Key Metrics Computed for Each Day (Next 7 Days)

For every city and website, each hourly scrape targets the **exact Polymarket resolution airport weather station** (e.g., `KLGA` LaGuardia for NYC, `KORD` O'Hare for Chicago, `EGLC` London City Airport for London, `LFPB` Le Bourget for Paris) and calculates:

- **`highest_temperature`**: Whole-degree predicted daily maximum in the city's Polymarket settlement unit (`°F` for US cities, `°C` for international cities, rounded half-up per Polymarket rules).
- **`highest_temperature_duration_hours`**: How many hours during that day the forecast stays at `highest_temperature` (e.g., if the highest temperature is `17°C` and occurs at `14:00`, `15:00`, and `16:00`, `highest_temperature_duration_hours = 3`).
- **`highest_temperature_hours`**: List of local hours at the daily peak (e.g., `["14:00", "15:00", "16:00"]`).
- **`highest_temperature_max_consecutive_hours`**: Longest unbroken streak of hours at the daily peak temperature.
- **`consecutive_scrapes_with_same_high`** & **`high_first_predicted_at_utc`**: How many consecutive hourly scrape runs have predicted this same daily high temperature.
- **`highest_temperature_exact`**, **`highest_temperature_c`**, **`highest_temperature_f`**: Unrounded floating-point peak temperatures in both Celsius and Fahrenheit.
- **`lowest_temperature`**, **`lowest_temperature_duration_hours`**, **`lowest_temperature_hours`**: Same analysis for Polymarket's daily low temperature markets.
- **Full Hourly Meteorological Data**:
  - `temperature_market`, `temperature_market_raw`, `temperature_c`, `temperature_f`
  - `feels_like_market`, `feels_like_c`, `feels_like_f`
  - `dew_point_c`, `dew_point_f`
  - `humidity_pct` (`%`)
  - `precip_prob_pct` (`%`), `precip_mm`, `rain_mm`, `snow_cm`
  - `wind_speed_kmh`, `wind_speed_mph`, `wind_gust_kmh`, `wind_gust_mph`, `wind_direction_deg`, `wind_direction_cardinal`
  - `cloud_cover_pct` (`%`), `pressure_hpa` (`hPa`), `visibility_km`, `uv_index`, `air_quality_index`, `condition`

---

## Folder Structure

Each of the 55 cities has its own folder under `data/`, containing a subfolder for each of the 11 websites:

```text
data/
├── all_cities_latest_summary.csv          # Master table across all 55 cities x 11 websites x 7 days
├── amsterdam/
│   ├── city_websites_summary.csv          # Side-by-side comparison of all 11 websites for Amsterdam
│   ├── msn_weather/
│   │   ├── 2026-11-16T15-00-00Z.json      # Timestamped snapshot for each hourly run
│   │   ├── latest.json                    # Most recent scrape JSON
│   │   ├── daily_summary.csv              # Cumulative log of daily highs & peak durations across runs
│   │   └── hourly_forecast.csv            # Full 7-day hour-by-hour forecast table
│   ├── weather_com/
│   ├── foreca/
│   ├── accuweather/
│   ├── meteoblue/
│   ├── aerisweather/
│   ├── weatherbit/
│   ├── open_meteo/
│   ├── yr_no/
│   ├── uk_met_office/
│   └── apple_weather/
├── ankara/
...
├── nyc/
...
└── zhengzhou/
```

---

## Running Remotely Every Hour

### Option 1: GitHub Actions (Cloud-Hosted, Runs Every Hour Automatically)
The included workflow [`.github/workflows/hourly_scrape.yml`](.github/workflows/hourly_scrape.yml) is configured with `cron: '0 * * * *'` to run automatically every hour on GitHub's cloud runners and commit the new snapshots into `data/<city>/<website>/`.
- You can also trigger a run manually anytime from the **Actions** tab (`Hourly Polymarket Weather Forecast Scraper` -> **Run workflow**).
- To add optional API keys for `Weatherbit`, `AerisWeather`, or `Apple WeatherKit`, add them under **Settings -> Secrets and variables -> Actions**.

### Option 2: Docker / Remote Server Daemon
Run continuously every hour on any Linux VPS or cloud instance:
```bash
docker compose up -d --build
```
Or run directly with Python 3.11+:
```bash
# Single scrape of all 55 cities x 11 websites
python3 run_scraper.py --output-dir data --workers 16

# Continuous hourly daemon mode (runs every 3600 seconds)
python3 run_scraper.py --output-dir data --workers 16 --loop --interval-seconds 3600

# Filter specific cities or websites
python3 run_scraper.py --cities nyc,london,tokyo --websites msn_weather,weather_com,foreca,accuweather
```
