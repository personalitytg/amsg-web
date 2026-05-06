# AMSG Web

> Compression-based cross-domain anomaly detection for geophysical time series — wrapped in a production-style web UI.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.6-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-3.4-38BDF8?logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![Docker](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![License: MIT](https://img.shields.io/badge/License-MIT-9333EA.svg)](LICENSE)

![AMSG hero](docs/screenshots/hero.jpg)

---

## What it is

**AMSG** (Algorithmic Mutual Surprise Graph) scores how surprising a window of data is by how poorly it compresses, then hunts for the same surprise across independent sources. It is methodologically honest, technically clean, and produced a **null result** in its own evidence gate — **0 / 23** candidate events survived shift-control replication.

This repository (`amsg-web`) is the production-style web UI on top of the research pipeline: a FastAPI backend that exposes the pipeline as a REST + SSE service, and a React/TypeScript SPA that drives analyses end-to-end — source selection, run configuration, live progress, time-series + heatmap + p-value dashboards, and CSV/JSON export.

> **Honest disclaimer.** This is a tool for **hypothesis generation**, not validation. AMSG surfaces windows worth inspecting; it is not a detector of confirmed phenomena. Read the in-app [Limitations section](http://localhost:5173/docs#limitations) before drawing conclusions from any output.

---

## Architecture

```mermaid
flowchart LR
    U[User] --> F[React SPA<br/>Vite + TS + Tailwind]
    F -- "REST + SSE" --> B[FastAPI]
    B --> J[Job Manager<br/>asyncio.Queue]
    B --> P[AMSG Pipeline<br/>numpy + zlib]
    P --> D[(External APIs<br/>OMNI / SWPC / NMDB)]
    J -- "progress events" --> F
```

- **Frontend** posts to `POST /api/analyze`, receives a `job_id`, and subscribes to `GET /api/analysis/{id}/progress` over Server-Sent Events for live stage/percent updates.
- **Backend** runs jobs as background `asyncio` tasks under a semaphore (`AMSG_MAX_CONCURRENT_JOBS`), with TTL-based eviction. The pipeline itself is `numpy` + `zlib` — no GPU, no trained model, no labels.
- **In-process** job state, by design. Restarting the backend evicts running jobs; the SPA handles the 404 gracefully.

---

## Stack & rationale

| Layer | Pick | Why |
|---|---|---|
| Backend | **FastAPI 0.115** + Pydantic v2 | Async-native, automatic OpenAPI, type-checked request/response shapes. |
| SSE | **sse-starlette** | Battle-tested wrapper that plays nicely with FastAPI lifespans. |
| Pipeline | **numpy + zlib** (vendored `amsg/`) | Method is compression-based; dependency surface stays tiny. |
| Frontend | **React 18 + TypeScript 5.6 strict** | Strict TS, `--max-warnings 0`. |
| Build | **Vite 5** | Fast dev, manual chunks for the heavy Plotly bundle. |
| Styling | **Tailwind 3 + Radix primitives + shadcn-style** | Consistent dark/light tokens, no UI kit lock-in. |
| Data | **TanStack Query 5** | Polling, retries, cache invalidation — the right tool for REST + SSE. |
| State | **Zustand 4 + persist** | Lightweight history store, persisted to `localStorage`. |
| Charts | **Recharts** (small) + **Plotly.js** (big) | Recharts for histograms/areas, Plotly for synced multi-axis time series. |
| Forms | **react-day-picker** in Radix Popover | Accessible date range picker without a date library. |
| Container | **Docker Compose** + **nginx alpine** | One command up, SSE-friendly nginx proxy. |

---

## Quickstart — Docker Compose

```bash
git clone <this repo>
cd amsg-web
cp .env.example .env
docker compose up --build
```

Then open <http://localhost:5173>.

The `demo` source runs the full pipeline on synthetic data offline — perfect for a smoke test before wiring up live fetches.

---

## Local dev

Run the two services in separate terminals.

### Backend

```bash
cd backend
pip install -e ".[dev]"
pytest                                      # offline smoke test, uses demo source
uvicorn app.main:app --reload --port 8000   # OpenAPI: /api/docs
```

More: [`backend/README.md`](backend/README.md).

### Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, /api proxied to :8000
npm run typecheck
npm run lint
npm run build        # production bundle
```

More: [`frontend/README.md`](frontend/README.md).

---

## Project layout

```
amsg-web/
├── docker-compose.yml          # backend + frontend, internal network
├── .env.example                # AMSG_* + VITE_* knobs
├── README.md                   # you are here
│
├── backend/                    # FastAPI service
│   ├── Dockerfile              # python:3.11-slim
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py             # create_app(), CORS, routers under /api
│   │   ├── api/routes/         # health, sources, analyze, analysis (+ SSE)
│   │   ├── schemas/            # Pydantic v2 wire models
│   │   ├── services/           # source_registry, pipeline_runner
│   │   ├── core/               # config (env-driven), jobs (in-mem manager)
│   │   └── amsg/               # vendored copy of the pipeline package
│   └── tests/
│
└── frontend/                   # React 18 SPA
    ├── Dockerfile              # node 20 alpine → nginx alpine
    ├── nginx.conf              # /api proxy with SSE-safe knobs
    ├── package.json
    └── src/
        ├── components/         # ui primitives + layout
        ├── features/
        │   ├── home/           # hero, features, pipeline, sample preview
        │   ├── analyze/        # form, source select, settings, history, progress
        │   ├── results/        # hero metrics, plotly chart, heatmap, hist, table, sheet
        │   └── docs/           # method walkthrough + sticky TOC
        ├── lib/                # typed axios client + SSE subscriber, types, utils
        ├── stores/             # Zustand history (persisted)
        └── routes/             # router + 404
```

---

## Screenshots

> Captured locally via `docker compose up`. Dark theme, 1440 × 900 viewport, `demo` source.

<table>
  <tr>
    <td width="50%" valign="top">
      <strong>Home</strong><br/>
      <sub>Hero, method walkthrough, sample chart, limitations callout.</sub><br/><br/>
      <img src="docs/screenshots/home.jpg" alt="Home page" />
    </td>
    <td width="50%" valign="top">
      <strong>Analyze</strong><br/>
      <sub>Source multiselect, date range, settings sliders, history sidebar.</sub><br/><br/>
      <img src="docs/screenshots/analyze.jpg" alt="Analyze page" />
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <strong>Results</strong><br/>
      <sub>Hero metrics, Plotly time-series with event bands, NMS heatmap, p-value histogram, events table.</sub><br/><br/>
      <img src="docs/screenshots/results.jpg" alt="Results page" />
    </td>
    <td width="50%" valign="top">
      <strong>Method</strong><br/>
      <sub>Walkthrough with marginalia table of contents.</sub><br/><br/>
      <img src="docs/screenshots/docs.jpg" alt="Method page" />
    </td>
  </tr>
</table>

---

## Status & roadmap

**Done.**

- Backend: FastAPI app, REST routes, SSE progress, async job manager, TTL eviction, vendored pipeline, smoke tests, Dockerfile.
- Frontend: full Home / Analyze / Results / Docs pages, dark/light theme, persisted history, CSV + JSON export, Plotly + Recharts dashboards, accessible Radix-based primitives.
- Docker Compose: one-command boot with nginx serving the SPA and proxying `/api` (SSE-safe).

**Not done.**

- Five sources are still `coming_soon` (`nmdb`, `geomag`, `usgs_hydro`, `meteo`, `pageviews`) — the catalog disables them in the multiselect; the backend rejects them with 400. Each is ~20 lines to wire if needed.
- No persistent job store. Restarting the backend evicts all jobs; the SPA shows a "Job expired" empty state if you click an old history entry afterwards.
- No auth, rate limiting, or multi-tenant isolation. The service is designed for trusted local / portfolio use.

---

## License

MIT — see [`LICENSE`](LICENSE).
