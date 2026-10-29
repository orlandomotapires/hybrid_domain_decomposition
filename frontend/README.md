# Hybrid Domain Decomposition Studio — Frontend (`frontend/`)

React 18 + TypeScript + Vite + Tailwind CSS single-page application.
- **Local mode (`./run.sh --ui`):** Built to `frontend/dist/` and served by the FastAPI backend (`backend/app.py`) with live `/api/*` execution.
- **GitHub Pages mode (`https://orlandomotapires.github.io/hybrid_domain_decomposition/`):** Automatically falls back to `src/api/staticFallback.ts` + `public/demo-snapshot.json` when no Python server is reachable, providing interactive browser-side coarsening previews, simulated runs, and pre-computed benchmark exploration.

## Development & Build

From the repository root:

```sh
./run.sh --ui                    # installs deps if needed, builds dist/, serves on :8000
```

For live frontend development with Vite Hot Module Replacement (HMR):

```sh
./run.sh --ui --reload           # terminal 1 — FastAPI backend on :8000
npm --prefix frontend run dev    # terminal 2 — Vite dev server on http://localhost:5173 (proxies /api to :8000)
```

Refresh the static GitHub Pages snapshot from local `matrices/` and `batch/` data:

```sh
./run.sh --export-demo
```

## Directory Layout

```text
frontend/
├── index.html                   # App shell, SVG favicon link, and pre-paint theme script
├── public/
│   ├── favicon.svg              # Browser tab vector icon
│   └── demo-snapshot.json       # Static fallback dataset for GitHub Pages
├── scripts/
│   ├── generate-theme.cjs       # Generates src/theme.css for Dark / Light mode
│   └── export_demo_snapshot.py  # Exports matrices/ and batch/ snapshot to public/demo-snapshot.json
└── src/
    ├── App.tsx                  # Header, tab navigation, Dark/Light toggle, global workspace state
    ├── theme.css                # CSS custom properties for dark (:root) and light (html.light) palettes
    ├── api/
    │   ├── client.ts            # Typed API client with automatic live-backend -> static-demo fallback
    │   └── staticFallback.ts    # Browser-side simulation & fallback handlers for GitHub Pages
    ├── types/pipeline.ts        # Shared TypeScript interfaces
    ├── data/wikiKnowledgeBase.ts# Structured Wiki articles and (i) popover definitions
    └── components/
        ├── PipelineStudio.tsx   # Pipeline tab (5 stages, presets, config diff, coarsening preview)
        ├── ExecutionConsole.tsx # Run tab (live log stream, 5-stage progress, run history)
        ├── BatchOrchestrator.tsx# Batch tab (matrix × scale × algorithm configurator)
        ├── ResultsExplorer.tsx  # Results tab (batch & single-run KPIs, curves, plots, LaTeX)
        ├── HardwareInspector.tsx# Hardware tab (SDK readiness & D-Wave/QLM probes)
        ├── HelpGuide.tsx        # Wiki tab
        └── InfoTooltip.tsx      # Contextual (i) popover component
```
