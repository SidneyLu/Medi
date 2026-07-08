from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "EDBuy RAG Prototype"
    postgres_url: str = Field(alias="POSTGRES_URL")
    chroma_host: str = Field(alias="CHROMA_HOST")
    chroma_port: int = Field(alias="CHROMA_PORT")
    dashscope_api_key: str = Field(default="", alias="DASHSCOPE_API_KEY")
    dashscope_base_url: str = Field(alias="DASHSCOPE_BASE_URL")
    chat_model: str = Field(alias="CHAT_MODEL")
    embedding_model: str = Field(alias="EMBEDDING_MODEL")
    embedding_dim: int = Field(alias="EMBEDDING_DIM")
    rerank_model: str = Field(alias="RERANK_MODEL")
    seed_data_dir: Path = Field(default=Path("/workspace/data/seed"), alias="SEED_DATA_DIR")
    processed_data_dir: Path = Field(default=Path("/workspace/data/processed"), alias="PROCESSED_DATA_DIR")
    raw_data_dir: Path = Field(default=Path("/workspace/data/raw"), alias="RAW_DATA_DIR")
    chroma_collection_name: str = "product_documents"


@lru_cache
def get_settings() -> Settings:
    return Settings()
