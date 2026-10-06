# Featured film backdrop

`app/movie_details.py` requests TMDB `GET /3/movie/{movie_id}/images` separately
from metadata. Both caches have a six-hour TTL and a 256-movie bound. Transient
image failures are not cached as successful galleries; metadata without images
retries after one minute. Empty galleries are cached normally.

Automatic selection accepts panoramas at least 1280 x 720 with an aspect ratio
of at least 1.5. It favors untagged images, high resolution and TMDB rating.
These criteria do not distinguish scene photography from promotional artwork.
The metadata's primary `backdrop_path` and portrait poster are not used as
unverified landscape fallbacks.

## Admin selection

The current-week admin film row includes **Imagem de destaque**. Its native
dialog shows thumbnails, resolution/language information, desktop/mobile crop
previews, two position sliders, an automatic option and a save action. Selection
persists on the club film record, rather than in a browser or TMDB response cache.
The homepage always requests `/films/{film_id}/details` to respect that choice.
Reloading or refreshing re-reads the saved choice; provider image requests remain
cached. A saved image remains available if metadata enrichment fails. Changing
the film's TMDB identity clears the old image selection.

Only authenticated admins can list or save these images. New choices must be
paths returned by TMDB for that film; arbitrary URLs are rejected. Crop positions
must be finite numbers from 0 to 100. Resetting to automatic does not require an
available TMDB provider. Migration `i9c0d1e2f3a4` adds three nullable columns with
no updates or deletions of existing rows. The Render startup migration remains
`alembic upgrade head`.

## Visually verified film photography

[Fear and Loathing in Las Vegas, TMDB backdrops](https://www.themoviedb.org/movie/1878-fear-and-loathing-in-las-vegas/images/backdrops)
was inspected directly. `/hUzs26surgYxbHATjyDIyWat6ZL.jpg` is a photograph of
Johnny Depp and Benicio del Toro in the convertible, distinct from the illustrated
poster. `/fingCiKiSbYvYogT35Bws1yhYhM.jpg` is another photographic scene. Two
other inspected backdrops were promotional illustrations. The first photograph
receives an automatic preference for movie 1878 only if it is still returned by
TMDB and meets the normal suitability thresholds. An admin override always wins.
No film image has been fabricated or bundled into the application.

TMDB attribution in the existing film-details footer and credits page is retained.
The hero's “Fotograma: TMDB” label has been removed; its image alt text makes no
unsupported claim about image type.

Local live gallery access requires `TMDB_API_KEY`. Tests mock provider responses
and use isolated databases or browser-intercepted state; they do not change real
films, votes, authentication records or production choices.
