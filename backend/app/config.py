from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    database_path: Path = BACKEND_DIR / "data" / "scanny.db"
    document_storage_path: Path = BACKEND_DIR / "data" / "documents"
    paddle_cache_path: Path = BACKEND_DIR / "data" / "paddle"
    frontend_dist_path: Path = BACKEND_DIR.parent / "frontend" / "build"
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_max_output_tokens: int = 8192
    gemini_timeout_seconds: float = 90
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_dimensions: int = 768
    gemini_embedding_timeout_seconds: float = 25
    embedding_max_input_chars: int = 12000
    semantic_search_min_score: float = 0.55
    semantic_search_max_results: int = 10
    classification_confidence_threshold: float = 0.65
    scan_confidence_threshold: float = 0.60
    scan_denoise_strength: float = 4.0
    scan_background_sigma: float = 25.0
    scan_clahe_clip_limit: float = 1.5
    scan_clahe_tile_size: int = 8
    scan_sharpen_amount: float = 0.25
    scan_bw_block_size: int = 31
    scan_bw_c: int = 9
    debug: bool = False
    max_upload_megabytes: int = 30
    session_days: int = 30
    secure_cookies: bool = False

    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", Path.cwd() / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_path", "document_storage_path", "paddle_cache_path", "frontend_dist_path", mode="before")
    @classmethod
    def make_path_absolute(cls, value: str | Path) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else (BACKEND_DIR.parent / path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
