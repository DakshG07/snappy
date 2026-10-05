from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import Document, User
from ..services.storage import absolute_path


router = APIRouter(prefix="/media", tags=["media"])


@router.get("/{document_id}/{filename}", response_class=FileResponse)
def get_document_media(
    document_id: int,
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id,
    ).first()
    if document is None:
        raise HTTPException(status_code=404, detail="File not found.")

    requested = Path(str(document_id)) / filename
    allowed = {
        Path(path)
        for path in (document.original_image_path, document.scanned_image_path, document.bw_image_path)
        if path
    }
    if requested not in allowed:
        raise HTTPException(status_code=404, detail="File not found.")
    path = absolute_path(requested.as_posix())
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path)
