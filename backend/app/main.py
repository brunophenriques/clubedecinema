from fastapi import FastAPI, Depends, HTTPException, Body, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload, selectinload, load_only
from sqlalchemy import func, event, String, cast
import json
import logging
import os
from dotenv import load_dotenv
import requests
from rapidfuzz import fuzz
import xml.etree.ElementTree as ET
import re

import time
import secrets
import hashlib
import hmac
import base64

from pathlib import Path
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .db import SessionLocal
from . import models

app = FastAPI(title="Cinema Club API")
logger = logging.getLogger("cinema_club.egress")

DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 100
CHAT_LIMIT = 50
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_DEFAULT = 180
RATE_LIMIT_AUTH = 40
RATE_LIMIT_AUTH_WRITE = 10
_rate_buckets: dict[tuple[str, str], list[float]] = {}
_response_cache: dict[str, tuple[float, object]] = {}


def clamp_limit(limit: int | None, default: int = DEFAULT_LIST_LIMIT, maximum: int = MAX_LIST_LIMIT) -> int:
    try:
        value = int(limit or default)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, maximum))


def cache_get(key: str):
    hit = _response_cache.get(key)
    if not hit:
        return None
    expires_at, value = hit
    if expires_at <= time.time():
        _response_cache.pop(key, None)
        return None
    return value


def cache_set(key: str, value, ttl: int = 20):
    _response_cache[key] = (time.time() + ttl, value)
    return value


def clear_response_cache():
    _response_cache.clear()


@event.listens_for(Session, "after_commit")
def _clear_cache_after_commit(session):
    clear_response_cache()


def approx_payload_size(payload) -> int:
    try:
        return len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"))
    except Exception:
        return 0


def log_db_response(path: str, purpose: str, rows: int, payload) -> None:
    logger.info(
        "db_response path=%s purpose=%s rows=%s approx_payload_bytes=%s",
        path,
        purpose,
        rows,
        approx_payload_size(payload),
    )


