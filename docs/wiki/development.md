# Development

## Repository layout

| Path | Content |
| --- | --- |
| `src/libs/` | The scientific pipeline: graph construction, coarsening, partitioning (METIS, annealing, QAOA), refinement, permutation, metrics, batch runner, tuning |
| `src/hdd/services/` | The application layer: what the app can do, without any user interface |
| `src/hdd/studio/` | The desktop app (PySide6) |
| `src/main.py` | Command-line entry point for one simulation |
| `simulations/`, `matrices/`, `batch/`, `tuning/` | Project data (the repository is a [workspace](workspaces.md)) |
| `notebooks/` | Analysis notebooks and plotting helpers |
| `packaging/linux/` | Application-menu launcher |
| `tests/` | Test suite |
| `docs/` | The paper and this wiki |
| `run.sh` | Single entry point for the app and every command |

## Layers

```text
hdd.studio  ──►  hdd.services  ──►  libs
(Qt widgets)     (plain data)       (pipeline)
```

- `libs` imports neither `hdd` nor any UI toolkit.
- `hdd.services` imports only `libs`, the standard library and the numeric libraries (`numpy`, `scipy`, `networkx`). It returns plain JSON-shaped data and raises `ServiceError` subclasses (`InvalidInput`, `NotFound`, `Conflict`) whose message is fit to show the user.
- `hdd.studio` talks only to `hdd.services`. Anything that can take more than a few milliseconds runs on a worker thread (`TaskRunner`).
- Importing the services or opening the app does not load the quantum stack (PennyLane, D-Wave, Optuna); those modules are imported when needed.
- Only `libs/runtime/workspace.py` decides where project data lives.

`tests/services/test_layering.py` enforces these rules.

### Services

| Module | Role |
| --- | --- |
| `simulations` | Create, rename, delete; presets; validation and estimates; coarsening preview |
| `matrices`, `matrix_files` | The matrix library: list, import, generate, delete; `.mtx` headers |
| `results` | Runs: outcome (completed, failed, incomplete) and first error, KPIs, curves, plots, export; batch analysis |
| `batch` | Batch configuration: load, validate, save, plan with time and QPU estimates |
| `tuning` | Automatic selection, studies (create, resume, stop, apply, delete) |
| `hardware` | SDK and credential checks, D-Wave and QLM probes |
| `catalog` | Every editable parameter (label, type, range, unit, help) and the display names of methods and choices |
| `wiki` | The help content (`data/wiki.json`) |
| `jobs` | The job manager (below) |

### Desktop app

`main_window.py` assembles the window. `project.py` and `tree.py` read the workspace into the project tree; `pages.py`, `sim_pages.py` and `batch_page.py` build the settings pages; `documents.py` and `batch_doc.py` hold editable copies with undo; `graphics/` draws plots with pyqtgraph; `theme/` generates the style sheet from design tokens. `hdd-studio --gallery` shows every styled widget, and `hdd-studio --screenshot DIR` writes captures of the window in both themes.

## Jobs

Every job (simulation, batch, tuning study) runs as `python -u -m libs.runtime.job_entry single|batch|tune …` in its own session, with its output going straight to its log file. The job manager (`hdd/services/jobs/manager.py`) follows the file, keeps a record in `<workspace>/.hdd/jobs/<id>.json` and notifies listeners. Because the child does not depend on the app, it keeps running when the app closes; on the next start the manager follows it again (matching the pid and the process start time) or, if it ended, reads how it ended from its log.

Progress is reported as structured events, one JSON object per line, written only inside a job (`HDD_EVENTS=1`):

```text
@@hdd-event {"event":"stage","stage":"coarsening","index":1,"of":5}
```

| Event | Fields |
| --- | --- |
| `stage` | `stage`, `index`, `of` — a pipeline stage starts |
| `progress` | `fraction` — work done in the current stage (bisections) |
| `result` | `result_dir` — the run's folder |
| `batch`, `batch_case`, `batch_done` | `total`; `index`, `total`, `case`; `case`, `status` |
| `tuning`, `trial` | `total`; `done`, `total`, `status` |
| `exit` | `code` — the job's exit code, so a job that ends while the app is closed is still settled |

Events are emitted with `libs.runtime.events` and never appear in the visible log.

## Tests

```sh
pip install -c constraints.txt -e ".[gui,dev]"
QT_QPA_PLATFORM=offscreen python -m pytest            # add --cov for a coverage report
ruff check src tests docs
```

`pyproject.toml` puts `src/` and the repository root on the path and stops any test that runs longer than 5 minutes. `tests/gui/` drives the real window headless with pytest-qt; `tests/jobs/` runs jobs with scripted fake processes plus one real METIS run; `tests/conftest.py` restores the workspace environment and closes the pipeline's log file after every test.

CI (`.github/workflows/ci.yml`) runs ruff and the whole suite on every pull request and on pushes to `main`, on Python 3.10 (the oldest supported), 3.12 (with a coverage report) and 3.14. `constraints.txt` pins the exact versions it installs from Python 3.12 on; refresh it with `pip freeze --exclude-editable` from an up-to-date environment, keeping the version marker.

## Documentation

This wiki lives in `docs/wiki/`. The [parameter reference](parameter-reference.md) is generated from `src/hdd/services/data/wiki.json`, the same file the app's F1 help reads:

```sh
python docs/wiki/generate_parameter_reference.py
```

`tests/test_wiki.py` fails when the reference is out of date or when a link in the README or the wiki points to a missing file.

The repository's [GitHub Wiki](https://github.com/orlandomotapires/hybrid_domain_decomposition/wiki) is a published copy of these pages. After changing them, export and push:

```sh
git clone https://github.com/orlandomotapires/hybrid_domain_decomposition.wiki.git /tmp/hdd-wiki
python docs/wiki/export_github_wiki.py /tmp/hdd-wiki
cd /tmp/hdd-wiki && git add -A && git commit -m "Update from docs/wiki" && git push
```
