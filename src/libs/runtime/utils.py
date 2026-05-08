from __future__ import annotations

from scipy.io import mmread
from scipy.io import mmwrite
import scipy.sparse as sp
import numpy as np
import networkx as nx

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.colors import hsv_to_rgb, to_hex
from scipy import sparse


PARTITION_MATRIX_OUTPUTS = {
    "matrix_k_initial_graph_partitions.png",
    "matrix_k_coarsened_graph_partitions.png",
    "matrix_k_uncoarsened_graph_partitions.png",
    "matrix_k_original_vs_permuted_colored.png",
    "matrix_m_initial_graph_partitions.png",
    "matrix_m_coarsened_graph_partitions.png",
    "matrix_m_uncoarsened_graph_partitions.png",
    "matrix_m_original_vs_permuted_colored.png",
}

AVAILABLE_SAVE_OUTPUTS = {
    "coarsened_graph",
    "matrix_k_permuted",
    "matrix_m_permuted",
    "permutation",
    "matrix_sparsity_comparison",
    "run_metrics",
    "frac_within_band_plot",
    "run_simulation_parameters",
} | PARTITION_MATRIX_OUTPUTS


def resolve_parameters_file_path(data_dir: Path, raw_value: Any) -> Path:
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValueError("simulation_config.parameters_file_path must be a non-empty string")

    parameters_path = (data_dir / raw_value.strip()).resolve()
    data_dir_resolved = data_dir.resolve()
    try:
        parameters_path.relative_to(data_dir_resolved)
    except ValueError as exc:
        raise ValueError(
            "simulation_config.parameters_file_path must stay inside the simulation data directory"
        ) from exc

    if parameters_path.suffix.lower() != ".json":
        raise ValueError(
            f"simulation_config.parameters_file_path must reference a JSON file; got {raw_value!r}"
        )
    if not parameters_path.exists():
        raise FileNotFoundError(f"Configured parameters file not found: {parameters_path}")
    if not parameters_path.is_file():
        raise ValueError(f"Configured parameters path is not a file: {parameters_path}")

    return parameters_path


def validate_and_normalize_simulation_config(config: dict) -> dict:
    if not isinstance(config, dict):
        raise ValueError("simulation_config must be a JSON object")

    out = dict(config)
    allowed_keys = {
        "parameters_file_path",
        "input_matrices",
        "save_output",
    }
    unsupported_keys = sorted(set(out.keys()) - allowed_keys)
    if unsupported_keys:
        raise ValueError(
            "Unsupported simulation_config keys: " + ", ".join(unsupported_keys)
        )

    parameters_file_path = out.get("parameters_file_path")
    if not isinstance(parameters_file_path, str) or not parameters_file_path.strip():
        raise ValueError("simulation_config.parameters_file_path must be a non-empty string")
    parameters_file_path = parameters_file_path.strip()
    if Path(parameters_file_path).suffix.lower() != ".json":
        raise ValueError("simulation_config.parameters_file_path must reference a JSON file")

    input_matrices = out.get("input_matrices")
    if not isinstance(input_matrices, dict):
        raise ValueError("simulation_config.input_matrices must be a JSON object")
    for key in ("matrix_k_file_path", "matrix_m_file_path"):
        value = input_matrices.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"simulation_config.input_matrices.{key} must be a non-empty string")

    save_output = out.get("save_output", [])
    if save_output is None:
        save_output = []
    if not isinstance(save_output, list) or not all(isinstance(item, str) for item in save_output):
        raise ValueError("simulation_config.save_output must be a list of strings")
    unknown_outputs = sorted(set(save_output) - AVAILABLE_SAVE_OUTPUTS)
    if unknown_outputs:
        raise ValueError(
            "Unsupported simulation_config.save_output entries: " + ", ".join(unknown_outputs)
        )

    out.update(
        {
            "parameters_file_path": parameters_file_path,
            "input_matrices": {
                **dict(input_matrices),
                "matrix_k_file_path": str(input_matrices["matrix_k_file_path"]).strip(),
                "matrix_m_file_path": str(input_matrices["matrix_m_file_path"]).strip(),
            },
            "save_output": list(save_output),
        }
    )
    return out

def _as_csr_matrix(matrix: Any) -> sp.csr_matrix:
    if sp.issparse(matrix):
        return matrix.tocsr()
    return sp.csr_matrix(matrix)


def load_mtx(path, label=None):
    matrix_path = Path(path)
    matrix_name = label or matrix_path.name

    if not matrix_path.exists():
        raise FileNotFoundError(f"Matrix file for {matrix_name} not found: {matrix_path}")
    if matrix_path.suffix.lower() != ".mtx":
        raise ValueError(
            f"Unsupported matrix file for {matrix_name}: {matrix_path}. "
            "Only Matrix Market .mtx files are supported."
        )

    return _as_csr_matrix(mmread(matrix_path))


