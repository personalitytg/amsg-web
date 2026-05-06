from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Override via env or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AMSG_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "AMSG Web"
    debug: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    runs_dir: Path = Path("./runs")
    cache_dir: Path = Path("./cache")
    job_ttl_seconds: int = 3600
    max_concurrent_jobs: int = 2

    def ensure_dirs(self) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
