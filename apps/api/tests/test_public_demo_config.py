import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_SECRET_KEY, Settings

SECURE_TEST_SECRET = "secure-test-secret-with-at-least-32-characters"


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


def test_non_development_rejects_default_secret():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            SECRET_KEY=DEFAULT_SECRET_KEY,
            SEED_ON_STARTUP=False,
        )


def test_non_development_rejects_short_secret():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(
            _env_file=None,
            APP_ENV="staging",
            SECRET_KEY="too-short",
            SEED_ON_STARTUP=False,
        )


def test_non_development_rejects_demo_seed():
    with pytest.raises(ValidationError, match="SEED_ON_STARTUP"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            SECRET_KEY=SECURE_TEST_SECRET,
            SEED_ON_STARTUP=True,
        )


def test_production_accepts_secure_config_without_demo_seed():
    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        SECRET_KEY=SECURE_TEST_SECRET,
        SEED_ON_STARTUP=False,
    )

    assert not settings.is_development
    assert settings.auto_migrate_on_startup is False


def test_non_development_rejects_startup_migration():
    with pytest.raises(ValidationError, match="数据库迁移"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            SECRET_KEY=SECURE_TEST_SECRET,
            SEED_ON_STARTUP=False,
            AUTO_MIGRATE_ON_STARTUP=True,
        )


def test_development_keeps_local_demo_defaults():
    settings = Settings(
        _env_file=None,
        APP_ENV="development",
        SECRET_KEY=DEFAULT_SECRET_KEY,
        SEED_ON_STARTUP=True,
    )

    assert settings.is_development
    assert settings.SEED_ON_STARTUP
    assert settings.auto_migrate_on_startup is True
