"""Frontend routing and asset checks, using an isolated temporary SQLite database."""
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

import tinycss2
from fastapi.testclient import TestClient


class FrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "app.db" in sys.modules:
            raise RuntimeError("Run frontend tests in a fresh process to isolate the database.")
        cls.temp = tempfile.TemporaryDirectory(prefix="cinema-frontend-tests-")
        cls.previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = "sqlite:///" + (Path(cls.temp.name) / "test.db").as_posix()
        # Run this suite in its own process: configure the database before importing the app.
        from app import db, frontend, models
        from app.main import app

        cls.db, cls.frontend, cls.models = db, frontend, models
        db.Base.metadata.create_all(db.engine)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.db.engine.dispose()
        cls.temp.cleanup()
        if cls.previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = cls.previous_database_url

    def test_public_pages_and_content_types(self):
        for route in ["/", "/preview", "/portugal", "/admin", "/archive",
                      "/como-funciona", "/watch", "/profile/test-user", "/leaderboard"]:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.headers["content-type"])
                self.assertIn("<!doctype html>", response.text.lower())
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertIn("javascript", self.client.get("/sw.js").headers["content-type"])

    def test_debug_endpoint_does_not_expose_credentials(self):
        for headers in [{}, {"Authorization": "Bearer invalid-token"}]:
            response = self.client.get("/debug/whoami", headers=headers)
            self.assertEqual(response.status_code, 404)
            self.assertNotIn("database_url", response.text)
            self.assertNotIn("token_prefix", response.text)

    def test_week_themes_and_independent_preview(self):
        for theme in [None, "portugal", "netflix", "italian"]:
            with self.subTest(theme=theme), self.db.SessionLocal() as session:
                week = self.models.Week(title="Frontend test", theme=theme, is_open=True)
                session.add(week)
                session.commit()
                try:
                    page = self.client.get("/")
                    self.assertEqual(page.status_code, 200)
                    if theme == "netflix":
                        self.assertIn('<body class="theme-netflix">', page.text)
                        self.assertIn('/static/images/netflix-n.png', page.text)
                    else:
                        filename = "portugal.html" if theme == "portugal" else "index.html"
                        self.assertEqual(page.content, (self.frontend.PAGES_DIR / filename).read_bytes())
                    preview = self.client.get("/preview")
                    self.assertEqual(preview.content, (self.frontend.PAGES_DIR / "index.html").read_bytes())
                finally:
                    session.delete(week)
                    session.commit()
        preview = self.client.get("/preview?theme=netflix")
        self.assertIn('<body class="theme-netflix">', preview.text)
        self.assertEqual(preview.headers["cache-control"], "no-store")

    def test_all_static_references_and_precache_urls_resolve(self):
        sources = [*self.frontend.FRONTEND_DIR.rglob("*"), Path(self.frontend.__file__)]
        urls = set()
        for source in sources:
            if source.suffix in {".html", ".css", ".js", ".json", ".py"}:
                urls.update(re.findall(r'/static/[\w./-]+', source.read_text(encoding="utf-8")))
        for url in sorted(urls):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.content)
        # HTML is served through page routes, never through the static directory.
        self.assertEqual(self.client.get("/static/pages/index.html").status_code, 404)

    def test_stylesheets_parse_and_imports_resolve(self):
        for source in (self.frontend.STATIC_DIR / "css").rglob("*.css"):
            with self.subTest(source=source.name):
                css = source.read_text(encoding="utf-8")
                errors = [rule for rule in tinycss2.parse_stylesheet(css) if rule.type == "error"]
                self.assertFalse(errors)
                for relative in re.findall(r'@import url\("(\./[^\"]+)"\)', css):
                    self.assertTrue((source.parent / relative).is_file(), relative)

    def voting_fixture(self, scheduled=True):
        from app import main
        main._rate_buckets.clear()
        clock = patch("app.week_schedule.time.time", return_value=1900000000)
        clock.start()
        self.addCleanup(clock.stop)
        with self.db.SessionLocal() as session:
            owner = self.models.User(username="film-owner", password_hash="unused", is_admin=True)
            voter = self.models.User(username="voter-only", password_hash="unused")
            session.add_all([owner, voter])
            session.flush()
            for user, token in [(owner, "owner-token"), (voter, "voter-token")]:
                session.add(self.models.Session(user_id=user.id, token=token,
                            created_at=1899999000, expires_at=1900010000))
            week = self.models.Week(title="Scheduled test", is_open=True,
                submission_deadline=1900000000 if scheduled else None,
                voting_deadline=1900000100 if scheduled else None)
            session.add(week)
            session.flush()
            film = self.models.Film(week_id=week.id, title="Candidate", submitter_key=str(owner.id))
            session.add(film)
            session.commit()
            ids = week.id, film.id, owner.id, voter.id

        def cleanup():
            with self.db.SessionLocal() as session:
                session.query(self.models.Week).filter_by(id=ids[0]).delete()
                session.query(self.models.User).filter(self.models.User.id.in_(ids[2:])).delete(synchronize_session=False)
                session.commit()
        self.addCleanup(cleanup)
        self.owner_auth = {"Authorization": "Bearer owner-token"}
        self.voter_auth = {"Authorization": "Bearer voter-token"}
        return ids[0], ids[1]

    def test_vote_without_submission_and_existing_restrictions(self):
        week, film = self.voting_fixture()
        route = f"/weeks/{week}/vote"
        self.assertEqual(self.client.post(route, json={"film_id": film, "voter_key": "123"}).status_code, 401)
        self.assertEqual(self.client.post(route, headers=self.owner_auth, json={"film_id": film}).status_code, 403)
        with self.db.SessionLocal() as session:
            session.query(self.models.User).filter_by(username="voter-only").update({"is_banned": True})
            session.commit()
        self.assertEqual(self.client.post(route, headers=self.voter_auth, json={"film_id": film}).status_code, 403)
        with self.db.SessionLocal() as session:
            session.query(self.models.User).filter_by(username="voter-only").update({"is_banned": False})
            session.commit()
        response = self.client.post(route, headers=self.voter_auth, json={"film_id": film})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["films"][0]["votes"], 1)
        self.assertEqual(self.client.post(route, headers=self.voter_auth, json={"film_id": film}).status_code, 409)

    def test_deadline_boundaries_enforce_separate_phases(self):
        week, film = self.voting_fixture()
        vote = f"/weeks/{week}/vote"
        submit = f"/weeks/{week}/submissions"
        body = {"title": "Another film", "poster_url": "https://example.test/poster.jpg"}
        with patch("app.week_schedule.time.time", return_value=1899999999):
            self.assertEqual(self.client.get(f"/weeks/{week}").json()["phase"], "submissions")
            self.assertEqual(self.client.post(vote, headers=self.voter_auth, json={"film_id": film}).status_code, 400)
            self.assertEqual(self.client.post(submit, headers=self.voter_auth, json=body).status_code, 200)
        self.assertEqual(self.client.get(f"/weeks/{week}").json()["phase"], "voting")
        self.assertEqual(self.client.post(submit, headers=self.voter_auth, json=body).status_code, 400)
        with patch("app.week_schedule.time.time", return_value=1900000100):
            response = self.client.get(f"/weeks/{week}").json()
            self.assertEqual(response["phase"], "voting_closed")
            self.assertFalse(response["voting_open"])
            self.assertTrue(response["is_open"])  # Admin still confirms the result.
            self.assertEqual(self.client.post(vote, headers=self.voter_auth, json={"film_id": film}).status_code, 400)

    def test_manual_pause_does_not_reopen_submissions(self):
        week, film = self.voting_fixture(scheduled=False)
        admin = f"/admin/weeks/{week}"
        self.assertEqual(self.client.post(admin + "/start-voting", headers=self.owner_auth).status_code, 200)
        response = self.client.post(admin + "/stop-voting", headers=self.owner_auth)
        self.assertEqual(response.json()["phase"], "paused")
        self.assertFalse(response.json()["submissions_open"])
        self.assertEqual(self.client.post(f"/weeks/{week}/vote", headers=self.voter_auth, json={"film_id": film}).status_code, 400)
        self.assertEqual(self.client.post(admin + "/start-voting", headers=self.owner_auth).json()["phase"], "voting")

    def test_deadline_admin_validation_and_no_reopening_after_votes(self):
        week, film = self.voting_fixture()
        route = f"/admin/weeks/{week}/deadlines"
        valid = {"submission_deadline": 1900000000, "voting_deadline": 1900000200}
        self.assertEqual(self.client.post(route, headers=self.voter_auth, json=valid).status_code, 403)
        for body in [{"submission_deadline": 1900000000},
                     {"submission_deadline": 1900000000, "voting_deadline": 1899999999}]:
            self.assertEqual(self.client.post(route, headers=self.owner_auth, json=body).status_code, 422)
        self.assertEqual(self.client.post(route, headers=self.owner_auth, json=valid).status_code, 200)
        self.assertEqual(self.client.post(f"/weeks/{week}/vote", headers=self.voter_auth, json={"film_id": film}).status_code, 200)
        valid["submission_deadline"] += 50
        self.assertEqual(self.client.post(route, headers=self.owner_auth, json=valid).status_code, 409)

    def test_manual_close_before_deadline_blocks_votes_and_selects_winner(self):
        week, film = self.voting_fixture()
        vote = f"/weeks/{week}/vote"
        self.assertEqual(self.client.post(vote, headers=self.voter_auth, json={"film_id": film}).status_code, 200)
        response = self.client.post(f"/admin/weeks/{week}/close", headers=self.owner_auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["phase"], "closed")
        self.assertEqual(response.json()["winner_film_id"], film)
        self.assertLess(response.json()["server_time"], response.json()["voting_deadline"])
        self.assertEqual(self.client.post(vote, headers=self.voter_auth, json={"film_id": film}).status_code, 400)

    def test_lisbon_deadlines_in_winter_summer_and_clock_change(self):
        from datetime import datetime, timezone
        from fastapi import HTTPException
        from app.week_schedule import parse_deadlines
        for local, utc in [("2026-01-15T18:00", "2026-01-15T18:00"),
                           ("2026-07-15T18:00", "2026-07-15T17:00")]:
            start, _ = parse_deadlines({"submission_deadline": local,
                                       "voting_deadline": local.replace("18:00", "20:00")})
            self.assertEqual(start, int(datetime.fromisoformat(utc).replace(tzinfo=timezone.utc).timestamp()))
        with self.assertRaises(HTTPException):
            parse_deadlines({"submission_deadline": "2026-03-29T01:30",
                             "voting_deadline": "2026-03-29T04:00"})


    def test_club_film_sheet_keeps_local_data_if_tmdb_is_unavailable(self):
        _, film = self.voting_fixture()
        with patch.dict(os.environ, {"TMDB_API_KEY": ""}):
            response = self.client.get(f"/films/{film}/details")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Candidate")
        self.assertEqual(response.json()["source"], "club")
        self.assertIsNone(response.json()["overview"])
        self.assertEqual(self.client.get("/films/999999/details").status_code, 404)

    def test_film_sheet_resolves_confident_match_without_editing_submission(self):
        _, film = self.voting_fixture()
        with patch.dict(os.environ, {"TMDB_API_KEY": "test-only-key"}), \
             patch("app.main.pick_best_tmdb_match", return_value={"tmdb_id": 129, "match_score": 100, "needs_review": False}), \
             patch("app.main.get_tmdb_details", return_value={"tmdb_id": 129, "source": "tmdb", "overview": "Synopsis"}):
            response = self.client.get(f"/films/{film}/details")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tmdb_id"], 129)
        with self.db.SessionLocal() as session:
            self.assertIsNone(session.get(self.models.Film, film).tmdb_id)


if __name__ == "__main__":
    unittest.main()
