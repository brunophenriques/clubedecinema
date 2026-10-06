"""Bounded, cached TMDB movie metadata for the in-app film sheet."""
import os
import time
import re
from urllib.parse import quote

from fastapi import HTTPException
import requests

_cache = {}
_images_cache = {}
_TTL = 60 * 60 * 6
_MAX_CACHE = 256

# Visually checked photography from the film, only used if TMDB still lists it.
_VERIFIED_SCENES = {1878: "/hUzs26surgYxbHATjyDIyWat6ZL.jpg"}


def backdrop_url(path, size="w1280"):
    if not isinstance(path, str) or not re.fullmatch(r"/[A-Za-z0-9]+\.(?:jpg|png|webp)", path):
        return None
    return f"https://image.tmdb.org/t/p/{size}{path}"


def get_backdrops(tmdb_id):
    """Cached /movie/{id}/images. Language tags do not identify scene photography."""
    if tmdb_id < 1:
        raise HTTPException(422, "Invalid movie ID")
    now = time.time()
    cached = _images_cache.get(tmdb_id)
    if cached and cached[0] > now:
        return cached[1]
    key = os.getenv("TMDB_API_KEY")
    if not key:
        raise HTTPException(503, "Movie images are unavailable")
    try:
        response = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}/images",
                                params={"api_key": key}, timeout=8)
        if response.status_code == 404:
            raise HTTPException(404, "Movie not found")
        response.raise_for_status()
        images = []
        seen = set()
        for raw in response.json().get("backdrops", []):
            path = raw.get("file_path")
            width, height = int(raw.get("width") or 0), int(raw.get("height") or 0)
            ratio = width / height if height else 0
            if not backdrop_url(path) or path in seen or not 1.3 <= ratio <= 4:
                continue
            seen.add(path)
            images.append({"file_path": path, "width": width, "height": height,
                           "aspect_ratio": ratio, "language": raw.get("iso_639_1"),
                           "vote_average": raw.get("vote_average") or 0,
                           "suitable": width >= 1280 and height >= 720 and ratio >= 1.5,
                           "verified_scene": _VERIFIED_SCENES.get(tmdb_id) == path,
                           "url": backdrop_url(path), "preview_url": backdrop_url(path, "w780"),
                           "thumbnail_url": backdrop_url(path, "w300")})
        images.sort(key=lambda item: (item["suitable"], item["verified_scene"],
                    item["language"] is None, item["width"] >= 1920,
                    item["vote_average"], item["width"]), reverse=True)
    except HTTPException:
        raise
    except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError):
        raise HTTPException(502, "Movie images are temporarily unavailable")
    if len(_images_cache) >= _MAX_CACHE:
        _images_cache.pop(next(iter(_images_cache)))
    _images_cache[tmdb_id] = (now + _TTL, images)
    return images


def letterboxd_url(tmdb_id=None, title="", year=None):
    query = f"tmdb:{tmdb_id}" if tmdb_id else f"{title} {year or ''}".strip()
    return f"https://letterboxd.com/search/{quote(query, safe=':')}/"


def get_details(tmdb_id):
    if tmdb_id < 1:
        raise HTTPException(422, "Invalid movie ID")
    now = time.time()
    cached = _cache.get(tmdb_id)
    if cached and cached[0] > now:
        return cached[1]
    key = os.getenv("TMDB_API_KEY")
    if not key:
        raise HTTPException(503, "Movie details are unavailable")
    try:
        response = requests.get(
            f"https://api.themoviedb.org/3/movie/{tmdb_id}",
            params={"api_key": key, "language": "pt-PT",
                    "append_to_response": "credits,translations"},
            timeout=8,
        )
        if response.status_code == 404:
            raise HTTPException(404, "Movie not found")
        response.raise_for_status()
        data = response.json()
        # Use an available English synopsis when TMDB has no Portuguese text.
        overview = data.get("overview") or ""
        overview_language = "pt" if overview else None
        if not overview:
            for translation in data.get("translations", {}).get("translations", []):
                if translation.get("iso_639_1") == "en" and translation.get("data", {}).get("overview"):
                    overview = translation["data"]["overview"]
                    overview_language = "en"
                    break
        image_url = lambda path, size: f"https://image.tmdb.org/t/p/{size}{path}" if path and path.startswith("/") else None
        images_unavailable = False
        try:
            backdrop = next((item for item in get_backdrops(tmdb_id) if item["suitable"]), None)
        except HTTPException:
            # Metadata still works if the optional image request fails; retry soon.
            backdrop = None
            images_unavailable = True
        credits = data.get("credits") or {}
        payload = {
            "tmdb_id": tmdb_id,
            "title": data.get("title") or data.get("original_title") or "",
            "original_title": data.get("original_title"),
            "year": (data.get("release_date") or "")[:4] or None,
            "overview": overview or None,
            "overview_language": overview_language,
            "runtime": data.get("runtime") or None,
            "genres": [g["name"] for g in data.get("genres", []) if g.get("name")],
            "directors": list(dict.fromkeys(c["name"] for c in credits.get("crew", []) if c.get("job") == "Director" and c.get("name"))),
            "cast": [{"name": c.get("name"), "character": c.get("character")} for c in credits.get("cast", [])[:8] if c.get("name")],
            "poster_url": image_url(data.get("poster_path"), "w500"),
            "backdrop_url": backdrop["url"] if backdrop else None,
            "backdrop_aspect_ratio": backdrop.get("aspect_ratio") if backdrop else None,
            "backdrop_position": {"x": 50, "y": 42},
            "backdrop_selection": "automatic",
            "rating": data.get("vote_average") if data.get("vote_count", 0) else None,
            "rating_count": data.get("vote_count") or 0,
            "letterboxd_url": letterboxd_url(tmdb_id),
            "tmdb_url": f"https://www.themoviedb.org/movie/{tmdb_id}",
            "source": "tmdb",
        }
    except HTTPException:
        raise
    except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError):
        # Never expose request URLs, which can contain the API key.
        raise HTTPException(502, "Movie details are temporarily unavailable")
    if len(_cache) >= _MAX_CACHE:
        _cache.pop(next(iter(_cache)))
    _cache[tmdb_id] = (now + (60 if images_unavailable else _TTL), payload)
    return payload
