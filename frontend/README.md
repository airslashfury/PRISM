# PRISM Frontend + API

A dark "command-center" web app over the PRISM PostGIS model: resilience scoring,
investment optimization, social-vulnerability economics, and ranked rail corridors —
rendered on WebGL maps and live charts.

**Stack:** Next.js 14 (App Router, TS) · Tailwind + shadcn-style UI · Deck.gl + MapLibre ·
TanStack Query · Recharts · FastAPI · Pydantic v2 · PostGIS.

```
api/        FastAPI — thin, read-only projection of PostGIS to typed JSON/GeoJSON
frontend/   Next.js app (this folder)
docker/     Dockerfile.api · Dockerfile.frontend · Dockerfile.postgis
```

## Run in development

Three processes: PostGIS (Docker), the API, and the Next dev server.

```bash
# 1. Database (from repo root)
docker compose up -d postgis

# 2. API  (port 8000)  — needs the api extras
uv pip install -e ".[api]"
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
#   docs:    http://localhost:8000/docs
#   health:  http://localhost:8000/health

# 3. Frontend (port 3000)
cd frontend
npm install
npm run dev
#   app:     http://localhost:3000
```

The browser talks to the API through a same-origin Next.js rewrite (`/api/*` →
`API_PROXY_TARGET`, default `http://127.0.0.1:8000`), so no CORS in dev.

### Testing from other devices on your LAN (phone, tablet, another laptop)

Both dev servers now bind `0.0.0.0`, so they accept connections from any device on
your local network — `npm run dev` uses `next dev -H 0.0.0.0` and the API line above
passes `--host 0.0.0.0`. To reach the app from another device:

```bash
# find this machine's LAN IP
ipconfig                 # Windows — look for IPv4 Address, e.g. 192.168.1.42
# then on the phone/tablet, open:
#   http://192.168.1.42:3000
```

The phone only needs to hit the frontend (`:3000`); `/api/*` is proxied server-side
by Next to the API on the same host, so no CORS or extra config is required. If
Windows Firewall prompts on first launch, allow Node/Python on **private networks**.

## Regenerate the typed API client

The fetch client is typed from the live OpenAPI spec. With the API running:

```bash
cd frontend
npm run gen:api      # writes lib/api-types.ts — never hand-edit
```

## Run the whole stack in Docker

```bash
docker compose up --build            # postgis + api + frontend
docker compose --profile tools up    # also pgAdmin on :5050
```

| Service  | URL                     |
|----------|-------------------------|
| Frontend | http://localhost:3000   |
| API docs | http://localhost:8000/docs |
| pgAdmin  | http://localhost:5050   |

> The PostGIS volume keeps the password it was first initialized with. The API
> and CLIs read `POSTGRES_PASSWORD` from `.env`; if auth fails, align them with
> `ALTER USER prism PASSWORD '<value>';` (or recreate the volume).

## Pages

| Route         | What it shows |
|---------------|---------------|
| `/`           | System briefing — counts, phase tracker, top-risk node, module cards |
| `/resilience` | Substation consequence map (3 scenarios), SPOF rings, click-through detail |
| `/portfolio`  | ILP runs — capital-by-type, efficiency frontier, intervention table |
| `/economy`    | SVI choropleth + VOLL exposure bubbles, tract tooltips |
| `/corridor`   | Ranked rail alternatives, terrain-typed segments, objective breakdown |
| `/sync`       | Digital-twin source registry + sync run log |
