from fastapi import FastAPI, Depends, HTTPException, Body, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
import os
from dotenv import load_dotenv
import requests
from rapidfuzz import fuzz

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
    return {"id": u.id, "username": u.username, "is_admin": bool(getattr(u, "is_admin", False))}


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