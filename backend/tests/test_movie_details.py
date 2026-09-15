import os
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
import requests

from app import movie_details


class MovieDetailsTests(unittest.TestCase):
    def setUp(self):
        movie_details._cache.clear()
        env = patch.dict(os.environ, {"TMDB_API_KEY": "test-only-key"})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(movie_details._cache.clear)

    @patch("app.movie_details.requests.get")
    def test_metadata_translation_cast_and_cache(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = {
            "title": "A viagem", "release_date": "2001-07-20", "overview": "", "runtime": 125,
            "genres": [{"name": "Animação"}], "poster_path": "/poster.jpg", "backdrop_path": "/still.jpg",
            "credits": {"crew": [{"job": "Director", "name": "Director"}],
                        "cast": [{"name": f"Actor {i}", "character": "Role"} for i in range(20)]},
            "translations": {"translations": [{"iso_639_1": "en", "data": {"overview": "English synopsis"}}]},
        }
        result = movie_details.get_details(129)
        self.assertEqual(result["overview_language"], "en")
        self.assertEqual(result["overview"], "English synopsis")
        self.assertEqual(result["directors"], ["Director"])
        self.assertEqual(len(result["cast"]), 8)
        self.assertEqual(result["runtime"], 125)
        self.assertEqual(result["letterboxd_url"], "https://letterboxd.com/search/tmdb:129/")
        self.assertEqual(movie_details.get_details(129), result)
        self.assertEqual(get.call_count, 1)

    @patch("app.movie_details.requests.get")
    def test_missing_optional_metadata_is_not_fabricated(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = {"title": "Film", "runtime": 0, "vote_average": 0, "vote_count": 0}
        result = movie_details.get_details(123)
        self.assertIsNone(result["overview"])
        self.assertIsNone(result["runtime"])
        self.assertIsNone(result["rating"])
        self.assertEqual(result["cast"], [])
        self.assertIsNone(result["backdrop_url"])

    @patch("app.movie_details.requests.get")
    def test_network_error_never_leaks_key_or_gets_cached(self, get):
        get.side_effect = requests.Timeout("https://api.themoviedb.org/?api_key=test-only-key")
        for _ in range(2):
            with self.assertRaises(HTTPException) as caught:
                movie_details.get_details(129)
            self.assertEqual(caught.exception.status_code, 502)
            self.assertNotIn("test-only-key", caught.exception.detail)
        self.assertEqual(get.call_count, 2)

    @patch("app.movie_details.requests.get")
    def test_missing_configuration_and_not_found(self, get):
        with patch.dict(os.environ, {"TMDB_API_KEY": ""}):
            with self.assertRaises(HTTPException) as caught:
                movie_details.get_details(129)
            self.assertEqual(caught.exception.status_code, 503)
        get.assert_not_called()
        get.return_value = Mock(status_code=404)
        with self.assertRaises(HTTPException) as caught:
            movie_details.get_details(999999)
        self.assertEqual(caught.exception.status_code, 404)
