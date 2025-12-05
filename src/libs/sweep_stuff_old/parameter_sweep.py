"""
Parameter sweep utilities for quantum graph partitioning.
Helps tune coarsening, QUBO, and annealing parameters.
"""
import json
import os
import sys
import time
from datetime import datetime
from itertools import product
from typing import Any, Dict, List, Callable, Optional, TextIO
import networkx as nx
import numpy as np


class ParameterSweep:
    """Run parameter grid search for quantum partitioning."""
    
    def __init__(self, output_dir: str = "results/sweeps", log_to_file: bool = True):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.results = []
        self.sweep_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_to_file = log_to_file
        self.log_file: Optional[TextIO] = None
        
        if self.log_to_file:
            log_path = os.path.join(self.output_dir, f"sweep_{self.sweep_id}.log")
            self.log_file = open(log_path, 'w', buffering=1)  # Line buffered
            self._log(f"Log file created: {log_path}")
    
    def _log(self, message: str, add_timestamp: bool = True):
        """Write message to log file and/or console."""
        if add_timestamp:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted_msg = f"[{timestamp}] {message}"
        else:
            formatted_msg = message
        
        if self.log_to_file and self.log_file:
            self.log_file.write(formatted_msg + "\n")
            self.log_file.flush()
        else:
            print(formatted_msg)
    
    def __del__(self):
        """Close log file on cleanup."""
        if self.log_file:
            self.log_file.close()
        
    def run_sweep(
        self,
        G: nx.Graph,
        param_grid: Dict[str, List[Any]],
        partition_fn: Callable,
        k_target: Optional[int] = None,
        weight: str = 'weight',
        n_trials: int = 3,
        baseline_fn: Optional[Callable] = None
    ) -> List[Dict]:
        """
        Run grid search over parameter combinations.
        
        Args:
            G: Input graph
            param_grid: Dict of parameter_name -> [values to try]
            partition_fn: Function that takes (G, k, **params) -> partition dict
            k_target: Number of partitions (if None, must be in param_grid as 'k_target')
            weight: Edge weight attribute
            n_trials: Number of trials per config (for stability)
            baseline_fn: Optional baseline function (e.g., METIS) for comparison
        
        Returns:
            List of result dicts with metrics
        """
        # Check if k_target is in param_grid
        k_in_grid = 'k_target' in param_grid
        if not k_in_grid and k_target is None:
            raise ValueError("k_target must be provided either as parameter or in param_grid")
        
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        
        total_configs = int(np.prod([len(v) for v in param_values]))
        
        self._log("="*80, add_timestamp=False)
        self._log(f"Starting parameter sweep: {total_configs} configs × {n_trials} trials = {total_configs * n_trials} total runs")
        self._log(f"Sweep ID: {self.sweep_id}")
        self._log(f"Output directory: {self.output_dir}")
        if not k_in_grid:
            self._log(f"Target partitions: {k_target}")
        self._log("="*80, add_timestamp=False)
        self._log("\nParameter grid:")
        for name, values in param_grid.items():
            self._log(f"  {name}: {values}", add_timestamp=False)
        self._log("")
        
        for config_idx, values in enumerate(product(*param_values)):
            params = dict(zip(param_names, values))
            
            # Extract k from params if in grid, otherwise use k_target
            k = params.pop('k_target') if k_in_grid else k_target
            
            self._log(f"\n{'='*80}", add_timestamp=False)
            self._log(f"[{config_idx+1}/{total_configs}] Testing configuration:")
            self._log(f"  k_target: {k}", add_timestamp=False)
            for key, val in params.items():
                self._log(f"  {key}: {val}", add_timestamp=False)
            self._log('='*80, add_timestamp=False)
            
            trial_results = []
            for trial in range(n_trials):
                result = self._run_single(
                    G, partition_fn, k, params, weight, trial
                )
                trial_results.append(result)
                if result['success']:
                    self._log(f"  Trial {trial+1}/{n_trials}: ✓ cut={result['cut']:.2f}, balance={result['balance_ratio']:.4f}, time={result['runtime']:.2f}s")
                else:
                    self._log(f"  Trial {trial+1}/{n_trials}: ✗ {result['error']}")
            
            # Re-add k_target to params for result storage
            params_with_k = params.copy()
            params_with_k['k_target'] = k
            
            # Aggregate trial results
            agg_result = self._aggregate_trials(params_with_k, trial_results)
            
            # Run baseline if provided
            if baseline_fn:
                self._log(f"\n  Running METIS baseline...")
                baseline_result = self._run_single(
                    G, baseline_fn, k, params, weight, 0
                )
                if baseline_result['success']:
                    self._log(f"  METIS baseline: cut={baseline_result['cut']:.2f}, balance={baseline_result['balance_ratio']:.4f}, time={baseline_result['runtime']:.2f}s")
                    self._log(f"  METIS weights: min={baseline_result['min_weight']:.2f}, max={baseline_result['max_weight']:.2f}, avg={baseline_result['avg_weight']:.2f}, std={baseline_result['std_weight']:.2f}")
                    agg_result['baseline_cut'] = baseline_result['cut']
                    agg_result['baseline_balance'] = baseline_result['balance_ratio']
                    agg_result['baseline_runtime'] = baseline_result['runtime']
                    agg_result['baseline_min_weight'] = baseline_result['min_weight']
                    agg_result['baseline_max_weight'] = baseline_result['max_weight']
                    agg_result['baseline_avg_weight'] = baseline_result['avg_weight']
                    agg_result['baseline_std_weight'] = baseline_result['std_weight']
                    
                    # Calculate improvement over baseline
                    if agg_result['success_rate'] > 0:
                        cut_improvement = ((agg_result['baseline_cut'] - agg_result['mean_cut']) / agg_result['baseline_cut'] * 100) if agg_result['baseline_cut'] > 0 else 0
                        self._log(f"  → Quantum vs METIS: cut improvement = {cut_improvement:+.2f}%")
                else:
                    self._log(f"  METIS baseline: ✗ {baseline_result['error']}")
            
            self.results.append(agg_result)
            
            # Print aggregate
            if agg_result['success_rate'] > 0:
                self._log(f"\n  → Aggregate: cut={agg_result['mean_cut']:.2f}±{agg_result['std_cut']:.2f}, "
                          f"balance={agg_result['mean_balance']:.4f}, "
                          f"time={agg_result['mean_runtime']:.2f}±{agg_result['std_runtime']:.2f}s")
            else:
                self._log(f"\n  → All trials failed!")
            
            # Save incrementally
            self._save_results()
        
        return self.results
    
    def _run_single(
        self,
        G: nx.Graph,
        partition_fn: Callable,
        k: int,
        params: Dict,
        weight: str,
        trial: int
    ) -> Dict:
        """Run single partitioning trial and collect metrics."""
        start_time = time.time()
        
        try:
            # Run partitioning
            partition = partition_fn(G, k, **params)
            runtime = time.time() - start_time
            
            # Compute metrics
            metrics = self._compute_metrics(G, partition, k, weight)
            metrics['runtime'] = runtime
            metrics['success'] = True
            metrics['error'] = None
            
        except Exception as e:
            runtime = time.time() - start_time
            metrics = {
                'runtime': runtime,
                'success': False,
                'error': str(e),
                'cut': float('inf'),
                'balance_ratio': 0.0,
                'max_imbalance': float('inf')
            }
        
        return metrics
    
    def _compute_metrics(
        self,
        G: nx.Graph,
        partition: Dict[int, int],
        k: int,
        weight: str
    ) -> Dict:
        """Compute partition quality metrics."""
        # Cut
        cut = 0.0
        for u, v, data in G.edges(data=True):
            if partition[u] != partition[v]:
                cut += float(data.get(weight, 1.0))
        
        # Balance
        part_weights = {}
        for node, part_id in partition.items():
            vw = float(G.nodes[node].get('vweight', 1.0))
            part_weights[part_id] = part_weights.get(part_id, 0.0) + vw
        
        weights = list(part_weights.values())
        if len(weights) == 0:
            # No partitions (error case)
            balance_ratio = 0.0
            max_imbalance = float('inf')
            min_weight = 0.0
            max_weight = 0.0
            avg_weight = 0.0
            std_weight = 0.0
        else:
            avg_weight = sum(weights) / len(weights)
            min_weight = min(weights)
            max_weight = max(weights)
            std_weight = float(np.std(weights))
            balance_ratio = min_weight / max_weight if max_weight > 0 else 0.0
            max_imbalance = max(abs(w - avg_weight) for w in weights) / avg_weight if avg_weight > 0 else float('inf')
        
        # Part sizes
        part_sizes = {}
        for node, part_id in partition.items():
            part_sizes[part_id] = part_sizes.get(part_id, 0) + 1
        
        return {
            'cut': cut,
            'balance_ratio': balance_ratio,
            'max_imbalance': max_imbalance,
            'num_parts': len(part_weights),
            'min_part_size': min(part_sizes.values()) if part_sizes else 0,
            'max_part_size': max(part_sizes.values()) if part_sizes else 0,
            'min_weight': float(min_weight),
            'max_weight': float(max_weight),
            'avg_weight': float(avg_weight),
            'std_weight': float(std_weight)
        }
    
    def _aggregate_trials(self, params: Dict, trials: List[Dict]) -> Dict:
        """Aggregate metrics across trials."""
        successes = [t for t in trials if t['success']]
        
        if not successes:
            return {
                'params': params,
                'n_trials': len(trials),
                'success_rate': 0.0,
                'mean_cut': float('inf'),
                'std_cut': 0.0,
                'min_cut': float('inf'),
                'mean_balance': 0.0,
                'mean_imbalance': float('inf'),
                'mean_runtime': np.mean([t['runtime'] for t in trials]),
                'std_runtime': np.std([t['runtime'] for t in trials]),
                'min_weight': 0.0,
                'max_weight': 0.0,
                'avg_weight': 0.0,
                'std_weight': 0.0,
                'errors': [t['error'] for t in trials]
            }
        
        return {
            'params': params,
            'n_trials': len(trials),
            'success_rate': len(successes) / len(trials),
            'mean_cut': float(np.mean([t['cut'] for t in successes])),
            'std_cut': float(np.std([t['cut'] for t in successes])),
            'min_cut': float(np.min([t['cut'] for t in successes])),
            'max_cut': float(np.max([t['cut'] for t in successes])),
            'mean_balance': float(np.mean([t['balance_ratio'] for t in successes])),
            'std_balance': float(np.std([t['balance_ratio'] for t in successes])),
            'mean_imbalance': float(np.mean([t['max_imbalance'] for t in successes])),
            'mean_runtime': float(np.mean([t['runtime'] for t in successes])),
            'std_runtime': float(np.std([t['runtime'] for t in successes])),
            'min_weight': float(np.mean([t['min_weight'] for t in successes])),
            'max_weight': float(np.mean([t['max_weight'] for t in successes])),
            'avg_weight': float(np.mean([t['avg_weight'] for t in successes])),
            'std_weight': float(np.mean([t['std_weight'] for t in successes]))
        }
    
    def _save_results(self):
        """Save results to JSON."""
        filepath = os.path.join(self.output_dir, f"sweep_{self.sweep_id}.json")
        
        # Save full results
        with open(filepath, 'w') as f:
            json.dump({
                'sweep_id': self.sweep_id,
                'timestamp': datetime.now().isoformat(),
                'n_configs': len(self.results),
                'results': self.results
            }, f, indent=2)
    
    def print_summary(self, top_n: int = 5, sort_by: str = 'cut'):
        """
        Print best configurations.
        
        Args:
            top_n: Number of top configs to show
            sort_by: Metric to sort by ('cut', 'balance', 'runtime')
        """
        if not self.results:
            self._log("No results to summarize.")
            return
        
        # Filter successful configs
        successful = [r for r in self.results if r['success_rate'] > 0]
        
        if not successful:
            self._log("No successful configurations!")
            return
        
        # Sort
        if sort_by == 'cut':
            sorted_results = sorted(successful, key=lambda x: x['mean_cut'])
            metric_name = "Cut"
        elif sort_by == 'balance':
            sorted_results = sorted(successful, key=lambda x: -x['mean_balance'])
            metric_name = "Balance"
        elif sort_by == 'runtime':
            sorted_results = sorted(successful, key=lambda x: x['mean_runtime'])
            metric_name = "Runtime"
        else:
            sorted_results = sorted(successful, key=lambda x: x['mean_cut'])
            metric_name = "Cut"
        
        self._log("\n" + "="*80, add_timestamp=False)
        self._log(f"TOP {min(top_n, len(sorted_results))} CONFIGURATIONS (sorted by {metric_name})")
        self._log("="*80, add_timestamp=False)
        
        for i, result in enumerate(sorted_results[:top_n], 1):
            self._log(f"\n{i}. Mean Cut: {result['mean_cut']:.2f} ± {result['std_cut']:.2f} (min: {result['min_cut']:.2f})", add_timestamp=False)
            self._log(f"   Balance: {result['mean_balance']:.4f} ± {result['std_balance']:.4f}", add_timestamp=False)
            self._log(f"   Imbalance: {result['mean_imbalance']:.4f}", add_timestamp=False)
            self._log(f"   Partition weights: min={result['min_weight']:.2f}, max={result['max_weight']:.2f}, avg={result['avg_weight']:.2f}, std={result['std_weight']:.2f}", add_timestamp=False)
            self._log(f"   Runtime: {result['mean_runtime']:.3f}s ± {result['std_runtime']:.3f}s", add_timestamp=False)
            self._log(f"   Success rate: {result['success_rate']:.1%}", add_timestamp=False)
            
            # Show baseline comparison if available
            if 'baseline_cut' in result:
                cut_improvement = ((result['baseline_cut'] - result['mean_cut']) / result['baseline_cut'] * 100) if result['baseline_cut'] > 0 else 0
                self._log(f"   METIS Baseline: cut={result['baseline_cut']:.2f}, balance={result['baseline_balance']:.4f}, time={result['baseline_runtime']:.3f}s", add_timestamp=False)
                self._log(f"   → Improvement: {cut_improvement:+.2f}% cut reduction vs METIS", add_timestamp=False)
            
            self._log(f"   Parameters:", add_timestamp=False)
            for k, v in result['params'].items():
                self._log(f"     {k}: {v}", add_timestamp=False)
        
        self._log("\n" + "="*80, add_timestamp=False)
        self._log(f"Results saved to: {self.output_dir}/sweep_{self.sweep_id}.json")
        if self.log_to_file and self.log_file:
            self._log(f"Log saved to: {self.log_file.name}")
        self._log("="*80, add_timestamp=False)


def create_annealing_wrapper(coarsen_fn, anneal_fn, lift_fn):
    """Create a partition function wrapper for quantum annealing with coarsening."""
    def partition_with_coarsening(G, k, **params):
        # Extract params
        coarsen_params = {
            'coarsen_limit': params.get('coarsen_limit', 100),
            'max_levels': params.get('max_levels', 200),
            'trial_seed': params.get('seed', 42),
            'weight': params.get('weight', 'weight')
        }
        anneal_params = {
            'balance_weight': params.get('balance_weight', 1.0),
            'num_reads': params.get('num_reads', 500),
            'choose_by': params.get('choose_by', 'vweight')
        }
        
        # Coarsen
        graphs, maps = coarsen_fn(G, **coarsen_params)
        Gc = graphs[-1]
        
        # Partition coarse graph
        part_coarse = anneal_fn(Gc, k, **anneal_params)
        
        # Lift to original
        part_orig = lift_fn(graphs, maps, part_coarse)
        
        return part_orig
    
    return partition_with_coarsening
