'use client'

import { useMemo } from 'react'
import type {
  EmbeddingOptionsResponse,
  EmbeddingProviderOption,
  VectorStoreIndex,
  VectorStoreInstance,
} from '@/lib/client'

export interface EmbeddingContractValue {
  embedding_provider_instance_id?: number | null
  embedding_provider?: string | null
  embedding_model?: string | null
  embedding_dims?: number | null
  embedding_metric?: string | null
  vector_store_instance_id?: number | null
  vector_store_index_id?: number | null
  vector_collection_name?: string | null
  vector_namespace?: string | null
}

interface EmbeddingContractControlsProps {
  value: EmbeddingContractValue
  onChange: (patch: Partial<EmbeddingContractValue>) => void
  embeddingOptions?: EmbeddingOptionsResponse | null
  vectorStores?: VectorStoreInstance[]
  disabled?: boolean
  includeVectorStore?: boolean
  includeMetric?: boolean
  includeVectorIndex?: boolean
  includeVectorDetails?: boolean
  allowBuiltInVectorStore?: boolean
  className?: string
  gridClassName?: string
  labelClassName?: string
  fieldClassName?: string
  helperClassName?: string
}

const DEFAULT_PROVIDER = 'local'
const DEFAULT_MODEL = 'all-MiniLM-L6-v2'
const DEFAULT_DIMS = 384
const DEFAULT_METRIC = 'cosine'

const DEFAULT_LABEL_CLASS = 'block text-sm font-medium mb-2'
const DEFAULT_FIELD_CLASS = 'w-full px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-ink text-white'
const DEFAULT_HELPER_CLASS = 'text-xs text-tsushin-muted mt-1'

function providerKey(provider: string | null | undefined, instanceId: number | null | undefined): string {
  return `${provider || DEFAULT_PROVIDER}:${instanceId ?? 'local'}`
}

