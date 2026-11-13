"""Parameter selection subsystem.

Two ways to pick HDD pipeline parameters for a matrix:

* **auto** (:mod:`libs.tuning.auto_select`): one-shot rules plus cheap coarsening dry-runs driven
  by the matrix features (:mod:`libs.tuning.features`).
* **iterative tuning** (:mod:`libs.tuning.tuner`): an Optuna study (TPE / NSGA-II / random / QMC /
  CMA-ES) that proposes candidates, runs the pipeline, scores the run with the chosen objectives
  (:mod:`libs.tuning.objectives`) and keeps refining.

Every pipeline run is also appended to a global history (:mod:`libs.tuning.history`) so later
studies can warm-start from what previous runs learned.
"""
