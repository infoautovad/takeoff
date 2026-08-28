import uuid
from pathlib import Path

import aiofiles

from app.config import get_settings


class StorageService:
    """Local storage now; S3-ready interface for later AWS deployment."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.root = self.settings.storage_path

    def build_key(self, project_id: int, filename: str) -> str:
        safe_name = Path(filename).name.replace(" ", "_")
        unique = uuid.uuid4().hex[:12]
        return f"projects/{project_id}/{unique}_{safe_name}"

    async def save_file(self, key: str, data: bytes) -> str:
        if self.settings.storage_backend == "s3":
            return await self._save_s3(key, data)
        return await self._save_local(key, data)

    async def save_upload_file(self, key: str, upload, *, max_bytes: int | None = None) -> int:
        """Stream an upload to disk in chunks so 1GB+ PDFs are not loaded into RAM."""
        if self.settings.storage_backend == "s3":
            data = await upload.read()
            if max_bytes and max_bytes > 0 and len(data) > max_bytes:
                raise ValueError(f"File exceeds {max_bytes} byte limit")
            await self._save_s3(key, data)
            return len(data)
        return await self._save_local_stream(key, upload, max_bytes=max_bytes)

    async def _save_local(self, key: str, data: bytes) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "wb") as f:
            await f.write(data)
        return str(path)

    async def _save_local_stream(self, key: str, upload, *, max_bytes: int | None = None) -> int:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        chunk_size = 1024 * 1024
        try:
            async with aiofiles.open(path, "wb") as f:
                while True:
                    chunk = await upload.read(chunk_size)
                    if not chunk:
                        break
                    size += len(chunk)
                    if max_bytes and max_bytes > 0 and size > max_bytes:
                        raise ValueError(f"File exceeds {max_bytes} byte limit")
                    await f.write(chunk)
        except Exception:
            if path.exists():
                path.unlink(missing_ok=True)
            raise
        return size

    async def _save_s3(self, key: str, data: bytes) -> str:
        # Placeholder for AWS S3 integration (Phase: operations / deployment)
        import boto3

        if not self.settings.s3_bucket:
            raise RuntimeError("S3_BUCKET is not configured")
        client = boto3.client(
            "s3",
            region_name=self.settings.aws_region,
            aws_access_key_id=self.settings.aws_access_key_id,
            aws_secret_access_key=self.settings.aws_secret_access_key,
        )
        client.put_object(Bucket=self.settings.s3_bucket, Key=key, Body=data)
        return f"s3://{self.settings.s3_bucket}/{key}"

    def resolve_local_path(self, key: str) -> Path:
        return self.root / key

    def delete_file(self, key: str) -> None:
        if self.settings.storage_backend == "local":
            path = self.resolve_local_path(key)
            if path.exists():
                path.unlink()


storage_service = StorageService()
