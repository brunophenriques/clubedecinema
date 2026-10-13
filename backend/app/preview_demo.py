"""Read-only preview fixtures. No database access, matching or external API calls."""
from copy import deepcopy

from fastapi import HTTPException

FILMS = [
    {"id": -671, "title": "Alien", "year": 1979, "director": "Ridley Scott", "tmdb_id": 348,
     "poster_url": "https://image.tmdb.org/t/p/w342/vfrQk5IPloGg1v9Rzbh2Eg3VGyM.jpg"},
    {"id": -672, "title": "The Thing", "year": 1982, "director": "John Carpenter", "tmdb_id": 1091,
     "poster_url": "https://image.tmdb.org/t/p/w342/tzGY49kseSE9QAKk47uuDGwnSCu.jpg"},
    {"id": -673, "title": "Psycho", "year": 1960, "director": "Alfred Hitchcock", "tmdb_id": 539,
     "poster_url": "https://image.tmdb.org/t/p/w342/yz4QVqPx3h1hD1DfqqQkCq3rmxW.jpg"},
    {"id": -674, "title": "Halloween", "year": 1978, "director": "John Carpenter", "tmdb_id": 948,
     "poster_url": "https://image.tmdb.org/t/p/w342/f7JAX5EGk4GgsEnus6OxyzwpFp7.jpg"},
]


def demo_week(stage: str):
    films = deepcopy(FILMS)
    for index, film in enumerate(films):
        film.update(votes=[4, 2, 1, 1][index] if stage == "winner" else 0,
                    needs_review=False, submitter_key="preview-demo")
    return {"id": -670, "title": "Demonstração", "theme": None,
            "is_open": stage != "winner", "is_ready": stage != "submissions",
            "phase": {"winner": "closed", "voting": "voting", "submissions": "submissions"}[stage],
            "submissions_open": stage == "submissions", "voting_open": stage == "voting",
            "winner_film_id": -671 if stage == "winner" else None,
            "submission_deadline": None, "voting_deadline": None, "server_time": 0, "films": films}


def preview_data(path: str, stage: str):
    """Only explicit fixture reads are supported. Never proxies arbitrary URLs."""
    path = path.split("?", 1)[0]
    if path == "/weeks/current":
        return demo_week(stage)
    if path == "/weeks":
        return []
    if path.startswith("/films/") and path.endswith("/details"):
        film = next((film for film in FILMS if path == f'/films/{film["id"]}/details'), None)
        if film:
            return {**film, "directors": [film["director"]], "genres": [], "cast": [],
                    "overview": "", "details_status": "fallback", "runtime": None,
                    "backdrop_url": "https://image.tmdb.org/t/p/w1280/AmR3JG1VQVxU8TfAvljUhfSFUOx.jpg" if film["id"] == -671 else None,
                    "backdrop_position": {"x": 50, "y": 42},
                    "tmdb_url": f'https://www.themoviedb.org/movie/{film["tmdb_id"]}',
                    "letterboxd_url": f'https://letterboxd.com/tmdb/{film["tmdb_id"]}/'}
    if path in [f'/films/{film["id"]}/reactions' for film in FILMS]:
        return {"counts": {}}
    if path in [f'/films/{film["id"]}/reactions/me' for film in FILMS]:
        return {"emoji": None}
    if path == "/weeks/-670/chat":
        return []
    if path == "/letterboxd/members" or path in [f'/letterboxd/film/{film["tmdb_id"]}' for film in FILMS]:
        return []
    raise HTTPException(404, "Não há dados de demonstração para este pedido.")
