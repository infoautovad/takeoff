from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AutoVAD"
    app_env: str = "development"
    secret_key: str = "dev-secret-change-me-civilmind-ai-2026"
    access_token_expire_minutes: int = 1440
    algorithm: str = "HS256"

    database_url: str = "sqlite:///./civilmind.db"

    storage_backend: str = "local"  # local | s3
    local_storage_path: str = "./storage"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str = "us-east-1"
    s3_bucket: str | None = None

    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-terra"
    # PDF plan sheets: render drawings for vision takeoff (not text-only)
    openai_pdf_vision_enabled: bool = True
    openai_vision_max_pages: int = 16
    openai_vision_dpi: int = 140
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    max_upload_size_mb: int = 200
    allowed_extensions: str = (
        "pdf,xlsx,xls,csv,png,jpg,jpeg,tif,tiff,zip,"
        "dxf,dwg,xml,landxml,"
        "json"  # Civil 3D / APS export packages (JSON metadata)
    )

    # Autodesk Platform Services (APS) — for native DWG / Civil 3D cloud translation
    autodesk_client_id: str | None = None
    autodesk_client_secret: str | None = None
    autodesk_bucket_key: str | None = None
    autodesk_poll_timeout_seconds: int = 540
    autodesk_poll_interval_seconds: int = 5
    # Design Automation — cloud AutoCAD/Civil 3D work items (DWG→DXF or plugin takeoff)
    design_automation_enabled: bool = True
    design_automation_nickname: str | None = None
    design_automation_engine: str = "auto"  # or e.g. Autodesk.AutoCAD+25_0
    design_automation_timeout_seconds: int = 540
    design_automation_prefer_plugin: bool = True
    design_automation_appbundle_path: str | None = None
    design_automation_fallback_model_derivative: bool = True
    cad_engine_enabled: bool = True
    cad_openai_enrichment: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_extension_list(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_extensions.split(",") if e.strip()}

    @property
    def storage_path(self) -> Path:
        path = Path(self.local_storage_path).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
