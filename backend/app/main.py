from fastapi import FastAPI, Depends, HTTPException, Body, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
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
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import SessionLocal
from . import models

# IMPORTANT: with Alembic migrations, do NOT auto-create tables at runtime
# from .db import Base, engine
# Base.metadata.create_all(bind=engine)

app = FastAPI(title="Cinema Club API")

# -----------------------------
# Serve frontend (static files + pages)
# -----------------------------
BASE_DIR = Path(__file__).resolve()

CANDIDATES = [
    BASE_DIR.parents[2] / "frontend",  # .../clubedecinema/frontend
    BASE_DIR.parents[1] / "frontend",  # .../backend/frontend
    BASE_DIR.parent / "frontend",      # .../app/frontend
]
FRONTEND_DIR = next((p for p in CANDIDATES if p.exists()), None)

if not FRONTEND_DIR:
    raise RuntimeError("Frontend folder not found. Expected a 'frontend' directory near the project root.")

# assets (css/js/img)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/", include_in_schema=False)
def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))

@app.get("/admin", include_in_schema=False)
def serve_admin():
    return FileResponse(str(FRONTEND_DIR / "admin.html"))

@app.get("/archive", include_in_schema=False)
def serve_archive():
    return FileResponse(str(FRONTEND_DIR / "archive.html"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later: restrict to your frontend domain(s)
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
    # store as: pbkdf2_sha256$iters$base64(salt)$base64(hash)
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
        # cleanup expired session
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
    # passing year can hurt if user is wrong; only use it when provided
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
    """
    Returns a dict:
      {
        "tmdb_id": int|None,
        "canonical_title": str,
        "canonical_year": int|None,
        "poster_url": str|None,
        "match_score": float|None,   # 0..1
        "needs_review": bool
      }
    """
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

    # if year might be wrong, try again without year when results are weak
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
        fuzzy_score = max(s1, s2) / 100.0  # 0..1

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

    # accept only if strong and clearly better than #2
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
    }


# ----------------------
# Public endpoints
# ----------------------

@app.get("/health")
def health():
    return {"ok": True}


# ---- Auth endpoints ----

@app.post("/auth/register")
def register(body: dict = Body(...), db: Session = Depends(get_db)):
    username = normalize_username(body.get("username"))
    password = body.get("password") or ""

    if not username:
        raise HTTPException(status_code=400, detail="username required")
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="username too short (min 3)")

    exists = db.query(models.User).filter(models.User.username == username).first()
    if exists:
        raise HTTPException(status_code=409, detail="username already exists")

    u = models.User(username=username, password_hash=hash_password(password))
    db.add(u)
    db.commit()
    db.refresh(u)

    token = create_session(db, u)
    return {"user": {"id": u.id, "username": u.username}, "token": token}



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
    """Set user avatar as a URL or base64 data URI."""
    user = get_current_user(db, authorization)
    avatar = (body.get("avatar_url") or "").strip()

    # Accept either a https URL or a data: URI (base64 image)
    if avatar and not (avatar.startswith("https://") or avatar.startswith("http://") or avatar.startswith("data:image/")):
        raise HTTPException(400, "avatar_url must be a valid URL or base64 data URI")

    # Limit base64 size to ~2MB
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


# ---- Weeks endpoints ----

@app.get("/weeks/current")
def current_week(db: Session = Depends(get_db)):
    week = db.query(models.Week).order_by(models.Week.id.desc()).first()
    if not week:
        raise HTTPException(404, "No week created yet")
    return week_payload(db, week, include_submitter=False)


@app.get("/weeks")
def list_weeks(db: Session = Depends(get_db)):
    weeks = db.query(models.Week).order_by(models.Week.id.desc()).all()
    return [week_payload(db, w, include_submitter=False) for w in weeks]


@app.get("/weeks/{week_id}")
def get_week(week_id: int, db: Session = Depends(get_db)):
    week = db.query(models.Week).filter(models.Week.id == week_id).first()
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

    # 1 submissão por user por semana (anti-spam / fairness)
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
    """
    NEW: Auth-based voting (Authorization: Bearer <token>)
    TEMP fallback: allows body.voter_key for compatibility with current frontend.
    """
    # Prefer auth if present
    voter_key = None
    if authorization:
        user = get_current_user(db, authorization)
        voter_key = str(user.id)
    else:
        # compatibility fallback (remove later once frontend is updated)
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

    # RULE 1: only submitters can vote this week
    submitter_keys = {
        k for (k,) in db.query(models.Film.submitter_key)
                        .filter(models.Film.week_id == week_id)
                        .distinct()
                        .all()
    }
    if voter_key not in submitter_keys:
        raise HTTPException(status_code=403, detail="Only submitters can vote this week")

    # RULE 2: cannot vote on your own film
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
# Admin endpoints (ADMIN = user.is_admin + Bearer token)
# ----------------------

