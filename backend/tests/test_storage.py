from app.services import storage


def test_delete_document_files_is_scoped_to_one_directory(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(storage.settings, "document_storage_path", tmp_path)
    target = tmp_path / "7"
    sibling = tmp_path / "8"
    target.mkdir()
    sibling.mkdir()
    (target / "scan.jpg").write_bytes(b"target")
    (sibling / "scan.jpg").write_bytes(b"keep")

    storage.delete_document_files(7)

    assert not target.exists()
    assert (sibling / "scan.jpg").read_bytes() == b"keep"
