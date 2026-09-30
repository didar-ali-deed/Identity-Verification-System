import pytest

from app.utils.storage import LocalStorage, StorageError


@pytest.mark.asyncio
async def test_sibling_directory_is_not_inside_storage(tmp_path):
    storage = LocalStorage(str(tmp_path / "uploads"))
    sibling = tmp_path / "uploads-private"
    sibling.mkdir()
    secret = sibling / "secret.txt"
    secret.write_text("synthetic", encoding="utf8")
    with pytest.raises(StorageError):
        await storage.read_file("../uploads-private/secret.txt")
    with pytest.raises(StorageError):
        await storage.delete_file("../uploads-private/secret.txt")
    with pytest.raises(StorageError):
        storage.get_absolute_path("../uploads-private/secret.txt")
    assert secret.exists()


@pytest.mark.asyncio
async def test_storage_round_trip(tmp_path):
    storage = LocalStorage(str(tmp_path))
    path = await storage.save_file(b"synthetic", "documents/demo", ".jpg")
    assert await storage.read_file(path) == b"synthetic"
    await storage.delete_file(path)
    assert not (tmp_path / path).exists()
