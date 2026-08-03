import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 주요 환경 변수 설정 (.env 파일에서 주입받음)
    CHROMA_HOST: str
    CHROMA_PORT: int
    MODEL_NAME: str
    VAULT_PATH: str
    DISCORD_WEBHOOK_URL: str = ""
    SPLIT_THRESHOLD: int = 2500  # 단일/분할 정제 분기 기준 (자)
    BIFROST_BASE_URL: str
    BIFROST_API_KEY: str
    OLLAMA_BASE_URL: str
    TOOL_SERVER_API_KEY: str

    @property
    def RAW_DIR(self) -> str:
        return os.path.join(self.VAULT_PATH, "raw")

    @property
    def TECH_DIR(self) -> str:
        return os.path.join(self.VAULT_PATH, "wiki_tech")

    @property
    def CAREER_DIR(self) -> str:
        return os.path.join(self.VAULT_PATH, "wiki_career")

    @property
    def PERSONAL_DIR(self) -> str:
        return os.path.join(self.VAULT_PATH, "wiki_hyeseong")

    @property
    def ARCHIVE_DIR(self) -> str:
        return os.path.join(self.VAULT_PATH, "archive")

    @property
    def ERROR_DIR(self) -> str:
        return os.path.join(self.VAULT_PATH, "error")

    @property
    def SCHEMA_PATH(self) -> str:
        return os.path.join(self.VAULT_PATH, "schema.md")

    class Config:
        env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        extra = "ignore"

settings = Settings()
