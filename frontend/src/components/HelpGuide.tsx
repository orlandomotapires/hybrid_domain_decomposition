import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  ArrowRight,
  BarChart3,
  BookOpen,
  Compass,
  Cpu,
  Database,
  FileCode,
  FolderPlus,
  GitBranch,
  Layers,
  Play,
  Search,
  Sliders,
  Sparkles,
  Wrench,
  X,
} from 'lucide-react';
import {
  WIKI_CATEGORIES,
  WIKI_TOPICS,
  WikiCategoryKey,
  WikiTopic,
} from '../data/wikiKnowledgeBase';

interface HelpGuideProps {
  onNavigateTab: (tab: 'pipeline' | 'execution' | 'batch' | 'results' | 'hardware') => void;
  onOpenNewDemonstrator: () => void;
  focusedTopicId?: string | null;
  onClearFocus?: () => void;
}

const CATEGORY_ICONS: Record<WikiCategoryKey, React.FC<{ className?: string }>> = {
  theory: Compass,
  stage1: Database,
  stage2: Layers,
  stage3: Cpu,
  stage4: GitBranch,
  stage5: Activity,
  metrics: BarChart3,
  workflows: Play,
};

export const HelpGuide: React.FC<HelpGuideProps> = ({
  onNavigateTab,
  onOpenNewDemonstrator,
  focusedTopicId,
  onClearFocus,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<WikiCategoryKey | 'all'>('theory');
  const [searchQuery, setSearchQuery] = useState('');

  const allTopics = useMemo(() => Object.values(WIKI_TOPICS), []);

  // When a user clicks "More details" on an (i) tooltip in the Studio,
  // switch to that topic's category and scroll to its anchor card.
  useEffect(() => {
    if (!focusedTopicId) return;
    const topic = WIKI_TOPICS[focusedTopicId];
    if (topic) {
      setSearchQuery('');
      setSelectedCategory(topic.category);
      const timer = window.setTimeout(() => {
        const el = document.getElementById(`wiki-topic-${focusedTopicId}`);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }, 80);
      return () => window.clearTimeout(timer);
    }
  }, [focusedTopicId]);

  const filteredTopics = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return allTopics.filter((t) => {
      const matchesCat =
        q.length > 0 || selectedCategory === 'all' || t.category === selectedCategory;
      if (!matchesCat) return false;
      if (!q) return true;
      return (
        t.title.toLowerCase().includes(q) ||
        (t.codeKey && t.codeKey.toLowerCase().includes(q)) ||
        t.shortSummary.toLowerCase().includes(q) ||
        (t.formula && t.formula.toLowerCase().includes(q)) ||
        t.scientificBackground.some((p) => p.toLowerCase().includes(q)) ||
        t.implementationDetails.some((p) => p.toLowerCase().includes(q))
      );
    });
  }, [allTopics, selectedCategory, searchQuery]);

  const activeCategoryMeta = WIKI_CATEGORIES.find((c) => c.key === selectedCategory);

  return (
    <div className="space-y-6 min-w-0">
      {/* Top Wiki Hero Banner */}
      <div className="bg-gradient-to-r from-slate-900 via-indigo-950/60 to-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="max-w-3xl space-y-1.5 min-w-0">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
              <BookOpen className="w-3.5 h-3.5" />
              Complete Scientific & Technical Project Wiki
            </div>
            <h2 className="text-xl font-bold text-white">
              Hybrid Quantum-Classical Domain Decomposition Encyclopedia
            </h2>
            <p className="text-xs text-slate-300 leading-relaxed">
              Comprehensive scientific theory, mathematical QUBO/Ising formulations, multilevel Heavy Edge Matching algorithms, JSON variable specifications, structural matrix metrics, and step-by-step operational workflows.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <button
              onClick={() => onNavigateTab('pipeline')}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/20 transition"
            >
              <Sliders className="w-3.5 h-3.5" />
              Back to Pipeline Studio
            </button>
            <button
              onClick={onOpenNewDemonstrator}
              className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
            >
              <FolderPlus className="w-3.5 h-3.5 text-indigo-400" />
              New Simulation
            </button>
          </div>
        </div>

        {/* Global Search Bar & Focused Topic Banner */}
        <div className="mt-5 pt-4 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-4">
          <div className="relative flex-1 min-w-[260px] max-w-xl">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-2.5" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search any variable (e.g. dof_per_node, qubo_balance_lambda), method (MHEM, QAOA), or equation..."
              className="w-full bg-slate-950/90 border border-slate-700 rounded-xl pl-10 pr-9 py-2 text-xs text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-3 top-2.5 text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {focusedTopicId && WIKI_TOPICS[focusedTopicId] && (
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-indigo-500/20 border border-indigo-400/50 text-xs text-indigo-200">
                <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                <span>
                  Focused: <strong className="text-white">{WIKI_TOPICS[focusedTopicId].title}</strong>
                </span>
                {onClearFocus && (
                  <button
                    onClick={onClearFocus}
                    className="ml-1 text-indigo-300 hover:text-white"
                    title="Clear highlight"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            )}

            <button
              onClick={() => {
                setSearchQuery('');
                setSelectedCategory('all');
              }}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition ${
                selectedCategory === 'all' && !searchQuery
                  ? 'bg-indigo-600 text-white border-indigo-500'
                  : 'bg-slate-950/80 text-slate-300 border-slate-800 hover:bg-slate-800'
              }`}
            >
              Show All ({allTopics.length} Entries)
            </button>
          </div>
        </div>
      </div>

      {/* Main Wiki Layout: Sidebar Chapters + Content Area */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 items-start">
        {/* Left Sidebar Navigation */}
        <aside className="lg:col-span-1 bg-slate-900/90 border border-slate-800 rounded-2xl p-4 space-y-2 lg:sticky lg:top-28 min-w-0">
          <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400 px-2 pb-1">
            Wiki Chapters & Modules
          </div>
          {WIKI_CATEGORIES.map((cat) => {
            const Icon = CATEGORY_ICONS[cat.key];
            const isSelected = selectedCategory === cat.key && !searchQuery;
            const count = allTopics.filter((t) => t.category === cat.key).length;

            return (
              <button
                key={cat.key}
                onClick={() => {
                  setSearchQuery('');
                  setSelectedCategory(cat.key);
                }}
                className={`w-full text-left px-3 py-2.5 rounded-xl text-xs font-semibold transition flex items-center justify-between gap-2 ${
                  isSelected
                    ? 'bg-indigo-600 text-white shadow'
                    : 'text-slate-300 hover:bg-slate-800/80 hover:text-white'
                }`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <Icon
                    className={`w-4 h-4 shrink-0 ${
                      isSelected ? 'text-white' : 'text-indigo-400'
                    }`}
                  />
                  <span className="truncate">{cat.shortLabel}</span>
                </div>
                <span
                  className={`text-[10px] font-mono px-1.5 py-0.5 rounded shrink-0 ${
                    isSelected
                      ? 'bg-indigo-800 text-indigo-100'
                      : 'bg-slate-950 text-slate-400'
                  }`}
                >
                  {count}
                </span>
              </button>
            );
          })}

          {/* Quick Jump Index within Active Category */}
          {!searchQuery && selectedCategory !== 'all' && (
            <div className="pt-3 mt-3 border-t border-slate-800 space-y-1">
              <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 px-2">
                Topics in this Chapter
              </div>
              {filteredTopics.map((t) => {
                const isFocused = focusedTopicId === t.id;
                return (
                  <button
                    key={t.id}
                    onClick={() => {
                      const el = document.getElementById(`wiki-topic-${t.id}`);
                      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }}
                    className={`w-full text-left px-2.5 py-1.5 rounded-lg text-[11px] transition truncate ${
                      isFocused
                        ? 'bg-indigo-500/20 text-indigo-200 font-semibold border border-indigo-500/40'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-950/60'
                    }`}
                    title={t.title}
                  >
                    • {t.title}
                  </button>
                );
              })}
            </div>
          )}
        </aside>

        {/* Right Wiki Content Area */}
        <div className="lg:col-span-3 space-y-5 min-w-0">
          {/* Active Chapter Header */}
          {!searchQuery && activeCategoryMeta && (
            <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5">
              <h3 className="text-base font-bold text-white">{activeCategoryMeta.label}</h3>
              <p className="text-xs text-slate-400 mt-1">{activeCategoryMeta.description}</p>
            </div>
          )}

          {searchQuery && (
            <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-4 text-xs text-slate-300">
              Showing <strong className="text-white">{filteredTopics.length}</strong> scientific wiki entries matching{' '}
              <code className="text-indigo-300">&quot;{searchQuery}&quot;</code>
            </div>
          )}

          {/* Step-by-Step User Workflows & Troubleshooting (when on 'workflows' chapter) */}
          {(selectedCategory === 'workflows' || searchQuery) && !searchQuery && (
            <div className="space-y-5">
              {/* Workflow 1 */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b border-slate-800">
                  <div>
                    <span className="text-xs font-mono uppercase text-indigo-400 font-bold">
                      Workflow 1 • Quick Start
                    </span>
                    <h4 className="text-base font-bold text-white mt-0.5">
                      How to Switch Methods, Customize Parameters & Run a Simulation
                    </h4>
                  </div>
                  <button
                    onClick={() => onNavigateTab('pipeline')}
                    className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white transition"
                  >
                    Go to Pipeline Studio <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-5 gap-3 text-xs">
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <div className="font-mono font-bold text-indigo-400">1. Pick Matrix</div>
                    <p className="text-slate-300">
                      Click <code>matrix_01</code>, <code>02</code>, or <code>03</code> in the top bar to load its configuration.
                    </p>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <div className="font-mono font-bold text-indigo-400">2. Check K & M</div>
                    <p className="text-slate-300">
                      In Stage 1, ensure K & M are present or click <strong>Generate Demo Mesh</strong> / <strong>Upload .mtx</strong>.
                    </p>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <div className="font-mono font-bold text-indigo-400">3. Coarsening</div>
                    <p className="text-slate-300">
                      In Stage 2, select an HEM rule (e.g., <code>Modified HEM</code>) and a scale preset (<code>Small</code>, <code>Medium</code>, <code>Big</code>).
                    </p>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <div className="font-mono font-bold text-indigo-400">4. Partitioner</div>
                    <p className="text-slate-300">
                      In Stage 3, choose <code>METIS</code>, <code>Quantum Annealing</code>, or <code>QAOA</code> and set <code>k_target</code>.
                    </p>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <div className="font-mono font-bold text-indigo-400">5. Save & Run</div>
                    <p className="text-slate-300">
                      Click <strong>Save to JSON Files</strong> or <strong>Run Pipeline Now</strong> to stream live logs and metrics.
                    </p>
                  </div>
                </div>
              </div>

              {/* Workflow 2 */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b border-slate-800">
                  <div>
                    <span className="text-xs font-mono uppercase text-emerald-400 font-bold">
                      Workflow 2 • Custom FEM Models
                    </span>
                    <h4 className="text-base font-bold text-white mt-0.5">
                      How to Create a New Simulation with Your Own ANSYS .mtx Matrices
                    </h4>
                  </div>
                  <button
                    onClick={onOpenNewDemonstrator}
                    className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white transition"
                  >
                    <FolderPlus className="w-3.5 h-3.5" /> Create New Matrix
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <div className="font-mono font-bold text-emerald-400">1. Clone Template</div>
                    <p className="text-slate-300">
                      Click <strong>+ New</strong> in the header bar, name your matrix folder, and clone settings from an existing workspace.
                    </p>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <div className="font-mono font-bold text-emerald-400">2. Upload .mtx</div>
                    <p className="text-slate-300">
                      In Stage 1, upload your sparse stiffness (<code>K</code>) and mass (<code>M</code>) Matrix Market files and select them in the dropdowns.
                    </p>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <div className="font-mono font-bold text-emerald-400">3. Set dof_per_node</div>
                    <p className="text-slate-300">
                      Ensure matrix dimension <code>N</code> is divisible by <code>dof_per_node</code> (e.g., 3 for 3D solid elements, 1 for scalar).
                    </p>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <div className="font-mono font-bold text-emerald-400">4. Inspect 10 Plots</div>
                    <p className="text-slate-300">
                      Run the pipeline and open <strong>Results, Plots & LaTeX Tables</strong> to inspect spy plots, heatmaps, and bandwidth reductions.
                    </p>
                  </div>
                </div>
              </div>

              {/* Troubleshooting FAQ */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 space-y-4">
                <h4 className="text-base font-bold text-white flex items-center gap-2">
                  <Wrench className="w-4 h-4 text-amber-400" />
                  Troubleshooting Common Validation & Runtime Messages
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-1.5">
                    <div className="font-mono font-bold text-rose-400">
                      &quot;Global size N not divisible by DOF_PER_NODE&quot;
                    </div>
                    <p className="text-slate-300">
                      <strong>Cause:</strong> Matrix dimension <code>N</code> is not an integer multiple of <code>dof_per_node</code>.<br />
                      <strong>Fix:</strong> Adjust <code>dof_per_node</code> in Stage 1 (e.g., set to <code>1</code> for node-level matrices or <code>3</code> for 3D solid meshes).
                    </p>
                  </div>

                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-1.5">
                    <div className="font-mono font-bold text-amber-400">
                      &quot;Unable to coarsen graph into requested range [inf, sup]&quot;
                    </div>
                    <p className="text-slate-300">
                      <strong>Cause:</strong> Coarsening stopped before reaching <code>superior_limit</code> or jumped across a narrow range.<br />
                      <strong>Fix:</strong> Widen <code>[coarsen_inferior_limit, coarsen_superior_limit]</code>, increase <code>max_levels</code> (e.g., 30), or set <code>coarsen_ratio = 0.99</code>.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Encyclopedia Topic Cards */}
          <div className="space-y-4">
            {filteredTopics.map((topic: WikiTopic) => {
              const isFocused = focusedTopicId === topic.id;
              return (
                <article
                  key={topic.id}
                  id={`wiki-topic-${topic.id}`}
                  className={`rounded-2xl p-6 transition-all space-y-4 min-w-0 overflow-hidden ${
                    isFocused
                      ? 'bg-indigo-950/40 border-2 border-indigo-400 ring-4 ring-indigo-500/20 shadow-2xl'
                      : 'bg-slate-900/85 border border-slate-800 hover:border-slate-700'
                  }`}
                >
                  {/* Topic Header */}
                  <div className="flex flex-wrap items-start justify-between gap-3 pb-3 border-b border-slate-800/80">
                    <div className="space-y-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        {isFocused && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-500 text-white">
                            Selected from Studio (i)
                          </span>
                        )}
                        <span className="px-2.5 py-0.5 rounded-md text-[11px] font-mono font-semibold bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
                          {topic.badge}
                        </span>
                        {topic.codeKey && (
                          <code className="px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-[11px] font-mono text-amber-300 break-all">
                            {topic.codeKey}
                          </code>
                        )}
                      </div>
                      <h4 className="text-base font-bold text-white pt-1 break-words">
                        {topic.title}
                      </h4>
                    </div>

                    {topic.sourceFile && (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-950 border border-slate-800 text-[11px] font-mono text-slate-400 shrink-0">
                        <FileCode className="w-3.5 h-3.5 text-cyan-400" />
                        {topic.sourceFile}
                      </span>
                    )}
                  </div>

                  {/* Concise Summary */}
                  <p className="text-xs text-slate-200 font-medium leading-relaxed">
                    {topic.shortSummary}
                  </p>

                  {/* Mathematical Formula / Invariant Box */}
                  {topic.formula && (
                    <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800/90 font-mono text-xs text-amber-300 overflow-x-auto">
                      {topic.formula}
                    </div>
                  )}

                  {/* Scientific & Mathematical Background + Implementation Details */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
                    <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 space-y-2 min-w-0">
                      <div className="text-[11px] font-mono uppercase tracking-wider text-indigo-400 font-bold">
                        Scientific & Mathematical Background
                      </div>
                      <div className="space-y-2 text-xs text-slate-300 leading-relaxed">
                        {topic.scientificBackground.map((paragraph, idx) => (
                          <p key={idx} className="break-words">
                            {paragraph}
                          </p>
                        ))}
                      </div>
                    </div>

                    <div className="space-y-3 min-w-0">
                      <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 space-y-2">
                        <div className="text-[11px] font-mono uppercase tracking-wider text-cyan-400 font-bold">
                          Pipeline Implementation Details
                        </div>
                        <ul className="space-y-1.5 text-xs text-slate-300 leading-relaxed list-disc list-inside">
                          {topic.implementationDetails.map((detail, idx) => (
                            <li key={idx} className="break-words">
                              {detail}
                            </li>
                          ))}
                        </ul>
                      </div>

                      {topic.tuningGuidelines && topic.tuningGuidelines.length > 0 && (
                        <div className="p-4 rounded-xl bg-indigo-950/25 border border-indigo-500/30 space-y-1.5">
                          <div className="text-[11px] font-mono uppercase tracking-wider text-amber-300 font-bold">
                            Practical Tuning Guidelines
                          </div>
                          <ul className="space-y-1 text-xs text-slate-300 leading-relaxed list-disc list-inside">
                            {topic.tuningGuidelines.map((tip, idx) => (
                              <li key={idx} className="break-words">
                                {tip}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
