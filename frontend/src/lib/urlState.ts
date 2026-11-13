/**
 * Keeps the active tab and selection in the URL hash, e.g.
 *   #/results?matrix=simulation_01&run=simulations/simulation_01/results/run_...
 * so refresh, back/forward and bookmarks restore the same view.
 */

export const TABS = ['pipeline', 'execution', 'batch', 'tuning', 'results', 'hardware', 'help'] as const;
export type ActiveTab = (typeof TABS)[number];

export interface UrlState {
  tab: ActiveTab;
  matrix?: string;
  job?: string;
  run?: string;
  batch?: string;
  topic?: string;
}

export function readUrlState(): UrlState {
  const raw = window.location.hash.replace(/^#\/?/, '');
  const [path, query = ''] = raw.split('?');
  const tab = (TABS as readonly string[]).includes(path) ? (path as ActiveTab) : 'pipeline';
  const params = new URLSearchParams(query);
  const get = (k: string) => params.get(k) || undefined;
  return {
    tab,
    matrix: get('matrix'),
    job: get('job'),
    run: get('run'),
    batch: get('batch'),
    topic: get('topic'),
  };
}

export function buildUrlHash(state: UrlState): string {
  const params = new URLSearchParams();
  if (state.matrix) params.set('matrix', state.matrix);
  if (state.tab === 'execution' && state.job) params.set('job', state.job);
  if (state.tab === 'results' && state.run) params.set('run', state.run);
  if (state.tab === 'results' && state.batch && !state.run) params.set('batch', state.batch);
  if (state.tab === 'help' && state.topic) params.set('topic', state.topic);
  const q = params.toString();
  return `#/${state.tab}${q ? `?${q}` : ''}`;
}

/** Push when the tab changes (so Back works), replace for in-tab selection changes. */
export function writeUrlState(state: UrlState): void {
  const next = buildUrlHash(state);
  if (next === window.location.hash) return;
  const prevTab = readUrlState().tab;
  if (prevTab !== state.tab) {
    window.history.pushState(null, '', next);
  } else {
    window.history.replaceState(null, '', next);
  }
}
