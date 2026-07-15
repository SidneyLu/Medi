import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    api_prefix: str
    secret_key: str
    session_expire_seconds: int
    database_path: Path
    upload_dir: Path
    seed_knowledge_path: Path
    qwen_model: str
    qwen_api_key: str | None
    msd_source_base_url: str
    cors_origins: list[str]


@lru_cache
def get_settings() -> Settings:
    root_dir = Path(__file__).resolve().parents[2]
    database_path = Path(os.getenv("MEDI_SQLITE_PATH", root_dir / "storage" / "medi.sqlite3"))
    upload_dir = Path(os.getenv("UPLOAD_DIR", root_dir / "storage" / "uploads"))
    seed_knowledge_path = root_dir / "app" / "data" / "seed_knowledge.json"

    if not database_path.is_absolute():
        database_path = root_dir / database_path
    if not upload_dir.is_absolute():
        upload_dir = root_dir / upload_dir

    database_path.parent.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)

    origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return Settings(
        app_name=os.getenv("APP_NAME", "Medi Backend"),
        app_env=os.getenv("APP_ENV", "development"),
        api_prefix=os.getenv("API_PREFIX", "/api/v1"),
        secret_key=os.getenv("SECRET_KEY", "dev-only-secret-change-me"),
        session_expire_seconds=int(os.getenv("SESSION_EXPIRE_SECONDS", os.getenv("ACCESS_TOKEN_EXPIRE_SECONDS", "7200"))),
        database_path=database_path,
        upload_dir=upload_dir,
        seed_knowledge_path=seed_knowledge_path,
        qwen_model=os.getenv("QWEN_MODEL", "qwen3.6-plus"),
        qwen_api_key=os.getenv("QWEN_API_KEY") or None,
        msd_source_base_url=os.getenv("MSD_SOURCE_BASE_URL", "https://www.msdmanuals.cn/home"),
        cors_origins=[item.strip() for item in origins.split(",") if item.strip()],
    )
