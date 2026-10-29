export type WikiCategoryKey =
  | 'theory'
  | 'stage1'
  | 'stage2'
  | 'stage3'
  | 'stage4'
  | 'stage5'
  | 'metrics'
  | 'workflows';

export interface WikiTopic {
  id: string;
  category: WikiCategoryKey;
  title: string;
  codeKey?: string;
  badge: string;
  shortSummary: string;
  formula?: string;
  scientificBackground: string[];
  implementationDetails: string[];
  tuningGuidelines?: string[];
  sourceFile?: string;
}

export const WIKI_CATEGORIES: Array<{
  key: WikiCategoryKey;
  label: string;
  shortLabel: string;
  description: string;
}> = [
  {
    key: 'theory',
    label: '1. Scientific Foundations & Thesis Theory',
    shortLabel: 'Scientific Theory',
    description:
      'Finite Element Method (FEM) linear systems, Domain Decomposition preconditioning, Multilevel graph reduction, and Quantum QUBO/Ising formulations.',
  },
  {
    key: 'stage1',
    label: '2. Stage 1 — FEM Matrices & Graph Mapping',
    shortLabel: 'Stage 1: FEM & Graph',
    description:
      'Stiffness (K) and Mass (M) Matrix Market inputs, nodal block compression (dof_per_node), vertex/edge weighting, and deterministic seeding.',
  },
  {
    key: 'stage2',
    label: '3. Stage 2 — Multilevel Coarsening (HEM)',
    shortLabel: 'Stage 2: Coarsening',
    description:
      'Graph contraction hierarchy, Heavy Edge Matching variants (Random, SHEM, MHEM, Light), and coarsening scale termination criteria.',
  },
  {
    key: 'stage3',
    label: '4. Stage 3 — Partitioning Backends & Quantum Solvers',
    shortLabel: 'Stage 3: Partitioning',
    description:
      'Classical PyMETIS k-way baseline, Quantum Annealing (dwave-neal & D-Wave Leap QPU), Gate-Based QAOA (PennyLane & QLM), and recursive bipartitioning.',
  },
  {
    key: 'stage4',
    label: '5. Stage 4 — Uncoarsening & KL Boundary Refinement',
    shortLabel: 'Stage 4: Refinement',
    description:
      'Coarse-to-fine partition projection and Kernighan-Lin-inspired greedy single-node boundary moves under cut and balance objectives.',
  },
  {
    key: 'stage5',
    label: '6. Stage 5 — Matrix Permutation & Output Artifacts',
    shortLabel: 'Stage 5: Permutation',
    description:
      'Subdomain-contiguous DOF reordering (P K P^T and P M P^T), randomized entry verification, and saved run artifacts.',
  },
  {
    key: 'metrics',
    label: '7. Structural & Graph Metrics Reference',
    shortLabel: 'Metrics & Diagnostics',
    description:
      'Mathematical definitions and solver interpretations of Maximum Bandwidth B(A), Factorization Proxy nB², Average Bandwidth B̄(A), and Diagonal Band Fractions.',
  },
  {
    key: 'workflows',
    label: '8. Step-by-Step User Workflows & Troubleshooting',
    shortLabel: 'User Workflows & FAQ',
    description:
      'Practical step-by-step instructions to customize methods, upload custom ANSYS .mtx matrices, run batch studies, and resolve validation errors.',
  },
];

