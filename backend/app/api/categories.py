from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..constants import REVIEW_CATEGORY_NAME
from ..db import get_db
from ..models import Category, Document, User
from ..schemas import CategoryCreate, CategoryRead, CategoryUpdate
from ..services.document_index import refresh_document_embedding


router = APIRouter(prefix="/categories", tags=["categories"])


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.split()).strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="Folder name cannot be empty.")
    return cleaned


def _read(category: Category, count: int) -> CategoryRead:
    return CategoryRead(
        id=category.id,
        name=REVIEW_CATEGORY_NAME if category.is_system else category.name,
        created_at=category.created_at,
        is_system=category.is_system,
        document_count=count,
    )


@router.get("", response_model=list[CategoryRead])
def list_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CategoryRead]:
    rows = (
        db.query(Category, func.count(Document.id))
        .outerjoin(Document)
        .filter(Category.user_id == current_user.id)
        .group_by(Category.id)
        .order_by(Category.is_system.asc(), func.lower(Category.name))
        .all()
    )
    return [_read(category, count) for category, count in rows]


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CategoryRead:
    name = _clean_name(payload.name)
    if db.query(Category).filter(
        Category.user_id == current_user.id,
        func.lower(Category.name) == name.lower(),
    ).first():
        raise HTTPException(status_code=409, detail="A folder with that name already exists.")
    category = Category(name=name, user_id=current_user.id)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A folder with that name already exists.")
    db.refresh(category)
    return _read(category, 0)


@router.patch("/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CategoryRead:
    category = db.query(Category).filter(
        Category.id == category_id,
        Category.user_id == current_user.id,
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="Folder not found.")
    if category.is_system:
        raise HTTPException(status_code=403, detail="The Needs Review folder cannot be renamed.")
    name = _clean_name(payload.name)
    duplicate = db.query(Category).filter(
        Category.user_id == current_user.id,
        func.lower(Category.name) == name.lower(),
        Category.id != category.id,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="A folder with that name already exists.")
    name_changed = category.name != name
    category.name = name
    document_ids: list[int] = []
    if name_changed:
        documents = db.query(Document).filter(Document.category_id == category.id).all()
        document_ids = [document.id for document in documents if document.ocr_text]
        for document in documents:
            document.embedding_json = None
            document.embedding_model = None
            document.embedding_updated_at = None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A folder with that name already exists.")
    count = db.query(Document).filter(Document.category_id == category.id).count()
    for document_id in document_ids:
        background_tasks.add_task(refresh_document_embedding, document_id)
    return _read(category, count)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    category = db.query(Category).filter(
        Category.id == category_id,
        Category.user_id == current_user.id,
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="Folder not found.")
    if category.is_system:
        raise HTTPException(status_code=403, detail="The Needs Review folder cannot be deleted.")
    if db.query(Document).filter(Document.category_id == category.id).first():
        raise HTTPException(status_code=409, detail="Move or remove this folder's documents before deleting it.")
    db.delete(category)
    db.commit()
