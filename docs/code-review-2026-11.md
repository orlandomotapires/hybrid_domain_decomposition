# Code review — November 2026

A whole-repository review covering architecture, error handling, security, testing/CI and edge cases. Five
reviewers read the code independently; their findings were merged, de-duplicated and ranked here.

- **Scope:** `src/hdd/studio`, `src/hdd/services`, `src/libs`, `tests/`, CI, packaging and docs.
- **Method:** static reading only. Items marked **verified** were re-checked line by line against the code; the
  rest are evidence-backed but were not reproduced by running them.
- **Severity:** Critical = wrong results or hard failure on a normal path; High = likely data loss, silent wrong
  results, or a security or reliability gap; Medium = real defect with limited blast radius; Low = hygiene.

Paths are relative to the repository root.

## Summary

The job lifecycle, path-traversal guards on service IDs and the exact P A Pᵀ test are solid. The weak points
are the quantum partitioning path (untested, one crash on a normal path), parameter semantics defined in
several places that disagree, and errors that never reach the user because the GUI has no logging.

| # | Severity | Finding | Area | Status |
|---|---|---|---|---|
| 1 | Critical | Recursive k-way splits a single-node block and crashes (QA/QAOA) | pipeline | Fixed |
| 35 | Critical | Emulated QAOA never trained its angles (found while fixing #12) | pipeline | Fixed |
| 2 | High | `balance_tolerance` changes meaning at 1.0; METIS ignores it | pipeline | Fixed |
| 3 | High | Default parameters defined 4–5 times and disagree | config | Fixed |
| 4 | High | Running tuning study invisible after 40 newer jobs | jobs/tuning | Fixed |
| 5 | High | Opening a shared workspace can execute code from it | security | Fixed |
| 6 | High | Job records trusted without validation | security | Fixed |
| 7 | High | GUI has no logging and no exception hooks | observability | Fixed |
| 8 | High | Crashed follower thread leaves job "running" forever | jobs | Fixed |
| 9 | High | Coarse problem size not checked before QAOA / simulated QA | pipeline | Fixed |
| 10 | High | Remote QPU calls never retried; "skipped" log is false | quantum | Fixed |
| 11 | High | Layering test does not guard `hdd.studio` | architecture | Fixed |
| 12 | High | Core algorithms have no tests | testing | Fixed |
| 13 | High | CI only tests Python 3.12 | CI | Fixed |
| 36 | High | GUI could deadlock: worker threads emitted Qt signals (found while fixing #26) | studio | Fixed |
| 14–28 | Medium | see below | | Fixed (#15: off-thread I/O only, no controller split) |
| 29–34 | Low | see below | | Fixed (33 partly: `libs` is a regular package; renaming `libs`/`main` deferred) |

The Critical and High fixes are on branch `fix/review-critical-high`, the Medium ones on
`fix/review-medium` (stacked on it) and the Low ones on `fix/review-low` (stacked on that), one
commit per finding. Medium decisions taken with the owner:
finding 15 only moves disk-bound work off the GUI thread (the controller split is left for its own
change), finding 23 changes METIS weight scaling (results change for matrices whose weights span more
than ~1e6), and finding 27 adds ruff, coverage, a test timeout and a constraints file. Decisions taken with the
owner: `balance_tolerance` is a percentage everywhere (old ratio values in tuning history and studies
are converted on read), and the Studio's defaults are the single source of default parameters.
Partly addressed Medium items: job records now use a unique temporary file (#14); cancelling an
unverified process and failed record saves are reported (#20); batch planning reuses the pipeline's
capacity limits (#21).

---

## Critical

### 1. Recursive k-way splits a single-node block and crashes — verified

- **Where:** `src/libs/multilevel_scheme/partitioning/utils/recursive.py:99-126`;
  `src/libs/domain_decomposition.py:129` (k clamp).
- **Problem:** `run_once` always splits the heaviest block, even when it holds one node. Both bipartitioners then
  leave one side empty; the fallback `half = max(1, len(nodes) // 2)` cannot split one node, so the run raises
  `RuntimeError("Bipartition fallback failed: produced an empty side")`. It is likely in practice: `k` is clamped
  to the coarse node count, node weights come from |diag| (orders of magnitude apart), and `max_node_weight`
  allows supernodes up to 1.5·W/k. Example: k=5 with blocks {A}=0.35W, 0.25W, 0.25W, 0.15W. METIS is unaffected.
  On a real QPU/QLM run the crash can come after many paid submissions.
- **Fix:** choose the heaviest block among blocks with ≥ 2 nodes. Add a regression test with k = coarse node
  count and skewed vertex weights.

### 35. Emulated QAOA never trained its angles — verified, found while writing the tests for #12

- **Where:** `src/libs/multilevel_scheme/partitioning/qaoa/qaoa.py` (`_qaoa_bipartition_on_pennylane`).
- **Problem:** the initial angles were a plain numpy array. PennyLane treats those as non-trainable, so
  `AdamOptimizer.step` returned them unchanged ("Attempted to differentiate a function with no trainable
  parameters"): emulated QAOA sampled from its random starting angles and `num_steps` had no effect. QLM
  runs (SciPy COBYLA) were not affected.
- **Fix:** make the angles a trainable `pennylane.numpy` array; a test checks every optimizer step moves
  them. Results of emulated QAOA runs change, including any produced before this fix.

### 36. The Studio could deadlock (High) — found while fixing #26

- **Where:** `src/hdd/studio/tasks.py`, `src/hdd/studio/diagnostics.py`.
- **Problem:** `TaskRunner` workers emitted a Qt signal to hand results to the GUI. The emitting thread
  holds Qt's connection lock while it waits for Python's GIL, and the GUI thread can hold the GIL while it
  waits for that lock (seen during garbage collection), so the window froze. It showed up as an
  intermittent hang in the GUI tests, captured with a stack dump.
- **Fix:** workers put results in a queue that a timer on the GUI thread drains, as `JobsBridge` already
  did; the error relay works the same way. Ten consecutive full test runs passed afterwards, where about
  one run in five had hung.
- **Second cause, found later:** a rarer hang remained. Python's cyclic garbage collector runs in whichever
  thread is allocating, so a worker building a graph could destroy a Qt widget, which Qt forbids; the
  GUI thread then waited forever on a Qt lock. Automatic collection is now off and a timer on the GUI
  thread collects instead (pyqtgraph's `GarbageCollector`, installed in `create_application`).

## High

### 2. `balance_tolerance` changes meaning at 1.0; METIS ignores it — verified

- **Where:** `src/libs/multilevel_scheme/uncoarsening/uncoarsening.py:10-22`,
  `src/libs/multilevel_scheme/partitioning/utils/metrics.py:28-32`,
  `src/libs/multilevel_scheme/partitioning/utils/recursive.py:54-57`, `src/hdd/services/catalog.py:152`,
  `src/libs/multilevel_scheme/partitioning/partitioning.py:50-69`, `src/libs/tuning/search_space.py:33-34`.
- **Problem:** values > 1.0 are read as percent, values ≤ 1.0 as a ratio, so `1.0` means 100% and `1.01` means
  1.01%. The rule is copied in three places. The editor allows 0–100; the UI default is 2.0 (2%) while the tuner
  searches 0.01–0.3 (ratio) and the validator default is 0.1. A user who types `1` meaning 1% gets a lower
  bound of 0 in refinement, so parts can drain to empty without an error. `pymetis.part_graph` never receives a
  tolerance (`ufactor`), although the wiki says it does.
- **Fix:** one conversion helper and one unit, a one-time migration for stored values, pass `ufactor` to METIS,
  align the tuner search space and the wiki.

### 3. Default parameters defined 4–5 times and disagree

- **Where:** `src/hdd/services/simulations.py:30-71`, `src/libs/runtime/utils.py:413-506`,
  `src/hdd/services/batch.py:19-21`, `src/hdd/services/data/wiki.json`,
  `src/libs/multilevel_scheme/partitioning/partitioning.py:76,125`.
- **Problem:** UI vs validator defaults: QA `num_reads` 20 vs 5, `num_starts` 20 vs 5, `qubo_balance_lambda`
  2.0 vs 0.1, `balance_violation_lambda` 5.0 vs 0.1; QAOA `circuit_depth` 1 vs 12, `num_steps` 5 vs 12;
  `k_target` 4 vs 2; `balance_tolerance` 2.0 vs 0.1. The wiki documents a third set. A batch preset or CLI file
  that omits a QAOA key runs at depth 12, which is very expensive in emulation, and the F1 help is wrong.
- **Fix:** one `DEFAULT_SIMULATION_PARAMETERS` in `libs`, imported by the validator and the services; test that
  wiki defaults match it.

### 4. Running tuning study invisible after 40 newer jobs — verified

- **Where:** `src/hdd/services/tuning.py:76-83`, `src/hdd/services/jobs/manager.py:396`.
- **Problem:** `running_job_for` iterates `jobs.list_jobs()`, whose default is `limit=40`. A long study pushed out
  of that window looks idle: `delete_study` can `rmtree` a live study, and `resume_study` can start a second
  process on the same `study.db`.
- **Fix:** scan all jobs (`limit=None`) or add a locked `JobManager` lookup.

### 5. Opening a shared workspace can execute code from it

- **Where:** `src/hdd/services/jobs/manager.py:494-502`, `src/hdd/services/jobs/commands.py:19-21`,
  `src/libs/batch/run_batch.py:246-248`.
- **Problem:** jobs run `python -u -m libs.runtime.job_entry` with `cwd` set to the workspace. With `-m`, the
  current directory is first on `sys.path`, so a `json.py`, `numpy.py` or `libs/` planted in a shared workspace
  runs as the user when they click Run, in a detached session that outlives the Studio.
- **Fix:** set `PYTHONSAFEPATH=1` / `-P` (3.11+) and, for 3.10, launch with `cwd` outside the workspace (jobs get
  the workspace from `HDD_WORKSPACE`). Same for `run_batch --nohup`. Test with a planted `json.py`.

### 6. Job records trusted without validation

- **Where:** `src/hdd/services/jobs/store.py:17-46`, `src/hdd/services/jobs/manager.py:184-187, 252-268,
  524-527, 631-634, 713-743`.
- **Problem:** `.hdd/jobs/*.json` fields are used as-is. A `job_id` with `../` makes `_save` overwrite a file
  outside the workspace; an absolute `log_path` makes `_finish` append to an arbitrary file; `pid_start: null`
  disables the pid-reuse check, so Cancel can SIGTERM/SIGKILL an unrelated process (also the normal case on
  platforms without `/proc`); `result_dir` is opened unchecked.
- **Fix:** validate `job_id` with `^[A-Za-z0-9_.-]+$` and keep paths inside the workspace; never signal a
  re-attached process whose start time is unknown.

### 7. GUI has no logging and no exception hooks

- **Where:** `src/hdd/studio/tasks.py:32-35`, `src/hdd/studio/app.py:109-133`, `run.sh:67`.
- **Problem:** no `logging`, `sys.excepthook`, `threading.excepthook` or Qt message handler anywhere in `src/`.
  `TaskRunner` stores `__traceback_text__` but nothing reads it. Exceptions in Qt slots, follower threads and
  timers go to stderr, which is lost when started from the desktop launcher.
- **Fix:** a small diagnostics module: rotating log in `<workspace>/.hdd/studio.log`, exception hooks that log the
  traceback and show a non-blocking error; `TaskRunner` logs tracebacks.

### 8. Crashed follower thread leaves job "running" forever

- **Where:** `src/hdd/services/jobs/manager.py:563-699`, `252-264`.
- **Problem:** `_follow` has `try/finally` but no `except`. A malformed event (`int(event["index"])`), an
  `OSError` on `stat()`, or a listener error ends the thread; `_finish` never runs, the job stays "running" and
  Stop stays enabled. During settle at startup the same exception escapes `JobManager.__init__` and the
  workspace fails to open. Related: failed record saves are swallowed (`except OSError: pass`).
- **Fix:** guard each line in `_apply_line`; on unexpected errors finish the job as failed with a message; guard
  per record in `_load_records`; log save failures.

### 9. Coarse problem size not checked before QAOA / simulated QA

- **Where:** `src/libs/multilevel_scheme/partitioning/qaoa/qaoa.py:26,139`, `src/libs/tuning/feasibility.py:17,35-42`,
  `src/libs/multilevel_scheme/partitioning/utils/qubo.py:71-77`.
- **Problem:** local QAOA is allowed up to 24 qubits (256 MB per state, plus backprop) while feasibility uses 18.
  Simulated annealing has no capacity limit and builds a dense O(n²) QUBO dict. Single runs never call the
  feasibility check, so an oversized problem is OOM-killed with no explanation.
- **Fix:** check capacity right after coarsening and fail fast with a clear message; one QAOA qubit constant; a
  configurable cap for simulated QA.

### 10. Remote QPU calls never retried; "skipped" log is false

- **Where:** `src/libs/multilevel_scheme/partitioning/qa/dwave_access.py:222-246`,
  `src/libs/multilevel_scheme/partitioning/qaoa/qlm_access.py:218-300`, `src/libs/domain_decomposition.py:172-215`.
- **Problem:** a hardware run makes up to `num_starts·(k-1)` submissions; one transient network error aborts the
  run and discards results already paid for. When the dense QUBO is too large for the QPU the log says the Leap
  submission "will be skipped", but the code still opens a sampler and then fails.
- **Fix:** bounded retry with backoff on connection errors for sampling and status polling (not for non-idempotent
  submits); fail immediately with the capacity message when the problem is too large.

### 11. Layering test does not guard `hdd.studio` — verified

- **Where:** `tests/services/test_layering.py:33-39`; violations in `src/hdd/studio/graphics/area.py`,
  `context.py`, `main_window.py`, `project.py`, `app.py`.
- **Problem:** the studio rule only forbids `backend`/`fastapi` (web-app leftovers). Five studio modules import
  `libs` directly, contrary to the documented `studio → services → libs` rule.
- **Fix:** forbid `libs` in `hdd.studio`; add a thin `hdd.services.workspace` facade and a matrix sparsity service.

### 12. Core algorithms have no tests

- **Where:** `src/libs/multilevel_scheme/**`, `src/libs/permutation.py`, `src/libs/graph_prep.py`.
- **Problem:** no test runs simulated annealing or QAOA, the QUBO/Ising algebra, Kernighan–Lin refinement
  invariants, coarsening invariants, the `dof_per_node > 1` path, or same-seed reproducibility. All three pipeline
  tests use METIS with `dof_per_node=1`. Some assertions are vacuous (`imbalance >= 0`).
- **Fix:** brute-force QUBO tests on 4–8 node graphs; property tests for matching, coarsening and refinement;
  small simulated QA/QAOA end-to-end runs; `dof_per_node=3`; determinism tests.

### 13. CI only tests Python 3.12

- **Where:** `.github/workflows/ci.yml`, `pyproject.toml:10`.
- **Problem:** the package declares `>=3.10` and the owner develops on 3.14; neither is tested, nor whether the
  dependency floors install on 3.10.
- **Fix:** a version matrix (3.10 / 3.12 / 3.14), with GUI tests only where wheels exist; or bump
  `requires-python` if a dependency needs it.

---

## Medium

### 14. Non-atomic `write_json`; fixed temp-file names — verified

- **Where:** `src/libs/runtime/utils.py:123-126`, `src/hdd/services/jobs/store.py:27-29`, `src/libs/tuning/tuner.py:157-160`.
- **Problem:** `write_json` truncates and then writes user parameter, config and batch files; a crash leaves them
  half-written. The "atomic" writers use a fixed `.json.tmp` name, which breaks under concurrent writers.
  `save_parameters` silently replaces an unreadable file and loses the inactive strategy blocks.
- **Fix:** one atomic writer with a unique temp file + `os.replace`, used everywhere.

### 15. `MainWindow` is a god class with disk I/O on the GUI thread

- **Where:** `src/hdd/studio/main_window.py:171-1439`.
- **Problem:** ~90 methods covering navigation, documents, CRUD, presets, tuning, batch, matrices, jobs and
  workspaces; reaches into private state (`doc._load`, `project._loaded`). Save, preset switch, batch plan (scans
  every batch log), rename and delete run synchronously on the GUI thread.
- **Fix:** split into controllers like the existing `PageActions`; move disk-bound calls to `TaskRunner`.

### 16. Workspace switch races with background tasks

- **Where:** `src/libs/runtime/workspace.py:48-67`, `src/hdd/studio/context.py:60-74`.
- **Problem:** the workspace is process-wide in `os.environ`; the switch waits at most 5 s for tasks, then changes
  it. A still-running task can write into the new workspace. Old followers only check `_closed` when idle.
- **Fix:** capture the root per task (or pass it explicitly); refuse to switch while tasks run; check `_closed` every loop.

### 17. Cancelled or killed batches leave inconsistent artifacts

- **Where:** `src/libs/batch/run_batch.py:66-68, 409, 524-527, 593-695`, `src/libs/runtime/job_entry.py:57-67`.
- **Problem:** no SIGTERM handler, so `finally` never runs: the manifest stays "running" and no summary is
  written. One undecodable JSON aborts the summary for all cases.
- **Fix:** SIGTERM → `sys.exit(143)` in `job_entry`; mark unfinished cases cancelled; per-row error handling.

### 18. Run status decided two different ways

- **Where:** `src/hdd/services/jobs/manager.py:292-393`, `src/hdd/services/results.py:132-154`.
- **Problem:** an OOM-killed run is "completed" in the Jobs panel and "incomplete" in the project tree. Jobs
  deleted without files come back as `hist_*`. A run folder deleted during startup crashes `JobManager.__init__`.
  All historical logs are read eagerly on the GUI thread.
- **Fix:** use `results.run_outcome` in the manager; load historical logs lazily; guard per run.

### 19. Concurrent JSONL appends can interleave

- **Where:** `src/libs/tuning/history.py:54-57`, `src/libs/tuning/tuner.py:184-186`.
- **Problem:** large entries flush in several writes; concurrent processes interleave, a crash leaves a partial line
  and the next good entry is glued to it and dropped.
- **Fix:** single `os.write` on an `O_APPEND` fd under `flock`; newline repair before append.

### 20. Exceptions swallowed or mis-classified

- **Where:** `src/hdd/services/simulations.py:225,273,309,325,356,525`, `src/hdd/services/jobs/manager.py:244-250,
  424-433, 513-541, 735-743`, `src/hdd/services/jobs/store.py:35-41`.
- **Problem:** broad `except Exception → InvalidInput` turns I/O errors and bugs into "invalid input". Cancel
  reports success when the signal failed. Delete-with-files reports success when `rmtree` failed. Corrupt job
  records vanish silently.
- **Fix:** catch specific exceptions; return/raise real outcomes; quarantine and count corrupt records.

### 21. Duplicated domain logic across layers

- **Where:** batch case expansion `src/hdd/services/batch.py:57-82` vs `src/libs/batch/run_batch.py:71-78`;
  capacity and workload formulas in `services/batch.py`, `services/simulations.py`, `libs/tuning/feasibility.py`,
  `libs/domain_decomposition.py`; coarsening preview `services/simulations.py:433-526`; stage labels in three files.
- **Problem:** copies already disagree (the services batch plan does not de-duplicate matrices and overcounts
  cases; stage labels differ).
- **Fix:** one pure function per rule in `libs`, wrapped by services.

### 22. Heavy libraries loaded in the GUI process

- **Where:** `src/hdd/services/tuning.py:38-41` → `libs/tuning/tuner.py` → `libs/profiling/matrix_metrics.py:4`;
  `src/libs/multilevel_scheme/partitioning/qa/__init__.py`.
- **Problem:** every project refresh imports `matplotlib.pyplot` (only used by a dead function). Hardware probes
  load PennyLane and neal via the `qa` package re-exports. The import-cost test misses both.
- **Fix:** delete the dead plot function; move study filenames to a light module; import probes directly; extend
  the test to load a real snapshot.

### 23. Matrix values not validated; METIS weights saturate

- **Where:** `src/hdd/services/matrix_files.py:76-113`, `src/libs/multilevel_scheme/partitioning/partitioning.py:14-26`.
- **Problem:** NaN/Inf entries reach METIS and fail with an opaque error. Weights scaled by `1/min` and clamped to
  1e6 saturate for FEM diagonals spanning > 10⁶, so METIS balances on node count.
- **Fix:** reject non-finite data on load; scale by max (or log-scale) and warn on clamping.

### 24. Permutation self-check rarely samples nonzeros

- **Where:** `src/libs/profiling/matrix_metrics.py:29-42`.
- **Problem:** uniform sampling over n² hits ~10 nonzeros on a 1e5×1e5 matrix with 1e6 nonzeros, so the UI KPI
  almost never detects a wrong permutation.
- **Fix:** exact O(nnz) comparison, or sample stored nonzeros; test with a corrupted permutation.

### 25. Parameter validation gaps

- **Where:** `src/libs/runtime/utils.py:248-256`, `src/hdd/services/batch.py:26-37`.
- **Problem:** unknown keys are silently ignored (typos use defaults); catalog bounds (e.g. `seed ≥ 0`,
  `qubo_balance_lambda ≥ 0`) are not enforced by the pipeline; saving a batch config does not validate presets.
- **Fix:** warn on unknown keys; shared numeric ranges in `libs`; dry-run preset validation on save.

### 26. Tests leak global state

- **Where:** `src/libs/runtime/log.py:32-36`, `src/libs/runtime/runtime.py:104`, `tests/test_run_batch.py`.
- **Problem:** the module-global log handle stays open after in-process runs, so later logs land in an old run's
  `run_log`; `test_run_batch` pins `HDD_WORKSPACE` to the repo and creates temp folders in the repo root.
- **Fix:** close the log in `run_simulation`'s `finally`; root `conftest.py` that restores env vars; temp workspaces.

### 27. Test and CI infrastructure gaps

- **Where:** `pyproject.toml`, `.github/workflows/ci.yml`, `requirements.txt`.
- **Problem:** no coverage, per-test timeout, lint, or `permissions:` block; unpinned dependencies; no pip cache;
  CI runs twice for PR pushes.
- **Fix:** `pytest-timeout`, `pytest-cov`, `ruff` (target py310), constraints file, `cache: pip`, concurrency group.

### 28. Stale references in help and docs

- **Where:** `src/hdd/services/data/wiki.json` (`sourceFile`/`codeKey` fields; `qlm_qpu_name` text).
- **Problem:** points to deleted `backend/routes/*` and `frontend/*` files; says `qlm_qpu_name` is loaded via
  `importlib`, which is no longer true.
- **Fix:** update the entries, regenerate the parameter reference, test that `sourceFile` exists.

## Low

| # | Finding | Where |
|---|---|---|
| 29 | Batch preset keys unchecked (`../` writes outside workspace); run export zip follows symlinks | `src/libs/batch/run_batch.py:94-110`, `src/hdd/services/results.py:247-256` |
| 30 | `.desktop` `Exec=` line built without quoting | `packaging/linux/install-launcher.sh:42-43` |
| 31 | Committed notebook output contains an absolute home path | `notebooks/plots_notebook.ipynb:27` |
| 32 | Dead or leftover code: `studio/prototype/`, stale `.gitignore` entries, `.env_ocean` lookup, `run_batch --nohup` | various |
| 33 | Generic top-level names (`main`, namespace package `libs`) installed into site-packages | `pyproject.toml` |
| 34 | Same-second batch dirs collide; cancel racing completion shows "cancelled"; unknown strategy → `AttributeError`; custom coarsening `weight` name dropped after level 0; log timestamp regex assumes UTC | `jobs/manager.py:460-471, 519-541`, `domain_decomposition.py:149,289`, `coarsening.py:150`, `services/batch.py:181` |

## What works well

- Detached job lifecycle: `exit` event in `finally`, settle-on-reopen, pid + start-time re-attach on Linux, atomic
  job records, bounded logs.
- Path-traversal guards on every service ID; no `pickle`, `eval`, `shell=True` or unsafe YAML; tokens never logged.
- Tests: exact P A Pᵀ check, preview-vs-run differential test, scripted job-manager tests, layering and lazy-import
  checks, polling waits instead of sleeps.