@app.middleware("http")
async def rate_limit_and_log(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static/") or path in {"/favicon.ico", "/sw.js"}:
        return await call_next(request)

    client = request.client.host if request.client else "unknown"
    now = time.time()
    bucket_key = (client, path)
    limit = RATE_LIMIT_DEFAULT
    if path in {"/auth/login", "/auth/register"}:
        limit = RATE_LIMIT_AUTH_WRITE
    elif path.startswith("/auth/"):
        limit = RATE_LIMIT_AUTH
    bucket = [ts for ts in _rate_buckets.get(bucket_key, []) if now - ts < RATE_LIMIT_WINDOW]
    if len(bucket) >= limit:
        return JSONResponse({"detail": "Too many requests"}, status_code=429)
    bucket.append(now)
    _rate_buckets[bucket_key] = bucket

    start = time.perf_counter()
    response = await call_next(request)
    logger.info(
        "request path=%s method=%s status=%s elapsed_ms=%s",
        path,
        request.method,
        response.status_code,
        round((time.perf_counter() - start) * 1000, 2),
    )
    return response

# -----------------------------
# Serve frontend (static files + pages)
# -----------------------------
BASE_DIR = Path(__file__).resolve()

CANDIDATES = [
    BASE_DIR.parents[2] / "frontend",
    BASE_DIR.parents[1] / "frontend",
    BASE_DIR.parent / "frontend",
]
FRONTEND_DIR = next((p for p in CANDIDATES if p.exists()), None)

if not FRONTEND_DIR:
    raise RuntimeError("Frontend folder not found. Expected a 'frontend' directory near the project root.")

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/sw.js", include_in_schema=False)
def serve_sw():
    from fastapi.responses import FileResponse
    return FileResponse(str(FRONTEND_DIR / "sw.js"), media_type="application/javascript")

@app.get("/", include_in_schema=False)
def serve_index():
    from .db import SessionLocal
    db = SessionLocal()
    try:
        theme = (
            db.query(models.Week.theme)
            .filter(models.Week.is_open == True)
            .order_by(models.Week.id.desc())
            .limit(1)
            .scalar()
        )
        if theme == "portugal":
            return FileResponse(str(FRONTEND_DIR / "portugal.html"))
    finally:
        db.close()
    return FileResponse(str(FRONTEND_DIR / "index.html"))

@app.get("/preview", include_in_schema=False)
def serve_theme_preview():
    """Always serve the neutral homepage so an active special theme cannot mask previews."""
    return FileResponse(str(FRONTEND_DIR / "index.html"))

@app.get("/portugal", include_in_schema=False)
def serve_portugal():
    return FileResponse(str(FRONTEND_DIR / "portugal.html"))

@app.get("/admin", include_in_schema=False)
def serve_admin():
    return FileResponse(str(FRONTEND_DIR / "admin.html"))

@app.get("/archive", include_in_schema=False)
def serve_archive():
    return FileResponse(str(FRONTEND_DIR / "archive.html"))

@app.get("/como-funciona", include_in_schema=False)
def serve_rules():
    return FileResponse(str(FRONTEND_DIR / "como-funciona.html"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv()

# ----------------------
# Utilities
# ----------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ----------------------
# Auth (username/password + DB sessions)
# ----------------------

PBKDF2_ITERS = 200_000
SESSION_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 dias


def normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def hash_password(password: str) -> str:
    if not password or len(password) < 4:
        raise HTTPException(status_code=400, detail="Password too short (min 4)")

    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERS)
    return (
        f"pbkdf2_sha256${PBKDF2_ITERS}$"
        f"{base64.b64encode(salt).decode()}$"
        f"{base64.b64encode(dk).decode()}"
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters_s, salt_b64, dk_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iters = int(iters_s)
        salt = base64.b64decode(salt_b64.encode())
        dk_expected = base64.b64decode(dk_b64.encode())
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)
        return hmac.compare_digest(dk, dk_expected)
    except Exception:
        return False


def create_session(db: Session, user: models.User) -> str:
    token = secrets.token_urlsafe(32)
    now = int(time.time())

    s = models.Session(
        user_id=user.id,
        token=token,
        created_at=now,
        expires_at=now + SESSION_TTL_SECONDS,
    )
    db.add(s)
    db.commit()
    return token


def get_current_user(db: Session, authorization: str | None) -> models.User:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header")

    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Invalid token")

    now = int(time.time())

    sess = db.query(models.Session).filter(models.Session.token == token).first()
    if not sess:
        raise HTTPException(status_code=401, detail="Invalid session")

    if sess.expires_at <= now:
        db.delete(sess)
        db.commit()
        raise HTTPException(status_code=401, detail="Session expired")

    user = db.query(models.User).filter(models.User.id == sess.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def require_login(db: Session, authorization: str | None) -> models.User:
    return get_current_user(db, authorization)


def require_admin_user(db: Session, authorization: str | None) -> models.User:
    u = get_current_user(db, authorization)
    if not getattr(u, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin only")
    return u


# ----------------------
# TMDB matching (lightweight)
# ----------------------

def tmdb_search_candidates(query: str, year: int | None = None, limit: int = 8):
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        return []

    params = {"api_key": api_key, "query": query}
    if year:
        params["year"] = year

    try:
        r = requests.get(
            "https://api.themoviedb.org/3/search/movie",
            params=params,
            timeout=6,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        results = data.get("results") or []
        return results[:limit]
    except Exception:
        return []


def pick_best_tmdb_match(submitted_title: str, submitted_year: int | None = None):
    title = (submitted_title or "").strip()
    if not title:
        return {
            "tmdb_id": None,
            "canonical_title": submitted_title,
            "canonical_year": submitted_year,
            "poster_url": None,
            "match_score": None,
            "needs_review": True,
        }

    candidates = tmdb_search_candidates(title, submitted_year, limit=8)

    if len(candidates) < 2:
        candidates = tmdb_search_candidates(title, None, limit=8)

    if not candidates:
        return {
            "tmdb_id": None,
            "canonical_title": submitted_title,
            "canonical_year": submitted_year,
            "poster_url": None,
            "match_score": None,
            "needs_review": True,
        }

    scored = []
    for c in candidates:
        cand_title = (c.get("title") or "").strip()
        cand_orig = (c.get("original_title") or "").strip()

        s1 = fuzz.token_set_ratio(title.lower(), cand_title.lower())
        s2 = fuzz.token_set_ratio(title.lower(), cand_orig.lower()) if cand_orig else 0
        fuzzy_score = max(s1, s2) / 100.0

        release = (c.get("release_date") or "").strip()
        cand_year = int(release[:4]) if len(release) >= 4 and release[:4].isdigit() else None

        year_adj = 0.0
        if submitted_year and cand_year:
            diff = abs(int(submitted_year) - int(cand_year))
            if diff == 0:
                year_adj = 0.06
            elif diff == 1:
                year_adj = 0.03
            elif diff <= 2:
                year_adj = 0.01
            else:
                year_adj = -0.05

        score = fuzzy_score + year_adj
        scored.append((score, c, cand_year))

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best, best_year = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0

    best_score = max(0.0, min(1.0, float(best_score)))
    second_score = max(0.0, min(1.0, float(second_score)))

    if best_score >= 0.92:
        needs_review = False
    else:
        needs_review = not (best_score >= 0.78 and (best_score - second_score) >= 0.06)

    poster_path = best.get("poster_path")
    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

    canonical_title = (best.get("title") or submitted_title).strip()
    canonical_year = best_year if best_year is not None else submitted_year
    tmdb_id = best.get("id")

    return {
        "tmdb_id": int(tmdb_id) if tmdb_id is not None else None,
        "canonical_title": canonical_title,
        "canonical_year": int(canonical_year) if canonical_year is not None else None,
        "poster_url": poster_url,
        "match_score": best_score,
        "needs_review": bool(needs_review),
    }


# ----------------------
# Payload
# ----------------------

def week_payload(db: Session, week: models.Week, include_submitter: bool = False):
    # ── FIX: single GROUP BY query instead of loading all votes into memory
    counts = dict(
        db.query(models.Vote.film_id, func.count(models.Vote.id))
          .filter(models.Vote.week_id == week.id)
          .group_by(models.Vote.film_id)
          .all()
    )

    films = []
    for f in week.films:
        film_obj = {
            "id": f.id,
            "title": f.title,
            "year": f.year,
            "director": f.director,
            "votes": int(counts.get(f.id, 0)),
            "poster_url": f.poster_url,
            "tmdb_id": f.tmdb_id,
        }

        if include_submitter:
            film_obj["submitter_key"] = f.submitter_key
            film_obj["submitted_title"] = f.submitted_title
            film_obj["submitted_year"] = f.submitted_year
            film_obj["tmdb_id"] = f.tmdb_id
            film_obj["match_score"] = f.match_score
            film_obj["needs_review"] = f.needs_review

        films.append(film_obj)

    return {
        "id": week.id,
        "title": week.title,
        "is_open": week.is_open,
        "winner_film_id": week.winner_film_id,
        "films": films,
        "is_ready": week.is_ready,
        "theme": week.theme,
    }


# ----------------------
# Public endpoints
# ----------------------

@app.get("/health")
def health():
    return {"ok": True}


# ---- Auth endpoints ----

import re as _re

USERNAME_RE = _re.compile(r'^[a-zA-Z0-9_.-]{3,32}$')

def validate_username(username: str):
    if not username:
        raise HTTPException(400, "Username obrigatório.")
    if len(username) < 3:
        raise HTTPException(400, "Username demasiado curto (mín. 3 caracteres).")
    if len(username) > 32:
        raise HTTPException(400, "Username demasiado longo (máx. 32 caracteres).")
    if not USERNAME_RE.match(username):
        raise HTTPException(400, "Username só pode ter letras, números, _, . e - (sem espaços ou ~).")


@app.post("/auth/register")
def register(body: dict = Body(...), db: Session = Depends(get_db)):
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""

    validate_username(username)

    exists = db.query(models.User).filter(
        func.lower(models.User.username) == username.lower()
    ).first()
    if exists:
        raise HTTPException(status_code=409, detail="Username já existe.")

    u = models.User(username=username, password_hash=hash_password(password))
    db.add(u)
    db.commit()
    db.refresh(u)

    token = create_session(db, u)
    return {"user": {"id": u.id, "username": u.username}, "token": token}


@app.patch("/auth/username")
def change_username(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    user = get_current_user(db, authorization)
    new_username = (body.get("username") or "").strip()

    validate_username(new_username)

    exists = db.query(models.User).filter(
        func.lower(models.User.username) == new_username.lower(),
        models.User.id != user.id,
    ).first()
    if exists:
        raise HTTPException(409, "Username já existe.")

    user.username = new_username
    db.commit()
    db.refresh(user)
    return {"ok": True, "username": user.username}



@app.post("/auth/login")
def login(body: dict = Body(...), db: Session = Depends(get_db)):
    username = normalize_username(body.get("username"))
    password = body.get("password") or ""

    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")

    u = db.query(models.User).filter(models.User.username == username).first()
    if not u or not verify_password(password, u.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")

    token = create_session(db, u)
    return {"user": {"id": u.id, "username": u.username}, "token": token}


@app.get("/auth/me")
def me(db: Session = Depends(get_db), authorization: str | None = Header(None)):
    u = get_current_user(db, authorization)
    effective_avatar = u.avatar_url or u.letterboxd_avatar_url
    return {
        "id": u.id,
        "username": u.username,
        "is_admin": bool(getattr(u, "is_admin", False)),
        "letterboxd_username": u.letterboxd_username,
        "letterboxd_avatar_url": u.letterboxd_avatar_url,
        "letterboxd_synced_at": u.letterboxd_synced_at,
        "avatar_url": effective_avatar,
    }


@app.patch("/auth/avatar")
def set_avatar(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    user = get_current_user(db, authorization)
    avatar = (body.get("avatar_url") or "").strip()

    if avatar and not (avatar.startswith("https://") or avatar.startswith("http://") or avatar.startswith("data:image/")):
        raise HTTPException(400, "avatar_url must be a valid URL or base64 data URI")

    if avatar.startswith("data:image/") and len(avatar) > 2_500_000:
        raise HTTPException(400, "Image too large (max ~2MB)")

    user.avatar_url = avatar or None
    db.commit()
    db.refresh(user)
    effective_avatar = user.avatar_url or user.letterboxd_avatar_url
    return {"ok": True, "avatar_url": effective_avatar}


@app.post("/auth/logout")
def logout(db: Session = Depends(get_db), authorization: str | None = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        return {"ok": True}

    token = authorization[7:].strip()
    sess = db.query(models.Session).filter(models.Session.token == token).first()
    if sess:
        db.delete(sess)
        db.commit()
    return {"ok": True}


@app.post("/auth/logout-all")
def logout_all_sessions(db: Session = Depends(get_db), authorization: str | None = Header(None)):
    user = get_current_user(db, authorization)
    deleted = (
        db.query(models.Session)
        .filter(models.Session.user_id == user.id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"ok": True, "deleted": int(deleted or 0)}


# ---- Weeks endpoints ----

@app.get("/weeks/current")
def current_week(db: Session = Depends(get_db)):
    week = (
        db.query(models.Week)
        .filter(models.Week.is_special == False)
        .options(
            load_only(models.Week.id, models.Week.title, models.Week.is_open, models.Week.is_ready, models.Week.winner_film_id, models.Week.theme),
            selectinload(models.Week.films).load_only(
                models.Film.id,
                models.Film.week_id,
                models.Film.title,
                models.Film.year,
                models.Film.director,
                models.Film.poster_url,
                models.Film.tmdb_id,
            ),
        )
        .order_by(models.Week.id.desc())
        .first()
    )
    if not week:
        raise HTTPException(404, "No week created yet")
    payload = week_payload(db, week, include_submitter=False)
    log_db_response("/weeks/current", "current week with films and vote counts", len(payload.get("films", [])), payload)
    return payload


@app.get("/weeks")
def list_weeks(
    page: int = Query(1, ge=1),
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    db: Session = Depends(get_db),
):
    limit = clamp_limit(limit)
    offset = (page - 1) * limit
    cache_key = f"weeks:{page}:{limit}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    weeks = (
        db.query(models.Week)
        .filter(models.Week.is_special == False)
        .options(
            load_only(models.Week.id, models.Week.title, models.Week.is_open, models.Week.is_ready, models.Week.winner_film_id, models.Week.theme),
            selectinload(models.Week.films).load_only(
                models.Film.id,
                models.Film.week_id,
                models.Film.title,
                models.Film.year,
                models.Film.director,
                models.Film.poster_url,
                models.Film.tmdb_id,
            ),
        )
        .order_by(models.Week.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    payload = [week_payload(db, w, include_submitter=False) for w in weeks]
    log_db_response("/weeks", "paginated archive weeks", len(payload), payload)
    return cache_set(cache_key, payload, ttl=30)


@app.get("/weeks/cinema")
def list_cinema_weeks(
    page: int = Query(1, ge=1),
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    db: Session = Depends(get_db),
):
    limit = clamp_limit(limit)
    offset = (page - 1) * limit
    cache_key = f"weeks:cinema:{page}:{limit}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    weeks = (
        db.query(models.Week)
        .filter(models.Week.is_special == True)
        .options(
            load_only(models.Week.id, models.Week.title, models.Week.is_open, models.Week.is_ready, models.Week.winner_film_id, models.Week.theme),
            selectinload(models.Week.films).load_only(
                models.Film.id,
                models.Film.week_id,
                models.Film.title,
                models.Film.year,
                models.Film.director,
                models.Film.poster_url,
                models.Film.tmdb_id,
            ),
        )
        .order_by(models.Week.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    payload = [week_payload(db, w, include_submitter=False) for w in weeks]
    log_db_response("/weeks/cinema", "paginated cinema weeks", len(payload), payload)
    return cache_set(cache_key, payload, ttl=60)


@app.get("/weeks/{week_id}")
def get_week(week_id: int, db: Session = Depends(get_db)):
    week = (
        db.query(models.Week)
        .filter(models.Week.id == week_id)
        .options(
            load_only(models.Week.id, models.Week.title, models.Week.is_open, models.Week.is_ready, models.Week.winner_film_id, models.Week.theme),
            selectinload(models.Week.films).load_only(
                models.Film.id,
                models.Film.week_id,
                models.Film.title,
                models.Film.year,
                models.Film.director,
                models.Film.poster_url,
                models.Film.tmdb_id,
            ),
        )
        .first()
    )
    if not week:
        raise HTTPException(404, "Week not found")
    return week_payload(db, week, include_submitter=False)


@app.post("/weeks/{week_id}/submissions")
def submit_film(
    week_id: int,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    user = get_current_user(db, authorization)
    submitter_key = str(user.id)

    week = db.query(models.Week).filter(models.Week.id == week_id).first()
    if not week:
        raise HTTPException(status_code=404, detail="Week not found")
    if not week.is_open:
        raise HTTPException(status_code=400, detail="Week is closed")

    already = (
        db.query(models.Film)
          .filter(models.Film.week_id == week_id, models.Film.submitter_key == submitter_key)
          .first()
    )
    if already:
        raise HTTPException(status_code=409, detail="You already submitted a film this week")

    title = (body.get("title") or "").strip()
    year = body.get("year")
    director = body.get("director")

    if not title:
        raise HTTPException(status_code=400, detail="title required")

    submitted_title = title
    submitted_year = year
    manual_poster_url = body.get("poster_url")

    if manual_poster_url:
        canonical_title = submitted_title
        canonical_year = submitted_year
        poster_url = manual_poster_url
        tmdb_id = None
        match_score = None
        needs_review = False
    else:
        match = pick_best_tmdb_match(submitted_title, submitted_year)
        canonical_title = match["canonical_title"]
        canonical_year = match["canonical_year"]
        poster_url = match["poster_url"]
        tmdb_id = match["tmdb_id"]
        match_score = match["match_score"]
        needs_review = match["needs_review"]

    film = models.Film(
        week_id=week_id,
        title=canonical_title,
        year=canonical_year,
        director=director,
        poster_url=poster_url,
        submitter_key=submitter_key,
        submitted_title=submitted_title,
        submitted_year=submitted_year,
        tmdb_id=tmdb_id,
        match_score=match_score,
        needs_review=needs_review,
    )

    db.add(film)
    db.commit()
    db.refresh(week)
    return week_payload(db, week, include_submitter=False)


from .db import DATABASE_URL

@app.get("/debug/whoami")
def debug_whoami(db: Session = Depends(get_db), authorization: str | None = Header(default=None)):
    token = None
    user = None
    is_admin = None
    try:
        token = authorization[7:].strip() if (authorization and authorization.lower().startswith("bearer ")) else None
        user = get_current_user(db, authorization)
        is_admin = bool(getattr(user, "is_admin", False))
    except Exception as e:
        return {
            "database_url": DATABASE_URL,
            "authorization_present": bool(authorization),
            "token_prefix": (token[:8] if token else None),
            "error": str(e),
        }

    return {
        "database_url": DATABASE_URL,
        "authorization_present": bool(authorization),
        "token_prefix": (token[:8] if token else None),
        "user_id": user.id,
        "username": user.username,
        "is_admin": is_admin,
    }

@app.post("/weeks/{week_id}/vote")
def vote(
    week_id: int,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    voter_key = None
    if authorization:
        user = get_current_user(db, authorization)
        voter_key = str(user.id)
    else:
        voter_key = (body.get("voter_key") or "").strip()

    film_id = body.get("film_id")

    if not voter_key or film_id is None:
        raise HTTPException(status_code=400, detail="film_id required (and auth)")

    week = db.query(models.Week).filter(models.Week.id == week_id).first()
    if not week:
        raise HTTPException(status_code=404, detail="Week not found")
    if not week.is_open:
        raise HTTPException(status_code=400, detail="Voting is closed")
    if not week.is_ready:
        raise HTTPException(status_code=400, detail="Voting not started yet")

    film = db.query(models.Film).filter(
        models.Film.id == int(film_id),
        models.Film.week_id == week_id
    ).first()
    if not film:
        raise HTTPException(status_code=404, detail="Film not found")

    submitter_keys = {
        k for (k,) in db.query(models.Film.submitter_key)
                        .filter(models.Film.week_id == week_id)
                        .distinct()
                        .all()
    }
    if voter_key not in submitter_keys:
        raise HTTPException(status_code=403, detail="Only submitters can vote this week")

    if film.submitter_key == voter_key:
        raise HTTPException(status_code=403, detail="You cannot vote on your own film")

    v = models.Vote(week_id=week_id, film_id=int(film_id), voter_key=voter_key)
    db.add(v)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="You already voted this week")

    db.refresh(week)
    return week_payload(db, week, include_submitter=False)


# ----------------------
# Admin endpoints
# ----------------------

@app.get("/admin/weeks/current")
def admin_current_week(
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    require_admin_user(db, authorization)
    week = (
        db.query(models.Week)
        .filter(models.Week.is_special == False)
        .options(
            load_only(models.Week.id, models.Week.title, models.Week.is_open, models.Week.is_ready, models.Week.winner_film_id, models.Week.theme),
            selectinload(models.Week.films).load_only(
                models.Film.id,
                models.Film.week_id,
                models.Film.title,
                models.Film.year,
                models.Film.director,
                models.Film.poster_url,
                models.Film.submitter_key,
                models.Film.submitted_title,
                models.Film.submitted_year,
                models.Film.tmdb_id,
                models.Film.match_score,
                models.Film.needs_review,
            ),
        )
        .order_by(models.Week.id.desc())
        .first()
    )
    if not week:
        raise HTTPException(404, "No week created yet")
    return week_payload(db, week, include_submitter=True)


@app.get("/admin/weeks")
def admin_list_weeks(
    page: int = Query(1, ge=1),
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    require_admin_user(db, authorization)
    limit = clamp_limit(limit)
    offset = (page - 1) * limit
    weeks = (
        db.query(models.Week)
        .filter(models.Week.is_special == False)
        .options(
            load_only(models.Week.id, models.Week.title, models.Week.is_open, models.Week.is_ready, models.Week.winner_film_id, models.Week.theme),
            selectinload(models.Week.films).load_only(
                models.Film.id,
                models.Film.week_id,
                models.Film.title,
                models.Film.year,
                models.Film.director,
                models.Film.poster_url,
                models.Film.submitter_key,
                models.Film.submitted_title,
                models.Film.submitted_year,
                models.Film.tmdb_id,
                models.Film.match_score,
                models.Film.needs_review,
            ),
        )
        .order_by(models.Week.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    payload = [week_payload(db, w, include_submitter=True) for w in weeks]
    log_db_response("/admin/weeks", "paginated admin weeks", len(payload), payload)
    return payload


@app.post("/admin/weeks")
def create_week(
    body: dict,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    require_admin_user(db, authorization)

    title = (body.get("title") or "").strip()
    theme = (body.get("theme") or "").strip() or None
    if not title:
        raise HTTPException(400, "title required")

    week = models.Week(title=title, is_open=True, theme=theme)
    db.add(week)
    db.commit()
    db.refresh(week)
    return week_payload(db, week, include_submitter=True)


@app.post("/admin/weeks/{week_id}/films")
def add_film(
    week_id: int,
    body: dict,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    require_admin_user(db, authorization)

    week = db.query(models.Week).filter(models.Week.id == week_id).first()
    if not week:
        raise HTTPException(404, "Week not found")

    title = (body.get("title") or "").strip()
    submitter_key = (body.get("submitter_key") or "").strip()
    year = body.get("year")
    director = body.get("director")

    if not title:
        raise HTTPException(400, "title required")
    if not submitter_key:
        raise HTTPException(400, "submitter_key required")

    submitted_title = title
    submitted_year = year

    manual_poster_url = body.get("poster_url")

    if manual_poster_url:
        canonical_title = submitted_title
        canonical_year = submitted_year
        poster_url = manual_poster_url
        tmdb_id = None
        match_score = None
        needs_review = False
    else:
        match = pick_best_tmdb_match(submitted_title, submitted_year)
        canonical_title = match["canonical_title"]
        canonical_year = match["canonical_year"]
        poster_url = match["poster_url"]
        tmdb_id = match["tmdb_id"]
        match_score = match["match_score"]
        needs_review = match["needs_review"]

    film = models.Film(
        week_id=week_id,
        title=canonical_title,
        year=canonical_year,
        director=director,
        poster_url=poster_url,
        submitter_key=submitter_key,
        submitted_title=submitted_title,
        submitted_year=submitted_year,
        tmdb_id=tmdb_id,
        match_score=match_score,
        needs_review=needs_review,
    )

    db.add(film)
    db.commit()
    db.refresh(week)
    return week_payload(db, week, include_submitter=True)


@app.delete("/admin/films/{film_id}")
def delete_film(
    film_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    require_admin_user(db, authorization)

    film = db.query(models.Film).filter(models.Film.id == film_id).first()
    if not film:
        raise HTTPException(404, "Film not found")

    week = db.query(models.Week).filter(models.Week.id == film.week_id).first()
    if week and week.winner_film_id == film.id:
        week.winner_film_id = None

    db.delete(film)
    db.commit()

    if not week:
        return {"deleted_film_id": film_id}
    db.refresh(week)
    return week_payload(db, week, include_submitter=True)


@app.patch("/admin/films/{film_id}")
def admin_update_film(
    film_id: int,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    require_admin_user(db, authorization)

    film = db.query(models.Film).filter(models.Film.id == film_id).first()
    if not film:
        raise HTTPException(404, "Film not found")

    if "title" in body and body["title"] is not None:
        film.title = str(body["title"]).strip() or film.title

    if "year" in body:
        film.year = body["year"]

    if "director" in body:
        film.director = body["director"]

    if "poster_url" in body:
        film.poster_url = body["poster_url"]

    if "tmdb_id" in body:
        film.tmdb_id = body["tmdb_id"]

    reviewed = body.get("reviewed", True)
    if reviewed:
        film.needs_review = False
        film.match_score = 1.0 if film.match_score is None else film.match_score

    db.commit()
    db.refresh(film)

    return {
        "id": film.id,
        "week_id": film.week_id,
        "title": film.title,
        "year": film.year,
        "director": film.director,
        "poster_url": film.poster_url,
        "submitter_key": film.submitter_key,
        "submitted_title": film.submitted_title,
        "submitted_year": film.submitted_year,
        "tmdb_id": film.tmdb_id,
        "match_score": film.match_score,
        "needs_review": film.needs_review,
    }


@app.delete("/admin/weeks/{week_id}")
def delete_week(
    week_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    require_admin_user(db, authorization)

    week = db.query(models.Week).filter(models.Week.id == week_id).first()
    if not week:
        raise HTTPException(404, "Week not found")

    db.delete(week)
    db.commit()
    return {"deleted_week_id": week_id}


@app.post("/admin/weeks/{week_id}/close")
def close_week(
    week_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    require_admin_user(db, authorization)

    week = db.query(models.Week).filter(models.Week.id == week_id).first()
    if not week:
        raise HTTPException(404, "Week not found")

    week.is_open = False

    rows = (
        db.query(models.Vote.film_id, func.count(models.Vote.id).label("c"))
          .filter(models.Vote.week_id == week_id)
          .group_by(models.Vote.film_id)
          .order_by(func.count(models.Vote.id).desc())
          .all()
    )

    if not rows:
        week.winner_film_id = None
    else:
        top_count = int(rows[0][1])
        tied = [int(fid) for (fid, c) in rows if int(c) == top_count]
        week.winner_film_id = tied[0] if len(tied) == 1 else None

    db.commit()
    db.refresh(week)
    return week_payload(db, week, include_submitter=True)


@app.post("/admin/weeks/{week_id}/open")
def open_week(
    week_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    require_admin_user(db, authorization)

    week = db.query(models.Week).filter(models.Week.id == week_id).first()
    if not week:
        raise HTTPException(404, "Week not found")

    week.is_open = True
    db.commit()
    db.refresh(week)
    return week_payload(db, week, include_submitter=True)


@app.post("/admin/weeks/{week_id}/winner")
def set_winner(
    week_id: int,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    require_admin_user(db, authorization)

    film_id = body.get("film_id")
    if film_id is None:
        raise HTTPException(status_code=400, detail="film_id required")

    week = db.query(models.Week).filter(models.Week.id == week_id).first()
    if not week:
        raise HTTPException(404, "Week not found")

    film = db.query(models.Film).filter(
        models.Film.id == int(film_id),
        models.Film.week_id == week_id
    ).first()
    if not film:
        raise HTTPException(404, "Film not found for this week")

    week.winner_film_id = int(film_id)
    db.commit()
    db.refresh(week)
    return week_payload(db, week, include_submitter=True)


@app.get("/admin/films/needs-review")
def films_needing_review(
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    require_admin_user(db, authorization)
    limit = clamp_limit(limit)

    films = (
        db.query(models.Film)
          .filter(models.Film.needs_review == True)  # noqa: E712
          .order_by(models.Film.id.desc())
          .limit(limit)
          .all()
    )

    return [
        {
            "id": f.id,
            "week_id": f.week_id,
            "title": f.title,
            "year": f.year,
            "director": f.director,
            "poster_url": f.poster_url,
            "submitter_key": f.submitter_key,
            "submitted_title": f.submitted_title,
            "submitted_year": f.submitted_year,
            "tmdb_id": f.tmdb_id,
            "match_score": f.match_score,
            "needs_review": f.needs_review,
        }
        for f in films
    ]


@app.post("/admin/weeks/{week_id}/start-voting")
def start_voting(
    week_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    require_admin_user(db, authorization)

    week = db.query(models.Week).filter(models.Week.id == week_id).first()
    if not week:
        raise HTTPException(404, "Week not found")

    week.is_ready = True
    db.commit()
    db.refresh(week)
    return week_payload(db, week, include_submitter=True)


@app.post("/admin/weeks/{week_id}/stop-voting")
def stop_voting(
    week_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    require_admin_user(db, authorization)

    week = db.query(models.Week).filter(models.Week.id == week_id).first()
    if not week:
        raise HTTPException(404, "Week not found")

    week.is_ready = False
    db.commit()
    db.refresh(week)
    return week_payload(db, week, include_submitter=True)


@app.post("/admin/films/{film_id}/rematch")
def admin_rematch_film(
    film_id: int,
    body: dict = Body(default={}),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    require_admin_user(db, authorization)

    film = db.query(models.Film).filter(models.Film.id == film_id).first()
    if not film:
        raise HTTPException(404, "Film not found")

    q_title = (film.submitted_title or film.title or "").strip()
    q_year = film.submitted_year or film.year

    override_title = (body.get("title") or "").strip()
    override_year = body.get("year")

    if override_title:
        q_title = override_title
    if override_year is not None:
        q_year = override_year

    match = pick_best_tmdb_match(q_title, q_year)

    if override_title:
        film.submitted_title = override_title
    if override_year is not None:
        film.submitted_year = override_year

    if match["tmdb_id"] is None:
        film.needs_review = True
        film.match_score = None
        film.tmdb_id = None
    else:
        film.title = match["canonical_title"]
        film.year = match["canonical_year"]
        film.poster_url = match["poster_url"]
        film.tmdb_id = match["tmdb_id"]
        film.match_score = match["match_score"]
        film.needs_review = match["needs_review"]

    db.commit()

    week = db.query(models.Week).filter(models.Week.id == film.week_id).first()
    if not week:
        return {"ok": True, "film_id": film_id}
    db.refresh(week)
    return week_payload(db, week, include_submitter=True)

# ─────────────────────────────────────────────
# Letterboxd RSS sync
# ─────────────────────────────────────────────

_STAR_MAP = {"★": 1.0, "½": 0.5}

def _parse_lb_rating(text: str) -> float | None:
    if not text:
        return None
    score = sum(_STAR_MAP.get(ch, 0.0) for ch in text)
    return score if score > 0 else None


def _parse_lb_date(date_str: str) -> int | None:
    if not date_str:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", date_str.strip())
    if m:
        import calendar, datetime
        d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return calendar.timegm(d.timetuple())
    return None


def _tmdb_id_from_lb_url(url: str) -> int | None:
    return None


def fetch_and_sync_letterboxd(db: Session, user: models.User) -> dict:
    lb_username = (user.letterboxd_username or "").strip()
    if not lb_username:
        return {"synced": 0, "avatar_url": None, "error": "no letterboxd username set"}

    rss_url = f"https://letterboxd.com/{lb_username}/rss/"
    try:
        resp = requests.get(rss_url, timeout=10, headers={"User-Agent": "ClubeDecinemaSyncBot/1.0"})
        if resp.status_code == 404:
            return {"synced": 0, "avatar_url": None, "error": "letterboxd user not found"}
        if resp.status_code != 200:
            return {"synced": 0, "avatar_url": None, "error": f"RSS returned {resp.status_code}"}
    except Exception as exc:
        return {"synced": 0, "avatar_url": None, "error": str(exc)}

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        return {"synced": 0, "avatar_url": None, "error": f"XML parse error: {exc}"}

    ns = {
        "lb": "https://letterboxd.com",
        "tmdb": "https://www.themoviedb.org/",
    }

    avatar_url = None
    try:
        profile_resp = requests.get(
            f"https://letterboxd.com/{lb_username}/",
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ClubeDecinemasBot/1.0)"}
        )
        if profile_resp.status_code == 200:
            html = profile_resp.text
            og_match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            if og_match:
                candidate = og_match.group(1)
                if "a.ltrbxd.com" in candidate and "/userpics/" in candidate:
                    avatar_url = candidate
            if not avatar_url:
                av_match = re.search(r'<img[^>]+class="[^"]*avatar[^"]*"[^>]+src="([^"]+)"', html)
                if av_match:
                    avatar_url = av_match.group(1)
            if not avatar_url:
                up_match = re.search(r'(https://a\.ltrbxd\.com/resized/avatar[^"\']+)', html)
                if not up_match:
                    up_match = re.search(r'(https://a\.ltrbxd\.com/[^"\']*userpic[^"\']+)', html)
                if up_match:
                    avatar_url = up_match.group(1)
    except Exception:
        pass

    items = root.findall(".//item")
    synced = 0
    seen_keys = set()

    # ── FIX: pre-load all existing entries for this user in one query instead
    # of querying per-item inside the loop
    existing_by_tmdb: dict[int, models.LetterboxdEntry] = {}
    existing_by_title: dict[tuple, models.LetterboxdEntry] = {}
    all_existing = (
        db.query(models.LetterboxdEntry)
        .filter(models.LetterboxdEntry.user_id == user.id)
        .order_by(models.LetterboxdEntry.watched_date.desc().nullslast())
        .limit(500)
        .all()
    )
    for e in all_existing:
        if e.tmdb_id is not None:
            existing_by_tmdb[e.tmdb_id] = e
        else:
            existing_by_title[(e.film_title.lower(), e.film_year)] = e

    # ── FIX: pre-load TMDB IDs from our films table in one query —
    # avoids one DB hit per RSS item
    tmdb_lookup: dict[tuple, int] = {}
    film_rows = (
        db.query(models.Film.title, models.Film.year, models.Film.tmdb_id)
        .filter(models.Film.tmdb_id.isnot(None))
        .limit(1000)
        .all()
    )
    for title_val, year_val, tmdb_id_val in film_rows:
        tmdb_lookup[(title_val.lower(), year_val)] = tmdb_id_val

    for item in items:
        watched_date_el = item.find("lb:watchedDate", ns)
        if watched_date_el is None:
            continue

        title_el = item.find("lb:filmTitle", ns)
        year_el = item.find("lb:filmYear", ns)
        rating_el = item.find("lb:memberRating", ns)
        rewatch_el = item.find("lb:rewatch", ns)
        link_el = item.find("link")

        film_title = (title_el.text or "").strip() if title_el is not None else ""
        if not film_title:
            continue

        film_year_raw = (year_el.text or "").strip() if year_el is not None else ""
        film_year = int(film_year_raw) if film_year_raw.isdigit() else None

        watched_date_raw = (watched_date_el.text or "").strip()
        watched_date = _parse_lb_date(watched_date_raw)

        dedup_key = f"{film_title.lower()}|{film_year}|{watched_date_raw}"
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        rating_raw = (rating_el.text or "").strip() if rating_el is not None else ""
        try:
            rating = float(rating_raw) if rating_raw else None
        except ValueError:
            rating = _parse_lb_rating(rating_raw)

        is_rewatch = (rewatch_el is not None and (rewatch_el.text or "").strip().lower() == "yes")
        lb_url = (link_el.text or "").strip() if link_el is not None else None

        # ── FIX: dict lookup instead of per-item DB query
        tmdb_id = tmdb_lookup.get((film_title.lower(), film_year))

        existing = None
        if tmdb_id:
            existing = existing_by_tmdb.get(tmdb_id)
        else:
            existing = existing_by_title.get((film_title.lower(), film_year))

        if existing:
            if watched_date and (existing.watched_date is None or watched_date > existing.watched_date):
                existing.watched_date = watched_date
                existing.rating = rating
                existing.is_rewatch = is_rewatch
                existing.letterboxd_url = lb_url
        else:
            entry = models.LetterboxdEntry(
                user_id=user.id,
                tmdb_id=tmdb_id,
                film_title=film_title,
                film_year=film_year,
                rating=rating,
                watched_date=watched_date,
                letterboxd_url=lb_url,
                is_rewatch=is_rewatch,
            )
            db.add(entry)
            # Track newly added entries to avoid re-inserting within same sync
            if tmdb_id:
                existing_by_tmdb[tmdb_id] = entry
            else:
                existing_by_title[(film_title.lower(), film_year)] = entry

        synced += 1

    if avatar_url:
        user.letterboxd_avatar_url = avatar_url
    user.letterboxd_synced_at = int(time.time())

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        return {"synced": 0, "avatar_url": avatar_url, "error": f"DB error: {exc}"}

    return {"synced": synced, "avatar_url": avatar_url, "error": None}


# ─────────────────────────────────────────────
# Letterboxd API endpoints
# ─────────────────────────────────────────────

@app.patch("/auth/letterboxd")
def set_letterboxd_username(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    user = get_current_user(db, authorization)

    if "avatar_url" in body:
        user.letterboxd_avatar_url = (body["avatar_url"] or "").strip() or None
        db.commit()
        db.refresh(user)
        return {
            "ok": True,
            "letterboxd_username": user.letterboxd_username,
            "letterboxd_avatar_url": user.letterboxd_avatar_url,
            "synced": 0,
            "error": None,
        }

    lb_username = (body.get("letterboxd_username") or "").strip()

    if not lb_username:
        user.letterboxd_username = None
        user.letterboxd_avatar_url = None
        user.letterboxd_synced_at = None
        db.commit()
        return {"ok": True, "letterboxd_username": None, "synced": 0}

    user.letterboxd_username = lb_username
    db.commit()

    result = fetch_and_sync_letterboxd(db, user)
    db.refresh(user)

    return {
        "ok": True,
        "letterboxd_username": user.letterboxd_username,
        "letterboxd_avatar_url": user.letterboxd_avatar_url,
        "synced": result["synced"],
        "error": result["error"],
    }


@app.post("/auth/letterboxd/sync")
def sync_letterboxd(
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    user = get_current_user(db, authorization)
    if not user.letterboxd_username:
        raise HTTPException(400, "No Letterboxd username set")

    db.query(models.LetterboxdEntry).filter(
        models.LetterboxdEntry.user_id == user.id
    ).delete()
    db.commit()

    result = fetch_and_sync_letterboxd(db, user)
    db.refresh(user)

    return {
        "ok": True,
        "synced": result["synced"],
        "avatar_url": result.get("avatar_url"),
        "error": result["error"],
        "letterboxd_synced_at": user.letterboxd_synced_at,
    }


@app.post("/admin/letterboxd/sync-all")
def admin_sync_all_letterboxd(
    limit: int = Query(50, ge=1, le=MAX_LIST_LIMIT),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    require_admin_user(db, authorization)
    limit = clamp_limit(limit, default=50)

    users = (
        db.query(models.User)
        .options(
            load_only(
                models.User.id,
                models.User.username,
                models.User.letterboxd_username,
                models.User.letterboxd_avatar_url,
                models.User.letterboxd_synced_at,
            )
        )
        .filter(models.User.letterboxd_username.isnot(None))
        .order_by(models.User.id.asc())
        .limit(limit)
        .all()
    )

    results = []
    synced_total = 0
    errors = 0
    started_at = int(time.time())

    for user in users:
        lb_username = (user.letterboxd_username or "").strip()
        if not lb_username:
            continue

        logger.info(
            "admin_letterboxd_sync user_id=%s username=%s letterboxd=%s started=1",
            user.id,
            user.username,
            lb_username,
        )
        result = fetch_and_sync_letterboxd(db, user)
        synced = int(result.get("synced") or 0)
        error = result.get("error")
        synced_total += synced
        if error:
            errors += 1

        results.append({
            "user_id": user.id,
            "username": user.username,
            "letterboxd_username": lb_username,
            "synced": synced,
            "error": error,
            "letterboxd_synced_at": user.letterboxd_synced_at,
        })

    payload = {
        "ok": errors == 0,
        "attempted": len(results),
        "synced_total": synced_total,
        "errors": errors,
        "started_at": started_at,
        "finished_at": int(time.time()),
        "results": results,
    }
    log_db_response("/admin/letterboxd/sync-all", "admin sync all letterboxd users", len(results), payload)
    return payload


@app.get("/letterboxd/film/{tmdb_id}")
def get_film_letterboxd_data(
    tmdb_id: int,
    limit: int = Query(MAX_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    db: Session = Depends(get_db),
):
    limit = clamp_limit(limit, default=MAX_LIST_LIMIT)
    cache_key = f"letterboxd:film:{tmdb_id}:{limit}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    rows = (
        db.query(
            models.User.id,
            models.User.username,
            models.User.letterboxd_username,
            models.User.avatar_url,
            models.User.letterboxd_avatar_url,
            models.LetterboxdEntry.rating,
            models.LetterboxdEntry.watched_date,
            models.LetterboxdEntry.letterboxd_url,
            models.LetterboxdEntry.is_rewatch,
        )
        .join(models.User, models.LetterboxdEntry.user_id == models.User.id)
        .filter(models.LetterboxdEntry.tmdb_id == tmdb_id)
        .order_by(models.LetterboxdEntry.watched_date.desc().nullslast())
        .limit(limit)
        .all()
    )

    result = []
    for row in rows:
        result.append({
            "user_id": row.id,
            "username": row.username,
            "letterboxd_username": row.letterboxd_username,
            "avatar_url": row.avatar_url or row.letterboxd_avatar_url,
            "rating": row.rating,
            "watched_date": row.watched_date,
            "letterboxd_url": row.letterboxd_url,
            "is_rewatch": row.is_rewatch,
        })

    log_db_response("/letterboxd/film/{tmdb_id}", "letterboxd watchers for film", len(result), result)
    return cache_set(cache_key, result, ttl=60)


@app.get("/letterboxd/members")
def get_all_members_letterboxd(
    limit: int = Query(MAX_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    db: Session = Depends(get_db),
):
    limit = clamp_limit(limit, default=MAX_LIST_LIMIT)
    cache_key = f"letterboxd:members:{limit}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    users = (
        db.query(
            models.User.id,
            models.User.username,
            models.User.avatar_url,
            models.User.letterboxd_avatar_url,
            models.User.letterboxd_username,
            models.User.letterboxd_synced_at,
        )
        .order_by(models.User.username.asc())
        .limit(limit)
        .all()
    )
    payload = [
        {
            "user_id": u.id,
            "username": u.username,
            "avatar_url": u.avatar_url or u.letterboxd_avatar_url,
            "letterboxd_username": u.letterboxd_username,
            "letterboxd_synced_at": u.letterboxd_synced_at,
        }
        for u in users
    ]
    log_db_response("/letterboxd/members", "letterboxd member directory", len(payload), payload)
    return cache_set(cache_key, payload, ttl=60)


# ─────────────────────────────────────────────
# Reactions
# ─────────────────────────────────────────────

ALLOWED_EMOJIS = {"👍", "😐", "67", "🇮🇱"}


@app.get("/films/{film_id}/reactions")
def get_reactions(film_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(models.Reaction.emoji, func.count(models.Reaction.id))
        .filter(models.Reaction.film_id == film_id)
        .group_by(models.Reaction.emoji)
        .all()
    )
    counts = {emoji: int(count) for emoji, count in rows}
    return {"counts": counts, "total": sum(counts.values())}


@app.get("/films/{film_id}/reactions/me")
def get_my_reaction(
    film_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    if not authorization:
        return {"emoji": None}
    try:
        user = get_current_user(db, authorization)
    except Exception:
        return {"emoji": None}
    r = db.query(models.Reaction).filter(
        models.Reaction.film_id == film_id,
        models.Reaction.user_id == user.id,
    ).first()
    return {"emoji": r.emoji if r else None}


@app.post("/films/{film_id}/reactions")
def set_reaction(
    film_id: int,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    user = get_current_user(db, authorization)
    emoji = (body.get("emoji") or "").strip()

    film = db.query(models.Film).filter(models.Film.id == film_id).first()
    if not film:
        raise HTTPException(404, "Film not found")

    if emoji and emoji not in ALLOWED_EMOJIS:
        raise HTTPException(400, f"Emoji not allowed. Use one of: {ALLOWED_EMOJIS}")

    existing = db.query(models.Reaction).filter(
        models.Reaction.film_id == film_id,
        models.Reaction.user_id == user.id,
    ).first()

    if not emoji:
        if existing:
            db.delete(existing)
            db.commit()
        return {"ok": True, "emoji": None}

    if existing:
        if existing.emoji == emoji:
            db.delete(existing)
            db.commit()
            return {"ok": True, "emoji": None}
        existing.emoji = emoji
    else:
        existing = models.Reaction(user_id=user.id, film_id=film_id, emoji=emoji)
        db.add(existing)

    db.commit()
    return {"ok": True, "emoji": emoji}


@app.get("/films/{film_id}/reactions/detail")
def get_reactions_detail(film_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(
            models.Reaction.emoji,
            models.User.username,
            models.User.avatar_url,
            models.User.letterboxd_avatar_url,
        )
        .join(models.User, models.Reaction.user_id == models.User.id)
        .filter(models.Reaction.film_id == film_id)
        .limit(MAX_LIST_LIMIT)
        .all()
    )
    detail = {}
    for row in rows:
        if row.emoji not in detail:
            detail[row.emoji] = []
        detail[row.emoji].append({
            "username": row.username,
            "avatar_url": row.avatar_url or row.letterboxd_avatar_url,
        })
    return detail


# ─────────────────────────────────────────────
# Chat
# ─────────────────────────────────────────────

@app.get("/weeks/{week_id}/chat")
def get_chat(
    week_id: int,
    since_id: int = Query(0, ge=0),
    limit: int = Query(CHAT_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    db: Session = Depends(get_db),
):
    limit = clamp_limit(limit, default=CHAT_LIMIT)
    query = (
        db.query(
            models.ChatMessage.id,
            models.ChatMessage.content,
            models.ChatMessage.created_at,
            models.User.id.label("user_id"),
            models.User.username,
            models.User.avatar_url,
            models.User.letterboxd_avatar_url,
        )
        .join(models.User, models.ChatMessage.user_id == models.User.id)
        .filter(models.ChatMessage.week_id == week_id)
    )
    if since_id:
        query = query.filter(models.ChatMessage.id > since_id).order_by(models.ChatMessage.id.asc())
    else:
        query = query.order_by(models.ChatMessage.id.desc())
    rows = query.limit(limit).all()
    if not since_id:
        rows = list(reversed(rows))
    payload = [
        {
            "id": m.id,
            "content": m.content,
            "created_at": m.created_at,
            "user": {
                "id": m.user_id,
                "username": m.username,
                "avatar_url": m.avatar_url or m.letterboxd_avatar_url,
            },
        }
        for m in rows
    ]
    log_db_response("/weeks/{week_id}/chat", "chat messages incremental" if since_id else "latest chat messages", len(payload), payload)
    return payload


@app.post("/weeks/{week_id}/chat")
def post_chat(
    week_id: int,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    user = get_current_user(db, authorization)

    week = db.query(models.Week).filter(models.Week.id == week_id).first()
    if not week:
        raise HTTPException(404, "Week not found")

    content = (body.get("content") or "").strip()
    if not content:
        raise HTTPException(400, "content required")
    if len(content) > 500:
        raise HTTPException(400, "Message too long (max 500 chars)")

    msg = models.ChatMessage(
        week_id=week_id,
        user_id=user.id,
        content=content,
        created_at=int(time.time()),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    return {
        "id": msg.id,
        "content": msg.content,
        "created_at": msg.created_at,
        "user": {
            "id": user.id,
            "username": user.username,
            "avatar_url": user.avatar_url or user.letterboxd_avatar_url,
        },
    }


@app.delete("/chat/{message_id}")
def delete_chat_message(
    message_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    user = get_current_user(db, authorization)
    msg = db.query(models.ChatMessage).filter(models.ChatMessage.id == message_id).first()
    if not msg:
        raise HTTPException(404, "Message not found")
    if msg.user_id != user.id and not getattr(user, "is_admin", False):
        raise HTTPException(403, "Not allowed")
    db.delete(msg)
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────
# Profile page
# ─────────────────────────────────────────────

@app.get("/search/movies")
def search_movies(q: str, page: int = 1, db: Session = Depends(get_db)):
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        raise HTTPException(500, "TMDB not configured")
    try:
        r = requests.get(
            "https://api.themoviedb.org/3/search/movie",
            params={"api_key": api_key, "query": q, "page": page, "language": "pt-PT"},
            timeout=8
        )
        data = r.json()
        results = []
        for m in data.get("results", [])[:12]:
            poster = m.get("poster_path")
            results.append({
                "id": m["id"],
                "title": m.get("title", ""),
                "year": (m.get("release_date") or "")[:4],
                "poster_url": f"https://image.tmdb.org/t/p/w300{poster}" if poster else None,
                "overview": m.get("overview", ""),
                "rating": m.get("vote_average", 0),
            })
        return {"results": results, "total": data.get("total_results", 0)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/movies/{tmdb_id}/trailer")
def get_movie_trailer(tmdb_id: int):
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        raise HTTPException(500, "TMDB not configured")

    cache_key = f"movie:trailer:{tmdb_id}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    videos = []
    try:
        for language in ("pt-PT", "en-US"):
            r = requests.get(
                f"https://api.themoviedb.org/3/movie/{tmdb_id}/videos",
                params={"api_key": api_key, "language": language},
                timeout=8,
            )
            if r.status_code == 404:
                raise HTTPException(404, "Movie not found")
            r.raise_for_status()
            videos.extend(r.json().get("results", []))
            if videos:
                break
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, str(e))

    youtube = [v for v in videos if (v.get("site") or "").lower() == "youtube" and v.get("key")]
    trailers = [v for v in youtube if (v.get("type") or "").lower() == "trailer"]
    candidates = trailers or youtube
    candidates.sort(key=lambda v: (not bool(v.get("official")), v.get("published_at") or ""), reverse=False)

    if not candidates:
        payload = {"trailer_url": None, "embed_url": None, "youtube_key": None, "name": None}
        return cache_set(cache_key, payload, ttl=60 * 60 * 12)

    chosen = candidates[0]
    key = chosen["key"]
    payload = {
        "trailer_url": f"https://www.youtube.com/watch?v={key}",
        "embed_url": f"https://www.youtube.com/embed/{key}?autoplay=1&rel=0",
        "youtube_key": key,
        "name": chosen.get("name"),
    }
    return cache_set(cache_key, payload, ttl=60 * 60 * 12)


@app.get("/watch", include_in_schema=False)
def serve_watch():
    from fastapi.responses import FileResponse
    return FileResponse(str(FRONTEND_DIR / "watch.html"))


@app.get("/profile/{username}", include_in_schema=False)
def serve_profile(username: str):
    from fastapi.responses import FileResponse
    return FileResponse(str(FRONTEND_DIR / "profile.html"))


def leaderboard_rank_for_user(db: Session, username: str) -> int | None:
    from sqlalchemy import case as sa_case

    rows = (
        db.query(
            models.User.username,
            func.count(models.Film.id).label("films_submitted"),
            func.count(
                sa_case(
                    (
                        (models.Week.is_open == False) &
                        (models.Week.winner_film_id == models.Film.id),
                        models.Film.id,
                    ),
                    else_=None,
                )
            ).label("films_won"),
        )
        .join(models.Film, models.Film.submitter_key == cast(models.User.id, String))
        .join(models.Week, models.Film.week_id == models.Week.id)
        .group_by(models.User.username)
        .all()
    )
    ranked = sorted(
        (
            {
                "username": row.username,
                "films_submitted": int(row.films_submitted or 0),
                "films_won": int(row.films_won or 0),
                "win_rate": round((row.films_won or 0) / (row.films_submitted or 1) * 100),
            }
            for row in rows
        ),
        key=lambda r: (-r["films_won"], -r["win_rate"], -r["films_submitted"]),
    )
    rank = 1
    for idx, row in enumerate(ranked):
        if idx > 0:
            prev = ranked[idx - 1]
            if row["films_won"] != prev["films_won"] or row["win_rate"] != prev["win_rate"]:
                rank = idx + 1
        if row["username"].lower() == username.lower():
            return rank
    return None


@app.get("/users/{username}/profile")
def get_user_profile(username: str, db: Session = Depends(get_db)):
    """Public profile data for a user — optimised: 5 queries instead of N+1."""
    user = (
        db.query(
            models.User.id,
            models.User.username,
            models.User.avatar_url,
            models.User.letterboxd_avatar_url,
            models.User.letterboxd_username,
            models.User.letterboxd_synced_at,
        )
        .filter(func.lower(models.User.username) == username.lower())
        .first()
    )
    if not user:
        raise HTTPException(404, "User not found")

    submitter_key = str(user.id)

    # ── FIX: load films with their week eagerly in one JOIN, and pre-load votes
    # via selectinload (one extra query for all films' votes, not one per film)
    submitted = (
        db.query(models.Film)
        .filter(models.Film.submitter_key == submitter_key)
        .options(
            load_only(
                models.Film.id,
                models.Film.title,
                models.Film.year,
                models.Film.director,
                models.Film.poster_url,
                models.Film.tmdb_id,
                models.Film.week_id,
            ),
            joinedload(models.Film.week),
        )
        .order_by(models.Film.id.desc())
        .limit(MAX_LIST_LIMIT)
        .all()
    )
    film_ids = [f.id for f in submitted]
    vote_counts = {}
    if film_ids:
        vote_counts = dict(
            db.query(models.Vote.film_id, func.count(models.Vote.id))
            .filter(models.Vote.film_id.in_(film_ids))
            .group_by(models.Vote.film_id)
            .all()
        )

    # ── FIX: COUNT in DB instead of loading all vote rows into Python
    votes_cast = (
        db.query(func.count(models.Vote.id))
        .filter(models.Vote.voter_key == submitter_key)
        .scalar()
    ) or 0

    # ── FIX: COUNT reactions in DB — also fetch grouped counts in one query
    reaction_rows = (
        db.query(models.Reaction.emoji, func.count(models.Reaction.id))
        .filter(models.Reaction.user_id == user.id)
        .group_by(models.Reaction.emoji)
        .all()
    )
    reaction_counts = {emoji: cnt for emoji, cnt in reaction_rows}
    reactions_given = sum(reaction_counts.values())

    # Letterboxd entries — unchanged, already efficient
    lb_entries = (
        db.query(models.LetterboxdEntry)
        .filter(models.LetterboxdEntry.user_id == user.id)
        .order_by(models.LetterboxdEntry.watched_date.desc())
        .limit(20)
        .all()
    )

    # Build submitted films list — f.week and f.votes already loaded above
    films_won = 0
    submitted_list = []
    for f in submitted:
        week = f.week
        is_winner = bool(week and not week.is_open and week.winner_film_id == f.id)
        if is_winner:
            films_won += 1
        submitted_list.append({
            "id": f.id,
            "title": f.title,
            "year": f.year,
            "director": f.director,
            "poster_url": f.poster_url,
            "tmdb_id": f.tmdb_id,
            "week_title": week.title if week else None,
            "week_id": week.id if week else None,
            "is_winner": is_winner,
            "votes": int(vote_counts.get(f.id, 0)),
        })

    films_submitted = len(submitted)
    most_successful = None
    if submitted_list:
        most_successful = max(
            submitted_list,
            key=lambda f: (int(f.get("votes") or 0), 1 if f.get("is_winner") else 0, int(f.get("id") or 0)),
        )
        most_successful = {
            "id": most_successful["id"],
            "title": most_successful["title"],
            "year": most_successful["year"],
            "poster_url": most_successful["poster_url"],
            "week_title": most_successful["week_title"],
            "week_id": most_successful["week_id"],
            "votes": most_successful["votes"],
            "is_winner": most_successful["is_winner"],
        }

    rank = leaderboard_rank_for_user(db, user.username)
    payload = {
        "user": {
            "id": user.id,
            "username": user.username,
            "avatar_url": user.avatar_url or user.letterboxd_avatar_url,
            "letterboxd_username": user.letterboxd_username,
            "letterboxd_synced_at": user.letterboxd_synced_at,
        },
        "stats": {
            "films_submitted": films_submitted,
            "films_won": films_won,
            "votes_cast": votes_cast,
            "reactions_given": reactions_given,
            "win_rate": round(films_won / films_submitted * 100) if films_submitted else 0,
            "leaderboard_rank": rank,
        },
        "most_successful_submitted_film": most_successful,
        "reaction_counts": reaction_counts,
        "submitted_films": submitted_list,
        "letterboxd_entries": [
            {
                "film_title": e.film_title,
                "film_year": e.film_year,
                "rating": e.rating,
                "watched_date": e.watched_date,
                "letterboxd_url": e.letterboxd_url,
                "tmdb_id": e.tmdb_id,
            }
            for e in lb_entries
        ],
    }
    log_db_response("/users/{username}/profile", "public user profile", len(submitted_list), payload)
    return payload


# ─────────────────────────────────────────────
# Leaderboard
# ─────────────────────────────────────────────

@app.get("/leaderboard", include_in_schema=False)
def serve_leaderboard():
    return FileResponse(str(FRONTEND_DIR / "leaderboard.html"))


@app.get("/api/leaderboard")
def get_leaderboard(db: Session = Depends(get_db)):
    """
    Optimised leaderboard — 3 queries total (was N+1 on films).

    Query 1: All users
    Query 2: films_submitted + films_won per user via GROUP BY + conditional COUNT
    Query 3: votes_cast per user via GROUP BY
    """
    # ── Query 1: all users (small table, fine)
    cached = cache_get("leaderboard")
    if cached is not None:
        return cached

    users = (
        db.query(
            models.User.id,
            models.User.username,
            models.User.avatar_url,
            models.User.letterboxd_avatar_url,
        )
        .order_by(models.User.username.asc())
        .limit(MAX_LIST_LIMIT)
        .all()
    )

    # ── Query 2: submitted + won counts per submitter_key in one query
    # films_won = COUNT of films where their week is closed and they are the winner
    from sqlalchemy import case as sa_case

    film_stats = (
        db.query(
            models.Film.submitter_key,
            func.count(models.Film.id).label("films_submitted"),
            func.count(
                sa_case(
                    (
                        (models.Week.is_open == False) &
                        (models.Week.winner_film_id == models.Film.id),
                        models.Film.id,
                    ),
                    else_=None,
                )
            ).label("films_won"),
        )
        .join(models.Week, models.Film.week_id == models.Week.id)
        .group_by(models.Film.submitter_key)
        .all()
    )
    stats_map = {
        row.submitter_key: {
            "submitted": row.films_submitted,
            "won": row.films_won,
        }
        for row in film_stats
    }

    # ── Query 3: votes cast per voter_key
    votes_q = (
        db.query(models.Vote.voter_key, func.count(models.Vote.id))
        .group_by(models.Vote.voter_key)
        .all()
    )
    votes_map = {vk: cnt for vk, cnt in votes_q}

    rows = []
    for user in users:
        key = str(user.id)
        s = stats_map.get(key)
        if not s:
            continue
        submitted = s["submitted"]
        won = s["won"]
        rows.append({
            "username": user.username,
            "avatar_url": user.avatar_url or user.letterboxd_avatar_url,
            "films_submitted": submitted,
            "films_won": won,
            "win_rate": round(won / submitted * 100) if submitted else 0,
            "votes_cast": votes_map.get(key, 0),
        })

    rows.sort(key=lambda r: (-r["films_won"], -r["win_rate"], -r["films_submitted"]))
    log_db_response("/api/leaderboard", "leaderboard aggregates", len(rows), rows)
    return cache_set("leaderboard", rows, ttl=60)
