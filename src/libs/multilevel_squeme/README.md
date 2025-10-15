# Multilevel Scheme (Library Deep Dive)

This module implements a modular multilevel graph partitioner with both 2-way and direct K-way pipelines, plus a METIS bridge. It’s designed to be simple, readable, and extensible, while capturing the core ideas behind METIS-like algorithms.

## Contents
- Coarsening (HEM)
- Initialization (GGGP, Spectral, Component-aware)
- Refinement (FM/KL), Rebalancing (2-way)
- K-way refinement and K-way rebalancing
- Drivers (bipartition, recursive K-way, direct K-way)
- METIS backend
- Parameters and practical tips
- Differences vs METIS and roadmap

---

## Coarsening

- `heavy_edge_matching(G, weight='weight', seed=None)`
  - Greedy matching: each node is paired with its heaviest unmatched neighbor (by |weight|).
  - Randomized node order via `seed` for variability.
- `coarsen_graph(G, weight='weight', seed=None)`
  - Contracts matched pairs into supernodes.
  - Sums parallel edge weights between supernodes (using absolute weights).
  - Aggregates node `vweight` (default 1.0 when missing).

Rationale: Coarsening reduces problem size while trying to preserve heavy connections. Absolute weights stabilize matching when matrices contain signed entries.

---

## Initialization (2-way)

- `initial_partition_gggp(G, weight='weight', balance_tol=0.03, seed=None)`
  - Greedy Graph Growing Partitioning. Starts from a seed; grows one part by gain while respecting vweight balance tolerance.
- `initial_partition_spectral(G, weight='weight', target_weight=None)`
  - Spectral bipartition using a robust set of fallbacks (generalized eigen, regularized Laplacian, identity fallback; component-aware splitting for disconnected graphs). Can accept a `target_weight` for partial splits.
- `initial_partition_component_aware(G, weight='weight', balance_tol=0.03)`
  - Packs whole components and splits at most one to reach target, improving robustness on disconnected graphs.

---

## Refinement (2-way) and Rebalancing

- `refine_partition_fm(G, part, weight='weight', balance_tol=0.03)`
  - Simple FM-like refinement with vweight balance checks.
- `refine_partition_kl(G, part, weight='weight')`
  - Simplified KL pair-swapping.
- `rebalance_partition(G, part, weight='weight', balance_tol=0.03)`
  - Greedy rebalance to enforce global 50/50 ± tol, helpful when graphs are disconnected or initializers overshoot.

Cut functions:
- `edge_cut(G, part, weight='weight')` (2-way)
- `edge_cut_kway(G, part, weight='weight')` (K-way)

---

## K-way refinement and K-way rebalancing

- `refine_partition_kway_fm(G, part, k, weight='weight', balance_tol=0.03, max_moves=None)`
  - K-way FM-like single-node move refinement. Scans moves u: a→b and applies the best positive-gain move that keeps both part a and b within per-part tolerance.
  - Balance model: target per part = total/k; allowed bound per part = `balance_tol * target` (METIS-like spirit).
- `rebalance_partition_kway(G, part, k, weight='weight', balance_tol=0.03, max_iters=100000)`
  - Greedy K-way rebalance to bring all parts within tolerance by moving nodes from heavy to light parts with minimal cut penalty.
  - Uses the same per-part bound model.
- Helpers:
  - `kway_balance_info(G, part)` — per-part weights and total using `vweight` if present.

Notes:
- Using absolute edge weights for gain (`|weight|`) is consistent with coarsening and scoring and avoids sign cancellation.

---

## Drivers

- `multilevel_bipartition(...)`
  - Coarsen until small; initialize (GGGP/Spectral/Component-aware); uncoarsen with multi-pass FM/KL; final 2-way rebalance. Multi-start trials pick the lowest cut.
- `k_way_partition(G, k, ...)`
  - Recursive application of the 2-way pipeline to get k parts. Chooses the next block to split by vweight (if available) or by size.
- `multilevel_kway_partition(G, k, ...)`
  - Direct K-way multilevel pipeline:
    - Coarsen via HEM.
    - Initialize K labels on the coarsest graph via METIS when available (fallback to recursive bisection bootstrap).
    - Uncoarsen with K-way refinement passes per level.
    - Final K-way rebalance to enforce per-part tolerance.

---

## METIS backend

- `partition_graph_metis(G, nparts, weight='weight', seed=None)`
  - Tries PyMetis, falls back to python-metis.
  - Converts float edge weights to scaled integers and forwards `vweight` when present.
  - Supports both 2-way and K-way.

---

## Parameters and practical tips

- `balance_tol`: relative per-part tolerance around `total/k` (k=2 in 2-way). Smaller means stricter balance.
- `refine_passes`: the number of refinement sweeps per level; more can reduce cut.
- `n_trials`: multi-start count; different seeds can find better coarsenings/initializations.
- `coarsen_limit`, `max_levels`: control hierarchy depth; lower limit / higher levels deepen the hierarchy.
- Seeds: fix them for reproducibility; vary to explore space.

Recommended defaults (starting points):
- 2-way: `balance_tol=0.03`, `refine_passes=5..12`, `n_trials=4..8`.
- K-way direct: `balance_tol=0.03`, `refine_passes=12..24`, `n_trials=6..10`.

---

## Differences vs METIS and roadmap

Differences:
- Coarsening: METIS uses tuned matching variants and tie-breakers; we use simple HEM.
- Initialization: METIS does K-aware seeding; we now use METIS to seed the coarsest graph when available.
- Refinement: METIS uses boundary queues and best-prefix FM; our K-way FM-like is greedy (no best-prefix yet).
- Balance handling: METIS integrates balance in move selection with robust feasibility; our per-part bound can get stuck with coarse `vweight` granularity.

Roadmap:
- Boundary (gain) queues per part and best-prefix rollback for K-way refinement.
- Pair-exchange or multi-move sequences to escape local infeasibility during rebalancing.
- Smarter coarsening (randomized HEM variants, tie-breaking, unmatched handling).
- Optional spectral/K-aware coarsest initialization without METIS.

---

## License

See `LICENSE` in the project root.
