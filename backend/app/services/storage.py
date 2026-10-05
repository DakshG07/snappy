from dataclasses import dataclass
from pathlib import Path
import shutil

import cv2
import numpy as np

from ..config import settings


ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png"}
EXTENSIONS = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png"}


class InvalidImageError(ValueError):
    pass


@dataclass(slots=True)
class ValidatedImage:
    data: bytes
    image: np.ndarray
    extension: str


def validate_image(data: bytes, content_type: str | None) -> ValidatedImage:
    if not data:
        raise InvalidImageError("The uploaded image is empty.")
    if len(data) > settings.max_upload_megabytes * 1024 * 1024:
        raise InvalidImageError(f"Images must be smaller than {settings.max_upload_megabytes} MB.")
    normalized_type = (content_type or "").lower().split(";")[0]
    if normalized_type not in ALLOWED_CONTENT_TYPES:
        raise InvalidImageError("Upload a JPG, JPEG, or PNG image.")
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise InvalidImageError("The file could not be decoded as an image.")
    return ValidatedImage(data=data, image=image, extension=EXTENSIONS[normalized_type])


def document_directory(document_id: int) -> Path:
    directory = settings.document_storage_path / str(document_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_original(document_id: int, image: ValidatedImage) -> str:
    relative = Path(str(document_id)) / f"original{image.extension}"
    destination = settings.document_storage_path / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(image.data)
    return relative.as_posix()


def save_jpeg(document_id: int, filename: str, image: np.ndarray, quality: int = 92) -> str:
    relative = Path(str(document_id)) / filename
    destination = settings.document_storage_path / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise OSError(f"Could not encode {filename}")
    destination.write_bytes(encoded.tobytes())
    return relative.as_posix()


def save_png(document_id: int, filename: str, image: np.ndarray) -> str:
    relative = Path(str(document_id)) / filename
    destination = settings.document_storage_path / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".png", image, [cv2.IMWRITE_PNG_COMPRESSION, 4])
    if not ok:
        raise OSError(f"Could not encode {filename}")
    destination.write_bytes(encoded.tobytes())
    return relative.as_posix()


def absolute_path(relative_path: str) -> Path:
    return settings.document_storage_path / relative_path


def media_url(relative_path: str | None) -> str | None:
    return f"/media/{relative_path}" if relative_path else None


def delete_document_files(document_id: int) -> None:
    """Delete only the storage directory assigned to one document."""
    storage_root = settings.document_storage_path.resolve()
    directory = (storage_root / str(document_id)).resolve()
    if directory.parent != storage_root:
        raise ValueError("Invalid document storage path")
    if directory.exists():
        shutil.rmtree(directory)
