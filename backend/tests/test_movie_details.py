import os
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
import requests

from app import movie_details


class MovieDetailsTests(unittest.TestCase):
    def setUp(self):
        movie_details._cache.clear()
        movie_details._images_cache.clear()
        env = patch.dict(os.environ, {"TMDB_API_KEY": "test-only-key"})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(movie_details._cache.clear)
        self.addCleanup(movie_details._images_cache.clear)

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
        self.assertEqual(get.call_count, 2)

    @patch("app.movie_details.requests.get")
    def test_backdrop_uses_images_endpoint_and_prefers_untagged_high_resolution(self, get):
        metadata, images = Mock(status_code=200), Mock(status_code=200)
        metadata.json.return_value = {"title": "Film", "backdrop_path": "/default.jpg"}
        images.json.return_value = {"backdrops": [
            {"file_path": "/portrait.jpg", "iso_639_1": None, "width": 1000, "height": 1500, "vote_average": 10},
            {"file_path": "/tiny.jpg", "iso_639_1": None, "width": 640, "height": 360, "vote_average": 10},
            {"file_path": "/titled.jpg", "iso_639_1": "en", "width": 3840, "height": 2160, "vote_average": 9},
            {"file_path": "/untagged.jpg", "iso_639_1": None, "width": 1920, "height": 1080, "vote_average": 7},
        ]}
        get.side_effect = [metadata, images]
        result = movie_details.get_details(129)
        self.assertTrue(result["backdrop_url"].endswith("/untagged.jpg"))
        self.assertAlmostEqual(result["backdrop_aspect_ratio"], 1920/1080)
        self.assertTrue(get.call_args.args[0].endswith("/129/images"))
        self.assertEqual(len(movie_details.get_backdrops(129)), 3)
        self.assertEqual(get.call_count, 2)

    @patch("app.movie_details.requests.get")
    def test_unsuitable_images_do_not_use_main_backdrop_or_poster(self, get):
        metadata, images = Mock(status_code=200), Mock(status_code=200)
        metadata.json.return_value = {"title": "Film", "poster_path": "/poster.jpg", "backdrop_path": "/default.jpg"}
        images.json.return_value = {"backdrops": [{"file_path": "/tiny.jpg", "width": 640, "height": 360}]}
        get.side_effect = [metadata, images]
        self.assertIsNone(movie_details.get_details(129)["backdrop_url"])

    @patch("app.movie_details.requests.get")
    def test_verified_fear_scene_is_preferred_only_if_listed(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = {"backdrops": [
            {"file_path": "/4BcunK3qpDAMBM5YBsCgQWx9zB6.jpg", "width": 1920, "height": 1080, "vote_average": 10},
            {"file_path": "/hUzs26surgYxbHATjyDIyWat6ZL.jpg", "width": 3840, "height": 2160, "vote_average": 5},
        ]}
        images = movie_details.get_backdrops(1878)
        self.assertTrue(images[0]["verified_scene"])
        self.assertEqual(images[0]["file_path"], "/hUzs26surgYxbHATjyDIyWat6ZL.jpg")
        movie_details._images_cache.clear()
        get.return_value.json.return_value["backdrops"].pop()
        self.assertFalse(movie_details.get_backdrops(1878)[0]["verified_scene"])

    @patch("app.movie_details.requests.get")
    def test_image_failure_preserves_metadata_without_leaking_key(self, get):
        metadata = Mock(status_code=200)
        metadata.json.return_value = {"title": "Film"}
        get.side_effect = [metadata, requests.Timeout("api_key=test-only-key")]
        self.assertEqual(movie_details.get_details(129)["title"], "Film")
        self.assertIsNone(movie_details.get_details(129)["backdrop_url"])
        self.assertNotIn(129, movie_details._images_cache)

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
