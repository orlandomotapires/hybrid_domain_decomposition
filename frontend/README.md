# Hybrid Domain Decomposition Studio — Frontend (`frontend/`)

React 18 + TypeScript + Vite + Tailwind CSS single-page application.
It is built to `frontend/dist/` and served by the local FastAPI backend (`backend/app.py`) via `./run.sh --ui`; every action goes through the backend's `/api/*` routes. The Studio requires the Python backend and is not meant to be hosted as a static site.

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

## Directory Layout

```text
frontend/
├── index.html                   # App shell, SVG favicon link, and pre-paint theme script
├── public/
│   └── favicon.svg              # Browser tab vector icon
├── scripts/
│   └── generate-theme.cjs       # Generates src/theme.css for Dark / Light mode
└── src/
    ├── App.tsx                  # Header, tab navigation, URL state, job polling, shortcuts, unsaved-changes guard
    ├── theme.css                # CSS custom properties for dark (:root) and light (html.light) palettes
    ├── api/
    │   └── client.ts            # Typed API client for the local FastAPI backend (/api/*)
    ├── lib/
    │   ├── download.ts          # CSV / text / chart (PNG, SVG) downloads
    │   ├── notify.ts            # Desktop notifications for finished runs
    │   └── urlState.ts          # Tab + selection <-> URL hash (#/results?run=...)
    ├── types/pipeline.ts        # Shared TypeScript interfaces
    ├── data/wikiKnowledgeBase.ts# Structured Wiki articles and (i) popover definitions
    └── components/
        ├── PipelineStudio.tsx   # Single Run tab: simulation tabs, stage flowchart, run-cost bar; wires the stages below
        ├── pipeline/            # Stage 1–5 cards (Stage 1 = matrix picker), compare & preset modals, constants
        ├── ExecutionConsole.tsx # Runs tab (live log with search/export, batch progress & ETA, history)
        ├── BatchOrchestrator.tsx# Batch Run tab (matrix × scale × algorithm configurator)
        ├── batch/ParamFields.tsx# Editable algorithm / shared parameter fields for Batch Run
        ├── ResultsExplorer.tsx  # Results tab (batch & multi-run comparison, CSV/PNG/SVG export, re-run)
        ├── HardwareInspector.tsx# Hardware tab (SDK readiness & D-Wave/QLM probes)
        ├── HelpGuide.tsx        # Wiki tab
        ├── InfoTooltip.tsx      # Contextual (i) popover component
        └── Toasts.tsx           # Success / error / undo notifications
```

## Keyboard Shortcuts

| Keys | Action |
| --- | --- |
| `Ctrl/⌘ + S` | Save configuration & parameters (Single Run) |
| `Ctrl/⌘ + Enter` | Run the current simulation (Single Run) |
| `1` – `6` | Switch tab (Single Run, Batch Run, Runs, Results, Hardware, Wiki) |
| `?` | Show the shortcut list |
| `Esc` | Close dialogs |
