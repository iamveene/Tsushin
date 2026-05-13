export const DEEPSEEK_DEFAULT_BASE_URL = 'https://api.deepseek.com'

export const DEEPSEEK_V4_FLASH_MODEL = 'deepseek-v4-flash'
export const DEEPSEEK_V4_PRO_MODEL = 'deepseek-v4-pro'
export const DEEPSEEK_LEGACY_MODEL_ALIASES = ['deepseek-chat', 'deepseek-reasoner'] as const

export type ProviderModelOption = { value: string; label: string }

export const PROVIDER_MODEL_CATALOG: Record<string, ProviderModelOption[]> = {
  gemini: [
    { value: 'gemini-3-flash-preview', label: 'Gemini 3 Flash (Preview)' },
    { value: 'gemini-3.1-flash-lite-preview', label: 'Gemini 3.1 Flash Lite (Preview)' },
    { value: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
    { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
    { value: 'gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash Lite' },
    { value: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash' },
    { value: 'gemini-1.5-pro', label: 'Gemini 1.5 Pro' },
    { value: 'gemini-1.5-flash', label: 'Gemini 1.5 Flash' },
  ],
  openai: [
    { value: 'gpt-5.5', label: 'GPT-5.5' },
    { value: 'gpt-5.5-pro', label: 'GPT-5.5 Pro' },
    { value: 'gpt-5.4', label: 'GPT-5.4' },
    { value: 'gpt-5.4-pro', label: 'GPT-5.4 Pro' },
    { value: 'gpt-5.4-mini', label: 'GPT-5.4 Mini' },
    { value: 'gpt-5.4-nano', label: 'GPT-5.4 Nano' },
    { value: 'o4-mini', label: 'o4 Mini' },
    { value: 'gpt-4.1', label: 'GPT-4.1' },
    { value: 'gpt-4.1-mini', label: 'GPT-4.1 Mini' },
    { value: 'gpt-4o', label: 'GPT-4o' },
    { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
  ],
  anthropic: [
    { value: 'claude-opus-4-7', label: 'Claude Opus 4.7' },
    { value: 'claude-opus-4-7-latest', label: 'Claude Opus 4.7 (Latest)' },
    { value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6' },
    { value: 'claude-opus-4-6', label: 'Claude Opus 4.6' },
    { value: 'claude-haiku-4-5', label: 'Claude Haiku 4.5' },
    { value: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4' },
    { value: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet' },
  ],
  groq: [
    { value: 'openai/gpt-oss-120b', label: 'GPT OSS 120B (Groq)' },
    { value: 'openai/gpt-oss-20b', label: 'GPT OSS 20B (Groq)' },
    { value: 'llama-3.3-70b-versatile', label: 'Llama 3.3 70B Versatile' },
    { value: 'llama-3.1-8b-instant', label: 'Llama 3.1 8B Instant' },
  ],
  grok: [
    { value: 'grok-4.3', label: 'Grok 4.3' },
    { value: 'grok-4.3-latest', label: 'Grok 4.3 (Latest)' },
    { value: 'grok-4.20-multi-agent-0309', label: 'Grok 4.20 Multi-Agent' },
    { value: 'grok-4.20-0309-reasoning', label: 'Grok 4.20 Reasoning' },
    { value: 'grok-4.20-0309-non-reasoning', label: 'Grok 4.20 Non-Reasoning' },
    { value: 'grok-4-1-fast-reasoning', label: 'Grok 4.1 Fast Reasoning' },
    { value: 'grok-4-1-fast-non-reasoning', label: 'Grok 4.1 Fast Non-Reasoning' },
    { value: 'grok-3-mini', label: 'Grok 3 Mini' },
    { value: 'grok-3', label: 'Grok 3' },
  ],
  openrouter: [
    { value: 'openai/gpt-5.5', label: 'GPT-5.5 (OpenRouter)' },
    { value: 'openai/gpt-5.5-pro', label: 'GPT-5.5 Pro (OpenRouter)' },
    { value: 'anthropic/claude-opus-4.7', label: 'Claude Opus 4.7 (OpenRouter)' },
    { value: 'x-ai/grok-4.3', label: 'Grok 4.3 (OpenRouter)' },
    { value: 'x-ai/grok-4.3-latest', label: 'Grok 4.3 Latest (OpenRouter)' },
    { value: 'x-ai/grok-4.20-multi-agent-0309', label: 'Grok 4.20 Multi-Agent (OpenRouter)' },
    { value: 'google/gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
    { value: 'meta-llama/llama-3.1-8b-instruct:free', label: 'Llama 3.1 8B (Free)' },
    { value: 'deepseek/deepseek-r1', label: 'DeepSeek R1' },
  ],
  deepseek: [
    { value: DEEPSEEK_V4_FLASH_MODEL, label: 'DeepSeek V4 Flash' },
    { value: DEEPSEEK_V4_PRO_MODEL, label: 'DeepSeek V4 Pro' },
    { value: 'deepseek-chat', label: 'DeepSeek Chat (legacy alias)' },
    { value: 'deepseek-reasoner', label: 'DeepSeek Reasoner (legacy alias)' },
  ],
  vertex_ai: [
    { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash (Vertex)' },
    { value: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro (Vertex)' },
    { value: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash (Vertex)' },
    { value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6 (Vertex)' },
    { value: 'claude-haiku-4-5-latest', label: 'Claude Haiku 4.5 (Vertex)' },
  ],
}

export const DEEPSEEK_MODEL_OPTIONS = PROVIDER_MODEL_CATALOG.deepseek

export const PROVIDER_DEFAULT_MODELS: Record<string, string> = {
  gemini: 'gemini-2.5-flash',
  openai: 'gpt-5.5',
  anthropic: 'claude-opus-4-7',
  groq: 'openai/gpt-oss-120b',
  grok: 'grok-4.3',
  deepseek: DEEPSEEK_V4_FLASH_MODEL,
  openrouter: 'openai/gpt-5.5',
  ollama: 'llama3.2:latest',
}

export const SENTINEL_DEFAULT_MODELS: Record<string, string> = {
  gemini: 'gemini-2.5-flash-lite',
  openai: 'gpt-5.5',
  anthropic: 'claude-opus-4-7',
  groq: 'openai/gpt-oss-20b',
  grok: 'grok-4.3',
  deepseek: DEEPSEEK_V4_FLASH_MODEL,
  openrouter: 'openai/gpt-5.5',
}

const PROVIDER_MODEL_LABELS = new Map<string, string>(
  Object.values(PROVIDER_MODEL_CATALOG)
    .flat()
    .map(model => [model.value, model.label])
)

const PROVIDER_MODEL_ORDER: Record<string, string[]> = Object.fromEntries(
  Object.entries(PROVIDER_MODEL_CATALOG).map(([vendor, options]) => [
    vendor,
    options.map(model => model.value),
  ])
)

const DEEPSEEK_LEGACY_MODEL_SET = new Set<string>(DEEPSEEK_LEGACY_MODEL_ALIASES)

export const DEEPSEEK_MODEL_IDS = PROVIDER_MODEL_ORDER.deepseek || []

export function normalizeVendor(vendor?: string | null): string {
  return vendor?.trim().toLowerCase() || ''
}

export function isDeepSeekVendor(vendor?: string | null): boolean {
  return normalizeVendor(vendor) === 'deepseek'
}

function appendUnique(target: string[], seen: Set<string>, model?: string | null) {
  const normalized = model?.trim()
  if (!normalized || seen.has(normalized)) return
  seen.add(normalized)
  target.push(normalized)
}

export function getProviderFallbackModels(vendor: string | null | undefined): string[] {
  return [...(PROVIDER_MODEL_ORDER[normalizeVendor(vendor)] || [])]
}

export function getProviderModelOptions(
  vendor: string | null | undefined,
  models: Array<string | null | undefined> = [],
  options?: { currentModel?: string | null; includeFallbacks?: boolean }
): string[] {
  const vendorKey = normalizeVendor(vendor)
  const includeFallbacks = options?.includeFallbacks !== false
  const normalizedModels = models
    .map(model => model?.trim())
    .filter((model): model is string => !!model)

  if (options?.currentModel?.trim()) {
    normalizedModels.push(options.currentModel.trim())
  }

  const seen = new Set<string>()
  const ordered: string[] = []

  if (includeFallbacks) {
    getProviderFallbackModels(vendorKey).forEach(model => appendUnique(ordered, seen, model))
  }

  const modelSource = isDeepSeekVendor(vendorKey)
    ? normalizedModels.filter(model => !DEEPSEEK_LEGACY_MODEL_SET.has(model))
    : normalizedModels

  modelSource.forEach(model => appendUnique(ordered, seen, model))

  if (!includeFallbacks && isDeepSeekVendor(vendorKey)) {
    DEEPSEEK_MODEL_IDS.forEach(model => appendUnique(ordered, seen, model))
  }

  return ordered
}

export function getPreferredProviderModel(
  vendor: string | null | undefined,
  models: Array<string | null | undefined> = [],
  currentModel?: string | null,
  options?: { sentinel?: boolean }
): string {
  const vendorKey = normalizeVendor(vendor)
  const preferredDefault = options?.sentinel
    ? SENTINEL_DEFAULT_MODELS[vendorKey]
    : PROVIDER_DEFAULT_MODELS[vendorKey]
  const modelOptions = getProviderModelOptions(vendorKey, models, {
    currentModel,
  })

  if (currentModel && modelOptions.includes(currentModel)) return currentModel
  if (preferredDefault && modelOptions.includes(preferredDefault)) return preferredDefault

  return preferredDefault || modelOptions[0] || ''
}

export function getProviderModelLabels(
  vendor: string | null | undefined,
  models: Array<string | null | undefined> = [],
  options?: { currentModel?: string | null; includeFallbacks?: boolean }
): ProviderModelOption[] {
  return getProviderModelOptions(vendor, models, options).map(model => ({
    value: model,
    label: PROVIDER_MODEL_LABELS.get(model) || model,
  }))
}

export function modelLabelFor(model: string): string {
  return PROVIDER_MODEL_LABELS.get(model) || model
}
