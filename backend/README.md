# AMSG Web — Backend

FastAPI service that wraps the AMSG anomaly-detection pipeline.

## Layout

```
app/
  main.py              FastAPI app factory + router registration
  api/routes/
    health.py          GET  /api/health
    sources.py         GET  /api/sources
    analyze.py         POST /api/analyze        (queues a background job)
    analysis.py        GET  /api/analysis/{id}
                       GET  /api/analysis/{id}/progress  (SSE)
  schemas/             Pydantic models for the wire format
  services/
    source_registry.py Static catalogue of available sources
    pipeline_runner.py Bridge to the vendored amsg pipeline
  core/
    config.py          Settings (env-driven via pydantic-settings)
    jobs.py            In-process job manager + progress queue
  amsg/                Vendored copy of the amsg pipeline package
tests/
  test_api_smoke.py    End-to-end test using the synthetic `demo` source
```

## Run locally

```bash
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

OpenAPI docs: <http://localhost:8000/api/docs>.

## Run tests

```bash
pytest
```

The smoke test uses only the offline `demo` source — no internet required.

## Configuration

All settings are env-driven with prefix `AMSG_`:

| Variable | Default | Notes |
|---|---|---|
| `AMSG_DEBUG` | `false` | |
| `AMSG_CORS_ORIGINS` | `["http://localhost:5173"]` | JSON array |
| `AMSG_RUNS_DIR` | `./runs` | Pipeline run artifacts |
| `AMSG_CACHE_DIR` | `./cache` | HTTP response cache for connectors |
| `AMSG_JOB_TTL_SECONDS` | `3600` | Finished jobs evicted after this |
| `AMSG_MAX_CONCURRENT_JOBS` | `2` | Semaphore on the job runner |

## Connector status

| Source | Status | Notes |
|---|---|---|
| `demo` | available | Synthetic, offline, ~1s |
| `omni` | available | NASA OMNI HAPI, ~30s for 7 days |
| `swpc` | available | NOAA SWPC, fixed 7-day window |
| `nmdb` | coming_soon | Helper not yet exposed at module level |
| `geomag`, `usgs_hydro`, `meteo`, `pageviews` | coming_soon | Same |

The "coming_soon" sources have working CLI flows in the underlying `amsg`
package; only the thin web adapter is missing. Adding one is ~20 lines.

## Deployment notes

- Job state is in-memory. Restarting the process drops queued/finished jobs.
  Swap `app.core.jobs.JobManager` for a Redis-backed implementation if you
  need durability or horizontal scaling.
- `run_pipeline` is CPU-bound and offloaded via `asyncio.to_thread` so it
  does not block the event loop. With the default `MAX_CONCURRENT_JOBS=2`
  on a 2-core host, latency stays predictable.
