from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import auth, categories, documents, media, search
from .config import settings
from .db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.document_storage_path.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(
    title="Scanny API",
    description="Local document capture and organization API",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(documents.router, prefix="/api")
app.include_router(categories.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(media.router)
app.include_router(search.router, prefix="/api")

@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


# In production the Svelte SPA is compiled into the container and served by
# FastAPI, keeping authentication cookies, API requests, and media same-origin.
frontend_dist = settings.frontend_dist_path.resolve()
frontend_assets = frontend_dist / "_app"
if frontend_assets.is_dir():
    app.mount("/_app", StaticFiles(directory=frontend_assets), name="frontend-assets")


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str):
    if full_path in {"api", "media"} or full_path.startswith(("api/", "media/")):
        raise HTTPException(status_code=404, detail="Not found")
    requested = (frontend_dist / full_path).resolve()
    if requested.is_relative_to(frontend_dist) and requested.is_file():
        return FileResponse(requested)
    index = frontend_dist / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="Web UI is not built.")
