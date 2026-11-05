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

/** Smooth-scroll to an element by id (topic cards and their sections carry scroll margins). */
const scrollToId = (id: string) => {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

/** Articles with at least this many paragraphs/bullets get an "On this page" table of contents. */
const TOC_MIN_ITEMS = 6;

type TopicSectionKey = 'formula' | 'background' | 'implementation' | 'tuning';

const topicSectionId = (topicId: string, section: TopicSectionKey) =>
  `wiki-topic-${topicId}-${section}`;

/** Sections an article actually renders, in display order. */
const topicSections = (topic: WikiTopic): Array<{ key: TopicSectionKey; label: string }> => [
  ...(topic.formula ? [{ key: 'formula' as const, label: 'Formula' }] : []),
  { key: 'background', label: 'Background' },
  { key: 'implementation', label: 'Implementation' },
  ...(topic.tuningGuidelines && topic.tuningGuidelines.length > 0
    ? [{ key: 'tuning' as const, label: 'Tuning guidelines' }]
    : []),
];

const isLongTopic = (topic: WikiTopic) =>
  topic.scientificBackground.length +
    topic.implementationDetails.length +
    (topic.tuningGuidelines?.length ?? 0) >=
  TOC_MIN_ITEMS;

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
        scrollToId(`wiki-topic-${focusedTopicId}`);
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
      {/* Compact Wiki Header: title + search + show all */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl px-4 py-3 flex flex-wrap items-center gap-3">
        <h2 className="flex items-center gap-2 text-sm font-bold text-white shrink-0">
          <BookOpen className="w-4 h-4 text-indigo-400" />
          Project Wiki
        </h2>

        <div className="relative flex-1 min-w-[220px] max-w-xl">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2" />
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search parameters, methods, metrics…"
            aria-label="Search the wiki"
            className="w-full bg-slate-950/90 border border-slate-700 rounded-xl pl-9 pr-9 py-1.5 text-xs text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1.5 text-slate-400 hover:text-white"
              aria-label="Clear search"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 ml-auto">
          {focusedTopicId && WIKI_TOPICS[focusedTopicId] && (
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-indigo-500/20 border border-indigo-400/50 text-xs text-indigo-200 min-w-0">
              <Sparkles className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
              <span className="truncate">
                Focused: <strong className="text-white">{WIKI_TOPICS[focusedTopicId].title}</strong>
              </span>
              {onClearFocus && (
                <button
                  type="button"
                  onClick={onClearFocus}
                  className="ml-1 text-indigo-300 hover:text-white"
                  title="Clear highlight"
                  aria-label="Clear highlight"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          )}

          <button
            type="button"
            aria-pressed={selectedCategory === 'all' && !searchQuery}
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
            Show all ({allTopics.length})
          </button>
        </div>
      </div>

      {/* Main Wiki Layout: Sidebar Chapters + Content Area */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 items-start">
        {/* Left Sidebar Navigation */}
        <aside
          aria-label="Wiki chapters"
          className="lg:col-span-1 bg-slate-900/90 border border-slate-800 rounded-2xl p-4 space-y-2 lg:sticky lg:top-24 lg:max-h-[calc(100vh-7.5rem)] lg:overflow-y-auto min-w-0"
        >
          <div className="text-xs font-mono uppercase tracking-wider text-slate-400 px-2 pb-1">
            Wiki Chapters & Modules
          </div>
          {WIKI_CATEGORIES.map((cat) => {
            const Icon = CATEGORY_ICONS[cat.key];
            const isSelected = selectedCategory === cat.key && !searchQuery;
            const count = allTopics.filter((t) => t.category === cat.key).length;

            return (
              <button
                key={cat.key}
                type="button"
                aria-pressed={isSelected}
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
                      isSelected ? 'text-white' : 'text-slate-400'
                    }`}
                  />
                  <span className="truncate">{cat.shortLabel}</span>
                </div>
                <span
                  className={`text-xs font-mono px-1.5 py-0.5 rounded shrink-0 ${
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
              <div className="text-xs font-mono uppercase tracking-wider text-slate-500 px-2">
                Topics in this chapter
              </div>
              {filteredTopics.map((t) => {
                const isFocused = focusedTopicId === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => scrollToId(`wiki-topic-${t.id}`)}
                    className={`w-full text-left px-2.5 py-1.5 rounded-lg text-xs transition truncate ${
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
                    type="button"
                    onClick={() => onNavigateTab('pipeline')}
                    className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white transition"
                  >
                    Go to Single Run <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-5 gap-3 text-xs">
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <div className="font-mono font-bold text-indigo-400">1. Pick Simulation</div>
                    <p className="text-slate-300">
                      In <strong>Single Run</strong>, click <code>simulation_01</code>, <code>02</code>, … in the top bar to load its configuration.
                    </p>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <div className="font-mono font-bold text-indigo-400">2. Pick a Matrix</div>
                    <p className="text-slate-300">
                      In Stage 1, pick any square sparse matrix from the shared library, or add one with <strong>Upload .mtx</strong> / <strong>Demo matrix</strong>.
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
                    <span className="text-xs font-mono uppercase text-indigo-400 font-bold">
                      Workflow 2 • Your Own Matrices
                    </span>
                    <h4 className="text-base font-bold text-white mt-0.5">
                      How to Create a New Simulation with Your Own .mtx Matrix
                    </h4>
                  </div>
                  <button
                    type="button"
                    onClick={onOpenNewDemonstrator}
                    className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white transition"
                  >
                    <FolderPlus className="w-3.5 h-3.5" /> New Simulation
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <div className="font-mono font-bold text-indigo-400">1. New Simulation</div>
                    <p className="text-slate-300">
                      Click <strong>New simulation</strong> in the Single Run top bar and optionally copy parameters from an existing simulation.
                    </p>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <div className="font-mono font-bold text-indigo-400">2. Upload .mtx</div>
                    <p className="text-slate-300">
                      In Stage 1, click <strong>Upload .mtx</strong> and choose any square Matrix Market file. It joins the shared library, so any simulation or batch can use it.
                    </p>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <div className="font-mono font-bold text-indigo-400">3. Set the block size</div>
                    <p className="text-slate-300">
                      Keep it at <code>1</code> (one graph node per row) unless rows come in fixed-size blocks, e.g. 3 DOFs per mesh node in 3D FEM. <code>N</code> must be divisible by it.
                    </p>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <div className="font-mono font-bold text-indigo-400">4. Inspect 10 Plots</div>
                    <p className="text-slate-300">
                      Run the pipeline and open <strong>Results & Plots</strong> to inspect spy plots, heatmaps, and bandwidth reductions.
                    </p>
                  </div>
                </div>
              </div>

              {/* Troubleshooting FAQ */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 space-y-4">
                <h4 className="text-base font-bold text-white flex items-center gap-2">
                  <Wrench className="w-4 h-4 text-slate-400" />
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
                  className={`rounded-2xl p-6 transition-all space-y-4 min-w-0 overflow-hidden scroll-mt-24 ${
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
                          <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-indigo-500 text-white">
                            Selected from Studio (i)
                          </span>
                        )}
                        <span className="px-2.5 py-0.5 rounded-md text-xs font-mono font-semibold bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
                          {topic.badge}
                        </span>
                        {topic.codeKey && (
                          <code className="px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-xs font-mono text-indigo-200 break-all">
                            {topic.codeKey}
                          </code>
                        )}
                      </div>
                      <h4 className="text-base font-bold text-white pt-1 break-words">
                        {topic.title}
                      </h4>
                    </div>

                    {topic.sourceFile && (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono text-slate-400 shrink-0">
                        <FileCode className="w-3.5 h-3.5 text-slate-500" />
                        {topic.sourceFile}
                      </span>
                    )}
                  </div>

                  {/* Concise Summary */}
                  <p className="text-xs text-slate-200 font-medium leading-relaxed">
                    {topic.shortSummary}
                  </p>

                  {/* On-this-page TOC for long articles */}
                  {isLongTopic(topic) && (
                    <nav
                      aria-label={`Sections of ${topic.title}`}
                      className="flex flex-wrap items-center gap-x-1 gap-y-1 text-xs"
                    >
                      <span className="text-slate-500 font-mono uppercase tracking-wider mr-1">
                        On this page:
                      </span>
                      {topicSections(topic).map((sec, i) => (
                        <React.Fragment key={sec.key}>
                          {i > 0 && <span className="text-slate-600">·</span>}
                          <a
                            href={`#${topicSectionId(topic.id, sec.key)}`}
                            onClick={(e) => {
                              e.preventDefault();
                              scrollToId(topicSectionId(topic.id, sec.key));
                            }}
                            className="px-1.5 py-0.5 rounded text-indigo-300 hover:text-white hover:bg-slate-800 transition"
                          >
                            {sec.label}
                          </a>
                        </React.Fragment>
                      ))}
                    </nav>
                  )}

                  {/* Mathematical Formula / Invariant Box */}
                  {topic.formula && (
                    <div
                      id={topicSectionId(topic.id, 'formula')}
                      className="p-3.5 rounded-xl bg-slate-950 border border-slate-800/90 font-mono text-xs text-slate-100 overflow-x-auto scroll-mt-24"
                    >
                      {topic.formula}
                    </div>
                  )}

                  {/* Scientific & Mathematical Background + Implementation Details */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
                    <div
                      id={topicSectionId(topic.id, 'background')}
                      className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 space-y-2 min-w-0 scroll-mt-24"
                    >
                      <div className="text-xs font-mono uppercase tracking-wider text-indigo-400 font-bold">
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
                      <div
                        id={topicSectionId(topic.id, 'implementation')}
                        className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 space-y-2 scroll-mt-24"
                      >
                        <div className="text-xs font-mono uppercase tracking-wider text-indigo-400 font-bold">
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
                        <div
                          id={topicSectionId(topic.id, 'tuning')}
                          className="p-4 rounded-xl bg-indigo-950/25 border border-indigo-500/30 space-y-1.5 scroll-mt-24"
                        >
                          <div className="text-xs font-mono uppercase tracking-wider text-indigo-300 font-bold">
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
