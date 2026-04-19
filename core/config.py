from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    openai_api_key: str = ""
    secret_key: str = "dev-secret-change-in-prod"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    database_url: str = "sqlite:///./placeholdr.db"
    temp_upload_dir: str = "./temp_uploads"
    tribe_model_path: str = "./brain/tribe_v2/pretrained"
    tribe_enabled: bool = False
    environment: str = "development"
    max_upload_size_mb: int = 500
    ffmpeg_path: str = r"C:\Users\moksh\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
    dataset_csv_path: str = "./data/youtube_trending.csv"

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
