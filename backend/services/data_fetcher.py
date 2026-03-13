"""Data fetcher orchestrator — schedules and coordinates all data source modules.

Heavy logic has been extracted into services/fetchers/:
  - _store.py      — shared state (latest_data, locks, timestamps)
  - plane_alert.py — aircraft enrichment DB
  - flights.py     — commercial flights, routes, trails, GPS jamming
  - military.py    — military flights, UAV detection
  - satellites.py  — satellite tracking (SGP4)
  - news.py        — RSS news fetching, clustering, risk assessment
"""
import yfinance as yf
import csv
import io
import json
import time
import math
import logging
import heapq
import concurrent.futures
from pathlib import Path
from datetime import datetime
from cachetools import TTLCache
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
load_dotenv()

from services.network_utils import fetch_with_curl
from services.cctv_pipeline import (
    init_db, TFLJamCamIngestor, LTASingaporeIngestor,
    AustinTXIngestor, NYCDOTIngestor, get_all_cameras,
)

# Shared state — all fetcher modules read/write through this
from services.fetchers._store import (
    latest_data, source_timestamps, _mark_fresh, _data_lock,  # noqa: F401 — source_timestamps re-exported for main.py
)

# Domain-specific fetcher modules
from services.fetchers.flights import fetch_flights
from services.fetchers.military import fetch_military_flights
from services.fetchers.satellites import fetch_satellites
from services.fetchers.news import fetch_news

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Financial data
# ---------------------------------------------------------------------------
def _fetch_single_ticker(symbol: str, period: str = "2d"):
    """Fetch a single yfinance ticker. Returns (symbol, data_dict) or (symbol, None)."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        if len(hist) >= 1:
            current_price = hist['Close'].iloc[-1]
            prev_close = hist['Close'].iloc[0] if len(hist) > 1 else current_price
            change_percent = ((current_price - prev_close) / prev_close) * 100 if prev_close else 0
            return symbol, {
                "price": round(float(current_price), 2),
                "change_percent": round(float(change_percent), 2),
                "up": bool(change_percent >= 0)
            }
    except Exception as e:
        logger.warning(f"Could not fetch data for {symbol}: {e}")
    return symbol, None

def fetch_defense_stocks():
    tickers = ["RTX", "LMT", "NOC", "GD", "BA", "PLTR"]
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = pool.map(lambda t: _fetch_single_ticker(t, "2d"), tickers)
        stocks_data = {sym: data for sym, data in results if data}
        with _data_lock:
            latest_data['stocks'] = stocks_data
        _mark_fresh("stocks")
    except Exception as e:
        logger.error(f"Error fetching stocks: {e}")

def fetch_oil_prices():
    tickers = {"WTI Crude": "CL=F", "Brent Crude": "BZ=F"}
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = pool.map(lambda item: (_fetch_single_ticker(item[1], "5d")[1], item[0]), tickers.items())
        oil_data = {name: data for data, name in results if data}
        with _data_lock:
            latest_data['oil'] = oil_data
        _mark_fresh("oil")
    except Exception as e:
        logger.error(f"Error fetching oil: {e}")

# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------
def fetch_weather():
    try:
        url = "https://api.rainviewer.com/public/weather-maps.json"
        response = fetch_with_curl(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "radar" in data and "past" in data["radar"]:
                latest_time = data["radar"]["past"][-1]["time"]
                with _data_lock:
                    latest_data["weather"] = {"time": latest_time, "host": data.get("host", "https://tilecache.rainviewer.com")}
                _mark_fresh("weather")
    except Exception as e:
        logger.error(f"Error fetching weather: {e}")

# ---------------------------------------------------------------------------
# CCTV
# ---------------------------------------------------------------------------
def fetch_cctv():
    try:
        cameras = get_all_cameras()
        with _data_lock:
            latest_data["cctv"] = cameras
        _mark_fresh("cctv")
    except Exception as e:
        logger.error(f"Error fetching cctv from DB: {e}")
        with _data_lock:
            latest_data["cctv"] = []

# ---------------------------------------------------------------------------
# KiwiSDR
# ---------------------------------------------------------------------------
def fetch_kiwisdr():
    try:
        from services.kiwisdr_fetcher import fetch_kiwisdr_nodes
        nodes = fetch_kiwisdr_nodes()
        with _data_lock:
            latest_data["kiwisdr"] = nodes
        _mark_fresh("kiwisdr")
    except Exception as e:
        logger.error(f"Error fetching KiwiSDR nodes: {e}")
        with _data_lock:
            latest_data["kiwisdr"] = []

# ---------------------------------------------------------------------------
# NASA FIRMS Fires
# ---------------------------------------------------------------------------
def fetch_firms_fires():
    """Fetch global fire/thermal anomalies from NASA FIRMS (NOAA-20 VIIRS, 24h, no key needed)."""
    fires = []
    try:
        url = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_Global_24h.csv"
        response = fetch_with_curl(url, timeout=30)
        if response.status_code == 200:
            reader = csv.DictReader(io.StringIO(response.text))
            all_rows = []
            for row in reader:
                try:
                    lat = float(row.get("latitude", 0))
                    lng = float(row.get("longitude", 0))
                    frp = float(row.get("frp", 0))
                    conf = row.get("confidence", "nominal")
                    daynight = row.get("daynight", "")
                    bright = float(row.get("bright_ti4", 0))
                    all_rows.append({
                        "lat": lat, "lng": lng, "frp": frp,
                        "brightness": bright, "confidence": conf,
                        "daynight": daynight,
                        "acq_date": row.get("acq_date", ""),
                        "acq_time": row.get("acq_time", ""),
                    })
                except (ValueError, TypeError):
                    continue
            fires = heapq.nlargest(5000, all_rows, key=lambda x: x["frp"])
        logger.info(f"FIRMS fires: {len(fires)} hotspots (from {response.status_code})")
    except Exception as e:
        logger.error(f"Error fetching FIRMS fires: {e}")
    with _data_lock:
        latest_data["firms_fires"] = fires
    if fires:
        _mark_fresh("firms_fires")

# ---------------------------------------------------------------------------
# Space Weather
# ---------------------------------------------------------------------------
def fetch_space_weather():
    """Fetch NOAA SWPC Kp index and recent solar events."""
    try:
        kp_resp = fetch_with_curl("https://services.swpc.noaa.gov/json/planetary_k_index_1m.json", timeout=10)
        kp_value = None
        kp_text = "QUIET"
        if kp_resp.status_code == 200:
            kp_data = kp_resp.json()
            if kp_data:
                latest_kp = kp_data[-1]
                kp_value = float(latest_kp.get("kp_index", 0))
                if kp_value >= 7:
                    kp_text = f"STORM G{min(int(kp_value) - 4, 5)}"
                elif kp_value >= 5:
                    kp_text = f"STORM G{min(int(kp_value) - 4, 5)}"
                elif kp_value >= 4:
                    kp_text = "ACTIVE"
                elif kp_value >= 3:
                    kp_text = "UNSETTLED"

        events = []
        ev_resp = fetch_with_curl("https://services.swpc.noaa.gov/json/edited_events.json", timeout=10)
        if ev_resp.status_code == 200:
            all_events = ev_resp.json()
            for ev in all_events[-10:]:
                events.append({
                    "type": ev.get("type", ""),
                    "begin": ev.get("begin", ""),
                    "end": ev.get("end", ""),
                    "classtype": ev.get("classtype", ""),
                })

        with _data_lock:
            latest_data["space_weather"] = {
                "kp_index": kp_value,
                "kp_text": kp_text,
                "events": events,
            }
        _mark_fresh("space_weather")
        logger.info(f"Space weather: Kp={kp_value} ({kp_text}), {len(events)} events")
    except Exception as e:
        logger.error(f"Error fetching space weather: {e}")

# ---------------------------------------------------------------------------
# Internet Outages (IODA)
# ---------------------------------------------------------------------------
_region_geocode_cache: TTLCache = TTLCache(maxsize=2000, ttl=86400)

def _geocode_region(region_name: str, country_name: str) -> tuple:
    """Geocode a region using OpenStreetMap Nominatim (cached, respects rate limit)."""
    cache_key = f"{region_name}|{country_name}"
    if cache_key in _region_geocode_cache:
        return _region_geocode_cache[cache_key]
    try:
        import urllib.parse
        query = urllib.parse.quote(f"{region_name}, {country_name}")
        url = f"https://nominatim.openstreetmap.org/search?q={query}&format=json&limit=1"
        response = fetch_with_curl(url, timeout=8, headers={"User-Agent": "ShadowBroker-OSINT/1.0"})
        if response.status_code == 200:
            results = response.json()
            if results:
                lat = float(results[0]["lat"])
                lon = float(results[0]["lon"])
                _region_geocode_cache[cache_key] = (lat, lon)
                return (lat, lon)
    except Exception:
        pass
    _region_geocode_cache[cache_key] = None
    return None

def fetch_internet_outages():
    """Fetch regional internet outage alerts from IODA (Georgia Tech)."""
    RELIABLE_DATASOURCES = {"bgp", "ping-slash24"}
    outages = []
    try:
        now = int(time.time())
        start = now - 86400
        url = f"https://api.ioda.inetintel.cc.gatech.edu/v2/outages/alerts?from={start}&until={now}&limit=500"
        response = fetch_with_curl(url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            alerts = data.get("data", [])
            region_outages = {}
            for alert in alerts:
                entity = alert.get("entity", {})
                etype = entity.get("type", "")
                level = alert.get("level", "")
                if level == "normal" or etype != "region":
                    continue
                datasource = alert.get("datasource", "")
                if datasource not in RELIABLE_DATASOURCES:
                    continue
                code = entity.get("code", "")
                name = entity.get("name", "")
                attrs = entity.get("attrs", {})
                country_code = attrs.get("country_code", "")
                country_name = attrs.get("country_name", "")
                value = alert.get("value", 0)
                history_value = alert.get("historyValue", 0)
                severity = 0
                if history_value and history_value > 0:
                    severity = round((1 - value / history_value) * 100)
                severity = max(0, min(severity, 100))
                if severity < 10:
                    continue
                if code not in region_outages or severity > region_outages[code]["severity"]:
                    region_outages[code] = {
                        "region_code": code,
                        "region_name": name,
                        "country_code": country_code,
                        "country_name": country_name,
                        "level": level,
                        "datasource": datasource,
                        "severity": severity,
                    }
            geocoded = []
            for rcode, r in region_outages.items():
                coords = _geocode_region(r["region_name"], r["country_name"])
                if coords:
                    r["lat"] = coords[0]
                    r["lng"] = coords[1]
                    geocoded.append(r)
            outages = heapq.nlargest(100, geocoded, key=lambda x: x["severity"])
        logger.info(f"Internet outages: {len(outages)} regions affected")
    except Exception as e:
        logger.error(f"Error fetching internet outages: {e}")
    with _data_lock:
        latest_data["internet_outages"] = outages
    if outages:
        _mark_fresh("internet_outages")

# ---------------------------------------------------------------------------
# Data Centers
# ---------------------------------------------------------------------------
_DC_GEOCODED_PATH = Path(__file__).parent.parent / "data" / "datacenters_geocoded.json"

def fetch_datacenters():
    """Load geocoded data centers (5K+ street-level precise locations)."""
    dcs = []
    try:
        if not _DC_GEOCODED_PATH.exists():
            logger.warning(f"Geocoded DC file not found: {_DC_GEOCODED_PATH}")
            return
        raw = json.loads(_DC_GEOCODED_PATH.read_text(encoding="utf-8"))
        for entry in raw:
            lat = entry.get("lat")
            lng = entry.get("lng")
            if lat is None or lng is None:
                continue
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                continue
            dcs.append({
                "name": entry.get("name", "Unknown"),
                "company": entry.get("company", ""),
                "street": entry.get("street", ""),
                "city": entry.get("city", ""),
                "country": entry.get("country", ""),
                "zip": entry.get("zip", ""),
                "lat": lat, "lng": lng,
            })
        logger.info(f"Data centers: {len(dcs)} geocoded locations loaded")
    except Exception as e:
        logger.error(f"Error loading data centers: {e}")
    with _data_lock:
        latest_data["datacenters"] = dcs
    if dcs:
        _mark_fresh("datacenters")

# ---------------------------------------------------------------------------
# Earthquakes
# ---------------------------------------------------------------------------
def fetch_earthquakes():
    quakes = []
    try:
        url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"
        response = fetch_with_curl(url, timeout=10)
        if response.status_code == 200:
            features = response.json().get("features", [])
            for f in features[:50]:
                mag = f["properties"]["mag"]
                lng, lat, depth = f["geometry"]["coordinates"]
                quakes.append({
                    "id": f["id"], "mag": mag,
                    "lat": lat, "lng": lng,
                    "place": f["properties"]["place"]
                })
    except Exception as e:
        logger.error(f"Error fetching earthquakes: {e}")
    with _data_lock:
        latest_data["earthquakes"] = quakes
    if quakes:
        _mark_fresh("earthquakes")

# ---------------------------------------------------------------------------
# Ships (AIS + Carriers)
# ---------------------------------------------------------------------------
def fetch_ships():
    """Fetch real-time AIS vessel data and combine with OSINT carrier positions."""
    from services.ais_stream import get_ais_vessels
    from services.carrier_tracker import get_carrier_positions

    ships = []
    try:
        carriers = get_carrier_positions()
        ships.extend(carriers)
    except Exception as e:
        logger.error(f"Carrier tracker error (non-fatal): {e}")
        carriers = []

    try:
        ais_vessels = get_ais_vessels()
        ships.extend(ais_vessels)
    except Exception as e:
        logger.error(f"AIS stream error (non-fatal): {e}")
        ais_vessels = []

    logger.info(f"Ships: {len(carriers)} carriers + {len(ais_vessels)} AIS vessels")
    with _data_lock:
        latest_data['ships'] = ships
    _mark_fresh("ships")

# ---------------------------------------------------------------------------
# Airports
# ---------------------------------------------------------------------------
cached_airports = []

def find_nearest_airport(lat, lng, max_distance_nm=200):
    """Find the nearest large airport to a given lat/lng using haversine distance."""
    if not cached_airports:
        return None

    best = None
    best_dist = float('inf')
    lat_r = math.radians(lat)
    lng_r = math.radians(lng)

    for apt in cached_airports:
        apt_lat_r = math.radians(apt['lat'])
        apt_lng_r = math.radians(apt['lng'])
        dlat = apt_lat_r - lat_r
        dlng = apt_lng_r - lng_r
        a = math.sin(dlat / 2) ** 2 + math.cos(lat_r) * math.cos(apt_lat_r) * math.sin(dlng / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        dist_nm = 3440.065 * c

        if dist_nm < best_dist:
            best_dist = dist_nm
            best = apt

    if best and best_dist <= max_distance_nm:
        return {
            "iata": best['iata'], "name": best['name'],
            "lat": best['lat'], "lng": best['lng'],
            "distance_nm": round(best_dist, 1)
        }
    return None

def fetch_airports():
    global cached_airports
    if not cached_airports:
        logger.info("Downloading global airports database from ourairports.com...")
        try:
            url = "https://ourairports.com/data/airports.csv"
            response = fetch_with_curl(url, timeout=15)
            if response.status_code == 200:
                f = io.StringIO(response.text)
                reader = csv.DictReader(f)
                for row in reader:
                    if row['type'] == 'large_airport' and row['iata_code']:
                        cached_airports.append({
                            "id": row['ident'],
                            "name": row['name'],
                            "iata": row['iata_code'],
                            "lat": float(row['latitude_deg']),
                            "lng": float(row['longitude_deg']),
                            "type": "airport"
                        })
                logger.info(f"Loaded {len(cached_airports)} large airports into cache.")
        except Exception as e:
            logger.error(f"Error fetching airports: {e}")

    with _data_lock:
        latest_data['airports'] = cached_airports

# ---------------------------------------------------------------------------
# Geopolitics & Liveuamap
# ---------------------------------------------------------------------------
from services.geopolitics import fetch_ukraine_frontlines, fetch_global_military_incidents

def fetch_frontlines():
    """Fetch Ukraine frontline data (fast — single GitHub API call)."""
    try:
        frontlines = fetch_ukraine_frontlines()
        if frontlines:
            with _data_lock:
                latest_data['frontlines'] = frontlines
            _mark_fresh("frontlines")
    except Exception as e:
        logger.error(f"Error fetching frontlines: {e}")


def fetch_gdelt():
    """Fetch GDELT global military incidents (slow — downloads 32 ZIP files)."""
    try:
        gdelt = fetch_global_military_incidents()
        if gdelt is not None:
            with _data_lock:
                latest_data['gdelt'] = gdelt
            _mark_fresh("gdelt")
    except Exception as e:
        logger.error(f"Error fetching GDELT: {e}")


def fetch_geopolitics():
    """Legacy wrapper — runs both sequentially. Used by recurring scheduler."""
    fetch_frontlines()
    fetch_gdelt()

def update_liveuamap():
    logger.info("Running scheduled Liveuamap scraper...")
    try:
        from services.liveuamap_scraper import fetch_liveuamap
        res = fetch_liveuamap()
        if res:
            with _data_lock:
                latest_data['liveuamap'] = res
            _mark_fresh("liveuamap")
    except Exception as e:
        logger.error(f"Liveuamap scraper error: {e}")

# ---------------------------------------------------------------------------
# Scheduler & Orchestration
# ---------------------------------------------------------------------------
def update_fast_data():
    """Fast-tier: moving entities that need frequent updates (every 60s)."""
    logger.info("Fast-tier data update starting...")
    fast_funcs = [
        fetch_flights,
        fetch_military_flights,
        fetch_ships,
        fetch_satellites,
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(fast_funcs)) as executor:
        futures = [executor.submit(func) for func in fast_funcs]
        concurrent.futures.wait(futures)
    with _data_lock:
        latest_data['last_updated'] = datetime.utcnow().isoformat()
    logger.info("Fast-tier update complete.")

def update_slow_data():
    """Slow-tier: feeds that change infrequently (every 30min).
    Each fetcher writes to latest_data independently as it finishes,
    so the frontend sees results progressively — no all-or-nothing barrier."""
    logger.info("Slow-tier data update starting...")
    slow_funcs = [
        fetch_news,
        fetch_defense_stocks,
        fetch_oil_prices,
        fetch_weather,
        fetch_cctv,
        fetch_earthquakes,
        fetch_frontlines,       # fast — single GitHub API call
        fetch_gdelt,            # slow — 32 ZIP downloads (runs in parallel, won't block frontlines)
        fetch_kiwisdr,
        fetch_space_weather,
        fetch_internet_outages,
        fetch_firms_fires,
        fetch_datacenters,
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(slow_funcs)) as executor:
        futures = [executor.submit(func) for func in slow_funcs]
        concurrent.futures.wait(futures)
    logger.info("Slow-tier update complete.")

def update_all_data():
    """Full update — runs on startup. All tiers run IN PARALLEL for fastest startup."""
    logger.info("Full data update starting (parallel)...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        f0 = pool.submit(fetch_airports)
        f1 = pool.submit(update_fast_data)
        f2 = pool.submit(update_slow_data)
        concurrent.futures.wait([f0, f1, f2])
    logger.info("Full data update complete.")

scheduler = BackgroundScheduler()

def start_scheduler():
    init_db()

    # NOTE: initial update_all_data() is called synchronously in main.py lifespan
    # before start_scheduler(). These are only the RECURRING interval jobs.
    scheduler.add_job(update_fast_data, 'interval', seconds=60)
    scheduler.add_job(update_slow_data, 'interval', minutes=30)

    def update_cctvs():
        logger.info("Running CCTV Pipeline Ingestion...")
        ingestors = [
            TFLJamCamIngestor,
            LTASingaporeIngestor,
            AustinTXIngestor,
            NYCDOTIngestor
        ]
        for ingestor in ingestors:
            try:
                ingestor().ingest()
            except Exception as e:
                logger.error(f"Failed {ingestor.__name__} cctv ingest: {e}")
        fetch_cctv()

    scheduler.add_job(update_cctvs, 'interval', minutes=1)

    scheduler.add_job(update_liveuamap, 'interval', hours=12)

    scheduler.start()

def stop_scheduler():
    scheduler.shutdown()

def get_latest_data():
    with _data_lock:
        return dict(latest_data)