def resolve_matrix_input_path(
    matrices_dir: Path,
    input_matrices: dict[str, Any],
    *,
    key: str,
    label: str,
) -> Path:
    raw_value = input_matrices.get(key)
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValueError(
            f"simulation_config.input_matrices.{key} must be set to a Matrix Market .mtx file"
        )

    matrix_path = matrices_dir / raw_value
    if matrix_path.suffix.lower() != ".mtx":
        raise ValueError(
            f"simulation_config.input_matrices.{key} for matrix {label} must reference a Matrix Market .mtx file; "
            f"got {raw_value!r}"
        )
    if not matrix_path.exists():
        raise FileNotFoundError(f"Configured matrix file for {label} not found: {matrix_path}")

    return matrix_path

def write_json(path: Path, obj: Any) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("w", encoding="utf-8") as f:
		json.dump(obj, f, indent=2, sort_keys=True)

def write_results_table_text(path: Path, data: dict[str, Any]) -> None:
    def _format_value(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:.6g}"
        if isinstance(v, (int, np.integer)):
            return str(int(v))
        if isinstance(v, (np.floating,)):
            return f"{float(v):.6g}"
        if v is None:
            return ""
        return str(v).replace("\n", " ")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for matrix_name, matrix_metrics in data.items():
            f.write(f"Matrix {matrix_name} metrics (original x permuted)\n\n")

            structural = {}
            if isinstance(matrix_metrics, dict):
                structural = matrix_metrics.get("structural_metrics", {})

            original = structural.get("original", {}) if isinstance(structural, dict) else {}
            permuted = structural.get("permuted", {}) if isinstance(structural, dict) else {}

            keys = list(dict.fromkeys(list(original.keys()) + list(permuted.keys())))
            rows: list[tuple[str, str, str]] = []
            for k in keys:
                rows.append(
                    (
                        str(k),
                        _format_value(original.get(k, "")),
                        _format_value(permuted.get(k, "")),
                    )
                )

            w_metric = max([len("Metric")] + [len(r[0]) for r in rows])
            w_orig = max([len("Original")] + [len(r[1]) for r in rows])
            w_perm = max([len("Permuted")] + [len(r[2]) for r in rows])

            f.write(f"{'Metric'.ljust(w_metric)}  {'Original'.rjust(w_orig)}  {'Permuted'.rjust(w_perm)}\n")
            for metric, orig_v, perm_v in rows:
                f.write(
                    f"{metric.ljust(w_metric)}  {orig_v.rjust(w_orig)}  {perm_v.rjust(w_perm)}\n"
                )

            perm_check = matrix_metrics.get("permutation_check", {}) if isinstance(matrix_metrics, dict) else {}
            if isinstance(perm_check, dict) and len(perm_check) > 0:
                f.write("\nPermutation check\n")
                pc_rows = [(str(k), _format_value(v)) for k, v in perm_check.items()]
                w_k = max([len("Metric")] + [len(r[0]) for r in pc_rows])
                w_v = max([len("Value")] + [len(r[1]) for r in pc_rows])
                f.write(f"{'Metric'.ljust(w_k)}  {'Value'.rjust(w_v)}\n")
                for k, v in pc_rows:
                    f.write(f"{k.ljust(w_k)}  {v.rjust(w_v)}\n")

            f.write("\n\n")
    
def save_mtx(path: Path, matrix, *, comment: str = "") -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	mmwrite(path, matrix, comment=comment)


def graph_to_sparse_matrix(graph: nx.Graph, *, weight_attr: str = "weight") -> sp.csr_matrix:
    nodes = sorted(graph.nodes())
    matrix = nx.to_scipy_sparse_array(graph, nodelist=nodes, weight=weight_attr, format="csr")
    return _as_csr_matrix(matrix)


def coarsen_graph_with_mapping(
    graph: nx.Graph,
    fine_to_coarse: dict[int, int],
    *,
    weight_attr: str = "weight",
) -> nx.Graph:
    coarse_graph = nx.Graph()
    node_weights: dict[int, float] = {}
    edge_weights: dict[tuple[int, int], float] = {}

    for node in graph.nodes():
        coarse_node = int(fine_to_coarse[int(node)])
        node_weights[coarse_node] = node_weights.get(coarse_node, 0.0) + float(graph.nodes[node].get("vweight", 1.0))

    for coarse_node, node_weight in node_weights.items():
        coarse_graph.add_node(int(coarse_node), vweight=float(node_weight))

    for u, v, data in graph.edges(data=True):
        coarse_u = int(fine_to_coarse[int(u)])
        coarse_v = int(fine_to_coarse[int(v)])
        if coarse_u == coarse_v:
            continue
        edge_key = (coarse_u, coarse_v) if coarse_u < coarse_v else (coarse_v, coarse_u)
        edge_weights[edge_key] = edge_weights.get(edge_key, 0.0) + abs(float(data.get(weight_attr, 1.0)))

    for (coarse_u, coarse_v), edge_weight in edge_weights.items():
        coarse_graph.add_edge(int(coarse_u), int(coarse_v), **{weight_attr: float(edge_weight)})

    return coarse_graph


def build_graph_chain_from_maps(
    initial_graph: nx.Graph,
    maps: list[dict[int, int]],
    *,
    weight_attr: str = "weight",
) -> list[nx.Graph]:
    graphs = [initial_graph]
    current_graph = initial_graph
    for fine_to_coarse in maps:
        current_graph = coarsen_graph_with_mapping(current_graph, fine_to_coarse, weight_attr=weight_attr)
        graphs.append(current_graph)
    return graphs


