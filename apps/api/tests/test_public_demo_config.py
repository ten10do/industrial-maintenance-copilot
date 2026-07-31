from app.core.config import Settings


def test_neon_postgresql_url_uses_installed_psycopg_driver():
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql://demo:secret@example.neon.tech/demo?sslmode=require",
    )

    assert settings.effective_database_url == (
        "postgresql+psycopg://demo:secret@example.neon.tech/demo?sslmode=require"
    )


def test_legacy_postgres_url_uses_installed_psycopg_driver():
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgres://demo:secret@example.neon.tech/demo",
    )

    assert settings.effective_database_url == (
        "postgresql+psycopg://demo:secret@example.neon.tech/demo"
    )


def test_explicit_sqlalchemy_driver_is_preserved():
    database_url = "postgresql+psycopg://demo:secret@localhost/demo"
    settings = Settings(_env_file=None, DATABASE_URL=database_url)

    assert settings.effective_database_url == database_url