@app.get("/admin/weeks/current")
def admin_current_week(
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    require_admin_user(db, authorization)
    week = db.query(models.Week).order_by(models.Week.id.desc()).first()
    if not week:
        raise HTTPException(404, "No week created yet")
    return week_payload(db, week, include_submitter=True)


@app.get("/admin/weeks")
def admin_list_weeks(
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    require_admin_user(db, authorization)
    weeks = db.query(models.Week).order_by(models.Week.id.desc()).all()
    return [week_payload(db, w, include_submitter=True) for w in weeks]


@app.post("/admin/weeks")
def create_week(
    body: dict,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    require_admin_user(db, authorization)

    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "title required")

    week = models.Week(title=title, is_open=True)
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

    # Allow updating canonical fields
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

    # Mark as reviewed if admin says so (default True)
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
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    require_admin_user(db, authorization)

    films = (
        db.query(models.Film)
          .filter(models.Film.needs_review == True)  # noqa: E712
          .order_by(models.Film.id.desc())
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

# Letterboxd star ratings come as Unicode star strings like ★★★½
_STAR_MAP = {"★": 1.0, "½": 0.5}

def _parse_lb_rating(text: str) -> float | None:
    """Convert '★★★½' → 3.5, empty/None → None."""
    if not text:
        return None
    score = sum(_STAR_MAP.get(ch, 0.0) for ch in text)
    return score if score > 0 else None


def _parse_lb_date(date_str: str) -> int | None:
    """Parse RSS pubDate or letterboxd:watchedDate → unix timestamp."""
    if not date_str:
        return None
    # letterboxd:watchedDate is YYYY-MM-DD
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", date_str.strip())
    if m:
        import calendar, datetime
        d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return calendar.timegm(d.timetuple())
    return None


def _tmdb_id_from_lb_url(url: str) -> int | None:
    """
    Letterboxd film pages sometimes embed a TMDB link in the description.
    We try to extract from the letterboxd film URL by hitting TMDB search
    but that's expensive; instead we rely on title+year matching done elsewhere.
    For now just return None — we match by title/year in the upsert logic.
    """
    return None


def fetch_and_sync_letterboxd(db: Session, user: models.User) -> dict:
    """
    Fetch the user's Letterboxd RSS diary feed, parse entries, upsert into DB.
    Returns {"synced": N, "avatar_url": str|None, "error": str|None}
    """
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

    # ── Avatar: scrape from profile page instead of RSS (RSS <image> is feed logo, not user avatar)
    avatar_url = None
    try:
        profile_resp = requests.get(
            f"https://letterboxd.com/{lb_username}/",
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ClubeDecinemasBot/1.0)"}
        )
        if profile_resp.status_code == 200:
            # Letterboxd avatar is in <img class="avatar" src="..."> or og:image meta
            html = profile_resp.text
            # Try og:image first (highest quality)
            og_match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            if og_match:
                candidate = og_match.group(1)
                # og:image is sometimes the site logo, filter it out
                if "a.ltrbxd.com" in candidate and "/userpics/" in candidate:
                    avatar_url = candidate
            # Fallback: look for avatar img tag
            if not avatar_url:
                av_match = re.search(r'<img[^>]+class="[^"]*avatar[^"]*"[^>]+src="([^"]+)"', html)
                if av_match:
                    avatar_url = av_match.group(1)
            # Fallback 2: any ltrbxd userpics URL
            if not avatar_url:
                up_match = re.search(r'(https://a\.ltrbxd\.com/resized/avatar[^"\']+)', html)
                if not up_match:
                    up_match = re.search(r'(https://a\.ltrbxd\.com/[^"\']*userpic[^"\']+)', html)
                if up_match:
                    avatar_url = up_match.group(1)
    except Exception:
        pass  # avatar is optional, don't fail the whole sync

    # ── Parse diary items
    items = root.findall(".//item")
    synced = 0

    for item in items:
        # Only process diary entries (have letterboxd:watchedDate)
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

        # memberRating is numeric e.g. "3.5" in newer RSS, or star text in older
        rating_raw = (rating_el.text or "").strip() if rating_el is not None else ""
        try:
            rating = float(rating_raw) if rating_raw else None
        except ValueError:
            rating = _parse_lb_rating(rating_raw)

        watched_date = _parse_lb_date((watched_date_el.text or "").strip())
        is_rewatch = (rewatch_el is not None and (rewatch_el.text or "").strip().lower() == "yes")
        lb_url = (link_el.text or "").strip() if link_el is not None else None

        # Try to match to a TMDB id from our films table
        tmdb_id = None
        film_match = (
            db.query(models.Film)
            .filter(models.Film.title.ilike(film_title))
            .filter(models.Film.year == film_year if film_year else True)
            .filter(models.Film.tmdb_id.isnot(None))
            .first()
        )
        if film_match:
            tmdb_id = film_match.tmdb_id

        # Upsert: if we have a tmdb_id use that unique key, else skip dedup
        existing = None
        if tmdb_id:
            existing = (
                db.query(models.LetterboxdEntry)
                .filter(
                    models.LetterboxdEntry.user_id == user.id,
                    models.LetterboxdEntry.tmdb_id == tmdb_id,
                )
                .first()
            )

        if existing:
            # Update if newer watch date or more info
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

        synced += 1

    # Update user avatar + sync timestamp
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
    """Set or update the user's Letterboxd username and/or avatar URL, then trigger a sync."""
    user = get_current_user(db, authorization)

    # Allow directly overriding avatar URL (e.g. user pastes a better image URL)
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
        # Allow clearing
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
    """Manually trigger a Letterboxd RSS sync for the current user."""
    user = get_current_user(db, authorization)
    if not user.letterboxd_username:
        raise HTTPException(400, "No Letterboxd username set")

    result = fetch_and_sync_letterboxd(db, user)
    db.refresh(user)

    return {
        "ok": True,
        "synced": result["synced"],
        "avatar_url": result.get("avatar_url"),
        "error": result["error"],
        "letterboxd_synced_at": user.letterboxd_synced_at,
    }


@app.get("/letterboxd/film/{tmdb_id}")
def get_film_letterboxd_data(
    tmdb_id: int,
    db: Session = Depends(get_db),
):
    """
    Return all club members' Letterboxd data for a given TMDB film ID.
    Used by the frontend to show who watched it and their ratings.
    """
    entries = (
        db.query(models.LetterboxdEntry, models.User)
        .join(models.User, models.LetterboxdEntry.user_id == models.User.id)
        .filter(models.LetterboxdEntry.tmdb_id == tmdb_id)
        .all()
    )

    result = []
    for entry, user in entries:
        result.append({
            "user_id": user.id,
            "username": user.username,
            "letterboxd_username": user.letterboxd_username,
            "avatar_url": user.avatar_url or user.letterboxd_avatar_url,
            "rating": entry.rating,
            "watched_date": entry.watched_date,
            "letterboxd_url": entry.letterboxd_url,
            "is_rewatch": entry.is_rewatch,
        })

    return result


@app.get("/letterboxd/members")
def get_all_members_letterboxd(
    db: Session = Depends(get_db),
):
    """Return all users with their Letterboxd info (for avatar display everywhere)."""
    users = db.query(models.User).all()
    return [
        {
            "user_id": u.id,
            "username": u.username,
            "avatar_url": u.avatar_url or u.letterboxd_avatar_url,
            "letterboxd_username": u.letterboxd_username,
            "letterboxd_synced_at": u.letterboxd_synced_at,
        }
        for u in users
    ]


# ─────────────────────────────────────────────
# Reactions
# ─────────────────────────────────────────────

ALLOWED_EMOJIS = {"👍", "😐", "67", "🇮🇱"}


@app.get("/films/{film_id}/reactions")
def get_reactions(film_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(models.Reaction, models.User)
        .join(models.User, models.Reaction.user_id == models.User.id)
        .filter(models.Reaction.film_id == film_id)
        .all()
    )
    # group counts + who reacted with what
    counts = {}
    mine = None
    for r, u in rows:
        counts[r.emoji] = counts.get(r.emoji, 0) + 1

    return {"counts": counts, "total": len(rows)}


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

    # Verify film exists
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
        # Remove reaction
        if existing:
            db.delete(existing)
            db.commit()
        return {"ok": True, "emoji": None}

    if existing:
        if existing.emoji == emoji:
            # Toggle off
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
    """Returns per-emoji lists of who reacted — for tooltip display."""
    rows = (
        db.query(models.Reaction, models.User)
        .join(models.User, models.Reaction.user_id == models.User.id)
        .filter(models.Reaction.film_id == film_id)
        .all()
    )
    detail = {}
    for r, u in rows:
        if r.emoji not in detail:
            detail[r.emoji] = []
        detail[r.emoji].append({
            "username": u.username,
            "avatar_url": u.avatar_url or u.letterboxd_avatar_url,
        })
    return detail


# ─────────────────────────────────────────────
# Chat
# ─────────────────────────────────────────────

@app.get("/weeks/{week_id}/chat")
def get_chat(week_id: int, db: Session = Depends(get_db)):
    messages = (
        db.query(models.ChatMessage, models.User)
        .join(models.User, models.ChatMessage.user_id == models.User.id)
        .filter(models.ChatMessage.week_id == week_id)
        .order_by(models.ChatMessage.created_at.asc())
        .all()
    )
    return [
        {
            "id": m.id,
            "content": m.content,
            "created_at": m.created_at,
            "user": {
                "id": u.id,
                "username": u.username,
                "avatar_url": u.avatar_url or u.letterboxd_avatar_url,
            },
        }
        for m, u in messages
    ]


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
    # Only author or admin can delete
    if msg.user_id != user.id and not getattr(user, "is_admin", False):
        raise HTTPException(403, "Not allowed")
    db.delete(msg)
    db.commit()
    return {"ok": True}
