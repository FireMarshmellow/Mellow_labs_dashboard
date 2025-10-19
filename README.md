# Mellow Labs Dashboard

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
  "name": "mellow-labs-dashboard",
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

## Docker + Synology NAS

- Build image locally: `docker compose up -d --build`
- App runs on `http://localhost:3000`. Data persists in a named volume.

What’s included
- `Dockerfile` for a Python/Flask container (port `3000`).
- `docker-compose.yml` for local use with a persistent `/data` volume.
- `deploy/synology-compose.yml` for Synology (includes Watchtower to auto-update).
- GitHub Actions workflow `.github/workflows/docker-publish.yml` to publish images to GHCR on push.

Local/dev with Docker
- Start: `docker compose up -d`
- Stop: `docker compose down`
- Persistent DB path in container: `/data/finance.db` (mounted from volume).

Publish image automatically (GHCR)
- Push to the `main` branch to trigger the workflow.
- The workflow publishes to `ghcr.io/<owner>/<repo>:latest` and `sha-<commit>`.
- No extra secrets needed for GHCR; it uses `${{ secrets.GITHUB_TOKEN }}`.
- Optional: set `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` repo secrets to also publish to Docker Hub.

Deploy on Synology (auto-updating)
1) Copy `deploy/synology-compose.yml` and `deploy/.env.example` to your NAS.
2) Rename `.env.example` to `.env` and edit:
   - `IMAGE=ghcr.io/<your-ghcr-user-or-org>/<repo>:latest`
   - `HOST_DATA_PATH=/volume1/docker/mellow-labs-dashboard/data` (or another folder)
3) In Synology Container Manager (or via SSH), deploy:
   - SSH: `cd /path/to/deploy && docker compose --env-file .env -f synology-compose.yml up -d`
   - UI: Import the compose file and set the two env vars.
4) The `watchtower` service checks every 15 minutes and upgrades the app when a new image is available, then prunes old images (`--cleanup`).

Keep working and ship updates
- Continue editing locally and push to `main`.
- GitHub Actions builds and publishes a new image.
- Synology’s Watchtower auto-pulls and restarts the app with zero manual steps.

App Version in Settings
- The Settings page displays the app version from `/api/version`.
- Docker images include `APP_VERSION` build arg (set by CI to the tag or `latest`).
- For Synology, set `APP_VERSION` in `deploy/.env` (defaults to `latest`).

Data persistence and migration
- Your DB lives on the NAS at `HOST_DATA_PATH` as `finance.db`.
- To migrate existing data, stop the container and copy your local `finance.db` into the NAS `HOST_DATA_PATH`, then start the stack.

Notes
- The container uses the Python backend by default. If you prefer the Node version, ask and we can add a Node-based `Dockerfile`.
- The app listens on `0.0.0.0:3000`; adjust port mappings as needed.
