import uuid
from pathlib import Path

import structlog

from app.config import get_settings

settings = get_settings()
logger = structlog.get_logger()


class StorageError(Exception):
    def __init__(self, detail: str):
        self.detail = detail


class LocalStorage:
    """Local filesystem storage for development."""

    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir or settings.upload_dir)

    def _ensure_dir(self, subdir: str) -> Path:
        dir_path = self.base_dir / subdir
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    async def save_file(
        self,
        file_content: bytes,
        subdir: str,
        extension: str,
    ) -> str:
        """Save file with a UUID name. Returns the relative file path."""
        dir_path = self._ensure_dir(subdir)
        filename = f"{uuid.uuid4().hex}{extension}"
        file_path = dir_path / filename
        relative_path = f"{subdir}/{filename}"

        try:
            file_path.write_bytes(file_content)
            await logger.ainfo(
                "File saved",
                path=relative_path,
                size=len(file_content),
            )
            return relative_path
        except OSError as e:
            await logger.aerror("File save failed", error=str(e))
            raise StorageError("Failed to save file") from e

    async def read_file(self, relative_path: str) -> bytes:
        """Read a file by its relative path."""
        file_path = self.base_dir / relative_path

        # Prevent path traversal
        resolved = file_path.resolve()
        base_resolved = self.base_dir.resolve()
        if not str(resolved).startswith(str(base_resolved)):
            raise StorageError("Invalid file path")

        if not file_path.exists():
            raise StorageError("File not found")

        try:
            return file_path.read_bytes()
        except OSError as e:
            await logger.aerror("File read failed", error=str(e))
            raise StorageError("Failed to read file") from e

    async def delete_file(self, relative_path: str) -> None:
        """Delete a file by its relative path."""
        file_path = self.base_dir / relative_path

        resolved = file_path.resolve()
        base_resolved = self.base_dir.resolve()
        if not str(resolved).startswith(str(base_resolved)):
            raise StorageError("Invalid file path")

        try:
            if file_path.exists():
                file_path.unlink()
                await logger.ainfo("File deleted", path=relative_path)
        except OSError as e:
            await logger.aerror("File delete failed", error=str(e))
            raise StorageError("Failed to delete file") from e

    def get_absolute_path(self, relative_path: str) -> str:
        """Get absolute filesystem path for a relative path."""
        return str((self.base_dir / relative_path).resolve())


def get_storage() -> LocalStorage:
    return LocalStorage()