def _build_distinct_node_colors(count: int) -> np.ndarray:
    if count <= 0:
        return np.empty((0, 3), dtype=float)
    hsv = np.column_stack(
        (
            np.linspace(0.0, 1.0, count, endpoint=False),
            np.full(count, 0.70, dtype=float),
            np.full(count, 0.95, dtype=float),
        )
    )
    return hsv_to_rgb(hsv)


def _build_partition_color_map(partitions: set[int]) -> dict[int, str]:
    sorted_partitions = sorted(int(partition) for partition in partitions)
    palette = _build_distinct_node_colors(len(sorted_partitions))
    return {
        partition: to_hex(palette[index], keep_alpha=False)
        for index, partition in enumerate(sorted_partitions)
    }


def _partition_order(partition: dict[int, int]) -> np.ndarray:
    return np.array(
        [
            int(node)
            for node, _ in sorted(
                ((int(node), int(partition_id)) for node, partition_id in partition.items()),
                key=lambda item: (item[1], item[0]),
            )
        ],
        dtype=int,
    )


def _permute_sparse_matrix(matrix: sp.csr_matrix, permutation: np.ndarray) -> sp.csr_matrix:
    permutation = np.asarray(permutation, dtype=int)
    matrix_coo = _as_csr_matrix(matrix).tocoo()
    inverse_permutation = np.empty_like(permutation)
    inverse_permutation[permutation] = np.arange(len(permutation))
    permuted_matrix = sp.coo_matrix(
        (matrix_coo.data, (inverse_permutation[matrix_coo.row], inverse_permutation[matrix_coo.col])),
        shape=matrix_coo.shape,
    )
    return permuted_matrix.tocsr()


def _expand_node_partition_labels(partition: dict[int, int], dof_per_node: int) -> np.ndarray:
    ordered_nodes = sorted(int(node) for node in partition.keys())
    expanded_labels = np.empty(len(ordered_nodes) * int(dof_per_node), dtype=np.int64)
    for node in ordered_nodes:
        start = int(node) * int(dof_per_node)
        stop = start + int(dof_per_node)
        expanded_labels[start:stop] = int(partition[node])
    return expanded_labels


def _permute_labels(labels: np.ndarray, permutation: np.ndarray) -> np.ndarray:
    permutation = np.asarray(permutation, dtype=int)
    labels = np.asarray(labels, dtype=np.int64)
    return labels[permutation]


def save_partition_matrix_plot(
    path: Path,
    matrix,
    labels: np.ndarray,
    *,
    partition_colors: dict[int, str] | None = None,
    title: str,
    dpi: int = 200,
) -> None:
    matrix_csr = _as_csr_matrix(matrix)
    matrix_coo = matrix_csr.tocoo()
    normalized_labels = np.asarray(labels, dtype=np.int64).ravel()
    matrix_size = matrix_csr.shape[0]
    if normalized_labels.shape[0] != matrix_size:
        raise ValueError("Matrix label count must match the matrix dimension")

    color_map = partition_colors or _build_partition_color_map(set(int(label) for label in normalized_labels.tolist()))
    row_colors = np.array([color_map[int(label)] for label in normalized_labels], dtype=object)

    figsize = (10.0, 10.0) if matrix_size <= 500 else (12.0, 12.0)
    fig, ax = plt.subplots(figsize=figsize, constrained_layout=True)

    marker_size = 18.0 if matrix_size <= 200 else 8.0 if matrix_size <= 2000 else 2.5
    if matrix_coo.nnz > 0:
        ax.scatter(
            matrix_coo.col,
            matrix_coo.row,
            c=row_colors[matrix_coo.row],
            s=marker_size,
            marker="s",
            linewidths=0,
        )

    diagonal_index = np.arange(matrix_size, dtype=int)
    if matrix_size > 0:
        ax.scatter(
            diagonal_index,
            diagonal_index,
            c=row_colors,
            s=marker_size * 1.5,
            marker="s",
            linewidths=0,
        )

    ax.set_title(title)
    ax.set_xlabel("Column index")
    ax.set_ylabel("Row index")
    ax.set_aspect("equal", adjustable="box")
    ax.invert_yaxis()
    ax.set_xlim(-0.5, max(matrix_size - 0.5, 0.5))
    ax.set_ylim(max(matrix_size - 0.5, 0.5), -0.5)

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi)
    plt.close(fig)


def save_coarse_graph_outputs(
    output_dir: Path,
    coarse_graph: nx.Graph,
    *,
    weight_attr: str = "weight",
    base_name: str = "coarsened_graph",
) -> None:
    coarse_matrix = graph_to_sparse_matrix(coarse_graph, weight_attr=weight_attr)
    save_mtx(
        output_dir / f"{base_name}.mtx",
        coarse_matrix,
        comment=f"Final coarse graph adjacency with {coarse_graph.number_of_nodes()} nodes",
    )


