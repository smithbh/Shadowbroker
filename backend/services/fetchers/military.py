"""Military flight tracking and UAV detection from ADS-B data."""
import logging
from services.network_utils import fetch_with_curl
from services.fetchers._store import latest_data, _data_lock, _mark_fresh
from services.fetchers.plane_alert import enrich_with_plane_alert

logger = logging.getLogger("services.data_fetcher")

# ---------------------------------------------------------------------------
# UAV classification — filters military drone transponders
# ---------------------------------------------------------------------------
_UAV_TYPE_CODES = {"Q9", "R4", "TB2", "MALE", "HALE", "HERM", "HRON"}
_UAV_CALLSIGN_PREFIXES = ("FORTE", "GHAWK", "REAP", "BAMS", "UAV", "UAS")
_UAV_MODEL_KEYWORDS = ("RQ-", "MQ-", "RQ4", "MQ9", "MQ4", "MQ1", "REAPER", "GLOBALHAWK", "TRITON", "PREDATOR", "HERMES", "HERON", "BAYRAKTAR")
_UAV_WIKI = {
    "RQ4": "https://en.wikipedia.org/wiki/Northrop_Grumman_RQ-4_Global_Hawk",
    "RQ-4": "https://en.wikipedia.org/wiki/Northrop_Grumman_RQ-4_Global_Hawk",
    "MQ4": "https://en.wikipedia.org/wiki/Northrop_Grumman_MQ-4C_Triton",
    "MQ-4": "https://en.wikipedia.org/wiki/Northrop_Grumman_MQ-4C_Triton",
    "MQ9": "https://en.wikipedia.org/wiki/General_Atomics_MQ-9_Reaper",
    "MQ-9": "https://en.wikipedia.org/wiki/General_Atomics_MQ-9_Reaper",
    "MQ1": "https://en.wikipedia.org/wiki/General_Atomics_MQ-1C_Gray_Eagle",
    "MQ-1": "https://en.wikipedia.org/wiki/General_Atomics_MQ-1C_Gray_Eagle",
    "REAPER": "https://en.wikipedia.org/wiki/General_Atomics_MQ-9_Reaper",
    "GLOBALHAWK": "https://en.wikipedia.org/wiki/Northrop_Grumman_RQ-4_Global_Hawk",
    "TRITON": "https://en.wikipedia.org/wiki/Northrop_Grumman_MQ-4C_Triton",
    "PREDATOR": "https://en.wikipedia.org/wiki/General_Atomics_MQ-1_Predator",
    "HERMES": "https://en.wikipedia.org/wiki/Elbit_Hermes_900",
    "HERON": "https://en.wikipedia.org/wiki/IAI_Heron",
    "BAYRAKTAR": "https://en.wikipedia.org/wiki/Bayraktar_TB2",
}


def _classify_uav(model: str, callsign: str):
    """Check if an aircraft is a UAV based on type code, callsign prefix, or model keywords.
    Returns (is_uav, uav_type, wiki_url) or (False, None, None)."""
    model_up = model.upper().replace(" ", "")
    callsign_up = callsign.upper().strip()

    if model_up in _UAV_TYPE_CODES:
        uav_type = "HALE Surveillance" if model_up in ("R4", "HALE") else "MALE ISR"
        wiki = _UAV_WIKI.get(model_up, "")
        return True, uav_type, wiki

    for prefix in _UAV_CALLSIGN_PREFIXES:
        if callsign_up.startswith(prefix):
            uav_type = "HALE Surveillance" if prefix in ("FORTE", "GHAWK", "BAMS") else "MALE ISR"
            wiki = _UAV_WIKI.get(prefix, "")
            if prefix == "FORTE":
                wiki = _UAV_WIKI["RQ4"]
            elif prefix == "BAMS":
                wiki = _UAV_WIKI["MQ4"]
            return True, uav_type, wiki

    for kw in _UAV_MODEL_KEYWORDS:
        if kw in model_up:
            if any(h in model_up for h in ("RQ4", "RQ-4", "GLOBALHAWK")):
                return True, "HALE Surveillance", _UAV_WIKI.get(kw, "")
            elif any(h in model_up for h in ("MQ4", "MQ-4", "TRITON")):
                return True, "HALE Maritime Surveillance", _UAV_WIKI.get(kw, "")
            elif any(h in model_up for h in ("MQ9", "MQ-9", "REAPER")):
                return True, "MALE Strike/ISR", _UAV_WIKI.get(kw, "")
            elif any(h in model_up for h in ("MQ1", "MQ-1", "PREDATOR")):
                return True, "MALE ISR/Strike", _UAV_WIKI.get(kw, "")
            elif "BAYRAKTAR" in model_up or "TB2" in model_up:
                return True, "MALE Strike", _UAV_WIKI.get("BAYRAKTAR", "")
            elif "HERMES" in model_up:
                return True, "MALE ISR", _UAV_WIKI.get("HERMES", "")
            elif "HERON" in model_up:
                return True, "MALE ISR", _UAV_WIKI.get("HERON", "")
            return True, "MALE ISR", _UAV_WIKI.get(kw, "")

    return False, None, None


