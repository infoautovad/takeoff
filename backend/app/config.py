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
    secret_key: str = "dev-secret-change-me-autovad-ai-2026"
    access_token_expire_minutes: int = 1440
    algorithm: str = "HS256"

    database_url: str = "sqlite:///./autovad.db"

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
    # Scan every page by default (upload page count is NOT limited by this).
    openai_vision_scan_all_pages: bool = True
    # Pages per OpenAI vision request (chunking only — not a document page limit).
    openai_vision_batch_pages: int = 8
    # Optional hard ceiling when scan_all is false, or safety stop when >0 with scan_all.
    # 0 = no ceiling (process the full PDF).
    openai_vision_max_pages: int = 0
    openai_vision_dpi: int = 150
    openai_vision_min_score: float = 18.0
    # When not scanning all pages, still force-include utility/schedule sheets
    openai_vision_force_utility_pages: bool = True
    # Seconds per OpenAI HTTP call (one batch). Stuck batch is skipped; remaining pages still run.
    openai_request_timeout_seconds: float = 600.0
    openai_max_retries: int = 1
    # Wall-clock budget for ALL vision batches. 0 = scan every page with no time cap.
    openai_vision_max_seconds: float = 0.0
    # Large files: smaller batches for RAM only. 0 max pages / 0 seconds = no skip.
    openai_vision_large_page_threshold: int = 80
    openai_vision_large_file_mb: int = 80
    openai_vision_large_max_pages: int = 0
    openai_vision_large_batch_pages: int = 2
    openai_vision_large_dpi: int = 150
    openai_vision_large_max_seconds: float = 0.0
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # 0 = unlimited upload size (no MB cap on document / bid uploads).
    max_upload_size_mb: int = 0
    allowed_extensions: str = (
        "pdf,xlsx,xls,csv,png,jpg,jpeg,tif,tiff,zip,"
        "dxf,dwg,xml,landxml,"
        "json"  # Civil 3D / APS export packages (JSON metadata)
    )

    # Autodesk Platform Services (APS) — for native DWG / Civil 3D cloud translation
    autodesk_client_id: str | None = None
    autodesk_client_secret: str | None = None
    autodesk_bucket_key: str | None = None
    autodesk_poll_timeout_seconds: int = 3600
    autodesk_poll_interval_seconds: int = 5
    # Design Automation — cloud AutoCAD/Civil 3D work items (DWG→DXF or plugin takeoff)
    design_automation_enabled: bool = True
    design_automation_nickname: str | None = None
    design_automation_engine: str = "auto"  # or e.g. Autodesk.AutoCAD+25_0
    design_automation_timeout_seconds: int = 3600
    design_automation_prefer_plugin: bool = True
    design_automation_appbundle_path: str | None = None
    design_automation_fallback_model_derivative: bool = True
    cad_engine_enabled: bool = True
    cad_openai_enrichment: bool = True
    # Entity payload caps persisted on CadModel.entities_json (0 = keep all parsed rows).
    cad_store_lines_limit: int = 5000
    cad_store_polylines_limit: int = 5000
    cad_store_circles_limit: int = 2000
    cad_store_hatches_limit: int = 2000
    # Optional path override for AutoVAD master bid template workbook.
    # When empty, backend looks for "Bid Item List 2026.xlsx" at repo root.
    autovad_master_bid_template_path: str | None = None
    autovad_master_bid_template_sheet: str = "Bid Items"

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
