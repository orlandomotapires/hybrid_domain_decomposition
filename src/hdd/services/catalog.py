"""User-facing names of methods and options. Pure data, shared by every front end."""

from __future__ import annotations

METHOD_LABELS = {
    "metis": "METIS (Classical)",
    "qa_emulated": "Quantum Annealing (Emulated)",
    "qa_hardware": "Quantum Annealing (D-Wave QPU)",
    "qaoa_emulated": "QAOA (Emulated)",
    "qaoa_hardware": "QAOA (QLM Hardware)",
}

METHOD_SHORT_LABELS = {
    "metis": "METIS",
    "qa_emulated": "QA Emulated",
    "qa_hardware": "QA D-Wave",
    "qaoa_emulated": "QAOA Emulated",
    "qaoa_hardware": "QAOA QLM",
}

#: Categorical colour slot of each method in plots, fixed so a method keeps its colour everywhere.
METHOD_SLOT = {"metis": 0, "qa_emulated": 1, "qa_hardware": 3, "qaoa_emulated": 2, "qaoa_hardware": 4}

STAGE_LABELS = {
    "initialization": "Graph construction",
    "coarsening": "Coarsening",
    "partitioning": "Partitioning",
    "uncoarsening": "Refinement",
    "permutation": "Permutation",
}

JOB_TYPE_LABELS = {"single": "Simulation", "batch": "Batch", "tuning": "Tuning"}
JOB_STATUS_LABELS = {"running": "Running", "completed": "Completed", "failed": "Failed", "cancelled": "Cancelled"}


def method_key(strategy: str | None, simulated: bool | None = None) -> str | None:
    """Method key of a partitioning strategy (or a batch algorithm key) and its ``simulated`` flag."""
    if not strategy:
        return None
    if strategy in METHOD_LABELS:
        return strategy
    if strategy in ("metis_partitioning", "metis"):
        return "metis"
    hardware = simulated is False
    if strategy == "quantum_approximation_optimizer" or strategy.startswith("qaoa"):
        return "qaoa_hardware" if hardware else "qaoa_emulated"
    if strategy == "quantum_annealing" or strategy.startswith("qa"):
        return "qa_hardware" if hardware else "qa_emulated"
    return None


def method_label(strategy: str | None, simulated: bool | None = None, short: bool = False) -> str:
    key = method_key(strategy, simulated)
    if key is None:
        return strategy or "—"
    return (METHOD_SHORT_LABELS if short else METHOD_LABELS)[key]


# ---------------------------------------------------------------- parameters
from dataclasses import dataclass, field  # noqa: E402
from typing import Any, Callable  # noqa: E402

Params = dict[str, Any]


@dataclass(frozen=True)
class ParamSpec:
    """One editable parameter. ``path`` locates it inside the simulation parameters."""

    path: tuple[str, ...]
    label: str
    kind: str  # "int" | "float" | "choice" | "bool" | "text" | "toggle"
    minimum: float | None = None
    maximum: float | None = None
    decimals: int = 3
    step: float = 1.0
    unit: str = ""
    choices: tuple[tuple[Any, str], ...] = ()
    optional: str | None = None  # label of the "no value" (None) option, e.g. "Automatic"
    default: Any = None  # value used when switching an optional parameter on
    help: str = ""
    visible: Callable[[Params], bool] | None = field(default=None, compare=False)

    @property
    def key(self) -> str:
        return ".".join(self.path)


def get_path(params: Params, path: tuple[str, ...]) -> Any:
    node: Any = params
    for part in path:
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def set_path(params: Params, path: tuple[str, ...], value: Any) -> None:
    node = params
    for part in path[:-1]:
        node = node.setdefault(part, {})
    node[path[-1]] = value


def _strategy(params: Params) -> str:
    return get_path(params, ("partitioning_parameters", "partitioning_strategy")) or "metis_partitioning"


def _strategy_value(params: Params, strategy: str, key: str, default: Any = None) -> Any:
    value = get_path(params, ("partitioning_parameters", "strategies", strategy, key))
    return default if value is None else value


QA = ("partitioning_parameters", "strategies", "quantum_annealing")
QAOA = ("partitioning_parameters", "strategies", "quantum_approximation_optimizer")


def _qa_hardware(params: Params) -> bool:
    return _strategy_value(params, "quantum_annealing", "simulated", True) is False


