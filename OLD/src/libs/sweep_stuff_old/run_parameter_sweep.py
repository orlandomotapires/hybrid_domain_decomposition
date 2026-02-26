"""
Run parameter sweep for quantum graph partitioning.
Usage: python src/run_parameter_sweep.py
"""
import os
import sys

# Add src to path
sys.path.insert(0, os.path.dirname(__file__))

from libs.sweep_stuff_old.parameter_sweep import ParameterSweep, create_annealing_wrapper
from libs.multilevel_squeme.coarsening import coarsen_chain
from libs.multilevel_squeme.quantum_annealing import recursive_kway_anneal, lift_partition_to_finer
from libs.metis_backend import partition_graph_metis
from libs.utils import load_mtx, matrix_to_graph


def main():
    print("="*80)
    print("QUANTUM GRAPH PARTITIONING - PARAMETER SWEEP")
    print("="*80)
    
    # Create output directory first
    output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "results", "sweeps"))
    os.makedirs(output_dir, exist_ok=True)
    
    # Initialize sweep (this creates the log file)
    sweep = ParameterSweep(output_dir=output_dir, log_to_file=True)
    
    print(f"Sweep ID: {sweep.sweep_id}")
    print(f"Log file: {output_dir}/sweep_{sweep.sweep_id}.log")
    print(f"Results: {output_dir}/sweep_{sweep.sweep_id}.json")
    print("\n⚠️  All detailed output is being written to the log file.")
    print("You can monitor progress with:")
    print(f"  tail -f {output_dir}/sweep_{sweep.sweep_id}.log")
    print("\nStarting sweep...\n")
    
    # Load data
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    k_matrix_path = os.path.join(data_dir, "hybrid_ma.classical.fem.matrix_k.mtx")
    
    sweep._log("Loading matrix...")
    A_K = load_mtx(k_matrix_path, 'K')
    if A_K is None:
        sweep._log("ERROR: Matrix load failed")
        raise RuntimeError("Matrix load failed")
    
    sweep._log(f"Loaded: K | shape={A_K.shape}, nnz={A_K.nnz}")
    
    # Build graph
    diag_K = A_K.diagonal()
    G_K = matrix_to_graph(
        A_K, symmetrize='sum', drop_diagonal=True,
        abs_weights=True, node_vweight='diag', diag=diag_K
    )
    sweep._log(f"Graph: |V|={G_K.number_of_nodes()}, |E|={G_K.number_of_edges()}")
    
    # Define parameter grid
    param_grid = {
        'coarsen_limit': list(range(200, 1000, 100)),      # [200, 300, 400, 500, 600, 700, 800, 900]
        'balance_weight': [round(x, 1) for x in [i/10 for i in range(1, 31, 5)]],  # [0.1, 0.3, 0.5, ..., 2.9]
        'num_reads': list(range(50, 501, 100)),          # [50, 100, 150, 200, 250, 300, 350, 400, 450, 500]
        #'k_target': list(range(2, 65, 2)),              # [2, 4, 6, 8, ..., 64]
    }
    
    # Fixed parameters
    n_trials = 3
    
    # Create partition function wrapper
    partition_fn = create_annealing_wrapper(
        coarsen_chain,
        recursive_kway_anneal,
        lift_partition_to_finer
    )
    
    # Create METIS baseline wrapper
    def metis_baseline(G, k, **params):
        """METIS baseline using coarsening with same coarsen_limit."""
        coarsen_limit = params.get('coarsen_limit', 100)
        graphs, maps = coarsen_chain(
            G,
            coarsen_limit=coarsen_limit,
            max_levels=params.get('max_levels', 200),
            trial_seed=params.get('seed', 42),
            weight=params.get('weight', 'weight')
        )
        Gc = graphs[-1]
        
        # Use METIS on coarse graph
        part_coarse = partition_graph_metis(
            Gc,
            nparts=k,
            weight='weight',
            seed=42,
            verbose=False
        )
        
        # Lift to original
        part_orig = lift_partition_to_finer(graphs, maps, part_coarse)
        return part_orig
    
    # Run sweep with baseline
    results = sweep.run_sweep(
        G_K,
        param_grid,
        partition_fn,
        k_target=32,  # k_target is in param_grid
        weight='weight',
        n_trials=n_trials,
        baseline_fn=metis_baseline
    )
    
    # Print summary to log
    sweep._log("\n\n=== SWEEP COMPLETE ===\n")
    sweep.print_summary(top_n=10, sort_by='cut')
    
    # Print minimal summary to console
    print("\n" + "="*80)
    print("SWEEP COMPLETE!")
    print("="*80)
    successful = [r for r in results if r['success_rate'] > 0]
    if successful:
        best = sorted(successful, key=lambda x: x['mean_cut'])[0]
        print(f"\n✅ Best configuration found:")
        print(f"   Mean Cut: {best['mean_cut']:.2f} ± {best['std_cut']:.2f}")
        print(f"   Balance: {best['mean_balance']:.4f}")
        print(f"   Partition weights: min={best['min_weight']:.2f}, max={best['max_weight']:.2f}, avg={best['avg_weight']:.2f}, std={best['std_weight']:.2f}")
        print(f"   Runtime: {best['mean_runtime']:.3f}s")
        
        # Show baseline comparison if available
        if 'baseline_cut' in best:
            cut_improvement = ((best['baseline_cut'] - best['mean_cut']) / best['baseline_cut'] * 100) if best['baseline_cut'] > 0 else 0
            print(f"   METIS Baseline: cut={best['baseline_cut']:.2f} (improvement: {cut_improvement:+.2f}%)")
        
        print(f"   Parameters: {best['params']}")
    else:
        print("\n❌ No successful configurations")
    
    print(f"\n📄 Full results:")
    print(f"   Log: {output_dir}/sweep_{sweep.sweep_id}.log")
    print(f"   JSON: {output_dir}/sweep_{sweep.sweep_id}.json")
    print("="*80)


if __name__ == "__main__":
    main()
