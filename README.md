# Scanny

Scanny turns handheld photos of school papers into cleaned, searchable, automatically organized scans. This repository contains the MVP server and its lightweight document-library UI.

## Quick start

Once the backend and frontend dependencies are installed, launch both together from the repository root:

```bash
./start.sh
```

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`; interactive documentation is at `http://localhost:8000/docs`.

Gemini Vision performs faithful Markdown transcription, title generation, and folder classification from the processed scan; set `GEMINI_API_KEY` in `backend/.env`. PaddleOCR is an optional emergency transcription fallback and is never loaded during successful Gemini processing. Install it with `pip install -r requirements-ocr.txt` if that fallback is desired. If both services are unavailable, the scan remains viewable under `Needs Review` with a timestamp-based title.

After transcription, Scanny creates a Gemini text embedding from the title, folder, and Markdown content. The web and iOS Recent views use `/api/search` for per-user semantic retrieval; weak matches are filtered rather than returned merely because they rank highest. Existing documents are indexed lazily the first time search is used.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`, create an account, and sign in. During development, Vite proxies `/api` and authenticated `/media` requests to FastAPI.

### iOS

The native SwiftUI companion lives in [`ios/Scanny.xcodeproj`](ios/Scanny.xcodeproj). It shares the web app's accounts, documents, folders, and server-side scanning pipeline. See [`ios/README.md`](ios/README.md) for Xcode, Simulator, physical-device, and LAN setup.

## Configuration

Copy `.env.example` to `backend/.env` if you want to override defaults. Images and SQLite data stay in `backend/data` by default. Semantic search is configured with `GEMINI_EMBEDDING_MODEL`, `SEMANTIC_SEARCH_MIN_SCORE`, and `SEMANTIC_SEARCH_MAX_RESULTS`. Set `SECURE_COOKIES=true` when serving Scanny over HTTPS in production.

## Deploy to Railway

Scanny is packaged as one Docker service. Railway automatically detects the root `Dockerfile`, builds the Svelte SPA, installs the complete FastAPI/OpenCV/PaddleOCR stack, and starts FastAPI on Railway's injected `PORT`. FastAPI serves the web app, API, and protected media from the same domain.

1. Push this repository to GitHub and create a Railway service from that repository. Leave the root directory at the repository root.
2. Add the required service variable `GEMINI_API_KEY`. Do not commit the key to GitHub.
3. Add a Railway Volume to the service with mount path `/data`. This persists the SQLite database, uploaded scans, and downloaded PaddleOCR models across deployments.
4. Generate a public Railway domain under the service's Networking settings.
5. Keep the service at one replica while using SQLite and a single attached Volume.

The image already configures these production paths:

```text
DATABASE_PATH=/data/scanny.db
DOCUMENT_STORAGE_PATH=/data/documents
PADDLE_CACHE_PATH=/data/paddle
SECURE_COOKIES=true
```

Optional tuning variables from `.env.example`, including Gemini models and semantic-search thresholds, can be added in Railway's Variables tab. The deployment health check is `/api/health`.

For the iOS app, set its server address to the generated `https://…railway.app` domain. HTTPS is required for the Release build.

## Authentication

Browser access uses database-backed sessions in an HttpOnly cookie. Documents, folders, and media files are private to each account. Existing pre-authentication data is preserved and assigned to the first account registered after migration.

Future hardware should use a separate per-device token tied to a user; devices should not store a user's email and password.
