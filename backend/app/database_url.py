from sqlalchemy.engine import make_url


def normalize_database_url(value: str) -> str:
    """Use the installed psycopg2 driver for synchronous PostgreSQL connections.

    Parse the URL so credentials, query parameters and percent encoding survive
    unchanged. Do not rely on SQLAlchemy's version-dependent default driver.
    """
    url = make_url(value)
    if url.drivername in {"postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2"}:
        return url.set(drivername="postgresql+psycopg2").render_as_string(hide_password=False)
    return value
