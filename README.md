# Mellow Biz

A lightweight local dashboard for tracking income, expenses and payroll, with a summary page and simple HTTP API. The repo includes a browser-only front end (HTML + Tailwind + Chart.js) and a minimal backend you can run via Node.js (`server.js`) or Python (`server.py`).

## Pages
- `financial_summary.html` — overview charts and tables
- `standalone_income_tracker_single_html_file.html` — income tracker
- `standalone_expense_tracker_single_html_file.html` — expense tracker
- `standalone_payroll_tracker_single_html_file.html` — payroll tracker
- `settings.html` — import/export helpers

## Backends

### Option A: Node.js
- Requires Node 18+ and the `better-sqlite3` dependency.
- Create `package.json` (optional, see below) and install deps:
  - `npm install better-sqlite3`
- Start: `node server.js`
- Serves the app at `http://localhost:3000`

### Option B: Python
- Requires Python 3.10+
- Install deps: `pip install -r requirements.txt`
- Start: `python server.py`

The app stores data in `finance.db` (SQLite). This file is ignored by Git.

## Customization
- The summary page has a “Customize” panel to toggle datasets, set time unit (day/week/month), choose pie type (pie/doughnut), and pick series colors. Preferences are stored in `localStorage`.

## Repo Hygiene
We keep the repository clean by ignoring local artifacts and environment folders. See `.gitignore`:
- Node: `node_modules/`
- Python: `.venv/`, `__pycache__/`
- Databases and runtime: `finance.db`, `*.sqlite*`, `*.db`
- Editor/OS: `.vscode/`, `.idea/`, `.DS_Store`, `Thumbs.db`

If you already have `node_modules/` or `.venv/` locally, you don’t need to commit them; they are re-creatable from `npm install` and `pip install -r requirements.txt`.

## Optional: package.json
If you prefer a reproducible Node setup, create a minimal `package.json` like:

```
{
  "name": "mellow-biz",
  "private": true,
  "type": "module",
  "scripts": {
    "start": "node server.js"
  },
  "dependencies": {
    "better-sqlite3": "^9.0.0"
  }
}
```

Then run `npm install` and `npm start`.

## Clean Up Locally
- Safe to delete: `node_modules/`, `.venv/` — re-create when needed.
- Safe to delete cache files and logs; they are ignored by Git.

## Notes
- Do not commit `finance.db` or other local database files; use the export/import features in Settings to move data between machines.

## Docker

What’s included
- `Dockerfile` for a Python/Flask container (port `3000`).
- `docker-compose.yml` for local dev (builds from source, named volume).
- `docker-compose.prod.yml` for production (runs published image, configurable host path or named volume).
- `docker-compose.watchtower.yml` optional auto-updater (any host, not Synology-specific).
- `.env.example` with general variables for production compose.
- GitHub Actions workflow `.github/workflows/docker-publish.yml` to publish images to GHCR (and optionally Docker Hub).

Local/dev (build from source)
- Start: `docker compose up -d --build`
- Stop: `docker compose down`
- Data persists in named volume `app-data` at `/data/finance.db` inside the container.

Production (run published image)
1) Copy `.env.example` to `.env` and edit:
   - `IMAGE=ghcr.io/<your-ghcr-user-or-org>/mellow_biz:latest` (or a pinned tag)
   - `HOST_DATA_PATH=/srv/mellow-biz/data` (or leave empty to use a named volume)
   - `PORT=3000`
   - `APP_VERSION=latest`
2) Start:
   - `docker compose --env-file .env -f docker-compose.prod.yml up -d`
3) Optional auto-update with Watchtower:
   - `docker compose --env-file .env -f docker-compose.prod.yml -f docker-compose.watchtower.yml up -d`

Publish image automatically (GHCR)
- Push to `main` or create a tag `vX.Y.Z`.
- CI builds multi-arch images (linux/amd64, linux/arm64) and publishes:
  - `ghcr.io/<owner>/mellow_biz:latest`
  - `ghcr.io/<owner>/mellow_biz:vX.Y.Z` (for tags)
  - `ghcr.io/<owner>/mellow_biz:sha-<commit>`
- Optional: set `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` to mirror to Docker Hub.

Synology NAS (variant)
- You can use the general production compose files above, or the dedicated `deploy/synology-compose.yml` (includes Watchtower with `--registry-auth`).
- For the dedicated file, copy `deploy/.env.example` to `deploy/.env` and edit `IMAGE` and `HOST_DATA_PATH`, then run:
  - `docker compose --env-file deploy/.env -f deploy/synology-compose.yml up -d`

App Version in Settings
- The Settings page displays the app version from `/api/version`.
- Docker images include `APP_VERSION` build arg (set by CI to the tag or `latest`).
- For general compose, set `APP_VERSION` in `.env`. For Synology, set it in `deploy/.env`.

Data persistence and migration
- Your DB lives on the NAS at `HOST_DATA_PATH` as `finance.db`.
- To migrate existing data, stop the container and copy your local `finance.db` into the NAS `HOST_DATA_PATH`, then start the stack.

Notes
- The container uses the Python backend by default. If you prefer the Node version, ask and we can add a Node-based `Dockerfile`.
- The app listens on `0.0.0.0:3000`; adjust port mappings as needed.
