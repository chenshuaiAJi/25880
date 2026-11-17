from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.1.0"
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:jlauto_dev@127.0.0.1:5432/jlauto"
    host: str = "127.0.0.1"
    port: int = 8787
    data_root: Path | None = None

    def resolved_data_root(self) -> Path:
        if self.data_root is not None:
            return self.data_root
        return REPO_ROOT / "file" / "2026年财务总报表"


def load_settings() -> Settings:
    return Settings()
