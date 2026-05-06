# Contributing to AMSG Web

Thanks for your interest. This is a small portfolio-grade project, but it
follows the same conventions you would expect from a production codebase.
Read this once before opening a PR.

## Quick start (development)

```bash
git clone https://github.com/personalitytg/amsg-web.git
cd amsg-web
cp .env.example .env

# Backend
cd backend
python -m venv .venv
. .venv/Scripts/activate         # Windows
# . .venv/bin/activate           # macOS / Linux
pip install -e ".[dev]"
pytest
uvicorn app.main:app --reload --port 8000

# Frontend (in a second terminal)
cd ../frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` to `http://localhost:8000`, so both
processes run on `localhost` with no CORS friction.

Full Docker stack:

```bash
docker compose up --build
# http://localhost:5173
```

## Project layout

```
backend/
  app/                          FastAPI app (routes, schemas, services, core)
  app/amsg/                     Vendored copy of the amsg-pipeline package
  tests/                        Pytest smoke tests (offline, demo source)
  pyproject.toml                Deps + ruff + pytest config
frontend/
  src/features/                 Feature-first folders (home, analyze, results, docs)
  src/components/{ui,layout}/   shadcn-style primitives + chrome
  src/lib/                      api client, types, query client, utils
  src/stores/                   Zustand persisted stores
docs/screenshots/               README screenshots
```

## Code style

### Backend

- Python 3.11+. Use `from __future__ import annotations` only when needed.
- Type-annotate all public functions. Pydantic v2 models for wire types.
- Async endpoints stay async — no blocking calls in handler bodies. CPU
  work goes through `asyncio.to_thread`.
- Lint with `ruff check` (config in `pyproject.toml`).
- Tests: pytest, no internet, no real connectors. Use the `demo` source.

### Frontend

- TypeScript strict, no `any`. Prefer `import type` for type-only imports.
- ESLint runs with `--max-warnings 0` — fix warnings, do not silence them
  globally. Local `// eslint-disable-next-line` is acceptable for the
  `react-refresh/only-export-components` rule next to a non-component
  export (e.g. `cva` variants), but justify it in a comment.
- Functional components only. Server state through TanStack Query.
  Client-side state through Zustand or component-local `useState`. Avoid
  Context unless it crosses many layers (theme is the one exception).
- No new color tokens or fonts without updating `index.css` and
  `tailwind.config.ts` together. The editorial dark palette is intentional;
  do not introduce purple/cyan/gradients.
- Charts: Recharts for simple, Plotly for time-series with zoom/pan.
  Re-tune Plotly colors to match the warm palette — never use the default
  theme.

### Across the stack

- No emojis in code, comments, or commit messages unless explicitly asked.
- The Limitations section ("hypothesis generation, not validation") is
  load-bearing across Home, Method, and README. Do not soften it without
  a discussion in the PR description.

## Commits and PRs

- Branch from `main`. Branch names: `feat/...`, `fix/...`, `docs/...`,
  `refactor/...`.
- Write commit messages in the imperative present:
  `Add NMDB connector adapter`, not `Added` or `Adds`.
- One logical change per commit when possible. `git commit --amend` is
  fine on your own branch before opening the PR.
- PR description should cover: what changed, why, and how you verified
  it. Screenshots required for visible UI changes.

## Adding a new data source

The five `coming_soon` sources in `app/services/source_registry.py`
(`nmdb`, `geomag`, `usgs_hydro`, `meteo`, `pageviews`) need a thin
adapter to be web-flow ready. Pattern, ~20 lines:

1. In `backend/app/amsg/<source>.py`, expose a `build_<source>_sources(...)`
   helper that returns `list[SeriesData]`. Mirror the signature of
   `build_omni_sources` in `omni.py` — most fetcher logic is already
   inside the existing `run_<source>_demo` function and just needs to be
   factored out.
2. In `backend/app/services/pipeline_runner.py`, add a branch in
   `_build_series_for_source(...)` that calls the new helper.
3. In `backend/app/services/source_registry.py`, flip
   `status="coming_soon"` to `status="available"`.
4. Test: `pytest`, then `POST /api/analyze` with the new `source_id` via
   Swagger at `/api/docs`.

## Testing checklist before opening a PR

```bash
# Backend
cd backend
ruff check
pytest

# Frontend
cd ../frontend
npm run typecheck
npm run lint
npm run build
```

All four must pass.

## Reporting a bug

Open an issue with:

1. What you ran (`docker compose up`, `npm run dev`, etc.).
2. What you expected.
3. What happened (full traceback for backend, browser console for frontend).
4. OS and versions: `python --version`, `node --version`,
   `docker --version`.

## License

By contributing, you agree your work is released under the project's MIT
license (see [`LICENSE`](LICENSE)).
