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