def save_partition_outputs(
    output_dir: Path,
    *,
    matrix_name: str,
    enabled_outputs: set[str],
    initial_graph: nx.Graph,
    coarse_graph: nx.Graph,
    final_graph: nx.Graph,
    original_matrix,
    permuted_matrix,
    coarse_partition: dict[int, int],
    final_partition: dict[int, int],
    permutation: np.ndarray,
    dof_per_node: int,
    weight_attr: str = "weight",
) -> None:
    color_map = _build_partition_color_map(
        set(int(partition_id) for partition_id in coarse_partition.values())
        | set(int(partition_id) for partition_id in final_partition.values())
    )

    initial_graph_matrix = graph_to_sparse_matrix(initial_graph, weight_attr=weight_attr)
    initial_graph_labels = np.array([int(final_partition[int(node)]) for node in sorted(initial_graph.nodes())], dtype=np.int64)

    coarse_graph_matrix = graph_to_sparse_matrix(coarse_graph, weight_attr=weight_attr)
    coarse_graph_labels = np.array([int(coarse_partition[int(node)]) for node in sorted(coarse_graph.nodes())], dtype=np.int64)

    final_graph_matrix = graph_to_sparse_matrix(final_graph, weight_attr=weight_attr)
    final_graph_order = _partition_order(final_partition)
    final_graph_labels = np.array([int(final_partition[int(node)]) for node in sorted(final_graph.nodes())], dtype=np.int64)
    final_graph_matrix_permuted = _permute_sparse_matrix(final_graph_matrix, final_graph_order)
    final_graph_labels_permuted = final_graph_labels[final_graph_order]

    original_matrix_labels = _expand_node_partition_labels(final_partition, dof_per_node)
    permuted_matrix_labels = _permute_labels(original_matrix_labels, permutation)

    initial_output_name = f"matrix_{matrix_name.lower()}_initial_graph_partitions.png"
    coarse_output_name = f"matrix_{matrix_name.lower()}_coarsened_graph_partitions.png"
    final_output_name = f"matrix_{matrix_name.lower()}_uncoarsened_graph_partitions.png"
    comparison_output_name = f"matrix_{matrix_name.lower()}_original_vs_permuted_colored.png"

    if initial_output_name in enabled_outputs:
        save_partition_matrix_plot(
            output_dir / initial_output_name,
            initial_graph_matrix,
            initial_graph_labels,
            partition_colors=color_map,
            title=f"Initial {matrix_name} graph colored by partition",
        )
    if coarse_output_name in enabled_outputs:
        save_partition_matrix_plot(
            output_dir / coarse_output_name,
            coarse_graph_matrix,
            coarse_graph_labels,
            partition_colors=color_map,
            title=f"Coarsened {matrix_name} graph colored by partition",
        )
    if final_output_name in enabled_outputs:
        save_partition_matrix_plot(
            output_dir / final_output_name,
            final_graph_matrix_permuted,
            final_graph_labels_permuted,
            partition_colors=color_map,
            title=f"Uncoarsened {matrix_name} graph colored by partition",
        )

    if comparison_output_name in enabled_outputs:
        fig, axes = plt.subplots(1, 2, figsize=(16.0, 7.5), constrained_layout=True)
        comparison_targets = [
            (original_matrix, original_matrix_labels, f"Original {matrix_name} colored by partition"),
            (permuted_matrix, permuted_matrix_labels, f"Permuted {matrix_name} colored by partition"),
        ]
        for ax, (matrix, labels, title_text) in zip(axes, comparison_targets):
            matrix_csr = _as_csr_matrix(matrix)
            matrix_coo = matrix_csr.tocoo()
            label_colors = np.array([color_map[int(label)] for label in np.asarray(labels, dtype=np.int64)], dtype=object)
            matrix_size = matrix_csr.shape[0]
            marker_size = 10.0 if matrix_size <= 400 else 4.0 if matrix_size <= 4000 else 1.5
            if matrix_coo.nnz > 0:
                ax.scatter(
                    matrix_coo.col,
                    matrix_coo.row,
                    c=label_colors[matrix_coo.row],
                    s=marker_size,
                    marker="s",
                    linewidths=0,
                )
            diagonal_index = np.arange(matrix_size, dtype=int)
            ax.scatter(
                diagonal_index,
                diagonal_index,
                c=label_colors,
                s=marker_size * 1.5,
                marker="s",
                linewidths=0,
            )
            ax.set_title(title_text)
            ax.set_xlabel("Column index")
            ax.set_ylabel("Row index")
            ax.set_aspect("equal", adjustable="box")
            ax.invert_yaxis()
            ax.set_xlim(-0.5, max(matrix_size - 0.5, 0.5))
            ax.set_ylim(max(matrix_size - 0.5, 0.5), -0.5)

        comparison_path = output_dir / comparison_output_name
        comparison_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(comparison_path, dpi=200)
        plt.close(fig)


