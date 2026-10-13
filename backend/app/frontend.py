"""HTML routes and static asset locations for the cinema club frontend."""
from pathlib import Path
from html import escape
import json
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, HTMLResponse

from . import models
from .db import SessionLocal
from .preview_demo import preview_data

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
def serve_theme_preview(theme: str | None = Query(None), demo: bool | None = Query(None),
                        stage: Literal["winner", "submissions", "voting"] = "winner"):
    """Always serve the neutral homepage so an active special theme cannot mask previews."""
    theme = (theme or "").strip().lower()
    if demo is None:
        with SessionLocal() as db:
            demo = db.query(models.Week.id).first() is None
    if not demo and theme not in {"halloween", "netflix"}:
        return FileResponse(str(PAGES_DIR / "index.html"), headers={"Cache-Control": "no-store"})
    page = netflix_index_response().body.decode("utf-8") if theme == "netflix" else (PAGES_DIR / "index.html").read_text(encoding="utf-8")
    if theme == "halloween":
        page = page.replace("<body>", '<body class="theme-halloween">', 1)
    if demo:
        config = json.dumps({"stage": stage})
        page = page.replace("<head>", f'<head>\n<script>window.CinemaPreview = {config};</script>', 1)
        links = []
        for name, label in [("winner", "Vencedor"), ("submissions", "Submissões"), ("voting", "Votação")]:
            href = escape("/preview?" + urlencode({"theme": theme, "demo": 1, "stage": name}), quote=True)
            current = ' aria-current="page"' if name == stage else ""
            links.append(f'<a href="{href}"{current}>{label}</a>')
        notice = '<aside class="preview-notice" aria-label="Pré-visualização"><strong>Dados de demonstração</strong><span>Sem semana real. Votos e submissões não são guardados.</span><nav aria-label="Estado de demonstração">' + "".join(links) + '</nav></aside>'
        page = page.replace('<header class="top">', notice + '<header class="top">', 1)
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


@router.get("/preview/data", include_in_schema=False)
def serve_preview_data(path: str, stage: Literal["winner", "submissions", "voting"] = "winner"):
    return preview_data(path, stage)

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
