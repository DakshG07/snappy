# Scanny backend

FastAPI owns document ingestion, OpenCV page detection and post-processing, local storage, and Gemini Vision document understanding. One multimodal Gemini request returns a faithful Markdown transcription, concise title, validated folder, and category confidence. Optional PaddleOCR stays cold unless that Gemini request fails.

User accounts use Argon2 password hashes and database-backed sessions. The raw session token is only sent in the `scanny_session` HttpOnly cookie; only its SHA-256 hash is stored. All document, category, processing, and media access is scoped to the authenticated user.

The upload endpoint saves the original and returns immediately while scanning and document understanding continue in a background task. Every stage degrades independently: failed detection creates a usable fallback scan with `needs_review`, Gemini failures can fall back to Paddle transcription, and no AI outage discards a document.

Semantic search uses a configurable Gemini embedding model and stores normalized vectors as JSON on each SQLite document. `GET /api/search?q=...` embeds only the query during normal searches, calculates cosine similarity over the authenticated user's documents, applies a strict relevance threshold, and returns at most the configured result count. Missing legacy embeddings are generated lazily; title and folder edits invalidate and refresh their document embeddings asynchronously.

Run tests from this directory with `pytest`.

For Railway, the root Docker image serves the compiled Svelte SPA and API from one Uvicorn process. Attach a persistent Volume at `/data`; the production defaults place SQLite, document images, and Paddle model caches there. Keep this SQLite deployment to one service replica.