def save_partition_outputs_for_both_matrices(
    output_dir: Path,
    *,
    enabled_outputs: set[str],
    initial_graph_k: nx.Graph,
    initial_graph_m: nx.Graph,
    coarse_graph_k: nx.Graph,
    coarse_graph_m: nx.Graph,
    final_graph_k: nx.Graph,
    final_graph_m: nx.Graph,
    original_matrix_k,
    original_matrix_m,
    permuted_matrix_k,
    permuted_matrix_m,
    coarse_partition: dict[int, int],
    final_partition: dict[int, int],
    permutation: np.ndarray,
    dof_per_node: int,
    weight_attr: str = "weight",
) -> None:
    save_partition_outputs(
        output_dir,
        matrix_name="K",
        enabled_outputs=enabled_outputs,
        initial_graph=initial_graph_k,
        coarse_graph=coarse_graph_k,
        final_graph=final_graph_k,
        original_matrix=original_matrix_k,
        permuted_matrix=permuted_matrix_k,
        coarse_partition=coarse_partition,
        final_partition=final_partition,
        permutation=permutation,
        dof_per_node=dof_per_node,
        weight_attr=weight_attr,
    )
    save_partition_outputs(
        output_dir,
        matrix_name="M",
        enabled_outputs=enabled_outputs,
        initial_graph=initial_graph_m,
        coarse_graph=coarse_graph_m,
        final_graph=final_graph_m,
        original_matrix=original_matrix_m,
        permuted_matrix=permuted_matrix_m,
        coarse_partition=coarse_partition,
        final_partition=final_partition,
        permutation=permutation,
        dof_per_node=dof_per_node,
        weight_attr=weight_attr,
    )

def save_permutation_txt(path: Path, permutation: np.ndarray) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	np.savetxt(path, np.asarray(permutation, dtype=np.int64), fmt="%d")

