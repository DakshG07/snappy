# Scanny for iOS

Scanny is a native SwiftUI companion for the existing FastAPI service. It uses the same account, folders, documents, processing pipeline, and HttpOnly session cookie as the web app.

Search has its own native tab with a bottom search field and explicit red submit button. A Gemini search request is made only when the user submits, and the app displays the backend's relevance order without re-sorting results.

## Run it

1. Install full Xcode 15 or newer and open `Scanny.xcodeproj`.
2. Start FastAPI so another device can reach it:

   ```bash
   cd backend
   .venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

3. Run Scanny in the iOS Simulator. Its default API address is `http://127.0.0.1:8000`.
4. For a physical iPhone, tap **Server** on the login screen and enter `http://YOUR-MAC.local:8000` or the Mac's LAN IP address. macOS may prompt you to allow incoming Python connections.

The Debug configuration permits HTTP for LAN development. Release only allows local-network HTTP exceptions; production should set `SCANNY_API_BASE_URL` in `Resources/Info.plist` to an HTTPS deployment.

## Capture behavior

Each shutter press is immediately compressed to a maximum 3000-pixel long edge, saved under Application Support, and handed to an independent upload task. The camera stays open and ready. Queued captures survive app interruption, failed uploads retain their JPEG for retry, and server documents are polled only while processing is active.
