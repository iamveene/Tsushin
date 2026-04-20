/**
 * Curated Ollama models offered by Tsushin for per-tenant auto-provisioning.
 *
 * Single source of truth shared by:
 *   - `frontend/components/ollama/OllamaSetupWizard.tsx`
 *   - `frontend/app/hub/page.tsx` (Hub > AI Providers > Ollama panel)
 *
 * No backend endpoint fronts this list because the curation is editorial
 * (chosen by Tsushin for disk/RAM trade-offs), not derived from an Ollama
 * registry call. Runtime-pulled models are reflected in the provider
 * instance's `available_models` field.
 *
 * When adding or removing an entry, both panels pick it up automatically.
 * The wizard-drift guard (backend/tests/test_wizard_drift.py) asserts the
 * two call-sites import from this module rather than redeclaring the list.
 */

export interface OllamaCuratedModel {
  /** Ollama tag, e.g. "llama3.2:3b". Passed to `ollama pull`. */
  id: string
  /** Human-readable label shown in the wizard cards. */
  label: string
  /** Parameter count / family shorthand, e.g. "3B". */
  params: string
  /** Approximate on-disk size, e.g. "2.0 GB". */
  disk: string
  /** One-line editorial blurb. */
  summary: string
}

export const OLLAMA_CURATED_MODELS: OllamaCuratedModel[] = [
  { id: 'llama3.2:1b',    label: 'Llama 3.2 1B',   params: '1B',   disk: '1.3 GB', summary: 'Smallest/fastest — basic tasks' },
  { id: 'llama3.2:3b',    label: 'Llama 3.2 3B',   params: '3B',   disk: '2.0 GB', summary: 'Balanced — general use' },
  { id: 'qwen2.5:3b',     label: 'Qwen 2.5 3B',    params: '3B',   disk: '1.9 GB', summary: 'Multilingual' },
  { id: 'qwen2.5:7b',     label: 'Qwen 2.5 7B',    params: '7B',   disk: '4.7 GB', summary: 'Stronger reasoning' },
  { id: 'deepseek-r1:7b', label: 'DeepSeek R1 7B', params: '7B',   disk: '4.7 GB', summary: 'Reasoning / math' },
  { id: 'phi3.5:3.8b',    label: 'Phi 3.5 3.8B',   params: '3.8B', disk: '2.2 GB', summary: 'Code-focused' },
  { id: 'mistral:7b',     label: 'Mistral 7B',     params: '7B',   disk: '4.1 GB', summary: 'General-purpose' },
]

/** Convenience — just the Ollama tag IDs, in the same order. */
export const OLLAMA_CURATED_MODEL_IDS: string[] = OLLAMA_CURATED_MODELS.map(m => m.id)
