# Hybrid Domain Decomposition Studio — Backend (`backend/`)

FastAPI web server that exposes the REST API (`/api/*`), manages asynchronous simulation & batch subprocesses, renders cached matrix/graph plots, and serves the built React Studio bundle (`frontend/dist/`).

## Launch

From the repository root:

```sh
./run.sh --ui                  # build frontend/dist and start backend on http://127.0.0.1:8000
./run.sh --ui --reload         # auto-reload Python backend on file changes
```

Interactive OpenAPI / Swagger documentation is served automatically at `http://127.0.0.1:8000/docs`.

## Directory Layout

```text
backend/
├── app.py                     # FastAPI application factory, CLI (--host, --port, --reload), and SPA static file serving
├── routes/
│   ├── matrices.py            # /api/demonstrators: CRUD for matrices/<id>, config/parameters, presets, .mtx upload, demo mesh generator, dry-run coarsening preview
│   ├── execution.py           # /api/execution: start, list, poll (incremental log streaming), cancel, and delete simulation jobs
│   ├── batch.py               # /api/batch: read/write batch_configuration.json, launch batch studies, inspect batch runs
│   ├── results.py             # /api/results: per-matrix run list, single-run KPIs & curves, cached plot images, .zip bundle download, batch LaTeX tables
│   └── quantum_hw.py          # /api/hardware: Python SDK readiness matrix, D-Wave clique capacity probe, QLM QPU inspector
└── services/
    ├── job_manager.py         # Subprocess lifecycle, real-time log parsing, 5-stage progress & telemetry extraction, historical run discovery
    ├── matrix_service.py      # Fast Matrix Market (.mtx) header inspection and synthetic 3D FEM hexahedral mesh generator
    └── plot_service.py        # Bandwidth KPI extraction, density curve sampling, cached Matplotlib rendering, and LaTeX table builders
```