def fetch_military_flights():
    military_flights = []
    detected_uavs = []
    try:
        url = "https://api.adsb.lol/v2/mil"
        response = fetch_with_curl(url, timeout=10)
        if response.status_code == 200:
            ac = response.json().get('ac', [])
            for f in ac:
                try:
                    lat = f.get("lat")
                    lng = f.get("lon")
                    heading = f.get("track") or 0

                    if lat is None or lng is None:
                        continue

                    model = str(f.get("t", "UNKNOWN")).upper()
                    callsign = str(f.get("flight", "MIL-UNKN")).strip()

                    if model == "TWR":
                        continue

                    alt_raw = f.get("alt_baro")
                    alt_value = 0
                    if isinstance(alt_raw, (int, float)):
                        alt_value = alt_raw * 0.3048

                    gs_knots = f.get("gs")
                    speed_knots = round(gs_knots, 1) if isinstance(gs_knots, (int, float)) else None

                    is_uav, uav_type, wiki_url = _classify_uav(model, callsign)
                    if is_uav:
                        detected_uavs.append({
                            "id": f"uav-{f.get('hex', '')}",
                            "callsign": callsign,
                            "aircraft_model": f.get("t", "Unknown"),
                            "lat": float(lat),
                            "lng": float(lng),
                            "alt": alt_value,
                            "heading": heading,
                            "speed_knots": speed_knots,
                            "country": f.get("flag", "Unknown"),
                            "uav_type": uav_type,
                            "wiki": wiki_url or "",
                            "type": "uav",
                            "registration": f.get("r", "N/A"),
                            "icao24": f.get("hex", ""),
                            "squawk": f.get("squawk", ""),
                        })
                        continue

                    mil_cat = "default"
                    if "H" in model and any(c.isdigit() for c in model):
                        mil_cat = "heli"
                    elif any(k in model for k in ["K35", "K46", "A33"]):
                        mil_cat = "tanker"
                    elif any(k in model for k in ["F16", "F35", "F22", "F15", "F18", "T38", "T6", "A10"]):
                        mil_cat = "fighter"
                    elif any(k in model for k in ["C17", "C5", "C130", "C30", "A400", "V22"]):
                        mil_cat = "cargo"
                    elif any(k in model for k in ["P8", "E3", "E8", "U2"]):
                        mil_cat = "recon"

                    military_flights.append({
                        "callsign": callsign,
                        "country": f.get("flag", "Military Asset"),
                        "lng": float(lng),
                        "lat": float(lat),
                        "alt": alt_value,
                        "heading": heading,
                        "type": "military_flight",
                        "military_type": mil_cat,
                        "origin_loc": None,
                        "dest_loc": None,
                        "origin_name": "UNKNOWN",
                        "dest_name": "UNKNOWN",
                        "registration": f.get("r", "N/A"),
                        "model": f.get("t", "Unknown"),
                        "icao24": f.get("hex", ""),
                        "speed_knots": speed_knots,
                        "squawk": f.get("squawk", "")
                    })
                except Exception as loop_e:
                    logger.error(f"Mil flight interpolation error: {loop_e}")
                    continue
    except Exception as e:
        logger.error(f"Error fetching military flights: {e}")

    if not military_flights and not detected_uavs:
        logger.warning("No military flights retrieved — keeping previous data if available")
        with _data_lock:
            if latest_data.get('military_flights'):
                return

    with _data_lock:
        latest_data['military_flights'] = military_flights
        latest_data['uavs'] = detected_uavs
    _mark_fresh("military_flights", "uavs")
    logger.info(f"UAVs: {len(detected_uavs)} real drones detected via ADS-B")

    # Cross-reference military flights with Plane-Alert DB
    tracked_mil = []
    remaining_mil = []
    for mf in military_flights:
        enrich_with_plane_alert(mf)
        if mf.get('alert_category'):
            mf['type'] = 'tracked_flight'
            tracked_mil.append(mf)
        else:
            remaining_mil.append(mf)
    with _data_lock:
        latest_data['military_flights'] = remaining_mil

    # Store tracked military flights — update positions for existing entries
    with _data_lock:
        existing_tracked = list(latest_data.get('tracked_flights', []))
    fresh_mil_map = {}
    for t in tracked_mil:
        icao = t.get('icao24', '').upper()
        if icao:
            fresh_mil_map[icao] = t

    updated_tracked = []
    seen_icaos = set()
    for old_t in existing_tracked:
        icao = old_t.get('icao24', '').upper()
        if icao in fresh_mil_map:
            fresh = fresh_mil_map[icao]
            for key in ('alert_category', 'alert_operator', 'alert_special', 'alert_flag'):
                if key in old_t and key not in fresh:
                    fresh[key] = old_t[key]
            updated_tracked.append(fresh)
            seen_icaos.add(icao)
        else:
            updated_tracked.append(old_t)
            seen_icaos.add(icao)
    for icao, t in fresh_mil_map.items():
        if icao not in seen_icaos:
            updated_tracked.append(t)
    with _data_lock:
        latest_data['tracked_flights'] = updated_tracked
    logger.info(f"Tracked flights: {len(updated_tracked)} total ({len(tracked_mil)} from military)")
