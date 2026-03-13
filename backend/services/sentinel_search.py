"""
Sentinel-2 satellite imagery search via Microsoft Planetary Computer STAC API.
Free, keyless search for metadata + thumbnails. Used in the right-click dossier.
"""

import logging
import requests
from datetime import datetime, timedelta
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Cache by rounded lat/lon (0.02° grid ~= 2km), TTL 1 hour
_sentinel_cache = TTLCache(maxsize=200, ttl=3600)


def search_sentinel2_scene(lat: float, lng: float) -> dict:
    """Search for the latest Sentinel-2 L2A scene covering a point."""
    cache_key = f"{round(lat, 2)}_{round(lng, 2)}"
    if cache_key in _sentinel_cache:
        return _sentinel_cache[cache_key]

    try:
        from pystac_client import Client

        catalog = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
        end = datetime.utcnow()
        start = end - timedelta(days=30)

        search = catalog.search(
            collections=["sentinel-2-l2a"],
            intersects={"type": "Point", "coordinates": [lng, lat]},
            datetime=f"{start.isoformat()}Z/{end.isoformat()}Z",
            sortby=[{"field": "datetime", "direction": "desc"}],
            max_items=3,
            query={"eo:cloud_cover": {"lt": 30}},
        )

        items = list(search.items())
        if not items:
            result = {"found": False, "message": "No clear scenes in last 30 days"}
            _sentinel_cache[cache_key] = result
            return result

        item = items[0]
        # Try to sign item first for Azure blob URLs
        try:
            import planetary_computer
            item = planetary_computer.sign_item(item)
        except ImportError:
            pass  # planetary_computer not installed, try unsigned URLs
        except (ConnectionError, TimeoutError, ValueError) as e:
            logger.warning(f"Sentinel-2 signing failed: {e}")

        # Get the rendered_preview (full-res PNG) and thumbnail separately
        rendered = item.assets.get("rendered_preview")
        thumbnail = item.assets.get("thumbnail")

        # Full-res image URL — what opens when user clicks
        fullres_url = rendered.href if rendered else (thumbnail.href if thumbnail else None)
        # Thumbnail URL — what shows in the popup card
        thumb_url = thumbnail.href if thumbnail else (rendered.href if rendered else None)

        result = {
            "found": True,
            "scene_id": item.id,
            "datetime": item.datetime.isoformat() if item.datetime else None,
            "cloud_cover": item.properties.get("eo:cloud_cover"),
            "thumbnail_url": thumb_url,
            "fullres_url": fullres_url,
            "bbox": list(item.bbox) if item.bbox else None,
            "platform": item.properties.get("platform", "Sentinel-2"),
        }
        _sentinel_cache[cache_key] = result
        return result

    except ImportError:
        logger.warning("pystac-client not installed — Sentinel-2 search unavailable")
        return {"found": False, "error": "pystac-client not installed"}
    except (requests.RequestException, ConnectionError, TimeoutError, ValueError) as e:
        logger.error(f"Sentinel-2 search failed for ({lat}, {lng}): {e}")
        return {"found": False, "error": str(e)}