function numberOrNull(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function stringOrNull(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function toIndex(raw: Record<string, any>, store: VectorStoreInstance, fallbackId: number): VectorStoreIndex {
  return {
    id: numberOrNull(raw.id) ?? fallbackId,
    tenant_id: raw.tenant_id ?? store.tenant_id,
    vector_store_instance_id: numberOrNull(raw.vector_store_instance_id) ?? store.id,
    owner_type: stringOrNull(raw.owner_type),
    owner_id: numberOrNull(raw.owner_id),
    index_name: stringOrNull(raw.index_name ?? raw.physical_index_name ?? raw.name),
    collection_name: stringOrNull(raw.collection_name ?? raw.physical_collection_name ?? raw.collection),
    namespace: stringOrNull(raw.namespace ?? raw.physical_namespace),
    physical_collection_name: stringOrNull(raw.physical_collection_name ?? raw.collection_name ?? raw.collection),
    physical_namespace: stringOrNull(raw.physical_namespace ?? raw.namespace),
    physical_index_name: stringOrNull(raw.physical_index_name ?? raw.index_name ?? raw.name),
    purpose: stringOrNull(raw.purpose ?? raw.index_type ?? raw.kind),
    embedding_provider_instance_id: numberOrNull(raw.embedding_provider_instance_id),
    embedding_provider: stringOrNull(raw.embedding_provider),
    embedding_model: stringOrNull(raw.embedding_model),
    embedding_dims: numberOrNull(raw.embedding_dims ?? raw.dimensions),
    embedding_metric: stringOrNull(raw.embedding_metric ?? raw.metric),
    embedding_task: stringOrNull(raw.embedding_task),
    embedding_task_document: stringOrNull(raw.embedding_task_document),
    embedding_task_query: stringOrNull(raw.embedding_task_query),
    contract_hash: stringOrNull(raw.contract_hash),
    vector_count: numberOrNull(raw.vector_count),
    document_count: numberOrNull(raw.document_count),
    chunk_count: numberOrNull(raw.chunk_count),
    health_status: stringOrNull(raw.health_status ?? raw.status),
    is_default: Boolean(raw.is_default ?? raw.default),
    is_active: raw.is_active !== false,
    created_at: stringOrNull(raw.created_at),
    updated_at: stringOrNull(raw.updated_at),
  }
}

export function getVectorStoreIndexes(store: VectorStoreInstance | null | undefined): VectorStoreIndex[] {
  if (!store) return []

  const direct = Array.isArray(store.indexes) ? store.indexes : []
  if (direct.length > 0) {
    return direct.map((item, index) => toIndex(item as unknown as Record<string, any>, store, -(index + 1)))
  }

  const extra = store.extra_config || {}
  const rawIndexes = Array.isArray(extra.indexes)
    ? extra.indexes
    : Array.isArray(extra.vector_indexes)
      ? extra.vector_indexes
      : []

  if (rawIndexes.length > 0) {
    return rawIndexes
      .filter((item): item is Record<string, any> => item && typeof item === 'object')
      .map((item, index) => toIndex(item, store, -(index + 1)))
  }

  const hasLegacyIndex = Boolean(
    extra.index_name
    || extra.collection_name
    || extra.namespace
    || extra.embedding_provider
    || extra.embedding_model
    || extra.embedding_dims
  )
  if (!hasLegacyIndex) return []

  return [
    toIndex(
      {
        id: store.default_vector_store_index_id ?? store.long_term_memory_index_id ?? -1,
        index_name: extra.index_name,
        collection_name: extra.collection_name,
        namespace: extra.namespace,
        purpose: 'case_memory',
        embedding_provider_instance_id: extra.embedding_provider_instance_id,
        embedding_provider: extra.embedding_provider,
        embedding_model: extra.embedding_model,
        embedding_dims: extra.embedding_dims,
        embedding_metric: extra.embedding_metric ?? extra.metric,
        is_default: true,
      },
      store,
      -1,
    ),
  ]
}

export function getDefaultVectorStoreIndex(store: VectorStoreInstance | null | undefined): VectorStoreIndex | null {
  const indexes = getVectorStoreIndexes(store)
  if (!store || indexes.length === 0) return null

  const desiredId = store.long_term_memory_index_id ?? store.default_vector_store_index_id
  return indexes.find((index) => desiredId != null && index.id === desiredId)
    || indexes.find((index) => index.is_default && (index.purpose || '').includes('memory'))
    || indexes.find((index) => index.is_default)
    || indexes[0]
}

export function formatVectorStoreIndex(index: VectorStoreIndex): string {
  const location = index.index_name
    || index.physical_index_name
    || index.collection_name
    || index.physical_collection_name
    || index.namespace
    || index.physical_namespace
    || `Index ${index.id}`
  const provider = index.embedding_provider || DEFAULT_PROVIDER
  const model = index.embedding_model || DEFAULT_MODEL
  const dims = index.embedding_dims || DEFAULT_DIMS
  return `${location} - ${provider} / ${model} / ${dims}d`
}

function patchFromIndex(index: VectorStoreIndex): Partial<EmbeddingContractValue> {
  return {
    vector_store_index_id: index.id > 0 ? index.id : null,
    vector_collection_name: index.collection_name ?? index.physical_collection_name ?? null,
    vector_namespace: index.namespace ?? index.physical_namespace ?? null,
    embedding_provider_instance_id: index.embedding_provider_instance_id ?? null,
    embedding_provider: index.embedding_provider || DEFAULT_PROVIDER,
    embedding_model: index.embedding_model || DEFAULT_MODEL,
    embedding_dims: index.embedding_dims || DEFAULT_DIMS,
    embedding_metric: index.embedding_metric || DEFAULT_METRIC,
  }
}

export default function EmbeddingContractControls({
  value,
  onChange,
  embeddingOptions,
  vectorStores = [],
  disabled = false,
  includeVectorStore = false,
  includeMetric = true,
  includeVectorIndex = true,
  includeVectorDetails = false,
  allowBuiltInVectorStore = true,
  className = '',
  gridClassName = 'grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4',
  labelClassName = DEFAULT_LABEL_CLASS,
  fieldClassName = DEFAULT_FIELD_CLASS,
  helperClassName = DEFAULT_HELPER_CLASS,
}: EmbeddingContractControlsProps) {
  const selectedProviderOption = useMemo<EmbeddingProviderOption | undefined>(() => {
    return embeddingOptions?.providers.find((option) => (
      option.provider === (value.embedding_provider || DEFAULT_PROVIDER)
      && (option.provider_instance_id ?? null) === (value.embedding_provider_instance_id ?? null)
    )) || embeddingOptions?.providers.find((option) => option.provider === (value.embedding_provider || DEFAULT_PROVIDER))
  }, [embeddingOptions, value.embedding_provider, value.embedding_provider_instance_id])
  const selectedProviderKey = selectedProviderOption
    ? providerKey(selectedProviderOption.provider, selectedProviderOption.provider_instance_id)
    : providerKey(value.embedding_provider, value.embedding_provider_instance_id)

  const selectedModelOption = selectedProviderOption?.models.find(
    (model) => model.model === (value.embedding_model || DEFAULT_MODEL),
  ) || selectedProviderOption?.models[0]

  const selectedVectorStore = vectorStores.find((store) => store.id === value.vector_store_instance_id) || null
  const selectedVectorStoreIndexes = getVectorStoreIndexes(selectedVectorStore)
  const selectedIndex = selectedVectorStoreIndexes.find((index) => (
    value.vector_store_index_id != null && index.id === value.vector_store_index_id
  )) || getDefaultVectorStoreIndex(selectedVectorStore)
  const selectedIndexKey = selectedIndex?.id.toString() || ''

  const handleProviderSelection = (nextValue: string) => {
    const option = embeddingOptions?.providers.find((candidate) => (
      providerKey(candidate.provider, candidate.provider_instance_id) === nextValue
    ))
    if (!option) return

    const model = option.models[0]
    const detectedDimsRequired = option.provider === 'ollama' && !model?.default_dimensions && !option.default_dimensions
    onChange({
      embedding_provider: option.provider,
      embedding_provider_instance_id: option.provider_instance_id,
      embedding_model: model?.model || option.default_model || DEFAULT_MODEL,
      embedding_dims: detectedDimsRequired ? 0 : Number(model?.default_dimensions || option.default_dimensions || value.embedding_dims || DEFAULT_DIMS),
    })
  }

  const handleModelSelection = (modelName: string) => {
    const model = selectedProviderOption?.models.find((candidate) => candidate.model === modelName)
    const detectedDimsRequired = selectedProviderOption?.provider === 'ollama' && !model?.default_dimensions
    onChange({
      embedding_model: modelName,
      embedding_dims: detectedDimsRequired ? 0 : Number(model?.default_dimensions || value.embedding_dims || DEFAULT_DIMS),
    })
  }

  const handleVectorStoreSelection = (nextValue: string) => {
    const storeId = nextValue ? Number(nextValue) : null
    const store = vectorStores.find((candidate) => candidate.id === storeId) || null
    const defaultIndex = getDefaultVectorStoreIndex(store)
    onChange({
      vector_store_instance_id: storeId,
      vector_store_index_id: null,
      vector_collection_name: null,
      vector_namespace: null,
      ...(defaultIndex ? patchFromIndex(defaultIndex) : {}),
    })
  }

  return (
    <div className={className}>
      <div className={gridClassName}>
        <div>
          <label className={labelClassName}>Embedding Provider</label>
          <select
            value={selectedProviderKey}
            onChange={(event) => handleProviderSelection(event.target.value)}
            disabled={disabled || !embeddingOptions?.providers.length}
            className={fieldClassName}
          >
            {embeddingOptions?.providers.length ? (
              embeddingOptions.providers.map((option) => (
                <option
                  key={providerKey(option.provider, option.provider_instance_id)}
                  value={providerKey(option.provider, option.provider_instance_id)}
                >
                  {option.instance_name}
                </option>
              ))
            ) : (
              <option value={selectedProviderKey}>
                {value.embedding_provider || DEFAULT_PROVIDER}
              </option>
            )}
          </select>
        </div>

        <div>
          <label className={labelClassName}>Embedding Model</label>
          {selectedProviderOption?.models.length ? (
            <select
              value={value.embedding_model || DEFAULT_MODEL}
              onChange={(event) => handleModelSelection(event.target.value)}
              disabled={disabled}
              className={fieldClassName}
            >
              {selectedProviderOption.models.map((model) => (
                <option key={model.model} value={model.model}>
                  {model.label || model.model}
                </option>
              ))}
            </select>
          ) : (
            <input
              type="text"
              value={value.embedding_model || DEFAULT_MODEL}
              onChange={(event) => onChange({ embedding_model: event.target.value })}
              disabled={disabled}
              className={fieldClassName}
            />
          )}
        </div>

        <div>
          <label className={labelClassName}>Dimensions</label>
          {selectedModelOption?.supported_dimensions?.length ? (
            <select
              value={value.embedding_dims || DEFAULT_DIMS}
              onChange={(event) => onChange({ embedding_dims: Number(event.target.value) })}
              disabled={disabled}
              className={fieldClassName}
            >
              {selectedModelOption.supported_dimensions.map((dims) => (
                <option key={dims} value={dims}>{dims}</option>
              ))}
            </select>
          ) : (
            <input
              type="number"
              min={1}
              value={value.embedding_dims || ''}
              onChange={(event) => onChange({ embedding_dims: Number(event.target.value) })}
              disabled={disabled}
              className={fieldClassName}
            />
          )}
        </div>

        {includeMetric && (
          <div>
            <label className={labelClassName}>Metric</label>
            <select
              value={value.embedding_metric || DEFAULT_METRIC}
              onChange={(event) => onChange({ embedding_metric: event.target.value })}
              disabled={disabled}
              className={fieldClassName}
            >
              <option value="cosine">Cosine</option>
              <option value="dotproduct">Dot product</option>
              <option value="euclidean">Euclidean</option>
            </select>
          </div>
        )}

        {includeVectorStore && (
          <div>
            <label className={labelClassName}>Vector Store</label>
            <select
              value={value.vector_store_instance_id ?? ''}
              onChange={(event) => handleVectorStoreSelection(event.target.value)}
              disabled={disabled}
              className={fieldClassName}
            >
              {allowBuiltInVectorStore && <option value="">Built-in Chroma</option>}
              {vectorStores.map((store) => (
                <option key={store.id} value={store.id}>
                  {store.instance_name} ({store.vendor})
                </option>
              ))}
            </select>
          </div>
        )}

        {includeVectorStore && includeVectorIndex && selectedVectorStore && selectedVectorStoreIndexes.length > 0 && (
          <div>
            <label className={labelClassName}>Vector Index</label>
            <select
              value={selectedIndexKey}
              onChange={(event) => {
                const index = selectedVectorStoreIndexes.find((candidate) => candidate.id.toString() === event.target.value)
                if (index) onChange(patchFromIndex(index))
              }}
              disabled={disabled}
              className={fieldClassName}
            >
              {selectedVectorStoreIndexes.map((index) => (
                <option key={index.id} value={index.id}>
                  {formatVectorStoreIndex(index)}
                </option>
              ))}
            </select>
            <p className={helperClassName}>Selecting an index pins its immutable embedding contract.</p>
          </div>
        )}

        {includeVectorDetails && (
          <>
            <div>
              <label className={labelClassName}>Collection</label>
              <input
                type="text"
                value={value.vector_collection_name || ''}
                onChange={(event) => onChange({ vector_collection_name: event.target.value || null })}
                disabled={disabled}
                className={fieldClassName}
              />
            </div>
            <div>
              <label className={labelClassName}>Namespace</label>
              <input
                type="text"
                value={value.vector_namespace || ''}
                onChange={(event) => onChange({ vector_namespace: event.target.value || null })}
                disabled={disabled}
                className={fieldClassName}
              />
            </div>
          </>
        )}
      </div>
    </div>
  )
}
