"""Database configuration helpers for the project PostgreSQL runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

DATABASE_ENV_KEYS = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
ENV_FILE_PATH = Path(".env.local")


def load_local_env_file(path: Path = ENV_FILE_PATH) -> None:
    """Load simple KEY=VALUE pairs from the local env file if not already set."""

    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        env_key = key.strip()
        env_value = value.strip().strip('"').strip("'")
        if env_key and env_key not in os.environ:
            os.environ[env_key] = env_value


load_local_env_file()


@dataclass(frozen=True)
class DatabaseConfig:
    """Read PostgreSQL connection settings from environment variables."""

    host: str = field(default_factory=lambda: os.getenv("DB_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("DB_PORT", "5432")))
    database: str = field(default_factory=lambda: os.getenv("DB_NAME", "daily_news"))
    user: str = field(default_factory=lambda: os.getenv("DB_USER", "postgres"))
    password: str = field(default_factory=lambda: os.getenv("DB_PASSWORD", "postgres"))

    @property
    def url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )

    @property
    def sync_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )

    @property
    def masked_sync_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.user}:***"
            f"@{self.host}:{self.port}/{self.database}"
        )


@dataclass(frozen=True)
class DatabaseProbeResult:
    layer: str
    ok: bool
    detail: str


def get_database_env_snapshot(*, mask_password: bool = True) -> dict[str, str | None]:
    snapshot: dict[str, str | None] = {}
    for key in DATABASE_ENV_KEYS:
        value = os.getenv(key)
        if mask_password and key == "DB_PASSWORD" and value:
            snapshot[key] = "***"
        else:
            snapshot[key] = value
    return snapshot


def get_missing_database_env_vars() -> list[str]:
    return [key for key in DATABASE_ENV_KEYS if not os.getenv(key)]


def probe_database_environment() -> DatabaseProbeResult:
    missing = get_missing_database_env_vars()
    if missing:
        return DatabaseProbeResult(
            layer="environment variable",
            ok=False,
            detail=f"Missing required database env vars: {', '.join(missing)}",
        )
    return DatabaseProbeResult(
        layer="environment variable",
        ok=True,
        detail="All required database env vars are set.",
    )


def probe_database_connection(config: DatabaseConfig | None = None) -> DatabaseProbeResult:
    config = config or DatabaseConfig()
    engine = create_sync_engine(config)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return DatabaseProbeResult(
            layer="DB connection",
            ok=True,
            detail=f"Connected successfully via {config.masked_sync_url}",
        )
    except Exception as exc:
        return DatabaseProbeResult(
            layer="DB connection",
            ok=False,
            detail=f"{type(exc).__name__}: {exc}",
        )
    finally:
        engine.dispose()


def probe_pgvector_extension(config: DatabaseConfig | None = None) -> DatabaseProbeResult:
    config = config or DatabaseConfig()
    engine = create_sync_engine(config)
    try:
        with engine.connect() as connection:
            has_vector = connection.execute(
                text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
            ).scalar_one()
        if has_vector:
            return DatabaseProbeResult(
                layer="pgvector",
                ok=True,
                detail="pgvector extension is installed.",
            )
        return DatabaseProbeResult(
            layer="pgvector",
            ok=False,
            detail="pgvector extension is not installed in the target database.",
        )
    except Exception as exc:
        return DatabaseProbeResult(
            layer="pgvector",
            ok=False,
            detail=f"{type(exc).__name__}: {exc}",
        )
    finally:
        engine.dispose()


def create_sync_engine(config: DatabaseConfig | None = None, **kwargs) -> Engine:
    if config is None:
        config = DatabaseConfig()
    return create_engine(config.sync_url, echo=kwargs.pop("echo", False), **kwargs)


def create_session_factory(config: DatabaseConfig | None = None) -> sessionmaker[Session]:
    engine = create_sync_engine(config)
    return sessionmaker(bind=engine, expire_on_commit=False)


@lru_cache(maxsize=8)
def _get_session_factory_for_url(sync_url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=create_engine(sync_url), expire_on_commit=False)


def get_session_factory() -> sessionmaker[Session]:
    config = DatabaseConfig()
    return _get_session_factory_for_url(config.sync_url)