export const WIKI_TOPICS: Record<string, WikiTopic> = {
  // ==========================================
  // 1. SCIENTIFIC FOUNDATIONS & THESIS THEORY
  // ==========================================
  'theory-fem-dd': {
    id: 'theory-fem-dd',
    category: 'theory',
    title: 'Finite Element Systems & Domain Decomposition Preconditioning',
    badge: 'Thesis Ch. 1–3',
    shortSummary:
      'Explains how reordering sparse FEM stiffness (K) and mass (M) matrices via graph partitioning reduces bandwidth and clusters nonzeros near the diagonal for faster linear solvers.',
    formula: "K u = f   and   (K - ω² M) φ = 0   →   K' = P K Pᵀ,  M' = P M Pᵀ",
    scientificBackground: [
      'In computational mechanics and Finite Element Analysis (FEA)—such as structural simulations of turbine blades in ANSYS—discretizing partial differential equations over a 3D mesh yields large, sparse symmetric linear systems involving a global stiffness matrix K and mass matrix M.',
      'When solving static systems (K u = f) or modal/harmonic eigenvalue problems ((K - ω² M) φ = 0), both direct sparse factorizations (Cholesky / LU) and preconditioned Krylov subspace solvers (Conjugate Gradient, GMRES with ILU or Schwarz domain-decomposition preconditioners) depend heavily on the ordering of Degrees of Freedom (DOFs).',
      'By partitioning the underlying finite-element mesh graph into k balanced subdomains with minimal inter-subdomain coupling (edge cut) and permuting DOFs contiguously by subdomain, the reordered matrices K’ = P K Pᵀ and M’ = P M Pᵀ concentrate nonzero entries into dense diagonal subdomain blocks with sparse off-diagonal interface coupling.',
    ],
    implementationDetails: [
      'The pipeline ingests K and M in Matrix Market (.mtx) format, extracts the nodal connectivity graph G_0 from K, computes a k-way partition via a multilevel hybrid scheme, and expands the nodal partition into a global DOF permutation vector p.',
      'Both K and M are permuted identically using p so that dynamic/modal ratios and eigenvalue spectra remain strictly invariant under similarity transformation.',
    ],
    sourceFile: 'src/orchestrator.py',
  },

  'theory-multilevel': {
    id: 'theory-multilevel',
    category: 'theory',
    title: 'Why Hybrid Multilevel Quantum-Classical Partitioning?',
    badge: 'Thesis Ch. 4 & 7',
    shortSummary:
      'Bridges the gap between industrial FEM meshes (10⁴–10⁶ DOFs) and current NISQ quantum hardware by combining classical multilevel graph coarsening with quantum coarse partitioning.',
    formula: 'G₀ (Fine FEM Graph) → G₁ → ... → G_c (Quantum-Sized Coarse Graph) → Uncoarsen & Refine → G₀',
    scientificBackground: [
      'Balanced minimum-cut graph partitioning is NP-hard. While it maps naturally to Quadratic Unconstrained Binary Optimization (QUBO) and Ising spin glass Hamiltonians suitable for Quantum Annealing (QA) and the Quantum Approximate Optimization Algorithm (QAOA), each vertex in a bipartition subproblem requires one logical binary variable (qubit).',
      'Current Noisy Intermediate-Scale Quantum (NISQ) processors and superconducting annealers cannot directly embed industrial FEM graphs containing tens or hundreds of thousands of nodes—especially because the quadratic balance penalty introduces all-to-all coupling among variables.',
      'The multilevel paradigm overcomes this hardware bottleneck in three phases: (1) Classical Heavy Edge Matching (HEM) iteratively contracts strongly coupled vertex pairs until the coarse graph G_c fits the target quantum processor capacity; (2) A quantum or classical solver partitions G_c into k balanced subdomains; (3) Classical uncoarsening projects the partition back level-by-level to G_0 while applying greedy Kernighan-Lin (KL) boundary refinement to recover fine-scale interface quality.',
    ],
    implementationDetails: [
      'Three canonical coarsening scales are benchmarked in the thesis: Small (4–5 coarse vertices for gate-based QAOA), Medium (100–175 coarse vertices for D-Wave Advantage clique embeddings), and Big (1500–2500 coarse vertices for classical METIS and simulated annealing).',
    ],
    sourceFile: 'src/orchestrator.py',
  },

  'theory-qubo-ising': {
    id: 'theory-qubo-ising',
    category: 'theory',
    title: 'QUBO & Ising Hamiltonian Formulation of Balanced Graph Bipartition',
    badge: 'Thesis Ch. 5–6',
    shortSummary:
      'Mathematical encoding of minimum-cut balanced bipartitioning as a Quadratic Unconstrained Binary Optimization (QUBO) objective and equivalent Ising spin Hamiltonian.',
    formula: 'H_QUBO(x) = Σ_{(u,v)∈E} w_uv (x_u + x_v - 2 x_u x_v) + λ_balance (Σ_u c_u x_u - W_target)²',
    scientificBackground: [
      'For a weighted graph G = (V, E) with vertex weights c_u and edge weights w_uv, binary decision variables x_u ∈ {0, 1} assign each vertex to part 0 or part 1.',
      'An edge (u, v) is cut if and only if x_u ≠ x_v, which is algebraically represented by the quadratic indicator (x_u + x_v - 2 x_u x_v). Summing over all edges gives the exact weighted edge cut.',
      'To prevent trivial partitions where all vertices fall into a single part, a quadratic penalty term λ_balance (Σ_u c_u x_u - W_target)² penalizes deviations from the target half-weight W_target = ½ Σ_u c_u. Expanding this square produces linear diagonal biases and all-to-all quadratic interactions 2 λ_balance c_u c_v x_u x_v.',
      'For gate-based QAOA, substituting x_u = (1 - z_u)/2 with spin variables z_u ∈ {-1, +1} (Pauli-Z operators Z_u) maps the QUBO into an Ising cost Hamiltonian H_P = const + Σ_u h_u Z_u + Σ_{u<v} J_uv Z_u Z_v.',
    ],
    implementationDetails: [
      'Because a single QUBO binary vector naturally encodes a 2-way split, k-way partitioning for k_target > 2 is achieved via recursive bipartitioning: the largest remaining subdomain is split proportionally until k_target subdomains are formed (requiring k_target - 1 bipartitions per multi-start run).',
    ],
    sourceFile: 'src/libs/multilevel_scheme/partitioning/quantum_annealing.py',
  },

  // ==========================================
  // 2. STAGE 1 — FEM MATRICES & GRAPH MAPPING
  // ==========================================
  'stage-1': {
    id: 'stage-1',
    category: 'stage1',
    title: 'Stage 1: Input FEM Matrices (K & M) & Graph Construction',
    badge: 'Pipeline Stage 01',
    shortSummary:
      'Loads sparse stiffness (K) and mass (M) matrices from Matrix Market (.mtx) files and compresses nodal DOF blocks into the initial node-weighted graph G_0.',
    formula: 'K (N × N)  →  G₀ = (V₀, E₀)  with  |V₀| = N / dof_per_node',
    scientificBackground: [
      'In structural Finite Element models, each physical mesh node possesses d = dof_per_node degrees of freedom (for example, d = 3 translational displacements u_x, u_y, u_z in 3D solid elements).',
      'Partitioning individual DOFs independently would split displacements belonging to the same physical mesh node across different subdomains. Stage 1 therefore groups contiguous d × d blocks along the matrix diagonal into single graph vertices.',
      'Each vertex u ∈ V_0 receives a vertex weight c(u) equal to the sum of the diagonal stiffness entries of its d DOFs, while each undirected edge (u, v) ∈ E_0 receives a weight w(u, v) equal to the symmetrized sum of absolute off-diagonal stiffness couplings between the DOF blocks of node u and node v.',
    ],
    implementationDetails: [
      'Implemented in matrix_to_graph(matrix, dof_per_node) inside src/libs/runtime/utils.py.',
      'Validates that K and M are square, share identical dimensions (N × N), and satisfy N mod dof_per_node == 0.',
    ],
    sourceFile: 'src/libs/runtime/utils.py',
  },

  'param-preset-file': {
    id: 'param-preset-file',
    category: 'stage1',
    title: 'Active Parameters Preset File',
    codeKey: 'simulation_config.parameters_file_path',
    badge: 'string (.json) • Config',
    shortSummary:
      'Selects which JSON parameter file inside matrices/<id>/data/ is loaded for the simulation.',
    scientificBackground: [
      'Decouples the matrix workspace configuration (simulation_config.json) from the algorithmic hyperparameters (simulation_parameters.json), allowing multiple named parameter presets to coexist in the same matrix folder.',
    ],
    implementationDetails: [
      'Stored in data/simulation_config.json under the key "parameters_file_path". You can create new presets via "Save as Preset" and switch between them at any time.',
    ],
    sourceFile: 'src/libs/runtime/utils.py',
  },

  'param-matrix-k': {
    id: 'param-matrix-k',
    category: 'stage1',
    title: 'Global Stiffness Matrix File (K)',
    codeKey: 'input_matrices.matrix_k_file_path',
    badge: 'string (.mtx) • Required',
    shortSummary:
      'Matrix Market (.mtx) file containing the sparse Finite Element stiffness matrix K used to build the nodal coupling graph G_0 and benchmarked after permutation.',
    formula: 'c(u) = Σ_{α∈B(u)} K_{αα},   w(u,v) = ½ Σ_{α∈B(u)} Σ_{β∈B(v)} (|K_{αβ}| + |K_{βα}|)',
    scientificBackground: [
      'The stiffness matrix K encodes elastic mechanical coupling between nodal degrees of freedom. Off-diagonal entries K_ij ≠ 0 indicate that DOF i and DOF j share an element stiffness contribution.',
      'Because K defines the sparsity pattern of static and implicit structural solvers, the weighted graph G_0 is constructed directly from K.',
    ],
    implementationDetails: [
      'Resolved relative to matrices/<id>/data/matrices/. Loaded as a SciPy CSR sparse matrix via scipy.io.mmread.',
    ],
    sourceFile: 'src/libs/runtime/utils.py',
  },

  'param-matrix-m': {
    id: 'param-matrix-m',
    category: 'stage1',
    title: 'Global Mass Matrix File (M)',
    codeKey: 'input_matrices.matrix_m_file_path',
    badge: 'string (.mtx) • Required',
    shortSummary:
      'Matrix Market (.mtx) file containing the sparse Finite Element mass matrix M. Reordered using the exact same DOF permutation vector P derived from K.',
    formula: "M' = P M Pᵀ   (must match shape of K: N × N)",
    scientificBackground: [
      'In dynamic, modal, and harmonic structural analyses, the mass matrix M represents inertial coupling and must be permuted congruently with K so that generalized eigenvalue problems (K - ω² M) φ = 0 remain consistent.',
    ],
    implementationDetails: [
      'Verified at runtime to have the exact same dimensions (N × N) as K. Permuted and profiled alongside K in Stage 5.',
    ],
    sourceFile: 'src/libs/runtime/runtime.py',
  },

  'stage-1-mtx-tools': {
    id: 'stage-1-mtx-tools',
    category: 'stage1',
    title: 'Matrix Market (.mtx) Upload & 3D FEM Mesh Generator',
    badge: 'Studio Provisioning Tool',
    shortSummary:
      'Upload custom Matrix Market (.mtx) files or generate a realistic 3D structured hexahedral FEM mesh (K and M) with one click.',
    scientificBackground: [
      'Because raw industrial Matrix Market files can be tens or hundreds of megabytes, matrices/*/data/matrices/*.mtx are excluded from Git tracking via .gitignore.',
      'To allow immediate experimentation on fresh clones or custom geometries, the Studio provides both a direct .mtx file uploader and a synthetic 3D FEM hexahedral elastic mesh generator.',
    ],
    implementationDetails: [
      'Implemented in backend/services/matrix_service.py. Builds a 3D structured nodal grid with 26-neighbor 3D brick stencil couplings and 3 DOFs per node, writing valid symmetric positive-definite K and M .mtx files.',
    ],
    sourceFile: 'backend/services/matrix_service.py',
  },

  'param-dof-per-node': {
    id: 'param-dof-per-node',
    category: 'stage1',
    title: 'Degrees of Freedom per Mesh Node',
    codeKey: 'general_parameters.dof_per_node',
    badge: 'integer > 0 • Default: 3',
    shortSummary:
      'Number of matrix rows/columns belonging to each physical mesh vertex. Compresses d × d matrix blocks into a single graph node during graph construction.',
    formula: '|V₀| = N / dof_per_node   (requires N mod dof_per_node == 0)',
    scientificBackground: [
      'In 3D solid mechanics (e.g., ANSYS SOLID185/SOLID186 elements), each node has 3 translational DOFs (u_x, u_y, u_z), so dof_per_node = 3. In 3D shell/beam elements with rotational DOFs, dof_per_node = 6; in scalar thermal/acoustic problems, dof_per_node = 1.',
      'Grouping all DOFs of a physical node into one graph vertex reduces graph size by a factor of d and guarantees that all DOFs of a mesh node remain in the same subdomain after permutation.',
    ],
    implementationDetails: [
      'Validated in src/libs/runtime/validation.py and checked against matrix dimension N before coarsening begins.',
    ],
    tuningGuidelines: [
      'Set to 3 for standard 3D solid structural matrices.',
      'If you receive "Global size N not divisible by DOF_PER_NODE", check whether your matrix dimension N is a multiple of 3 or set dof_per_node = 1 for pre-condensed scalar graphs.',
    ],
    sourceFile: 'src/libs/runtime/utils.py',
  },

  'param-seed': {
    id: 'param-seed',
    category: 'stage1',
    title: 'Master Random Seed',
    codeKey: 'general_parameters.seed',
    badge: 'integer • Default: 42',
    shortSummary:
      'Controls deterministic pseudo-random number generation across HEM vertex matching, multi-start quantum/classical partitioning, and randomized permutation checks.',
    scientificBackground: [
      'Multilevel graph partitioning involves several stochastic steps: random vertex visitation order during coarsening, random initial parameter/state initialization in multi-start QA and QAOA, and random coordinate sampling during permutation verification.',
      'Fixing the master seed guarantees reproducible coarse hierarchies and deterministic classical tie-breaking.',
    ],
    implementationDetails: [
      'Passed via numpy.random.default_rng(seed) into coarsen_graph, partitioner backends, and verify_permutation_random_entries.',
    ],
    tuningGuidelines: [
      'Keep fixed (e.g., 42) when comparing two partitioning algorithms on the exact same coarsened graph G_c.',
      'Vary across multiple runs to evaluate statistical variance.',
    ],
    sourceFile: 'src/orchestrator.py',
  },

  // ==========================================
  // 3. STAGE 2 — MULTILEVEL COARSENING (HEM)
  // ==========================================
  'stage-2': {
    id: 'stage-2',
    category: 'stage2',
    title: 'Stage 2: Multilevel Graph Coarsening (Heavy Edge Matching)',
    badge: 'Pipeline Stage 02',
    shortSummary:
      'Constructs a sequence of progressively smaller weighted graphs G_0 → G_1 → ... → G_c by contracting matched vertex pairs into supernodes.',
    formula: 'c(U_k) = c(u) + c(v),   w(U_k, U_l) = Σ_{x∈U_k} Σ_{y∈U_l} w(x, y)',
    scientificBackground: [
      'Given graph G_l = (V_l, E_l), a matching M_l ⊆ E_l is a set of edges in which no two edges share a vertex. Contracting each matched pair (u, v) ∈ M_l merges them into a single coarse supernode U_k in G_{l+1} with combined vertex weight c(u) + c(v).',
      'Unmatched vertices are copied directly as singleton supernodes. Parallel edges induced between coarse supernodes are collapsed into a single coarse edge whose weight is the sum of its constituent fine edge weights.',
      'Because edges internal to a matched pair (u, v) disappear inside the supernode U_k, they cannot be cut in the coarse graph. Selecting a matching with large edge weights (Heavy Edge Matching) therefore biases subsequent coarse partitions toward low fine-graph edge cuts.',
    ],
    implementationDetails: [
      'Implemented in src/libs/multilevel_scheme/coarsening/coarsening.py.',
      'Maintains a hierarchy list of LevelRecord objects storing the fine-to-coarse node mapping map_to_coarse so Stage 4 can project labels back to G_0.',
    ],
    sourceFile: 'src/libs/multilevel_scheme/coarsening/coarsening.py',
  },

  'method-hem-random': {
    id: 'method-hem-random',
    category: 'stage2',
    title: 'Random Heavy Edge Matching (random)',
    codeKey: 'coarsening_parameters.strategy = "random"',
    badge: 'HEM Variant • Foundational',
    shortSummary:
      'Visits vertices in random order and matches each unmatched vertex u with the eligible unmatched neighbor v having the largest raw edge weight w(u, v).',
    formula: 'Order: Random permutation of V_l   |   score(u, v) = w(u, v)',
    scientificBackground: [
      'Standard Karypis-Kumar Heavy Edge Matching (HEM). By visiting vertices in a uniformly random order and greedily selecting the heaviest incident edge that does not violate max_node_weight, it rapidly reduces graph size by roughly 40–50% per level while hiding heavy edges inside supernodes.',
    ],
    implementationDetails: [
      'Uses rng.permutation(V_l) for visitation order and evaluates score_fn = lambda u, v, w: w.',
    ],
    sourceFile: 'src/libs/multilevel_scheme/coarsening/coarsening.py',
  },

  'method-hem-sorted': {
    id: 'method-hem-sorted',
    category: 'stage2',
    title: 'Sorted Heavy Edge Matching (sorted / SHEM)',
    codeKey: 'coarsening_parameters.strategy = "sorted"',
    badge: 'HEM Variant • Degree-Ordered',
    shortSummary:
      'Sorts vertices in descending order of weighted degree before applying Heavy Edge Matching, preventing high-degree hub nodes from being left unmatched.',
    formula: 'Order: Descending Σ_v w(u, v)   |   score(u, v) = w(u, v)',
    scientificBackground: [
      'In irregular meshes, random visitation can match all neighbors of a high-degree vertex before visiting the hub itself, leaving it as an isolated singleton supernode.',
      'Sorted HEM (SHEM) prioritizes vertices with the largest total incident edge weight Σ_v w(u, v), ensuring strongly coupled hubs are matched first.',
    ],
    implementationDetails: [
      'Computes weighted degree G.degree(weight="weight") and sorts vertices descending with random tie-breaking.',
    ],
    sourceFile: 'src/libs/multilevel_scheme/coarsening/coarsening.py',
  },

  'method-hem-modified': {
    id: 'method-hem-modified',
    category: 'stage2',
    title: 'Modified Heavy Edge Matching (modified / MHEM)',
    codeKey: 'coarsening_parameters.strategy = "modified"',
    badge: 'HEM Variant • Thesis Default',
    shortSummary:
      'Normalizes edge weight by the geometric mean of endpoint vertex weights √(c(u)·c(v)), preventing the creation of disproportionately heavy supernodes.',
    formula: 'score(u, v) = w(u, v) / √(c(u) · c(v))',
    scientificBackground: [
      'Across multiple coarsening levels (especially when coarsening down to 100 or 4 nodes for quantum hardware), pure edge-weight matching can repeatedly merge already-large supernodes, creating highly skewed vertex weights on G_c that make balanced partitioning difficult.',
      'Modified HEM (MHEM) divides the coupling weight w(u, v) by √(c(u)·c(v)), favoring strong couplings between moderate-weight vertices and preserving uniform supernode weights across deep hierarchies.',
    ],
    implementationDetails: [
      'Uses random visitation order with score_fn(u, v, w) = w / sqrt(c(u) * c(v)). Selected as the primary coarsening strategy in the thesis benchmarks.',
    ],
    sourceFile: 'src/libs/multilevel_scheme/coarsening/coarsening.py',
  },

  'method-hem-light': {
    id: 'method-hem-light',
    category: 'stage2',
    title: 'Light-Edge Matching (light)',
    codeKey: 'coarsening_parameters.strategy = "light"',
    badge: 'HEM Variant • Ablation Baseline',
    shortSummary:
      'Inverts the edge scoring rule to preferentially contract the lightest incident edges first, serving as a comparative ablation baseline.',
    formula: 'score(u, v) = -w(u, v)',
    scientificBackground: [
      'Contracts weakly coupled neighbor pairs first, leaving heavy edges exposed in the coarse graph. Useful for ablation experiments demonstrating the impact of edge-weight prioritization.',
    ],
    implementationDetails: [
      'Evaluates score_fn(u, v, w) = -w during greedy neighbor selection.',
    ],
    sourceFile: 'src/libs/multilevel_scheme/coarsening/coarsening.py',
  },

  'param-coarsen-inferior': {
    id: 'param-coarsen-inferior',
    category: 'stage2',
    title: 'Coarsening Inferior Node Limit',
    codeKey: 'coarsening_parameters.coarsen_inferior_limit',
    badge: 'integer >= 1 • Default: 100',
    shortSummary:
      'Minimum allowed vertex count for the coarsened graph G_c. Coarsening halts before accepting any contraction level that would drop below this bound.',
    formula: '|V_c| ≥ coarsen_inferior_limit',
    scientificBackground: [
      'Prevents over-coarsening the graph into fewer vertices than k_target or below the desired quantum problem size.',
      'If a contraction step would jump directly from above coarsen_superior_limit to below coarsen_inferior_limit, the pipeline discards that step and raises an explicit range error so you can widen the window.',
    ],
    implementationDetails: [
      'Checked at every level in coarsen_graph(). Canonical thesis presets: Small = 4, Medium = 100, Big = 1500.',
    ],
    tuningGuidelines: [
      'Must always be ≥ k_target (and ≤ coarsen_superior_limit).',
    ],
    sourceFile: 'src/libs/multilevel_scheme/coarsening/coarsening.py',
  },

  'param-coarsen-superior': {
    id: 'param-coarsen-superior',
    category: 'stage2',
    title: 'Coarsening Superior Node Limit',
    codeKey: 'coarsening_parameters.coarsen_superior_limit',
    badge: 'integer | null • Default: 175',
    shortSummary:
      'Maximum accepted vertex count for the final coarse graph G_c. As soon as |V_l| falls inside [inferior_limit, superior_limit], coarsening succeeds and stops.',
    formula: 'coarsen_inferior_limit ≤ |V_c| ≤ coarsen_superior_limit',
    scientificBackground: [
      'Defines the upper hardware capacity bound for the coarse partitioner. For D-Wave Advantage clique embeddings of dense balanced-cut QUBOs, 175 nodes stays safely within the ~177–180 logical clique limit of Pegasus/Zephyr topologies.',
    ],
    implementationDetails: [
      'Can be set to null for no upper bound, or an integer ≥ coarsen_inferior_limit. Canonical thesis presets: Small = 5, Medium = 175, Big = 2500.',
    ],
    tuningGuidelines: [
      'Since each HEM level roughly halves the number of vertices, choose a [inferior, superior] interval wide enough (e.g., [100, 175] or [4, 6]) that a halving trajectory lands inside it.',
    ],
    sourceFile: 'src/libs/multilevel_scheme/coarsening/coarsening.py',
  },

  'param-max-levels': {
    id: 'param-max-levels',
    category: 'stage2',
    title: 'Maximum Coarsening Levels',
    codeKey: 'coarsening_parameters.max_levels',
    badge: 'integer >= 1 • Default: 15',
    shortSummary:
      'Maximum number of contraction steps allowed from G_0 to G_c.',
    formula: 'L ≤ max_levels   (|V_L| ≈ |V₀| · (0.5)^L)',
    scientificBackground: [
      'Caps the depth of the multilevel hierarchy. Because each matching step contracts at most half of the vertices (|V_{l+1}| ≥ |V_l| / 2), reaching 4 coarse nodes from a 100,000-node graph requires at least log₂(100000/4) ≈ 15–20 levels.',
    ],
    implementationDetails: [
      'Loop bound in coarsen_graph(). If max_levels is reached before |V_c| ≤ coarsen_superior_limit, a RuntimeError is raised.',
    ],
    tuningGuidelines: [
      'Use 15–20 for Medium/Big scales, and 25–30 when coarsening large meshes down to the Small (4–5 node) scale.',
    ],
    sourceFile: 'src/libs/multilevel_scheme/coarsening/coarsening.py',
  },

  'param-coarsen-ratio': {
    id: 'param-coarsen-ratio',
    category: 'stage2',
    title: 'Coarsening Reduction Ratio Threshold',
    codeKey: 'coarsening_parameters.coarsen_ratio',
    badge: 'float in (0, 1] • Default: 0.85',
    shortSummary:
      'Stagnation threshold (n_coarse / n_prev). Coarsening stops if a level fails to shrink the vertex count below this fraction.',
    formula: 'Stop if   |V_{l+1}| / |V_l| > coarsen_ratio',
    scientificBackground: [
      'Detects matching stagnation when almost no vertex pairs can be merged (for example, on star graphs or when max_node_weight blocks most pairings).',
    ],
    implementationDetails: [
      'Evaluated after each contraction step in coarsen_graph().',
    ],
    tuningGuidelines: [
      'Standard value is 0.85–0.90. Increase to 0.99 when coarsening down to very small vertex counts (4–5 nodes) where late levels may only contract one or two pairs at a time.',
    ],
    sourceFile: 'src/libs/multilevel_scheme/coarsening/coarsening.py',
  },

  'param-max-node-weight': {
    id: 'param-max-node-weight',
    category: 'stage2',
    title: 'Maximum Supernode Weight Cap',
    codeKey: 'coarsening_parameters.max_node_weight',
    badge: 'float > 0 | null • Default: Auto',
    shortSummary:
      'Upper bound on the combined weight c(u) + c(v) of any matched supernode. Prevents creating a single supernode heavier than an entire target subdomain.',
    formula: 'c(u) + c(v) ≤ max_node_weight   (Auto default: 1.5 × W_total / k_target)',
    scientificBackground: [
      'If a single coarse supernode accumulates a weight larger than (1 + ε) W_total / k_target, no partition of the coarse graph can ever satisfy the subdomain balance constraint.',
      'By default (null), the pipeline automatically applies the classical METIS heuristic 1.5 × W_total / k_target.',
    ],
    implementationDetails: [
      'Checked for every candidate neighbor v during matching: if c(u) + c(v) > max_node_weight, edge (u, v) is skipped.',
    ],
    tuningGuidelines: [
      'Leave blank (null) for standard runs where |V_c| > 2 · k_target.',
      'When coarsening down to 4–5 nodes with k_target = 4 or 8 (where coarse nodes must hold ≥ W_total / 4 weight), set a large value (e.g. 1e18) or batch_runner will adjust it automatically.',
    ],
    sourceFile: 'src/libs/multilevel_scheme/coarsening/coarsening.py',
  },

  // ==========================================
  // 4. STAGE 3 — PARTITIONING BACKENDS & QUANTUM SOLVERS
  // ==========================================
  'stage-3': {
    id: 'stage-3',
    category: 'stage3',
    title: 'Stage 3: Coarse Graph Partitioning Backends',
    badge: 'Pipeline Stage 03',
    shortSummary:
      'Partitions the coarsened graph G_c into k_target balanced subdomains using classical METIS, Quantum Annealing (Emulated or D-Wave QPU), or QAOA (Emulated or QLM QPU).',
    formula: 'V_c = P₀ ∪ P₁ ∪ ... ∪ P_{k-1}   minimizing Cut(P) subject to Balance(P) ≤ ε',
    scientificBackground: [
      'At the bottom of the multilevel V-cycle, the coarse graph G_c is small enough that global combinatorial optimization methods—including quantum annealers and variational quantum circuits—can search for low-cut balanced partitions without getting trapped in purely local minima.',
      'The Studio exposes 5 execution modes across 3 algorithmic families so you can benchmark classical heuristics, noiseless/emulated quantum heuristics, and physical quantum processors on identical coarse graphs.',
    ],
    implementationDetails: [
      'Dispatched by partition_coarse_graph() in src/orchestrator.py based on partitioning_parameters.partitioning_strategy and the strategy’s simulated flag.',
    ],
    sourceFile: 'src/orchestrator.py',
  },

  'param-k-target': {
    id: 'param-k-target',
    category: 'stage3',
    title: 'Target Number of Subdomains (k_target)',
    codeKey: 'partitioning_parameters.common.k_target',
    badge: 'integer >= 1 • Default: 4 or 8',
    shortSummary:
      'Number of subdomains k into which the mesh graph and matrices are decomposed.',
    formula: 'k = k_target   (Recursive quantum solvers perform k - 1 bipartitions per start)',
    scientificBackground: [
      'Determines the number of diagonal subdomain blocks in the permuted matrices K’ and M’. In parallel domain decomposition solvers, k typically corresponds to the number of MPI subdomains / processor cores.',
    ],
    implementationDetails: [
      'Passed directly as nparts to PyMETIS, or used as the target leaf count in the recursive bipartitioning queue for Quantum Annealing and QAOA.',
    ],
    tuningGuidelines: [
      'Powers of two (2, 4, 8, 16) produce symmetric recursive bipartition trees, though any integer k ≥ 2 is supported (via proportional target split ratio k_left / k_curr).',
    ],
    sourceFile: 'src/libs/runtime/validation.py',
  },

  'param-balance-tolerance': {
    id: 'param-balance-tolerance',
    category: 'stage3',
    title: 'Subdomain Weight Balance Tolerance',
    codeKey: 'partitioning_parameters.common.balance_tolerance',
    badge: 'float >= 0 • Default: 2.0 (2%)',
    shortSummary:
      'Maximum allowed relative weight deviation of any subdomain from the ideal average weight W_total / k_target.',
    formula: '(1 - ε) · (W_total / k) ≤ W(P_i) ≤ (1 + ε) · (W_total / k)',
    scientificBackground: [
      'Ensures computational load balance across subdomains. A tolerance of 2.0 (interpreted as ε = 0.02 or 2%) requires every subdomain weight to lie within ±2% of the ideal mean weight.',
    ],
    implementationDetails: [
      'Normalized via _normalize_balance_tolerance(): values > 1.0 are divided by 100 (e.g., 2.0 → 0.02), while values ≤ 1.0 are used directly as fractions (e.g., 0.02 → 2%). Used in METIS ufactor, QA/QAOA candidate scoring, and Stage 4 KL refinement bounds.',
    ],
    sourceFile: 'src/libs/multilevel_scheme/partitioning/metis_partitioning.py',
  },

  'method-metis': {
    id: 'method-metis',
    category: 'stage3',
    title: 'METIS Classical Baseline (PyMETIS k-Way)',
    codeKey: 'partitioning_strategy = "metis_partitioning"',
    badge: 'Classical Baseline',
    shortSummary:
      'Partitions the coarse graph G_c directly into k_target parts using the classical METIS multilevel k-way library (pymetis).',
    formula: 'pymetis.part_graph(nparts=k_target, xadj, adjncy, vweights, eweights)',
    scientificBackground: [
      'METIS is the industry-standard classical graph partitioner for finite-element meshes. Running PyMETIS on the coarse graph G_c provides a fast, deterministic classical baseline against which Quantum Annealing and QAOA are benchmarked.',
    ],
    implementationDetails: [
      'Implemented in src/libs/multilevel_scheme/partitioning/metis_partitioning.py.',
      'Scales floating-point vertex and edge weights to positive integers (weight_scale = 1000) and builds CSR adjacency arrays (xadj, adjncy).',
    ],
    sourceFile: 'src/libs/multilevel_scheme/partitioning/metis_partitioning.py',
  },

  'method-qa-emulated': {
    id: 'method-qa-emulated',
    category: 'stage3',
    title: 'Quantum Annealing — Emulated (dwave-neal)',
    codeKey: 'partitioning_strategy = "quantum_annealing", simulated = true',
    badge: 'Quantum Emulated • Local CPU',
    shortSummary:
      'Solves recursive balanced-cut QUBO bipartitions locally using D-Wave’s SimulatedAnnealingSampler (dwave-neal) without requiring cloud QPU credentials.',
    formula: 'Q_uu = Σ_v w_uv + λ_bal (c_u² - 2 W_target c_u),   Q_uv = 2 (λ_bal c_u c_v - w_uv)',
    scientificBackground: [
      'Simulated Annealing emulates thermal/quantum fluctuations over the exact same QUBO energy landscape built for D-Wave hardware, without minor-embedding chain breaks or QPU queue latency.',
      'This allows testing large coarse graphs (up to 2500 nodes) and tuning qubo_balance_lambda locally before submitting to physical superconducting hardware.',
    ],
    implementationDetails: [
      'Implemented in src/libs/multilevel_scheme/partitioning/quantum_annealing.py using neal.SimulatedAnnealingSampler().sample_qubo().',
    ],
    sourceFile: 'src/libs/multilevel_scheme/partitioning/quantum_annealing.py',
  },

  'method-qa-hardware': {
    id: 'method-qa-hardware',
    category: 'stage3',
    title: 'Quantum Annealing — D-Wave Leap QPU Hardware',
    codeKey: 'partitioning_strategy = "quantum_annealing", simulated = false',
    badge: 'Quantum Hardware • D-Wave QPU',
    shortSummary:
      'Minor-embeds and samples recursive balanced-cut QUBO bipartitions directly on remote D-Wave Advantage / Advantage2 superconducting quantum annealers.',
    formula: 'H(s) = -A(s)/2 Σ_i σ_i^x + B(s)/2 (Σ_i h_i σ_i^z + Σ_{i<j} J_ij σ_i^z σ_j^z)',
    scientificBackground: [
      'Physical quantum annealing evolves a system of superconducting flux qubits from an initial transverse-field superposition to the problem Ising Hamiltonian.',
      'Because the quadratic balance penalty couples every pair of vertices in the coarse graph, the QUBO graph is complete (all-to-all) whenever qubo_balance_lambda ≠ 0. Embedding this complete graph onto the sparse Pegasus/Zephyr QPU topology requires chaining multiple physical qubits per logical coarse node via EmbeddingComposite.',
    ],
    implementationDetails: [
      'Connects via DWaveSampler(region=qpu_region, solver=qpu_solver_name) wrapped in EmbeddingComposite.',
      'Requires DWAVE_API_TOKEN or a configured D-Wave Leap profile, and coarse graph size |V_c| ≤ max clique capacity (~100–175 nodes).',
    ],
    sourceFile: 'src/libs/multilevel_scheme/partitioning/quantum_annealing.py',
  },

  'method-qaoa-emulated': {
    id: 'method-qaoa-emulated',
    category: 'stage3',
    title: 'Gate-Based QAOA — Emulated (PennyLane + Adam)',
    codeKey: 'partitioning_strategy = "quantum_approximation_optimizer", simulated = true',
    badge: 'Quantum Emulated • PennyLane',
    shortSummary:
      'Simulates a p-layer variational QAOA quantum circuit locally in PennyLane using the Adam gradient optimizer to minimize the Ising balanced-cut expectation.',
    formula: '|ψ(γ, β)⟩ = Π_{l=1}^p [ exp(-i β_l Σ_i X_i) exp(-i γ_l H_P) ] |+⟩^{⊗n}',
    scientificBackground: [
      'The Quantum Approximate Optimization Algorithm (Farhi et al.) prepares an equal superposition |+⟩^{⊗n} and applies p alternating layers of the Ising cost unitary U_P(γ_l) = exp(-i γ_l H_P) (implemented via RZ and MultiRZ/CNOT-RZ-CNOT gates) and transverse-field mixer unitary U_M(β_l) = exp(-i β_l Σ_i RX_i).',
      'A classical optimizer (Adam in simulated mode) iteratively updates the 2p variational angles (γ, β) to minimize the expected energy ⟨ψ(γ, β)| H_P |ψ(γ, β)⟩, after which computational-basis measurement shots sample low-energy bitstrings.',
    ],
    implementationDetails: [
      'Implemented in src/libs/multilevel_scheme/partitioning/quantum_approximation_optimizer.py using qml.device("default.qubit") and qml.AdamOptimizer(stepsize=adam_learning_rate).',
      'Because full statevector simulation scales as O(2^n), keep coarse graph size |V_c| ≤ 18–20 nodes (typically the Small 4–5 node preset).',
    ],
    sourceFile: 'src/libs/multilevel_scheme/partitioning/quantum_approximation_optimizer.py',
  },

  'method-qaoa-hardware': {
    id: 'method-qaoa-hardware',
    category: 'stage3',
    title: 'Gate-Based QAOA — Remote QLM / myQLM Hardware',
    codeKey: 'partitioning_strategy = "quantum_approximation_optimizer", simulated = false',
    badge: 'Quantum Hardware • QLM / QPU',
    shortSummary:
      'Executes variational QAOA circuits on remote Atos/Eviden QLM / myQLM quantum processors (e.g. QSolidQPU10) using derivative-free COBYLA optimization.',
    formula: 'Minimize_{(γ, β)} ⟨H_P⟩_shots   via SciPy COBYLA + QLM Program/QRoutine',
    scientificBackground: [
      'On gate-based quantum hardware or remote QLM appliances, analytical backprop gradients are unavailable and circuit evaluations are subject to shot noise.',
      'The pipeline constructs explicit QRoutine circuits (H, RZ, CNOT-RZ-CNOT, RX gates), submits shot-based jobs to the target QLM QPU, reconstructs the Ising energy from bitstring counts, and optimizes (γ, β) using SciPy’s derivative-free COBYLA optimizer.',
    ],
    implementationDetails: [
      'Loads the QPU backend dynamically via module:Class specification in qlm_qpu_name (default "qat.qpus:QSolidQPU10").',
    ],
    sourceFile: 'src/libs/multilevel_scheme/partitioning/quantum_approximation_optimizer.py',
  },

  'param-qubo-balance-lambda': {
    id: 'param-qubo-balance-lambda',
    category: 'stage3',
    title: 'QUBO Quadratic Balance Penalty (qubo_balance_lambda)',
    codeKey: 'qubo_balance_lambda',
    badge: 'float • Default: 2.0',
    shortSummary:
      'Penalty coefficient λ_balance weighting the quadratic size-balance constraint (Σ c_u x_u - W_target)² inside the bipartition QUBO.',
    formula: 'f_QUBO(x) = Cut(x) + qubo_balance_lambda · (Σ_u c_u x_u - W_target)²',
    scientificBackground: [
      'Controls the trade-off inside the quantum Hamiltonian between minimizing edge cut and enforcing equal subdomain weights.',
      'Before building the QUBO, vertex weights c_u and edge weights w_uv are normalized by their respective maximum values on the subproblem so that qubo_balance_lambda is scale-invariant across different meshes and coarsening levels.',
    ],
    implementationDetails: [
      'Used in _build_balanced_bipartition_qubo() for both Quantum Annealing and QAOA.',
    ],
    tuningGuidelines: [
      'Values in [1.0, 5.0] (default 2.0) provide a strong balance restoring force without drowning out the edge-cut couplings.',
      'Setting qubo_balance_lambda = 0 removes all-to-all balance terms, making the QUBO sparse (matching G_c’s topology) at the risk of unbalanced splits.',
    ],
    sourceFile: 'src/libs/multilevel_scheme/partitioning/quantum_annealing.py',
  },

  'param-num-starts': {
    id: 'param-num-starts',
    category: 'stage3',
    title: 'Multi-Start Recursive Trees (num_starts)',
    codeKey: 'num_starts',
    badge: 'integer >= 1 • Default: 20 (QA) / 5 (QAOA)',
    shortSummary:
      'Number of independent recursive k-way partitioning trees executed; the pipeline retains the tree achieving the best overall k-way objective score.',
    formula: 'Total Bipartitions = num_starts × (k_target - 1)',
    scientificBackground: [
      'Because recursive bipartitioning is a greedy tree of (k_target - 1) splits and quantum sampling is stochastic, running multiple independent starts with different random seeds explores diverse partition trees and selects the globally best k-way partition.',
    ],
    implementationDetails: [
      'Outer loop in partition_graph_quantum_annealing() and partition_graph_qaoa().',
    ],
    tuningGuidelines: [
      'For emulated runs, 10–20 starts improve robustness. For remote D-Wave / QLM hardware runs, reduce to 1–5 starts to conserve QPU quota.',
    ],
    sourceFile: 'src/libs/multilevel_scheme/partitioning/quantum_annealing.py',
  },

  'param-num-reads': {
    id: 'param-num-reads',
    category: 'stage3',
    title: 'Annealing Samples per Bipartition (num_reads)',
    codeKey: 'strategies.quantum_annealing.num_reads',
    badge: 'integer >= 1 • Default: 20',
    shortSummary:
      'Number of annealing readouts (bitstring samples) drawn from the QPU or simulated annealer for each bipartition QUBO.',
    formula: 'Total QPU Reads = num_starts × (k_target - 1) × num_reads',
    scientificBackground: [
      'Each annealing cycle produces one candidate binary assignment x ∈ {0, 1}^n. Drawing num_reads samples per QUBO submission allows the post-processor to evaluate all returned bitstrings and pick the lowest-cost feasible split.',
    ],
    implementationDetails: [
      'Passed as num_reads to sampler.sample_qubo(Q, num_reads=num_reads).',
    ],
    sourceFile: 'src/libs/multilevel_scheme/partitioning/quantum_annealing.py',
  },

  'param-balance-violation-lambda': {
    id: 'param-balance-violation-lambda',
    category: 'stage3',
    title: 'Post-Sample Balance Violation Penalty (balance_violation_lambda)',
    codeKey: 'balance_violation_lambda',
    badge: 'float >= 0 • Default: 1,000,000',
    shortSummary:
      'Classical post-selection penalty applied when ranking candidate quantum bitstrings that exceed the allowed balance_tolerance.',
    formula: 'Score = E_QUBO(x) + balance_violation_lambda · max(0, Imbalance(x) - ε)²',
    scientificBackground: [
      'Even with qubo_balance_lambda in the Hamiltonian, noisy quantum hardware samples may occasionally violate the hard balance tolerance ε. This high penalty guarantees that any sample satisfying the balance tolerance is strictly preferred over an imbalanced sample during bitstring post-selection.',
    ],
    implementationDetails: [
      'Used when ranking samples in _solve_bipartition_qa() and _solve_bipartition_qaoa(), as well as when comparing full k-way partitions across multi-starts.',
    ],
    sourceFile: 'src/libs/multilevel_scheme/partitioning/quantum_annealing.py',
  },

  'param-qpu-solver-name': {
    id: 'param-qpu-solver-name',
    category: 'stage3',
    title: 'D-Wave QPU Solver Name (qpu_solver_name)',
    codeKey: 'strategies.quantum_annealing.qpu_solver_name',
    badge: 'string | null • D-Wave Hardware',
    shortSummary:
      'Target D-Wave Leap quantum processor identifier (e.g., Advantage2_system2.1 or Advantage_system4.1) used when simulated = false.',
    scientificBackground: [
      'Selects the specific physical superconducting quantum annealer in D-Wave Leap. Leave empty/null to let D-Wave Ocean automatically select the default available QPU in the chosen region.',
    ],
    implementationDetails: [
      'Passed as solver=qpu_solver_name to dwave.system.DWaveSampler.',
    ],
    sourceFile: 'src/libs/multilevel_scheme/partitioning/quantum_annealing.py',
  },

  'param-qpu-region': {
    id: 'param-qpu-region',
    category: 'stage3',
    title: 'D-Wave Leap Cloud Region (qpu_region)',
    codeKey: 'strategies.quantum_annealing.qpu_region',
    badge: 'string | null • Default: "eu-central-1"',
    shortSummary:
      'Geographic D-Wave Leap cloud endpoint region (e.g., eu-central-1 or na-west-1).',
    scientificBackground: [
      'Routes QPU API traffic to the specified regional Leap solver datacenter.',
    ],
    implementationDetails: [
      'Passed as region=qpu_region to DWaveSampler.',
    ],
    sourceFile: 'src/libs/multilevel_scheme/partitioning/quantum_annealing.py',
  },

  'param-qpu-problem-label': {
    id: 'param-qpu-problem-label',
    category: 'stage3',
    title: 'D-Wave Leap Problem Label (qpu_problem_label)',
    codeKey: 'strategies.quantum_annealing.qpu_problem_label',
    badge: 'string | null • D-Wave Dashboard Tag',
    shortSummary:
      'Human-readable label attached to QPU submissions in your D-Wave Leap cloud dashboard.',
    scientificBackground: [
      'Helps identify and filter QPU jobs belonging to a specific demonstrator or experiment in the D-Wave Leap web console.',
    ],
    implementationDetails: [
      'Passed as label=qpu_problem_label to sample_qubo().',
    ],
    sourceFile: 'src/libs/multilevel_scheme/partitioning/quantum_annealing.py',
  },

  'param-circuit-depth': {
    id: 'param-circuit-depth',
    category: 'stage3',
    title: 'QAOA Variational Circuit Depth p (circuit_depth)',
    codeKey: 'strategies.quantum_approximation_optimizer.circuit_depth',
    badge: 'integer >= 1 • Default: 1 to 5',
    shortSummary:
      'Number of alternating Cost (U_P) and Mixer (U_M) unitary layers p in the QAOA quantum circuit.',
    formula: '2p variational parameters: γ = (γ₁, ..., γ_p),  β = (β₁, ..., β_p)',
    scientificBackground: [
      'In the limit p → ∞, QAOA converges to the exact ground state of the cost Hamiltonian by trotterizing adiabatic evolution. At finite NISQ depths (p = 1..5), larger p increases circuit expressivity at the cost of deeper two-qubit CNOT/MultiRZ gate counts and a 2p-dimensional classical optimization landscape.',
    ],
    implementationDetails: [
      'Controls the shape (2, circuit_depth) of the variational parameter tensor in _solve_bipartition_qaoa().',
    ],
    sourceFile: 'src/libs/multilevel_scheme/partitioning/quantum_approximation_optimizer.py',
  },

  'param-num-steps': {
    id: 'param-num-steps',
    category: 'stage3',
    title: 'Classical Optimizer Iterations (num_steps)',
    codeKey: 'strategies.quantum_approximation_optimizer.num_steps',
    badge: 'integer >= 1 • Default: 5',
    shortSummary:
      'Number of classical optimization iterations (Adam steps or COBYLA evaluations) performed to train the QAOA circuit angles (γ, β) for each bipartition.',
    formula: 'Total Circuit Evaluations = num_starts × (k_target - 1) × (num_steps + 1)',
    scientificBackground: [
      'In each variational loop, the classical optimizer updates (γ, β) for num_steps iterations to minimize ⟨H_P⟩ before drawing the final measurement shot distribution.',
    ],
    implementationDetails: [
      'Controls the training loop iterations in PennyLane (Adam) and maxiter in SciPy minimize(method="COBYLA") for QLM.',
    ],
    sourceFile: 'src/libs/multilevel_scheme/partitioning/quantum_approximation_optimizer.py',
  },

  'param-num-shots': {
    id: 'param-num-shots',
    category: 'stage3',
    title: 'Circuit Measurement Shots (num_shots)',
    codeKey: 'strategies.quantum_approximation_optimizer.num_shots',
    badge: 'integer >= 1 • Default: 5 to 100',
    shortSummary:
      'Number of projective computational-basis measurements executed per QAOA circuit evaluation.',
    scientificBackground: [
      'Determines how many bitstring samples are drawn from the final variational state |ψ(γ*, β*)⟩ (and per energy evaluation on shot-based QLM hardware).',
    ],
    implementationDetails: [
      'Passed as shots=num_shots to the PennyLane sampling device and QLM circuit.to_job(nbshots=num_shots).',
    ],
    sourceFile: 'src/libs/multilevel_scheme/partitioning/quantum_approximation_optimizer.py',
  },

  'param-adam-learning-rate': {
    id: 'param-adam-learning-rate',
    category: 'stage3',
    title: 'PennyLane Adam Learning Rate (adam_learning_rate)',
    codeKey: 'strategies.quantum_approximation_optimizer.adam_learning_rate',
    badge: 'float > 0 • Default: 0.1',
    shortSummary:
      'Gradient step size η used by PennyLane’s AdamOptimizer when training QAOA variational angles in simulated mode.',
    scientificBackground: [
      'Controls how rapidly the variational angles (γ, β) move along the analytical gradient ∇_{(γ,β)} ⟨H_P⟩ during local simulation.',
    ],
    implementationDetails: [
      'Passed to qml.AdamOptimizer(stepsize=adam_learning_rate) when simulated = true.',
    ],
    sourceFile: 'src/libs/multilevel_scheme/partitioning/quantum_approximation_optimizer.py',
  },

  'param-qlm-qpu-name': {
    id: 'param-qlm-qpu-name',
    category: 'stage3',
    title: 'Remote QLM QPU Target Class (qlm_qpu_name)',
    codeKey: 'strategies.quantum_approximation_optimizer.qlm_qpu_name',
    badge: 'string • Default: "qat.qpus:QSolidQPU10"',
    shortSummary:
      'Python module:Class path specifying the Atos/Eviden QLM or myQLM quantum processor backend used when simulated = false.',
    scientificBackground: [
      'Allows targeting either remote hardware QPUs (such as QSolidQPU10) or local myQLM noisy/linlag simulators (such as qat.qpus:PyLinalg) without changing code.',
    ],
    implementationDetails: [
      'Resolved dynamically via importlib.import_module(module_name) and getattr(mod, class_name)() in _load_qlm_qpu().',
    ],
    sourceFile: 'src/libs/multilevel_scheme/partitioning/quantum_approximation_optimizer.py',
  },

  // ==========================================
  // 5. STAGE 4 — UNCOARSENING & KL REFINEMENT
  // ==========================================
  'stage-4': {
    id: 'stage-4',
    category: 'stage4',
    title: 'Stage 4: Uncoarsening & Greedy Boundary Refinement (KL-Style)',
    badge: 'Pipeline Stage 04',
    shortSummary:
      'Projects coarse subdomain labels back level-by-level from G_c to G_0, performing greedy boundary vertex moves at each level to reduce edge cut while preserving balance.',
    formula: 'part_{l-1}[u] = part_l[ map_to_coarse[u] ]   followed by greedy boundary refinement',
    scientificBackground: [
      'While a coarse partition on G_c captures the global macroscopic structure of the mesh, each supernode contraction restricted the partition boundary to follow coarse supernode borders.',
      'During uncoarsening (walking backwards from level L down to level 0), the pipeline projects each supernode’s subdomain label onto its constituent fine vertices and immediately runs a Kernighan-Lin / Fiduccia-Mattheyses (KL/FM) style greedy boundary refinement pass.',
      'At each pass, only boundary vertices (vertices with at least one neighbor in a different subdomain) are inspected. Moving a boundary vertex u from subdomain A to neighboring subdomain B changes the global edge cut by Δcut = Σ_{v∈B} w(u,v) - Σ_{v∈A} w(u,v). Beneficial moves that respect the subdomain weight bounds [(1-ε)W/k, (1+ε)W/k] are applied greedily.',
    ],
    implementationDetails: [
      'Implemented in uncoarsen_and_refine() and refine_kway_boundary_moves() inside src/libs/multilevel_scheme/uncoarsening/uncoarsening.py.',
    ],
    sourceFile: 'src/libs/multilevel_scheme/uncoarsening/uncoarsening.py',
  },

  'method-refine-cut': {
    id: 'method-refine-cut',
    category: 'stage4',
    title: 'Strict Cut Refinement Objective ("cut")',
    codeKey: 'uncoarsening_parameters.refine_objective = "cut"',
    badge: 'Refinement Mode',
    shortSummary:
      'Scores candidate boundary moves purely by edge-cut reduction (gain = w_to_dst - w_to_src) while enforcing hard subdomain weight bounds.',
    formula: 'Score(u: A → B) = Σ_{v∈B} w(u, v) - Σ_{v∈A} w(u, v) > 0',
    scientificBackground: [
      'Classic greedy KL boundary refinement: a boundary node u is moved to a neighboring subdomain B if and only if u is more strongly coupled to B than to its current subdomain A, and the move keeps both A and B within [(1-ε)W/k, (1+ε)W/k].',
    ],
    implementationDetails: [
      'Selected when refine_objective = "cut".',
    ],
    sourceFile: 'src/libs/multilevel_scheme/uncoarsening/uncoarsening.py',
  },

  'method-refine-cut-balance': {
    id: 'method-refine-cut-balance',
    category: 'stage4',
    title: 'Joint Cut + Balance Refinement Objective ("cut_balance")',
    codeKey: 'uncoarsening_parameters.refine_objective = "cut_balance"',
    badge: 'Refinement Mode • Thesis Default',
    shortSummary:
      'Scores boundary moves using a combined objective that rewards both edge-cut reduction and reductions in subdomain weight imbalance.',
    formula: 'Score(u: A → B) = Δcut_reduction - refine_balance_lambda · Δbalance_penalty > 0',
    scientificBackground: [
      'Quantum coarse partitions on very small graphs (or with high balance penalty) may occasionally start slightly outside the fine-graph balance window or benefit from trading a tiny edge-cut change for a large improvement in weight parity.',
      'The "cut_balance" objective augments the cut gain with a normalized quadratic balance penalty term, allowing refinement to actively repair weight imbalance across levels.',
    ],
    implementationDetails: [
      'Computes normalized quadratic deviation from target weight W/k before and after the candidate move, weighted by refine_balance_lambda.',
    ],
    sourceFile: 'src/libs/multilevel_scheme/uncoarsening/uncoarsening.py',
  },

  'param-refine-balance-lambda': {
    id: 'param-refine-balance-lambda',
    category: 'stage4',
    title: 'Refinement Balance Weight (refine_balance_lambda)',
    codeKey: 'uncoarsening_parameters.refine_balance_lambda',
    badge: 'float >= 0 • Default: 1.0',
    shortSummary:
      'Weighting factor λ_refine multiplying the normalized balance improvement term when refine_objective = "cut_balance".',
    formula: 'Score = (gain / avg_edge_w) - refine_balance_lambda · (Pen_after - Pen_before)',
    scientificBackground: [
      'Controls how strongly the uncoarsening refinement pass prioritizes equalizing subdomain weights relative to reducing edge cut.',
    ],
    implementationDetails: [
      'Used inside refine_kway_boundary_moves() when refine_objective == "cut_balance".',
    ],
    sourceFile: 'src/libs/multilevel_scheme/uncoarsening/uncoarsening.py',
  },

  'param-refine-max-passes': {
    id: 'param-refine-max-passes',
    category: 'stage4',
    title: 'Maximum Refinement Passes per Level (refine_max_passes_per_level)',
    codeKey: 'uncoarsening_parameters.refine_max_passes_per_level',
    badge: 'integer >= 0 • Default: 50',
    shortSummary:
      'Maximum number of greedy boundary sweeps performed at each uncoarsening level before projecting to the next finer level.',
    scientificBackground: [
      'During each pass, all boundary vertices are visited once. Sweeps repeat until an entire pass produces zero beneficial moves (local optimum reached) or refine_max_passes_per_level is hit.',
    ],
    implementationDetails: [
      'Setting to 0 disables boundary refinement completely (pure projection of the coarse partition).',
    ],
    sourceFile: 'src/libs/multilevel_scheme/uncoarsening/uncoarsening.py',
  },

  'param-refine-max-moves': {
    id: 'param-refine-max-moves',
    category: 'stage4',
    title: 'Maximum Node Moves per Pass (refine_max_moves_per_pass)',
    codeKey: 'uncoarsening_parameters.refine_max_moves_per_pass',
    badge: 'integer >= 1 | null • Default: null (Unlimited)',
    shortSummary:
      'Optional cap on the number of boundary vertices moved within a single refinement pass.',
    scientificBackground: [
      'When null (unlimited), every boundary vertex with a positive-score move is updated in a pass. Setting an integer cap limits per-pass movement on very large graphs.',
    ],
    implementationDetails: [
      'Checked inside the inner boundary loop of refine_kway_boundary_moves().',
    ],
    sourceFile: 'src/libs/multilevel_scheme/uncoarsening/uncoarsening.py',
  },

  // ==========================================
  // 6. STAGE 5 — MATRIX PERMUTATION & OUTPUTS
  // ==========================================
  'stage-5': {
    id: 'stage-5',
    category: 'stage5',
    title: 'Stage 5: Matrix Permutation, Verification & Output Artifacts',
    badge: 'Pipeline Stage 05',
    shortSummary:
      'Converts the final fine-graph partition on G_0 into a global DOF permutation vector p, symmetrically permutes K and M, verifies exact entry correspondence, and saves run outputs.',
    formula: "K'[i, j] = K[p[i], p[j]],   M'[i, j] = M[p[i], p[j]]",
    scientificBackground: [
      'Once every vertex u ∈ V_0 has a final subdomain label part[u] ∈ {0, ..., k-1}, vertices are ordered contiguously by subdomain label: all vertices of subdomain 0 first, then subdomain 1, up to subdomain k-1.',
      'Each node u is expanded back into its d = dof_per_node contiguous global DOF indices [u·d, u·d + 1, ..., u·d + d - 1], yielding a global permutation array p of length N.',
      'Applying p to both rows and columns of K and M produces the domain-block-reordered matrices K’ = P K Pᵀ and M’ = P M Pᵀ. Finally, 1,000 random coordinate pairs (i, j) are sampled to verify that K’[i, j] == K[p[i], p[j]] with zero mismatches.',
    ],
    implementationDetails: [
      'Implemented in permute_fem_matrices_from_graph_partition() inside src/libs/runtime/utils.py and profiled via compute_run_metrics() in src/libs/runtime/metrics.py.',
    ],
    sourceFile: 'src/libs/runtime/utils.py',
  },

  'output-coarsened-graph': {
    id: 'output-coarsened-graph',
    category: 'stage5',
    title: 'Coarsened Graph Matrix (coarsened_graph.mtx)',
    codeKey: 'save_output includes "coarsened_graph"',
    badge: 'Output Artifact (.mtx)',
    shortSummary:
      'Exports the weighted adjacency matrix of the final coarse graph G_c (with vertex weights on the diagonal) in Matrix Market format.',
    scientificBackground: [
      'Allows inspecting the exact coarse graph topology and weight distribution that was handed to METIS, Quantum Annealing, or QAOA, and powers Plot #7 (Coarse Graph Partition Topology) in the Results Explorer.',
    ],
    implementationDetails: [
      'Written by save_coarsened_graph_matrix() in src/libs/runtime/reporting.py.',
    ],
    sourceFile: 'src/libs/runtime/reporting.py',
  },

  'output-matrix-k-permuted': {
    id: 'output-matrix-k-permuted',
    category: 'stage5',
    title: 'Permuted Stiffness Matrix (matrix_k_permuted.mtx)',
    codeKey: 'save_output includes "matrix_k_permuted"',
    badge: 'Output Artifact (.mtx)',
    shortSummary:
      'Exports the domain-decomposed stiffness matrix K’ = P K Pᵀ in Matrix Market format for downstream solvers and spy-plot diagnostics.',
    scientificBackground: [
      'Required to visualize the permuted sparsity pattern, distance-to-diagonal histograms, and 2D log10(|K|) density heatmaps in the Results Explorer.',
    ],
    implementationDetails: [
      'Written via scipy.io.mmwrite to results/run_<timestamp>/matrix_k_permuted.mtx.',
    ],
    sourceFile: 'src/orchestrator.py',
  },

  'output-matrix-m-permuted': {
    id: 'output-matrix-m-permuted',
    category: 'stage5',
    title: 'Permuted Mass Matrix (matrix_m_permuted.mtx)',
    codeKey: 'save_output includes "matrix_m_permuted"',
    badge: 'Output Artifact (.mtx)',
    shortSummary:
      'Exports the congruently permuted mass matrix M’ = P M Pᵀ in Matrix Market format.',
    scientificBackground: [
      'Used alongside K’ in modal/harmonic structural solvers.',
    ],
    implementationDetails: [
      'Written via scipy.io.mmwrite to results/run_<timestamp>/matrix_m_permuted.mtx.',
    ],
    sourceFile: 'src/orchestrator.py',
  },

  'output-permutation': {
    id: 'output-permutation',
    category: 'stage5',
    title: 'DOF Permutation Vector (permutation.txt)',
    codeKey: 'save_output includes "permutation"',
    badge: 'Output Artifact (.txt)',
    shortSummary:
      'Saves the 1D integer array p of length N mapping new permuted row/column index i to original DOF index p[i].',
    scientificBackground: [
      'Allows external FEM solvers to reorder right-hand-side load vectors f’ = P f and recover physical nodal displacements u = Pᵀ u’ without storing duplicate matrices.',
    ],
    implementationDetails: [
      'Saved as newline-delimited integers via np.savetxt("permutation.txt", perm, fmt="%d").',
    ],
    sourceFile: 'src/orchestrator.py',
  },

  'output-run-metrics': {
    id: 'output-run-metrics',
    category: 'stage5',
    title: 'Structural & Graph Metrics Report (run_metrics.json / .txt)',
    codeKey: 'save_output includes "run_metrics"',
    badge: 'Output Artifact (.json & .txt)',
    shortSummary:
      'Saves comprehensive before/after bandwidth, nB², average bandwidth, diagonal band fractions (0.1%–1.0%), graph cut, balance, and permutation check results.',
    scientificBackground: [
      'Primary quantitative benchmark record used for thesis tables and cross-algorithm comparisons.',
    ],
    implementationDetails: [
      'Generated by compute_run_metrics() and write_run_metrics_files() in src/libs/runtime/metrics.py.',
    ],
    sourceFile: 'src/libs/runtime/metrics.py',
  },

  'output-run-simulation-parameters': {
    id: 'output-run-simulation-parameters',
    category: 'stage5',
    title: 'Normalized Parameters Snapshot (run_simulation_parameters.json)',
    codeKey: 'save_output includes "run_simulation_parameters"',
    badge: 'Output Artifact (.json)',
    shortSummary:
      'Saves the exact validated hyperparameter dictionary used for the run inside the timestamped result folder for full scientific reproducibility.',
    scientificBackground: [
      'Guarantees that every historical run folder is self-documenting even if data/simulation_parameters.json is later modified.',
    ],
    implementationDetails: [
      'Written via save_json() in src/orchestrator.py.',
    ],
    sourceFile: 'src/orchestrator.py',
  },

  // ==========================================
  // 7. STRUCTURAL & GRAPH METRICS REFERENCE
  // ==========================================
  'metric-bandwidth': {
    id: 'metric-bandwidth',
    category: 'metrics',
    title: 'Maximum Matrix Bandwidth B(A)',
    codeKey: 'bandwidth_stats.original_bw / permuted_bw',
    badge: 'Structural Metric • Envelope Bound',
    shortSummary:
      'Maximum absolute index distance |i - j| over all nonzero entries A_ij ≠ 0. Bounds the worst-case envelope width in banded direct factorizations.',
    formula: 'B(A) = max_{A_{ij} ≠ 0} |i - j|',
    scientificBackground: [
      'For a symmetric matrix A of dimension N, the semi-bandwidth B(A) defines the narrowest diagonal band containing 100% of all nonzero entries.',
      'In banded Gaussian elimination or Cholesky factorization, fill-in is strictly confined within the envelope |i - j| ≤ B(A). Reducing B(A) shrinks memory footprint and worst-case elimination work.',
    ],
    implementationDetails: [
      'Computed on upper-triangular nonzero coordinates (i ≤ j) in matrix_bandwidth_stats() inside src/libs/runtime/metrics.py.',
    ],
    sourceFile: 'src/libs/runtime/metrics.py',
  },

  'metric-nb2': {
    id: 'metric-nb2',
    category: 'metrics',
    title: 'Worst-Case Banded Factorization Complexity Proxy (nB²)',
    codeKey: 'C_fact ≈ n · B(A)²',
    badge: 'Structural Metric • Thesis Ch. 3 & 8',
    shortSummary:
      'Asymptotic upper-bound flop count proxy n · B(A)² for dense-within-band Cholesky/LU factorization.',
    formula: 'C_fact(A) = N · B(A)²   |   Δ(nB²)% = (B_perm² - B_orig²) / B_orig² × 100%',
    scientificBackground: [
      'Factorizing an N × N banded matrix with semi-bandwidth B requires O(N · B²) floating-point operations in the worst case.',
      'Because B(A) appears squared, even a 15–25% reduction in maximum bandwidth B(A) yields a 28–44% reduction in the worst-case factorization complexity bound nB².',
    ],
    implementationDetails: [
      'Computed automatically in the Results Explorer and thesis LaTeX table generator from original_bw, permuted_bw, and matrix dimension N.',
    ],
    sourceFile: 'backend/routes/results.py',
  },

  'metric-avg-bandwidth': {
    id: 'metric-avg-bandwidth',
    category: 'metrics',
    title: 'Average Bandwidth B̄(A)',
    codeKey: 'bandwidth_stats.original_avg_bw / permuted_avg_bw',
    badge: 'Structural Metric • Mean Distance',
    shortSummary:
      'Arithmetic mean of |i - j| across all upper-triangular nonzero entries of the matrix.',
    formula: 'B̄(A) = (1 / |Ω⁺|) Σ_{(i,j)∈Ω⁺} |i - j|   where Ω⁺ = {(i,j) : i ≤ j, A_{ij} ≠ 0}',
    scientificBackground: [
      'While B(A) is sensitive to a single extreme outlier entry far from the diagonal, the average bandwidth B̄(A) reflects the typical row-column index separation of all nonzeros.',
      'Note: Domain-block ordering groups vertices by subdomain (0, 1, ..., k-1); interface edges connecting subdomain 0 and subdomain k-1 can have large index distance, so always inspect B̄(A) alongside local diagonal band fractions.',
    ],
    implementationDetails: [
      'Computed as float(np.mean(dist)) over upper-triangular nonzeros in matrix_bandwidth_stats().',
    ],
    sourceFile: 'src/libs/runtime/metrics.py',
  },

  'metric-diag-fractions': {
    id: 'metric-diag-fractions',
    category: 'metrics',
    title: 'Near-Diagonal Band Concentration Fractions (frac_0.1% – frac_1.0%)',
    codeKey: 'band_fractions.frac_0.1pct ... frac_1.0pct',
    badge: 'Structural Metric • Preconditioner Locality',
    shortSummary:
      'Fraction of upper-triangular nonzero entries lying within a narrow corridor b_ρ = ⌈(ρ/100)·N⌉ around the main diagonal for ρ ∈ {0.1%, 0.4%, 0.7%, 1.0%}.',
    formula: 'frac_{ρ%}(A) = |{(i,j)∈Ω⁺ : |i - j| ≤ ⌈(ρ/100)N⌉}| / |Ω⁺|',
    scientificBackground: [
      'Incomplete LU/Cholesky preconditioners and banded block-Jacobi / Schwarz smoothers retain nonzeros close to the main diagonal and drop or approximate distant couplings.',
      'Measuring the fraction of nonzeros captured within 0.1%, 0.4%, 0.7%, and 1.0% of the matrix dimension N directly quantifies local diagonal concentration after domain permutation.',
    ],
    implementationDetails: [
      'Evaluated at percentages (0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0) in matrix_band_Metrics() inside src/libs/runtime/metrics.py.',
    ],
    sourceFile: 'src/libs/runtime/metrics.py',
  },

  'metric-edge-cut': {
    id: 'metric-edge-cut',
    category: 'metrics',
    title: 'Weighted Graph Edge Cut & Relative Cut Fraction',
    codeKey: 'partition_stats.cut_weight / cut_fraction',
    badge: 'Graph Partition Metric',
    shortSummary:
      'Total weight of edges crossing between different subdomains on both the coarse graph G_c and the fine graph G_0.',
    formula: 'Cut(P) = Σ_{(u,v)∈E, P[u]≠P[v]} w(u, v),   CutFrac = Cut(P) / Σ_{(u,v)∈E} w(u, v)',
    scientificBackground: [
      'In domain decomposition, edges crossing between different subdomains correspond to interface DOFs (Schur complement couplings) that require inter-processor communication or interface solves.',
      'Minimizing Cut(P) while maintaining subdomain weight balance minimizes the coupling strength outside the block-diagonal preconditioner.',
    ],
    implementationDetails: [
      'Computed on both G_c (coarse_graph_partition) and G_0 (fine_graph_partition) in graph_partition_stats().',
    ],
    sourceFile: 'src/libs/runtime/metrics.py',
  },

  'batch-study': {
    id: 'batch-study',
    category: 'workflows',
    title: 'Multi-Matrix & Multi-Scale Batch Study Orchestrator',
    codeKey: 'batch/batch_configuration.json',
    badge: 'Batch Benchmarking Engine',
    shortSummary:
      'Automates Cartesian benchmarking across multiple matrices (geometries), coarsening scales (small, medium, big), and partitioning backends.',
    formula: 'Cases = Matrices × Allowed(Algorithm_Presets × Coarsening_Scales)',
    scientificBackground: [
      'To systematically evaluate classical vs. quantum partitioning, each matrix case (matrix_01, matrix_02, matrix_03) is tested across multiple coarse graph scales and solver backends under identical uncoarsening rules.',
      'Each algorithm preset specifies allowed_sizes (for instance, QAOA runs on "small" 4–5 node coarse graphs due to qubit simulation/hardware limits, whereas METIS and QA run on "small", "medium", and "big").',
    ],
    implementationDetails: [
      'Configured via batch/batch_configuration.json and executed by batch/run_batch.py, producing batch/runs/batch_<timestamp>/batch_summary.json.',
    ],
    sourceFile: 'batch/run_batch.py',
  },

  'hardware-backends': {
    id: 'hardware-backends',
    category: 'workflows',
    title: 'Runtime SDKs & Quantum Hardware Probes',
    codeKey: 'backend/routes/quantum_hw.py',
    badge: 'Environment & QPU Diagnostics',
    shortSummary:
      'Checks installed Python classical/quantum SDKs (PyMETIS, D-Wave Neal, D-Wave System, PennyLane, myQLM) and probes live QPU capacities.',
    scientificBackground: [
      'Dense QUBO balance penalties require embedding a complete graph K_n onto physical QPU topologies (Pegasus/Zephyr on D-Wave Advantage), bounding the maximum coarse graph size to ~175–180 nodes.',
      'Gate-based QAOA on QLM / myQLM inspects the target QPU specifications (reported_max_qubits, connectivity topology, and COBYLA remote variational job support).',
    ],
    implementationDetails: [
      'Calls get_qpu_dense_clique_capacity() via dwave-system / minorminer and get_qlm_qpu_api_summary() in src/libs/multilevel_scheme/partitioning/qa/.',
    ],
    sourceFile: 'backend/routes/quantum_hw.py',
  },

  'tool-dry-run-coarsening': {
    id: 'tool-dry-run-coarsening',
    category: 'stage2',
    title: 'Dry-Run Coarsening Trajectory Preview',
    codeKey: 'POST /api/demonstrators/{dem_id}/preview-coarsening',
    badge: 'Interactive Hierarchy Simulator',
    shortSummary:
      'Executes Stage 1 and Stage 2 Heavy Edge Matching in ~35 ms to preview the exact level-by-level contraction hierarchy G_0 → G_1 → … → G_L before launching a full run.',
    scientificBackground: [
      'Shows the vertex and edge counts, contraction ratio r_l = |V_l|/|V_{l-1}|, and maximum supernode weight at each level, along with whether the target range [coarsen_inferior_limit, coarsen_superior_limit] was reached or why contraction stopped.',
    ],
    implementationDetails: [
      'Implemented in preview_coarsening_trajectory() in backend/routes/matrices.py.',
    ],
    sourceFile: 'backend/routes/matrices.py',
  },

  'tool-feasibility-check': {
    id: 'tool-feasibility-check',
    category: 'stage3',
    title: 'Cross-Stage Qubit & Embedding Feasibility Check',
    codeKey: 'coarsen_inferior_limit / coarsen_superior_limit',
    badge: 'Stage 2 ↔ Stage 3 Guardrail',
    shortSummary:
      'Warns when the Stage 2 coarse node range exceeds the practical capacity of the selected Stage 3 quantum backend.',
    scientificBackground: [
      'PennyLane default.qubit statevector emulation scales as O(2^n) memory and time per coarse vertex, making coarse graphs above ~18 nodes impractical for local statevector QAOA.',
      'D-Wave Advantage QPUs require complete-graph K_n minor-embedding when qubo_balance_lambda > 0, limiting dense QUBOs to ~175–180 logical coarse vertices.',
    ],
    implementationDetails: [
      'Provides a 1-click Auto-Adjust button to set Stage 2 coarse limits to Small [4, 5] for QAOA or Medium [100, 175] for D-Wave QPU.',
    ],
    sourceFile: 'frontend/src/components/PipelineStudio.tsx',
  },

  'tool-compare-configs': {
    id: 'tool-compare-configs',
    category: 'workflows',
    title: 'Configuration & Run Comparators',
    codeKey: 'Compare Configs / Compare Run B',
    badge: 'Side-by-Side Diff Tools',
    shortSummary:
      'Compares two parameter presets side-by-side in the Pipeline Studio, or compares two completed runs (Run A vs. Run B) in the Results Explorer.',
    scientificBackground: [
      'Highlights parameter differences across Stages 1–4 before execution, and compares Matrix K & M bandwidth, nB² reduction, and diagonal locality curves across two runs.',
    ],
    implementationDetails: [
      'Implemented in PipelineStudio.tsx and ResultsExplorer.tsx.',
    ],
    sourceFile: 'frontend/src/components/ResultsExplorer.tsx',
  },
};

export function getWikiTopic(topicId: string): WikiTopic | undefined {
  return WIKI_TOPICS[topicId];
}

