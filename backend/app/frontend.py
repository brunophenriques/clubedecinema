"""HTML routes and static asset locations for the cinema club frontend."""
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, HTMLResponse

from . import models
from .db import SessionLocal

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
PAGES_DIR = FRONTEND_DIR / "pages"
STATIC_DIR = FRONTEND_DIR / "static"
router = APIRouter()


def netflix_index_response() -> HTMLResponse:
    """Render the Netflix skin in HTML so it does not depend on client-side JS/cache."""
    page = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
    page = page.replace("<body>", '<body class="theme-netflix">', 1)
    page = page.replace(
        '<div class="hero-backdrop" aria-hidden="true"></div>',
        '<div class="hero-backdrop" aria-hidden="true"></div>'
        '<img class="netflix-brand-mark" src="/static/images/netflix-n.png" alt="" aria-hidden="true">',
        1,
    )
    page = page.replace(
        '<div class="kicker" id="heroKicker">Esta semana</div>',
        '<div class="kicker" id="heroKicker">SÓ NA NETFLIX</div>',
        1,
    )
    page = page.replace(
        '<p id="heroSub" class="muted">Submete um filme e vota no favorito da semana.</p>',
        '<p id="heroSub" class="muted"></p>',
        1,
    )
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


@router.get("/sw.js", include_in_schema=False)
def serve_sw():
    return FileResponse(str(STATIC_DIR / "sw.js"), media_type="application/javascript")

@router.get("/", include_in_schema=False)
def serve_index():
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
            return FileResponse(str(PAGES_DIR / "portugal.html"))
        if theme == "netflix":
            return netflix_index_response()
    finally:
        db.close()
    return FileResponse(str(PAGES_DIR / "index.html"))

@router.get("/preview", include_in_schema=False)
def serve_theme_preview(theme: str | None = Query(None)):
    """Always serve the neutral homepage so an active special theme cannot mask previews."""
    if (theme and theme.strip().lower() == "netflix"):
        return netflix_index_response()
    return FileResponse(str(PAGES_DIR / "index.html"))

@router.get("/portugal", include_in_schema=False)
def serve_portugal():
    return FileResponse(str(PAGES_DIR / "portugal.html"))

@router.get("/admin", include_in_schema=False)
def serve_admin():
    return FileResponse(str(PAGES_DIR / "admin.html"))

@router.get("/archive", include_in_schema=False)
def serve_archive():
    return FileResponse(str(PAGES_DIR / "archive.html"))

@router.get("/como-funciona", include_in_schema=False)
def serve_rules():
    return FileResponse(str(PAGES_DIR / "como-funciona.html"))


@router.get("/watch", include_in_schema=False)
def serve_watch():
    return FileResponse(str(PAGES_DIR / "watch.html"))


@router.get("/profile/{username}", include_in_schema=False)
def serve_profile(username: str):
    return FileResponse(str(PAGES_DIR / "profile.html"))


@router.get("/leaderboard", include_in_schema=False)
def serve_leaderboard():
    return FileResponse(str(PAGES_DIR / "leaderboard.html"), headers={"Cache-Control": "no-cache"})
