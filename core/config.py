from pydantic_settings import BaseSettings
from typing import Optional, List


class Settings(BaseSettings):
    openai_api_key: str = ""
    secret_key: str = "dev-secret-change-in-prod"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    database_url: str = "sqlite:///./nuro.db"
    temp_upload_dir: str = "./temp_uploads"
    tribe_model_path: str = "./brain/tribe_v2/pretrained"
    tribe_enabled: bool = False
    environment: str = "development"
    max_upload_size_mb: int = 500
    ffmpeg_path: str = ""
    dataset_csv_path: str = "./data/youtube_trending.csv"

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # Comma-separated list of allowed CORS origins. Defaults to wildcard in dev.
    cors_origins: str = "*"

    @property
    def cors_origins_list(self) -> List[str]:
        if self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    class Config:
        env_file = ".env"


settings = Settings()