def _qaoa_hardware(params: Params) -> bool:
    return _strategy_value(params, "quantum_approximation_optimizer", "simulated", True) is False


GENERAL_SPECS = (
    ParamSpec(("general_parameters", "dof_per_node"), "Rows per graph node", "int", 1, 64,
              help="Matrix rows grouped into one graph node (degrees of freedom per mesh node). Must divide n."),
    ParamSpec(("general_parameters", "seed"), "Random seed", "int", 0, 2**31 - 1, help="Makes matching and annealing reproducible."),
)

COARSENING_SPECS = (
    ParamSpec(("coarsening_parameters", "strategy"), "Matching strategy", "choice",
              choices=(("sorted", "Heavy-edge, sorted"), ("random", "Heavy-edge, random"), ("modified", "Modified heavy-edge"), ("light", "Light-edge")),
              help="How node pairs are chosen for contraction at each level."),
    ParamSpec(("coarsening_parameters", "coarsen_inferior_limit"), "Lower limit", "int", 1, 10**7, unit="nodes",
              help="A level is only kept if the coarse graph still has at least this many nodes."),
    ParamSpec(("coarsening_parameters", "coarsen_superior_limit"), "Upper limit", "int", 1, 10**7, unit="nodes", optional="No upper limit",
              default=200, help="The coarsest graph must have at most this many nodes; the run fails if it cannot get there."),
    ParamSpec(("coarsening_parameters", "coarsen_ratio"), "Reduction ratio", "float", 0.05, 1.0, decimals=2, step=0.05,
              help="Stop when a level keeps more than this fraction of the previous level's nodes."),
    ParamSpec(("coarsening_parameters", "max_levels"), "Maximum levels", "int", 1, 200),
    ParamSpec(("coarsening_parameters", "max_node_weight"), "Maximum node weight", "float", 0.001, 1e15, decimals=3, step=1.0,
              optional="Automatic", default=1000.0, help="Largest weight a supernode may reach. Automatic: 1.5 x total weight / k."),
)

PARTITIONING_SPECS = (
    ParamSpec(("partitioning_parameters", "partitioning_strategy"), "Method", "choice",
              choices=(("metis_partitioning", "METIS (classical)"), ("quantum_annealing", "Quantum annealing"),
                       ("quantum_approximation_optimizer", "QAOA"))),
    ParamSpec(("partitioning_parameters", "common", "k_target"), "Number of parts (k)", "int", 1, 4096),
    ParamSpec(("partitioning_parameters", "common", "balance_tolerance"), "Balance tolerance", "float", 0.0, 100.0, decimals=3, step=0.01,
              help="Allowed imbalance between part weights, in percent of the ideal part weight (2.0 = ±2%)."),
)

QA_SPECS = (
    ParamSpec(QA + ("simulated",), "Backend", "toggle", choices=((True, "Emulated"), (False, "D-Wave QPU"))),
    ParamSpec(QA + ("num_reads",), "Reads per bisection", "int", 1, 100000),
    ParamSpec(QA + ("num_starts",), "Restarts", "int", 1, 10000),
    ParamSpec(QA + ("qubo_balance_lambda",), "QUBO balance weight", "float", 0.0, 1e6, decimals=3, step=0.1),
    ParamSpec(QA + ("balance_violation_lambda",), "Balance violation weight", "float", 0.0, 1e6, decimals=3, step=0.1),
    ParamSpec(QA + ("qpu_solver_name",), "QPU solver", "text", optional="Default solver", default="Advantage2_system2.1", visible=_qa_hardware),
    ParamSpec(QA + ("qpu_region",), "QPU region", "text", optional="Default region", default="eu-central-1", visible=_qa_hardware),
)

