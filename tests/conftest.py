"""Safety net: tests must never run schema operations against a real database.

A fixture in this suite once called ``db.drop_all()`` while the application was
still bound to the developer's Postgres instance, and dropped every table and
row. The mistake was subtle: the fixture *did* set a SQLite URI, but it set it
**after** ``create_app()``. ``Config`` reads ``DATABASE_URL`` at import time and
``db.init_app()`` binds the engine during ``create_app()``, so updating
``app.config`` afterwards changed nothing that mattered.

Guessing wrong here is unrecoverable, so this makes it loud instead. Any call to
``create_all`` or ``drop_all`` is refused unless the engine it would run against
is SQLite - and refused as well when the target cannot be determined, on the
principle that "not sure" should never be treated as "safe to drop".

The correct pattern, which the error message repeats::

    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(Config, "SQLALCHEMY_ENGINE_OPTIONS", {})
    app = create_app()          # patch BEFORE this line
"""
import pytest

from extensions import db

_SCHEMA_OPERATIONS = ("create_all", "drop_all")

_MESSAGE = (
    "db.{name}() refused by tests/conftest.py.\n"
    "\n"
    "Tests may only run schema operations against SQLite, but the app is bound "
    "to {url}.\n"
    "\n"
    "Config reads DATABASE_URL at import time and create_app() binds the engine, "
    "so setting app.config['SQLALCHEMY_DATABASE_URI'] afterwards has no effect. "
    "Patch the Config class BEFORE calling create_app():\n"
    "\n"
    "    monkeypatch.setattr(Config, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///:memory:')\n"
    "    monkeypatch.setattr(Config, 'SQLALCHEMY_ENGINE_OPTIONS', {{}})\n"
    "    app = create_app()\n"
)


def _target_url() -> str:
    """The database a schema operation would hit, or a marker if unknowable."""
    try:
        return str(db.engine.url)
    except Exception:
        return "<no bound engine>"


def _guarded(name, original):
    def wrapper(*args, **kwargs):
        url = _target_url()
        if not url.startswith("sqlite"):
            raise RuntimeError(_MESSAGE.format(name=name, url=repr(url)))
        return original(*args, **kwargs)

    return wrapper


@pytest.fixture(autouse=True, scope="session")
def forbid_schema_operations_outside_sqlite():
    originals = {name: getattr(db, name) for name in _SCHEMA_OPERATIONS}
    for name, original in originals.items():
        setattr(db, name, _guarded(name, original))
    yield
    for name, original in originals.items():
        setattr(db, name, original)
