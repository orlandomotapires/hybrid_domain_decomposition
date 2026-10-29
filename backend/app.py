from __future__ import annotations

import argparse
from pathlib import Path
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

for p in (str(ROOT_DIR), str(SRC_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.routes.matrices import router as matrices_router
from backend.routes.execution import router as execution_router
from backend.routes.batch import router as batch_router
from backend.routes.results import router as results_router
from backend.routes.quantum_hw import router as quantum_hw_router

app = FastAPI(
    title="Hybrid Domain Decomposition Studio API",
    description="Web Studio API for Hybrid Quantum-Classical Graph Partitioning & Matrix Permutation Pipeline",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(matrices_router)
app.include_router(execution_router)
app.include_router(batch_router)
app.include_router(results_router)
app.include_router(quantum_hw_router)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "hybrid-domain-decomposition-studio"}


if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        candidate = (FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(
            FRONTEND_DIST / "index.html",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )


def cli_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Launch the Hybrid Domain Decomposition Web Studio.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args(argv)

    print(f"Starting Hybrid Domain Decomposition Studio on http://{args.host}:{args.port}")
    uvicorn.run(
        "backend.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        app_dir=str(ROOT_DIR),
    )


if __name__ == "__main__":
    cli_main()
