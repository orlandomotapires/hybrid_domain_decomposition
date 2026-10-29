# Hybrid Domain Decomposition Studio — Frontend

React 18 + TypeScript + Vite + Tailwind CSS single-page app. In production it is built to `dist/` and served by the FastAPI backend (`src/api/app.py`).

## Run

From the repository root:

```sh
./run.sh --ui            # installs deps on first launch, builds dist/, serves on :8000
```

For live frontend development with hot reload, run the backend and the Vite dev server side by side:

```sh
./run.sh --ui --reload           # terminal 1 — API on :8000
npm --prefix frontend run dev    # terminal 2 — UI with HMR on http://localhost:5173 (proxies /api to :8000)
```

Manual production build:

```sh
npm --prefix frontend run build
```

## Layout

```
src/
├── App.tsx                 # header, tab navigation, theme toggle, global state
├── main.tsx
├── index.css               # Tailwind entry + light-mode tweaks
├── theme.css               # AUTO-GENERATED color variables (dark + light)
├── api/client.ts           # typed fetch wrapper for every /api endpoint
├── types/pipeline.ts       # shared TypeScript types (config, parameters, jobs…)
├── data/wikiKnowledgeBase.ts  # Wiki articles shown in the Wiki tab and (i) popovers
└── components/
    ├── PipelineStudio.tsx     # Pipeline tab (5 stages, presets, compare, preview)
    ├── ExecutionConsole.tsx   # Run tab (live log, stages, history)
    ├── BatchOrchestrator.tsx  # Batch tab
    ├── ResultsExplorer.tsx    # Results tab (batch + single run, charts, LaTeX)
    ├── HardwareInspector.tsx  # Hardware tab
    ├── HelpGuide.tsx          # Wiki tab
    └── InfoTooltip.tsx        # (i) popover linking to a Wiki topic
```

## Dark / Light theme

The color scales used by the app (`slate`, `indigo`, `violet`, `emerald`, `amber`, `cyan`, `rose`, `fuchsia`, and `white`) are mapped in `tailwind.config.js` to CSS variables in `src/theme.css`. Switching to light mode adds `class="light"` to `<html>`, which mirrors each shade (`950 ↔ 50`, `900 ↔ 100`, …). This way the existing utility classes (`bg-slate-900`, `text-indigo-300`, …) stay readable without per-component `dark:` variants. Accent mid-tones (500–700) are kept as they are, so solid buttons keep their colors.

- The toggle lives in the header (`App.tsx`). The choice is stored in `localStorage` under `studio-theme` and applied before first paint in `index.html`.
- To add a new color scale, add it to `SCALES` in both `scripts/generate-theme.cjs` and `tailwind.config.js`, then regenerate:

```sh
cd frontend && node scripts/generate-theme.cjs
```

## Adding Wiki content

Add an entry to `src/data/wikiKnowledgeBase.ts` with a unique `id`, then reference it from any component with `<InfoTooltip topicId="your-id" onOpenWiki={onOpenWiki} />`.
