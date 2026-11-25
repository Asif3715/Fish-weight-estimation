# AquaPense Data Collection

A local data collection workspace for aquarium research. The edge PC records RTSP cameras, organizes collection runs and feeding-event markers, and queues completed files for Google Drive upload. A browser dashboard provides collection controls, camera configuration and upload status.

## Technology

| Component | Technology |
| --- | --- |
| Frontend | React, TypeScript, Vite, CSS |
| Backend | Python, FastAPI, Uvicorn |
| Camera recording | FFmpeg over RTSP/TCP |
| Local catalogue | SQLite |
| Cloud uploads | Google Drive API with Desktop OAuth |

ESP32 sensor integration is planned; no sensor readings are currently collected. Dashboard updates currently use polling.

## Repository layout

```text
.
├── backend/
│   ├── app/
│   │   ├── core/              # Configuration
│   │   ├── db/                # SQLite catalogue
│   │   ├── modules/
│   │   │   ├── cameras/
│   │   │   ├── recordings/
│   │   │   ├── drive/
│   │   │   └── ...            # Reserved integration modules
│   │   └── main.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/               # App composition and state provider
│   │   ├── components/        # Layout and shared UI
│   │   ├── features/          # Overview, cameras, experiments, recordings, Drive
│   │   ├── hooks/             # State and data loading
│   │   ├── lib/               # API client
│   │   ├── types/
│   │   ├── styles/
│   │   └── main.tsx
│   └── package.json
├── runtime/                  # Local data; created at runtime, excluded from Git
├── .gitignore
└── README.md
```

The repository contains application source and this documentation. Runtime data, credentials, dependencies and generated builds are excluded from version control.

## Local setup

Requirements: Python 3.11 or later, Node.js with npm, and FFmpeg available on PATH. Both cameras must be reachable from the edge PC. Internet is needed for Google authorization and uploads, while recording saves locally.

### Backend

Open PowerShell in the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

If `python` is not on PATH, use the full path to your Python executable for the first command that creates the virtual environment.

### Frontend

Open a second PowerShell terminal in the repository root:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

- Dashboard: http://127.0.0.1:5173
- Backend API documentation: http://127.0.0.1:8000/docs

Keep both terminals open. Press Ctrl+C in each to stop. Stop active recordings through the dashboard before shutting down.

### Frontend production build

```powershell
cd frontend
npm.cmd run build
```

When `frontend/dist` exists at backend startup, FastAPI also serves the built dashboard at http://127.0.0.1:8000. Restart the backend after the first build. Development mode uses the Vite server on port 5173, which proxies API requests to port 8000.

## Runtime folder: local application data

By default, the backend creates `runtime` beside `backend` and `frontend`:

```text
runtime/
├── catalogue.sqlite
├── secrets/
│   ├── credentials.json       # Google Desktop OAuth app configuration
│   └── token.json             # Created only after successful authorization
└── recordings/
    └── <collection-id>/
        ├── manifest.json
        ├── events.json        # Written when the collection is stopped
        └── <camera-folder>/
            └── <connection-attempt>/
                ├── 000000.mkv
                ├── 000001.mkv
                └── segments.csv
```

- **`catalogue.sqlite`** stores camera settings, collection records, events, file paths and upload state. Camera passwords are currently stored in this database; protect the runtime directory with OS account permissions.
- **`secrets`** holds Google configuration and authorization. Never commit or share these files. They are not included in recording uploads.
- **`recordings`** holds compressed video chunks and collection metadata. Video segments target 60 seconds; actual boundaries depend on camera keyframes.
- Each camera gets a stable name-derived folder when first saved. Renaming its display name keeps the folder identity intact.
- Google Drive receives catalogued recording chunks and collection metadata. Local copies remain after upload; there is no automatic deletion policy.
- Deleting the database loses local configuration and upload tracking, even if video files remain on disk. Back up the runtime data as a unit when migrating the recorder.

The runtime folder is **local data, not source code**. Git ignores it. A fresh clone will not include recordings, camera configuration or Google authorization.

### Choose another data disk

Set an absolute path before starting the backend:

```powershell
$env:AQUAPENSE_DATA = 'D:\AquaPenseData'
$env:FFMPEG_PATH = 'C:\Tools\ffmpeg\bin\ffmpeg.exe'
```

`AQUAPENSE_DATA` changes the location of all runtime data, including the database and secrets. It does not move existing data automatically. `FFMPEG_PATH` is optional when FFmpeg is already on PATH. Configuration is currently read from environment variables; `.env` files are not automatically loaded.

## Collection workflow

1. Open **Cameras**, add a camera, and enter its name, local address, username and password. Repeat for additional cameras. The default RTSP path follows the reference script; adjust it for each device as needed.
2. Open **Overview**, select session or continuous recording, and start collection. Both modes currently run until manually stopped; continuous mode also supports event markers without restarting the cameras.
3. Use **Experiments** to mark observation starts, feed additions, disturbances and observation ends. Include the amount or uncertainty in the note when relevant.
4. Stop through the dashboard to finalize the current recording and save event metadata.
5. Open **Recordings** to inspect catalogued files and upload state.

Recording workers reconnect independently. The current implementation pauses recording attempts at low disk space and does not automatically delete old data.

## Google Drive setup

1. Enable Google Drive API in your Google Cloud project.
2. Configure consent and authorized test users, then create a **Desktop app** OAuth client.
3. Save the downloaded JSON as `runtime/secrets/credentials.json`, or under the equivalent directory in `AQUAPENSE_DATA`.
4. Open **Storage & Drive → Connect Google Drive** and complete consent in the browser on the edge PC.
5. Leave the destination blank to create an app-owned `AquaPense Collection` folder. An existing destination must be accessible to the app under its granted permissions.

The backend uses the limited `drive.file` scope and stores authorization in `token.json`. It checks pending uploads every 30 seconds after authorization; **Upload now** also triggers the queue. Failed files remain pending for retry. Run and camera folder structure is reproduced in Drive.

This version supports one authorized Google account. Initial sign-in uses a local browser callback; remote authorization through VPN and multi-account selection are not implemented.

## Validation and current limitations

The frontend production build and isolated API checks have passed. Live hardware and Google uploads require separate validation.

- Live preview and synchronized playback are not implemented.
- The target is at least 5 distinct recorded frames per second per camera. Actual saved FPS is not yet measured or guaranteed.
- UTC event timestamps are collected, but camera delay and precise video-to-event alignment remain unverified. A shared visible timing marker and timestamp mapping are required for validated synchronization.
- ESP32/MQTT sensor collection is not implemented.
- Feeding markers exist; a structured experiment lifecycle and automated baseline/post-feeding timers are not implemented.
- Dashboard authentication for LAN/VPN access is not implemented. Run the current application on localhost only.
- Google token presence indicates saved authorization, not a guarantee that the grant remains valid.

## Git

```powershell
git add .gitignore README.md backend/ frontend/
```

Review `git status` before committing. Runtime data, OAuth files, virtual environments, `node_modules` and `dist` must remain excluded.
