from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class CategoryUpdate(CategoryCreate):
    pass


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    is_system: bool
    document_count: int = 0


class CategoryBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_system: bool


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    category_id: int
    category: CategoryBrief
    created_at: datetime
    original_image_url: str
    scanned_image_url: str
    bw_image_url: str | None
    ocr_text: str | None  # Markdown transcription; legacy API field name.
    ocr_error: str | None
    classification_error: str | None
    processing_status: str
    classification_confidence: float | None
    detected_corners: dict[str, Any] | None
    scan_confidence: float | None
    scan_debug: dict[str, Any] | None
    scan_mode: Literal["color", "black_and_white"]


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category_id: int | None = None


class DocumentCorners(BaseModel):
    top_left: tuple[float, float]
    top_right: tuple[float, float]
    bottom_right: tuple[float, float]
    bottom_left: tuple[float, float]


class DocumentAdjustment(BaseModel):
    corners: DocumentCorners
    scan_mode: Literal["color", "black_and_white"] = "color"


class SearchDebug(BaseModel):
    semantic_score: float
    keyword_boost: float


class SearchResult(BaseModel):
    document: DocumentRead
    score: float
    debug: SearchDebug | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


class AuthCredentials(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class RegistrationCredentials(AuthCredentials):
    password: str = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