QAOA_SPECS = (
    ParamSpec(QAOA + ("simulated",), "Backend", "toggle", choices=((True, "Emulated"), (False, "QLM QPU"))),
    ParamSpec(QAOA + ("circuit_depth",), "Circuit depth (p)", "int", 1, 64),
    ParamSpec(QAOA + ("num_steps",), "Optimizer steps", "int", 1, 10000),
    ParamSpec(QAOA + ("num_shots",), "Shots", "int", 1, 10**6),
    ParamSpec(QAOA + ("num_starts",), "Restarts", "int", 1, 10000),
    ParamSpec(QAOA + ("qubo_balance_lambda",), "QUBO balance weight", "float", 0.0, 1e6, decimals=3, step=0.1),
    ParamSpec(QAOA + ("balance_violation_lambda",), "Balance violation weight", "float", 0.0, 1e6, decimals=3, step=0.1),
    ParamSpec(QAOA + ("adam_learning_rate",), "Learning rate", "float", 0.0001, 10.0, decimals=4, step=0.01,
              visible=lambda p: not _qaoa_hardware(p)),
    ParamSpec(QAOA + ("qlm_qpu_name",), "QLM QPU", "text", optional=None, default="qat.qpus:QSolidQPU10", visible=_qaoa_hardware,
              help="Required on hardware, e.g. qat.qpus:QSolidQPU10."),
)

REFINEMENT_SPECS = (
    ParamSpec(("uncoarsening_parameters", "refine_objective"), "Objective", "choice",
              choices=(("cut_balance", "Edge cut and balance"), ("cut", "Edge cut only"))),
    ParamSpec(("uncoarsening_parameters", "refine_balance_lambda"), "Balance weight (λ)", "float", 0.0, 1e6, decimals=3, step=0.1),
    ParamSpec(("uncoarsening_parameters", "refine_max_passes_per_level"), "Passes per level", "int", 0, 10000),
    ParamSpec(("uncoarsening_parameters", "refine_max_moves_per_pass"), "Moves per pass", "int", 1, 10**8, optional="No limit", default=5000),
    ParamSpec(("uncoarsening_parameters", "validate_node_weights"), "Validate node weights after each level", "bool"),
)

STRATEGY_SPECS = {"metis_partitioning": (), "quantum_annealing": QA_SPECS, "quantum_approximation_optimizer": QAOA_SPECS}

ALL_SPECS = GENERAL_SPECS + COARSENING_SPECS + PARTITIONING_SPECS + QA_SPECS + QAOA_SPECS + REFINEMENT_SPECS


def spec_for_error(message: str) -> ParamSpec | None:
    """The parameter a validation message is about (messages name it as ``block.key``)."""
    # The parameter named first is the subject ("upper must be >= lower" is about upper).
    found = [(message.index(spec.key), -len(spec.key), i) for i, spec in enumerate(ALL_SPECS) if spec.key in message]
    best = ALL_SPECS[min(found)[2]] if found else None
    if best is None:
        for spec in ALL_SPECS:
            dotted = f"{spec.path[0]}.{spec.path[-1]}"
            if dotted in message:
                return spec
    return best


def flatten(params: Params, prefix: str = "") -> dict[str, Any]:
    """``{"block.key": value}`` for every leaf, for comparing two parameter sets."""
    out: dict[str, Any] = {}
    for key, value in params.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flatten(value, name))
        else:
            out[name] = value
    return out


def diff(left: Params, right: Params, *, active_strategies_only: bool = True) -> list[tuple[str, Any, Any]]:
    """Leaves that differ between two parameter sets: ``(key, left, right)``.

    By default the blocks of strategies neither side uses are ignored.
    """
    a, b = flatten(left), flatten(right)
    used = {_strategy(left), _strategy(right)}
    rows = []
    for key in sorted(set(a) | set(b)):
        if active_strategies_only and key.startswith("partitioning_parameters.strategies."):
            if key.split(".")[2] not in used:
                continue
        if a.get(key) != b.get(key):
            rows.append((key, a.get(key), b.get(key)))
    return rows


def choice_label(value: Any) -> str:
    """Display label of a choice value (a method, matching strategy, refinement objective...)."""
    for spec in ALL_SPECS:
        for choice, label in spec.choices:
            if choice == value and not isinstance(value, bool):
                return label
    return str(value)


def label_for_key(key: str) -> str:
    spec = next((s for s in ALL_SPECS if s.key == key), None)
    if spec is None:
        return key
    block = {"general_parameters": "Graph", "coarsening_parameters": "Coarsening", "uncoarsening_parameters": "Refinement"}.get(spec.path[0])
    if spec.path[:3] == QA:
        block = "Quantum annealing"
    elif spec.path[:3] == QAOA:
        block = "QAOA"
    elif spec.path[0] == "partitioning_parameters":
        block = "Partitioning"
    return f"{block} › {spec.label}"
