# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
pip install -r requirements.txt   # first time only
python app.py                     # starts Flask on http://localhost:5000
iniciar.bat                       # Windows shortcut: opens browser + starts server
```

There are no tests or linter configured for this project.

## Architecture

Single-file Flask backend (`app.py`) + Jinja2 templates. No frontend framework — vanilla JS only. Database is a flat JSON file (`data/tasks.json`) read and written on every request.

**Request flow:** every page load calls `rollover_tasks()` which scans `tasks.json` and moves any incomplete task whose `due_date < today` to today's date before rendering.

**Routes:**
- `GET /` → redirects to `/day/<today>`
- `GET /day/<date_str>` → renders `day.html` with tasks + Google Calendar events for that date
- `GET /inbox` → tasks where `due_date` is null and `completed` is false
- `GET /pending` → all incomplete tasks grouped by date, ascending
- `GET /completed` → all completed tasks grouped by date, ascending
- `GET /gcal/setup` → Google Calendar setup instructions page
- `GET /auth/google` · `GET /auth/google/callback` · `GET /auth/google/disconnect` → OAuth web flow
- `GET /login` · `POST /login` · `GET /logout` → session auth
- `POST /api/tasks` · `PUT /api/tasks/<id>` · `DELETE /api/tasks/<id>` · `POST /api/tasks/<id>/toggle` → JSON API consumed by frontend JS

**Task schema** (fields in `tasks.json`): `id`, `title`, `notes`, `due_date` (ISO string or null), `category` (category id or null), `completed` (bool), `created_at`, `completed_at`

**Category schema** (stored in `tasks.json` under `categories`): `id`, `name`, `color` (hex string)

**Category API:** `GET /api/categories` · `POST /api/categories` · `PUT /api/categories/<id>` · `DELETE /api/categories/<id>` (also clears `category` from all tasks)

## Templates

`base.html` contains all CSS, the sidebar, the edit modal, and shared JS functions (`openEdit`, `closeEdit`, `saveEdit`, `toggleTask`, `deleteTask`). Child templates extend it via `{% block content %}` and add page-specific JS inside `{% block scripts %}`, which is wrapped in `<script>` tags in `base.html`.

Edit buttons use `data-*` attributes (`data-id`, `data-title`, `data-notes`, `data-date`) — never inline `onclick` with `tojson` — to avoid HTML attribute quote-escaping bugs.

**Sidebar state:** `get_sidebar_data(current_date_str)` passes `sidebar.current_date` (None for non-day views, date string for day view) to templates. Active nav link uses `request.path` for static routes (`/inbox`, `/pending`, `/completed`) and `sidebar.current_date == d` for date-based links. Sidebar order: Inbox → Hoy → Pendientes → Completadas → Otros días → Google Calendar status → Cerrar sesión (bottom).

`login.html` is a standalone page (does not extend `base.html`) — it has its own full HTML with embedded styles matching the app's dark theme.

## Authentication

All routes except `/login` are protected by a `before_request` hook. API routes (`/api/*`) return `401 JSON` when unauthenticated instead of redirecting. Sessions last 8 hours (`app.permanent_session_lifetime`). Password comparison uses `hmac.compare_digest` to prevent timing attacks.

Credentials come from environment variables `APP_USERNAME` and `APP_PASSWORD`.

## Persistent data

All persistent files live in `data/` (Docker volume):
- `data/tasks.json` — task database
- `data/credentials.json` — Google OAuth client secrets (user-provided)
- `data/token.json` — Google OAuth token (auto-generated after first auth)

`os.makedirs(DATA_DIR, exist_ok=True)` runs at startup to create the directory if missing.

## Google Calendar integration

Optional — only activates when `data/credentials.json` is present. Uses web-based OAuth flow (not `run_local_server`) so it works on headless servers.

- `get_calendar_service()` — loads/refreshes token from `data/token.json`, returns `None` if not authenticated (never launches browser)
- `get_calendar_events(date_str)` — fetches events using local timezone offset; returns list of dicts with `title`, `time`, `is_all_day`, `location`, `notes`, `html_link`
- `_callback_url()` — uses `BASE_URL` env var if set, otherwise derives from request (needed behind proxies)
- Events render in `day.html` as blue cards above the task list; read-only
- `sidebar.gcal_connected` / `sidebar.gcal_enabled` control the sidebar status indicator

## Environment variables

Set in `docker-compose.yml`:

| Variable | Purpose |
|---|---|
| `APP_USERNAME` | Login username |
| `APP_PASSWORD` | Login password |
| `SECRET_KEY` | Flask session signing key |
| `BASE_URL` | Full server URL e.g. `http://192.168.0.35:5000` — required for Google OAuth callback |
| `OAUTHLIB_INSECURE_TRANSPORT` | Set to `1` to allow OAuth over HTTP (omit when using HTTPS) |
| `FLASK_DEBUG` | Set to `true` to enable debug mode (off by default) |

## Docker deployment

```bash
# Windows shortcut (prompts for Docker Hub username)
build_and_push.bat

# Manual — use versioned tags to preserve previous images on Docker Hub
docker build -t sockenteufel/todo-app:1.0.0 -t sockenteufel/todo-app:latest .
docker push sockenteufel/todo-app:1.0.0
docker push sockenteufel/todo-app:latest
```

`docker-compose.yml` is deployed directly in Portainer (Stacks). The app runs on static IP `192.168.0.35:5000` on the `prod_lan` external network. `credentials.json` is placed in the volume via Portainer's volume browser after first deploy.

Production uses **gunicorn** (`--workers 2 --timeout 60`) — not the Flask dev server. `flask run` / `python app.py` is only for local development.

When deploying behind nginx with HTTPS: add `X-Forwarded-For`, `X-Forwarded-Proto`, and `Host` proxy headers in the nginx `location` block, and remove `OAUTHLIB_INSECURE_TRANSPORT` from the compose file.

## Date formatting

Spanish month/day names are hardcoded in `app.py` (`MONTHS_ES`, `DAYS_ES`, `DAYS_SHORT`) — no locale dependency, works on any OS.
