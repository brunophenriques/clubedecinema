# Render database driver

The project retains `psycopg2-binary`. Both `app/db.py` and `alembic/env.py`
use `app/database_url.py` to select `postgresql+psycopg2` explicitly. Generic
`postgres://` and `postgresql://` URLs and an existing `postgresql+psycopg://`
URL resolve to the same installed driver. Credentials and connection parameters
are preserved; URLs must never be printed for diagnosis.

Alembic also escapes percent signs when putting the URL into ConfigParser,
so percent-encoded passwords are not interpreted as configuration expressions.
Its usual `alembic upgrade head` startup step remains required and unchanged.

Validation: install `backend/requirements-dev.txt` into a fresh virtual
environment and run `python -m unittest discover -s tests -v` from `backend`.
Driver tests construct the actual application and online Alembic engines for
four PostgreSQL URL forms, verify both load `psycopg2`, and prevent all network
connections. A separate disposable SQLite database verifies migration upgrades,
idempotency and preservation of an existing test record. No production database
is created, reset or contacted by these tests.
