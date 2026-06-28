from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent
PROJECT_ENV_FILE = PROJECT_DIR / ".env"
BACKEND_ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    app_name: str = "Security Agent Web Demo"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    ark_model: str = "ep-m-20260518145505-mt7gb"
    ark_api_key: str = ""
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_reasoning_effort: str = ""
    ark_timeout_seconds: float = 30
    ark_max_retries: int = 0

    agent_model_timeout_seconds: float = 25
    agent_tool_timeout_seconds: float = 15
    agent_history_max_messages: int = 20

    web_search_enabled: bool = True
    web_search_timeout_seconds: int = 10

    vikingdb_ak: str = ""
    vikingdb_sk: str = ""
    vikingdb_host: str = "api-vikingdb.vikingdb.ap-southeast-1.bytepluses.com"
    vikingdb_region: str = "ap-southeast-1"
    vikingdb_project_name: str = "default"
    vikingdb_collection_name: str = "yingshi_bp"
    vikingdb_index_name: str = "yingshi_bp_index"

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ENV_FILE, BACKEND_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