def matrix_to_graph(A, dof_per_node: int = 1):
    """Convert a (sparse/dense) matrix into an undirected NetworkX graph.

    Minimal behavior:
    - If dof_per_node > 1, aggregate DOF blocks to node-level adjacency
    - Uses absolute values for edge weights
    - Symmetrizes by sum (A + A^T)
    - Drops diagonal/self-loops
    - Edge weights stored under attribute 'weight'
    """
    if not sp.issparse(A):
        A = sp.csr_matrix(A)
    A = A.tocsr()

    d = int(dof_per_node)
    if d > 1:
        C = A.tocoo()
        values = np.abs(C.data)
        node_row = (C.row // d).astype(int)
        node_col = (C.col // d).astype(int)
        n = A.shape[0] // d
        A = sp.coo_matrix((values, (node_row, node_col)), shape=(n, n)).tocsr()
    else:
        C = A.tocoo()
        C.data = np.abs(C.data)
        A = C.tocsr()

    A = A + A.T
    A.setdiag(0)
    A.eliminate_zeros()

    return nx.from_scipy_sparse_array(A, create_using=nx.Graph, edge_attribute='weight')

def save_matrices_sparsity_comparison(
    A,
    B,
    name_a: str = "K",
    name_b: str = "M",
    figsize=(12, 5),
    markersize: float = 0.5,
    *,
    save_path: str | None = None,
    dpi: int = 200,
):
    fig, axes = plt.subplots(1, 2, figsize=figsize, constrained_layout=True)

    for ax, mat, title in zip(axes, [A, B], [name_a, name_b]):
        if sparse.issparse(mat):
            ax.spy(mat, markersize=markersize, color="black")
        else:
            ax.spy(mat != 0, markersize=markersize, color="black")
        ax.set_title(f"Sparsity pattern: {title}")
        ax.set_xlabel("Column index")
        ax.set_ylabel("Row index")

    fig.savefig(save_path, dpi=dpi)


def validate_and_normalize_simulation_parameters(params: dict) -> dict:
    """Validate and normalize simulation parameters.

    - Enforces presence of required keys and basic value ranges.
    - Coerces a small set of common JSON-ish types (e.g. "True" -> True).
    - Ignores unknown keys (keeps them as-is).

    Returns a normalized parameters dict with the same overall structure.
    """

    def _require_dict(obj: Any, name: str) -> dict:
        if not isinstance(obj, dict):
            raise ValueError(f"{name} must be a JSON object")
        return obj

    def _coerce_int(v: Any, name: str) -> int:
        if isinstance(v, bool):
            raise ValueError(f"{name} must be an integer")
        if isinstance(v, (int, np.integer)):
            return int(v)
        if isinstance(v, (float, np.floating)) and float(v).is_integer():
            return int(v)
        if isinstance(v, str) and v.strip() != "":
            try:
                return int(v)
            except (TypeError, ValueError, OverflowError) as e:
                raise ValueError(f"{name} must be an integer") from e
        raise ValueError(f"{name} must be an integer")

    def _coerce_float(v: Any, name: str) -> float:
        if isinstance(v, bool):
            raise ValueError(f"{name} must be a number")
        if isinstance(v, (int, np.integer, float, np.floating)):
            vf = float(v)
            if not np.isfinite(vf):
                raise ValueError(f"{name} must be a finite number")
            return vf
        if isinstance(v, str) and v.strip() != "":
            try:
                vf = float(v)
            except (TypeError, ValueError, OverflowError) as e:
                raise ValueError(f"{name} must be a number") from e
            if not np.isfinite(vf):
                raise ValueError(f"{name} must be a finite number")
            return vf
        raise ValueError(f"{name} must be a number")

    def _coerce_bool(v: Any, name: str) -> bool:
        if isinstance(v, bool):
            return bool(v)
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("true", "1", "yes", "y"):
                return True
            if s in ("false", "0", "no", "n"):
                return False
        raise ValueError(f"{name} must be a boolean")

    def _coerce_optional_str(v: Any, name: str) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            if s == "":
                raise ValueError(f"{name} must be a non-empty string if provided")
            return s
        raise ValueError(f"{name} must be a string if provided")

    params = _require_dict(params, "simulation_parameters")

    out = dict(params)
    gp = _require_dict(out.get("general_parameters"), "general_parameters")
    cp = _require_dict(out.get("coarsening_parameters"), "coarsening_parameters")
    pp = _require_dict(out.get("partitioning_parameters"), "partitioning_parameters")
    up = _require_dict(out.get("uncoarsening_parameters"), "uncoarsening_parameters")

    # general_parameters
    dof_per_node = _coerce_int(gp.get("dof_per_node"), "general_parameters.dof_per_node")
    if dof_per_node <= 0:
        raise ValueError("general_parameters.dof_per_node must be > 0")
    seed = _coerce_int(gp.get("seed"), "general_parameters.seed")
    gp_out = dict(gp)
    gp_out.update({"dof_per_node": dof_per_node, "seed": seed})

    # coarsening_parameters
    coarsen_inferior_raw = cp.get("coarsen_inferior_limit")
    if coarsen_inferior_raw is None:
        raise ValueError("coarsening_parameters.coarsen_inferior_limit must be provided")
    coarsen_inferior_limit = _coerce_int(
        coarsen_inferior_raw,
        "coarsening_parameters.coarsen_inferior_limit",
    )
    if coarsen_inferior_limit < 1:
        raise ValueError("coarsening_parameters.coarsen_inferior_limit must be >= 1")

    coarsen_superior_raw = cp.get("coarsen_superior_limit")
    if coarsen_superior_raw is not None:
        coarsen_superior_limit = _coerce_int(
            coarsen_superior_raw,
            "coarsening_parameters.coarsen_superior_limit",
        )
        if coarsen_superior_limit < coarsen_inferior_limit:
            raise ValueError(
                "coarsening_parameters.coarsen_superior_limit must be >= coarsening_parameters.coarsen_inferior_limit"
            )
    else:
        coarsen_superior_limit = None

    max_levels = _coerce_int(cp.get("max_levels"), "coarsening_parameters.max_levels")
    if max_levels < 1:
        raise ValueError("coarsening_parameters.max_levels must be >= 1")
    weight = cp.get("weight")
    if not isinstance(weight, str) or not weight.strip():
        raise ValueError("coarsening_parameters.weight must be a non-empty string")
    strategy = cp.get("strategy")
    if not isinstance(strategy, str) or not strategy.strip():
        raise ValueError("coarsening_parameters.strategy must be a non-empty string")
    strategy = strategy.strip().lower()
    if strategy not in ("random", "sorted", "modified", "light"):
        raise ValueError(
            "coarsening_parameters.strategy must be one of: random, sorted, modified, light"
        )
    coarsen_ratio = _coerce_float(cp.get("coarsen_ratio"), "coarsening_parameters.coarsen_ratio")
    if not (0.0 < coarsen_ratio <= 1.0):
        raise ValueError("coarsening_parameters.coarsen_ratio must be in (0, 1]")
    max_node_weight = cp.get("max_node_weight")
    if max_node_weight is not None:
        max_node_weight = _coerce_float(max_node_weight, "coarsening_parameters.max_node_weight")
        if max_node_weight <= 0.0:
            raise ValueError("coarsening_parameters.max_node_weight must be > 0 if provided")

    cp_out = dict(cp)
    cp_out.update(
        {
            "coarsen_inferior_limit": coarsen_inferior_limit,
            "coarsen_superior_limit": coarsen_superior_limit,
            "max_levels": max_levels,
            "weight": weight.strip(),
            "strategy": strategy,
            "coarsen_ratio": coarsen_ratio,
            "max_node_weight": max_node_weight,
        }
    )

    # partitioning_parameters
    partitioning_strategy = pp.get("partitioning_strategy")
    if not isinstance(partitioning_strategy, str) or not partitioning_strategy.strip():
        raise ValueError("partitioning_parameters.partitioning_strategy must be a non-empty string")
    partitioning_strategy = partitioning_strategy.strip()
    if partitioning_strategy not in (
        "metis_partitioning",
        "quantum_annealing",
        "quantum_approximation_optimizer",
    ):
        raise ValueError(
            "partitioning_parameters.partitioning_strategy must be one of: "
            "metis_partitioning, quantum_annealing, quantum_approximation_optimizer"
        )

    common_raw = pp.get("common")
    if common_raw is None:
        common_raw = {}
    common = _require_dict(common_raw, "partitioning_parameters.common")

    # Defaults (from your tables)
    k_target = _coerce_int(
        common.get("k_target", 2), "partitioning_parameters.common.k_target"
    )
    if k_target < 1:
        raise ValueError("partitioning_parameters.common.k_target must be >= 1")
    balance_tolerance = _coerce_float(
        common.get("balance_tolerance", 0.1), "partitioning_parameters.common.balance_tolerance"
    )
    if balance_tolerance < 0.0:
        raise ValueError("partitioning_parameters.common.balance_tolerance must be >= 0")

    strategies_raw = pp.get("strategies")
    if strategies_raw is None:
        strategies_raw = {}
    strategies = _require_dict(strategies_raw, "partitioning_parameters.strategies")

    strat_raw = strategies.get(partitioning_strategy)
    if strat_raw is None:
        strat_raw = {}
    strat_params = _require_dict(
        strat_raw,
        f"partitioning_parameters.strategies.{partitioning_strategy}",
    )

    def _value_or_default(key: str, default: Any) -> Any:
        if key in strat_params and strat_params.get(key) is None:
            raise ValueError(
                f"partitioning_parameters.strategies.{partitioning_strategy}.{key} cannot be null"
            )
        return strat_params.get(key, default)

    strat_out = dict(strat_params)
    if partitioning_strategy == "quantum_annealing":
        # Defaults (from your tables)
        qa_defaults = {
            "qubo_balance_lambda": 0.1,
            "num_reads": 5,
            "num_starts": 5,
            "balance_violation_lambda": 0.1,
            "simulated": True,
        }
        strat_out["qubo_balance_lambda"] = _coerce_float(
            _value_or_default("qubo_balance_lambda", qa_defaults["qubo_balance_lambda"]),
            "partitioning_parameters.strategies.quantum_annealing.qubo_balance_lambda",
        )
        strat_out["num_starts"] = _coerce_int(
            _value_or_default("num_starts", qa_defaults["num_starts"]),
            "partitioning_parameters.strategies.quantum_annealing.num_starts",
        )
        if strat_out["num_starts"] < 1:
            raise ValueError("partitioning_parameters.strategies.quantum_annealing.num_starts must be >= 1")
        strat_out["num_reads"] = _coerce_int(
            _value_or_default("num_reads", qa_defaults["num_reads"]),
            "partitioning_parameters.strategies.quantum_annealing.num_reads",
        )
        if strat_out["num_reads"] < 1:
            raise ValueError("partitioning_parameters.strategies.quantum_annealing.num_reads must be >= 1")
        strat_out["balance_violation_lambda"] = _coerce_float(
            _value_or_default(
                "balance_violation_lambda", qa_defaults["balance_violation_lambda"]
            ),
            "partitioning_parameters.strategies.quantum_annealing.balance_violation_lambda",
        )
        if strat_out["balance_violation_lambda"] < 0.0:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_annealing.balance_violation_lambda must be >= 0"
            )
        strat_out["simulated"] = _coerce_bool(
            _value_or_default("simulated", qa_defaults["simulated"]),
            "partitioning_parameters.strategies.quantum_annealing.simulated",
        )
        strat_out["qpu_solver_name"] = _coerce_optional_str(
            strat_params.get("qpu_solver_name"),
            "partitioning_parameters.strategies.quantum_annealing.qpu_solver_name",
        )
        strat_out["qpu_region"] = _coerce_optional_str(
            strat_params.get("qpu_region"),
            "partitioning_parameters.strategies.quantum_annealing.qpu_region",
        )
        strat_out["qpu_problem_label"] = _coerce_optional_str(
            strat_params.get("qpu_problem_label"),
            "partitioning_parameters.strategies.quantum_annealing.qpu_problem_label",
        )
    elif partitioning_strategy == "quantum_approximation_optimizer":
        # Defaults (from your tables)
        qaoa_defaults = {
            "qubo_balance_lambda": 0.1,
            "num_starts": 12,
            "balance_violation_lambda": 0.1,
            "circuit_depth": 12,
            "num_steps": 12,
            "num_shots": 5,
            "simulated": True,
        }
        if "qaoa_backend" in strat_params:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_approximation_optimizer.qaoa_backend is no longer used. "
                "Use simulated=true for PennyLane or simulated=false with qlm_qpu_name for QLM execution."
            )
        if "qlm_remote" in strat_params:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_approximation_optimizer.qlm_remote is no longer used. "
                "QAOA uses PennyLane when simulated=true and the QLM backend named by qlm_qpu_name when simulated=false."
            )
        if "qlm_require_gate_based_hardware" in strat_params:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_approximation_optimizer.qlm_require_gate_based_hardware is no longer supported. "
                "The repository now keeps only backend information that is actually exposed by the QLM API."
            )
        strat_out["qubo_balance_lambda"] = _coerce_float(
            _value_or_default("qubo_balance_lambda", qaoa_defaults["qubo_balance_lambda"]),
            "partitioning_parameters.strategies.quantum_approximation_optimizer.qubo_balance_lambda",
        )
        strat_out["num_starts"] = _coerce_int(
            _value_or_default("num_starts", qaoa_defaults["num_starts"]),
            "partitioning_parameters.strategies.quantum_approximation_optimizer.num_starts",
        )
        if strat_out["num_starts"] < 1:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_approximation_optimizer.num_starts must be >= 1"
            )
        strat_out["num_steps"] = _coerce_int(
            _value_or_default("num_steps", qaoa_defaults["num_steps"]),
            "partitioning_parameters.strategies.quantum_approximation_optimizer.num_steps",
        )
        if strat_out["num_steps"] < 1:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_approximation_optimizer.num_steps must be >= 1"
            )
        strat_out["num_shots"] = _coerce_int(
            _value_or_default("num_shots", qaoa_defaults["num_shots"]),
            "partitioning_parameters.strategies.quantum_approximation_optimizer.num_shots",
        )
        if strat_out["num_shots"] < 1:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_approximation_optimizer.num_shots must be >= 1"
            )
        strat_out["balance_violation_lambda"] = _coerce_float(
            _value_or_default(
                "balance_violation_lambda", qaoa_defaults["balance_violation_lambda"]
            ),
            "partitioning_parameters.strategies.quantum_approximation_optimizer.balance_violation_lambda",
        )
        if strat_out["balance_violation_lambda"] < 0.0:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_approximation_optimizer.balance_violation_lambda must be >= 0"
            )
        strat_out["circuit_depth"] = _coerce_int(
            _value_or_default("circuit_depth", qaoa_defaults["circuit_depth"]),
            "partitioning_parameters.strategies.quantum_approximation_optimizer.circuit_depth",
        )
        if strat_out["circuit_depth"] < 1:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_approximation_optimizer.circuit_depth must be >= 1"
            )
        strat_out["simulated"] = _coerce_bool(
            _value_or_default("simulated", qaoa_defaults["simulated"]),
            "partitioning_parameters.strategies.quantum_approximation_optimizer.simulated",
        )
        if strat_out["simulated"]:
            strat_out["adam_learning_rate"] = _coerce_float(
                _value_or_default("adam_learning_rate", 0.1),
                "partitioning_parameters.strategies.quantum_approximation_optimizer.adam_learning_rate",
            )
            if strat_out["adam_learning_rate"] <= 0.0:
                raise ValueError(
                    "partitioning_parameters.strategies.quantum_approximation_optimizer.adam_learning_rate must be > 0"
                )
        else:
            adam_learning_rate = strat_params.get("adam_learning_rate")
            if adam_learning_rate is not None:
                adam_learning_rate = _coerce_float(
                    adam_learning_rate,
                    "partitioning_parameters.strategies.quantum_approximation_optimizer.adam_learning_rate",
                )
                if adam_learning_rate <= 0.0:
                    raise ValueError(
                        "partitioning_parameters.strategies.quantum_approximation_optimizer.adam_learning_rate must be > 0"
                    )
            strat_out["adam_learning_rate"] = adam_learning_rate
        strat_out["qlm_qpu_name"] = _coerce_optional_str(
            strat_params.get("qlm_qpu_name"),
            "partitioning_parameters.strategies.quantum_approximation_optimizer.qlm_qpu_name",
        )
        if not strat_out["simulated"] and not strat_out["qlm_qpu_name"]:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_approximation_optimizer.qlm_qpu_name must be set when simulated is false"
            )
    else:
        # metis_partitioning requires no extra keys
        strat_out = dict(strat_params)

    pp_out = dict(pp)
    pp_out.update(
        {
            "partitioning_strategy": partitioning_strategy,
            "common": {"k_target": k_target, "balance_tolerance": balance_tolerance, **{k: v for k, v in common.items() if k not in ("k_target", "balance_tolerance")}},
            "strategies": {**strategies, partitioning_strategy: strat_out},
        }
    )

    # uncoarsening_parameters
    refine_objective = up.get("refine_objective")
    if not isinstance(refine_objective, str) or not refine_objective.strip():
        raise ValueError("uncoarsening_parameters.refine_objective must be a non-empty string")
    refine_objective = refine_objective.strip().lower()
    if refine_objective not in ("cut", "cut_balance"):
        raise ValueError("uncoarsening_parameters.refine_objective must be 'cut' or 'cut_balance'")
    refine_balance_lambda = _coerce_float(
        up.get("refine_balance_lambda"), "uncoarsening_parameters.refine_balance_lambda"
    )
    if refine_balance_lambda < 0.0:
        raise ValueError("uncoarsening_parameters.refine_balance_lambda must be >= 0")
    refine_max_passes_per_level = _coerce_int(
        up.get("refine_max_passes_per_level"), "uncoarsening_parameters.refine_max_passes_per_level"
    )
    if refine_max_passes_per_level < 0:
        raise ValueError("uncoarsening_parameters.refine_max_passes_per_level must be >= 0")
    refine_max_moves_per_pass = up.get("refine_max_moves_per_pass")
    if refine_max_moves_per_pass is not None:
        refine_max_moves_per_pass = _coerce_int(
            refine_max_moves_per_pass, "uncoarsening_parameters.refine_max_moves_per_pass"
        )
        if refine_max_moves_per_pass < 1:
            raise ValueError("uncoarsening_parameters.refine_max_moves_per_pass must be >= 1 if provided")

    validate_node_weights = up.get("validate_node_weights")
    if validate_node_weights is not None:
        validate_node_weights = _coerce_bool(
            validate_node_weights, "uncoarsening_parameters.validate_node_weights"
        )

    up_out = dict(up)
    up_out.update(
        {
            "refine_objective": refine_objective,
            "refine_balance_lambda": refine_balance_lambda,
            "refine_max_passes_per_level": refine_max_passes_per_level,
            "refine_max_moves_per_pass": refine_max_moves_per_pass,
            "validate_node_weights": validate_node_weights,
        }
    )

    out.update(
        {
            "general_parameters": gp_out,
            "coarsening_parameters": cp_out,
            "partitioning_parameters": pp_out,
            "uncoarsening_parameters": up_out,
        }
    )
    return out