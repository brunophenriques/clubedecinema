"""Bounded, cached TMDB movie metadata for the in-app film sheet."""
import os
import time
from urllib.parse import quote

from fastapi import HTTPException
import requests

_cache = {}
_TTL = 60 * 60 * 6
_MAX_CACHE = 256


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
            params={"api_key": key, "language": "pt-PT", "append_to_response": "credits,translations"},
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
            "backdrop_url": image_url(data.get("backdrop_path"), "w1280"),
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
    _cache[tmdb_id] = (now + _TTL, payload)
    return payload
