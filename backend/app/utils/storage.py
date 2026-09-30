import asyncio
import shutil
import uuid
from pathlib import Path

from app.config import get_settings


class StorageError(Exception):
    def __init__(self, detail: str):
        self.detail = detail


class LocalStorage:
    """Private filesystem storage. All paths must remain inside the configured root."""

    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir or get_settings().upload_dir).resolve()

    def _resolve(self, relative_path: str) -> Path:
        path = (self.base_dir / relative_path).resolve()
        if not path.is_relative_to(self.base_dir):
            raise StorageError("Invalid file path")
        return path

    async def save_file(self, file_content: bytes, subdir: str, extension: str) -> str:
        if extension not in (".jpg", ".png"):
            raise StorageError("Invalid file extension")
        relative = f"{subdir}/{uuid.uuid4().hex}{extension}"
        path = self._resolve(relative)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(path.write_bytes, file_content)
        except OSError as exc:
            raise StorageError("Failed to save file") from exc
        return relative

    async def read_file(self, relative_path: str) -> bytes:
        try:
            return await asyncio.to_thread(self._resolve(relative_path).read_bytes)
        except OSError as exc:
            raise StorageError("Failed to read file") from exc

    async def delete_file(self, relative_path: str) -> None:
        try:
            await asyncio.to_thread(self._resolve(relative_path).unlink, missing_ok=True)
        except OSError as exc:
            raise StorageError("Failed to delete file") from exc

    def get_absolute_path(self, relative_path: str) -> str:
        return str(self._resolve(relative_path))

    async def delete_application_files(self, application_id: uuid.UUID) -> None:
        for category in ("documents", "selfies"):
            # UUID-derived targets are checked by _resolve against the upload root.
            target = self._resolve(f"{category}/{application_id}")
            if target.is_dir():
                await asyncio.to_thread(shutil.rmtree, target)


def get_storage() -> LocalStorage:
    return LocalStorage()
