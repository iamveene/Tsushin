'use client'

import { useEffect, useState, useCallback } from 'react'
import {
  api,
  AgentKnowledge,
  AgentKnowledgeConfig,
  EmbeddingOptionsResponse,
  KnowledgeChunk,
  KnowledgeSearchResult,
  VectorStoreInstance,
} from '@/lib/client'
import { formatDate } from '@/lib/dateUtils'
import { UploadIcon, SearchIcon, BookOpenIcon } from '@/components/ui/icons'

interface Props {
  agentId: number
}

const MAX_DOCUMENT_TAGS = 12
const MAX_DOCUMENT_TAG_LENGTH = 48

function parseKnowledgeTags(input: string): string[] {
  return input
    .split(/[,\n]/)
    .map((tag) => tag.trim().toLowerCase().replace(/\s+/g, ' '))
    .filter(Boolean)
}

export default function AgentKnowledgeManager({ agentId }: Props) {
  const [documents, setDocuments] = useState<AgentKnowledge[]>([])
  const [selectedDoc, setSelectedDoc] = useState<AgentKnowledge | null>(null)
  const [chunks, setChunks] = useState<KnowledgeChunk[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [dragActive, setDragActive] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<KnowledgeSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [editingDoc, setEditingDoc] = useState<AgentKnowledge | null>(null)
  const [editDocumentName, setEditDocumentName] = useState('')
  const [editTagsText, setEditTagsText] = useState('')
  const [savingEdit, setSavingEdit] = useState(false)
  const [config, setConfig] = useState<AgentKnowledgeConfig | null>(null)
  const [draftConfig, setDraftConfig] = useState<AgentKnowledgeConfig | null>(null)
  const [embeddingOptions, setEmbeddingOptions] = useState<EmbeddingOptionsResponse | null>(null)
  const [vectorStores, setVectorStores] = useState<VectorStoreInstance[]>([])
  const [savingConfig, setSavingConfig] = useState(false)
  const [testingEmbedding, setTestingEmbedding] = useState(false)
  const [embeddingTestMessage, setEmbeddingTestMessage] = useState<string | null>(null)
  const [reprocessingIds, setReprocessingIds] = useState<Set<number>>(new Set())

  const normalizedEditTags = parseKnowledgeTags(editTagsText)
  const uniqueEditTags = Array.from(new Set(normalizedEditTags))
  const overlongTag = uniqueEditTags.find((tag) => tag.length > MAX_DOCUMENT_TAG_LENGTH)
  const tagValidationError =
    uniqueEditTags.length > MAX_DOCUMENT_TAGS
      ? `Use up to ${MAX_DOCUMENT_TAGS} tags per document.`
      : overlongTag
        ? `Each tag must be ${MAX_DOCUMENT_TAG_LENGTH} characters or fewer.`
        : null

  useEffect(() => {
    loadDocuments()
  }, [agentId])

  const loadDocuments = async () => {
    setLoading(true)
    try {
      const [docs, kbConfig, options, stores] = await Promise.all([
        api.getAgentKnowledge(agentId),
        api.getAgentKnowledgeConfig(agentId),
        api.getAgentKnowledgeEmbeddingOptions(agentId),
        api.getVectorStoreInstances(),
      ])
      setDocuments(docs)
      setConfig(kbConfig)
      setDraftConfig(kbConfig)
      setEmbeddingOptions(options)
      setVectorStores(stores)
    } catch (err) {
      console.error('Failed to load documents:', err)
      // Set empty array if API not yet implemented
      setDocuments([])
    } finally {
      setLoading(false)
    }
  }

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return

    const file = files[0]

    // Validate file type - match backend allowed extensions
    const validTypes = [
      'text/plain',                    // .txt
      'text/csv',                      // .csv
      'application/json',              // .json
      'application/pdf',               // .pdf
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document' // .docx
    ]

    // Also check by file extension since MIME types can vary
    const fileName = file.name.toLowerCase()
    const validExtensions = ['.txt', '.csv', '.json', '.pdf', '.docx']
    const hasValidExtension = validExtensions.some(ext => fileName.endsWith(ext))

    if (!validTypes.includes(file.type) && !hasValidExtension) {
      alert('Invalid file type. Please upload TXT, CSV, JSON, PDF, or DOCX files.')
      return
    }

    // Validate file size (50 MB max, matching backend)
    if (file.size > 50 * 1024 * 1024) {
      alert('File too large. Maximum size is 50 MB.')
      return
    }

    setUploading(true)
    try {
      await api.uploadKnowledgeDocument(agentId, file)
      alert('Document uploaded successfully! Processing will begin shortly.')
      loadDocuments()
    } catch (err) {
      console.error('Failed to upload document:', err)
      alert('Failed to upload document (backend not yet implemented)')
    } finally {
      setUploading(false)
    }
  }

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    handleUpload(e.dataTransfer.files)
  }, [])

  const viewDocument = async (doc: AgentKnowledge) => {
    setSelectedDoc(doc)
    try {
      const docChunks = await api.getKnowledgeChunks(agentId, doc.id)
      setChunks(docChunks)
    } catch (err) {
      console.error('Failed to load chunks:', err)
      alert('Failed to load document chunks (backend not yet implemented)')
      setChunks([])
    }
  }

  const startEditDocument = (doc: AgentKnowledge) => {
    setEditingDoc(doc)
    setEditDocumentName(doc.document_name)
    setEditTagsText((doc.tags || []).join(', '))
  }

  const closeEditDocument = () => {
    setEditingDoc(null)
    setEditDocumentName('')
    setEditTagsText('')
    setSavingEdit(false)
  }

  const saveDocumentMetadata = async () => {
    if (!editingDoc) return

    const documentName = editDocumentName.trim()
    if (!documentName) {
      alert('Document name is required.')
      return
    }

    if (tagValidationError) {
      alert(tagValidationError)
      return
    }

    const tags = uniqueEditTags

    setSavingEdit(true)
    try {
      const updated = await api.updateKnowledgeDocument(agentId, editingDoc.id, {
        document_name: documentName,
        tags,
      })
      setDocuments((prev) => prev.map((doc) => (doc.id === updated.id ? updated : doc)))
      setSelectedDoc((prev) => (prev && prev.id === updated.id ? updated : prev))
      closeEditDocument()
    } catch (err) {
      console.error('Failed to update document metadata:', err)
      alert(err instanceof Error ? err.message : 'Failed to update document details')
      setSavingEdit(false)
    }
  }

  const deleteDocument = async (docId: number) => {
    if (!confirm('Delete this document?\n\nThis will remove all chunks from the knowledge base.')) {
      return
    }

    try {
      await api.deleteKnowledgeDocument(agentId, docId)
      alert('Document deleted successfully')
      setSelectedDoc(null)
      loadDocuments()
    } catch (err) {
      console.error('Failed to delete document:', err)
      alert('Failed to delete document (backend not yet implemented)')
    }
  }

  const searchKnowledge = async () => {
    if (!searchQuery.trim()) return

    setSearching(true)
    try {
      const results = await api.searchAgentKnowledge(agentId, searchQuery, 5)
      setSearchResults(results)
    } catch (err) {
      console.error('Failed to search knowledge:', err)
      alert('Failed to search knowledge (backend not yet implemented)')
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i]
  }

  const getStatusBadge = (status: string) => {
    const badges: Record<string, { bg: string; text: string; label: string }> = {
      pending: { bg: 'bg-yellow-100 dark:bg-yellow-800/30', text: 'text-yellow-800 dark:text-yellow-200', label: 'Pending' },
      processing: { bg: 'bg-blue-100 dark:bg-blue-800/30', text: 'text-blue-800 dark:text-blue-200', label: 'Processing...' },
      completed: { bg: 'bg-green-100 dark:bg-green-800/30', text: 'text-green-800 dark:text-green-200', label: 'Completed' },
      failed: { bg: 'bg-red-100 dark:bg-red-800/30', text: 'text-red-800', label: 'Failed' },
    }
    const badge = badges[status] || badges.pending
    return (
      <span className={`px-2 py-1 rounded text-xs font-medium ${badge.bg} ${badge.text}`}>
        {badge.label}
      </span>
    )
  }

  const renderTags = (tags?: string[]) => {
    if (!tags || tags.length === 0) {
      return <span className="text-xs text-tsushin-muted">No tags</span>
    }

    return (
      <div className="flex flex-wrap gap-1">
        {tags.map((tag) => (
          <span
            key={tag}
            className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-teal-500/10 text-teal-300 border border-teal-500/20"
          >
            {tag}
          </span>
        ))}
      </div>
    )
  }

  const selectedProviderOption = embeddingOptions?.providers.find((option) => (
    option.provider === draftConfig?.embedding_provider
    && (option.provider_instance_id ?? null) === (draftConfig?.embedding_provider_instance_id ?? null)
  )) || embeddingOptions?.providers.find((option) => option.provider === draftConfig?.embedding_provider)

  const selectedModelOption = selectedProviderOption?.models.find(
    (model) => model.model === draftConfig?.embedding_model,
  ) || selectedProviderOption?.models[0]

  const updateDraftConfig = (patch: Partial<AgentKnowledgeConfig>) => {
    setDraftConfig((prev) => (prev ? { ...prev, ...patch } : prev))
    setEmbeddingTestMessage(null)
  }

  const handleProviderSelection = (value: string) => {
    if (!draftConfig || !embeddingOptions) return
    const option = embeddingOptions.providers.find((candidate) => `${candidate.provider}:${candidate.provider_instance_id ?? 'local'}` === value)
    if (!option) return
    const model = option.models[0]
    const detectedDimsRequired = option.provider === 'ollama' && !model?.default_dimensions && !option.default_dimensions
    updateDraftConfig({
      embedding_provider: option.provider,
      embedding_provider_instance_id: option.provider_instance_id,
      embedding_model: model?.model || option.default_model || '',
      embedding_dims: detectedDimsRequired ? 0 : Number(model?.default_dimensions || option.default_dimensions || draftConfig.embedding_dims),
    })
  }

  const handleModelSelection = (modelName: string) => {
    if (!draftConfig || !selectedProviderOption) return
    const model = selectedProviderOption.models.find((candidate) => candidate.model === modelName)
    const detectedDimsRequired = selectedProviderOption.provider === 'ollama' && !model?.default_dimensions
    updateDraftConfig({
      embedding_model: modelName,
      embedding_dims: detectedDimsRequired ? 0 : Number(model?.default_dimensions || draftConfig.embedding_dims),
    })
  }

  const saveKnowledgeConfig = async () => {
    if (!draftConfig) return
    setSavingConfig(true)
    try {
      const saved = await api.updateAgentKnowledgeConfig(agentId, {
        embedding_provider_instance_id: draftConfig.embedding_provider_instance_id,
        embedding_provider: draftConfig.embedding_provider,
        embedding_model: draftConfig.embedding_model,
        embedding_dims: draftConfig.embedding_dims,
        embedding_metric: draftConfig.embedding_metric,
        vector_store_instance_id: draftConfig.vector_store_instance_id,
        chunk_strategy: draftConfig.chunk_strategy,
        chunk_size: draftConfig.chunk_size,
        chunk_overlap: draftConfig.chunk_overlap,
        parser: draftConfig.parser,
        search_top_k: draftConfig.search_top_k,
        similarity_threshold: draftConfig.similarity_threshold,
      })
      setConfig(saved)
      setDraftConfig(saved)
      setEmbeddingTestMessage('Saved KB indexing settings.')
      await loadDocuments()
    } catch (err) {
      console.error('Failed to save KB config:', err)
      alert(err instanceof Error ? err.message : 'Failed to save KB settings')
    } finally {
      setSavingConfig(false)
    }
  }

  const testEmbeddingConfig = async () => {
    if (!draftConfig) return
    setTestingEmbedding(true)
    setEmbeddingTestMessage(null)
    try {
      const result = await api.testEmbeddingProvider({
        provider: draftConfig.embedding_provider,
        provider_instance_id: draftConfig.embedding_provider_instance_id,
        model: draftConfig.embedding_model,
        dimensions: draftConfig.embedding_dims > 0 ? draftConfig.embedding_dims : null,
        text: 'Knowledge base embedding smoke test',
      })
      if (result.success) {
        const dims = result.actual_dimensions || result.requested_dimensions
        setEmbeddingTestMessage(`Embedding test passed: ${dims} dimensions, batch ${result.batch_count}, ${result.latency_ms} ms.`)
        if (dims && dims !== draftConfig.embedding_dims) {
          updateDraftConfig({ embedding_dims: dims })
        }
      } else {
        setEmbeddingTestMessage(result.error || 'Embedding test failed.')
      }
    } catch (err) {
      console.error('Failed to test embedding config:', err)
      setEmbeddingTestMessage(err instanceof Error ? err.message : 'Embedding test failed.')
    } finally {
      setTestingEmbedding(false)
    }
  }

  const reprocessDocument = async (doc: AgentKnowledge) => {
    if (!confirm(`Reprocess ${doc.document_name} with the current KB settings?`)) {
      return
    }
    setReprocessingIds((prev) => new Set(prev).add(doc.id))
    try {
      await api.reprocessKnowledgeDocument(agentId, doc.id)
      await loadDocuments()
    } catch (err) {
      console.error('Failed to reprocess document:', err)
      alert(err instanceof Error ? err.message : 'Failed to reprocess document')
    } finally {
      setReprocessingIds((prev) => {
        const next = new Set(prev)
        next.delete(doc.id)
        return next
      })
    }
  }

  const documentContract = (doc: AgentKnowledge) => {
    const vectorStore = doc.vector_store_instance_id
      ? vectorStores.find((store) => store.id === doc.vector_store_instance_id)?.instance_name || `Store ${doc.vector_store_instance_id}`
      : 'Built-in Chroma'
    return `${doc.embedding_provider || 'local'} / ${doc.embedding_model || 'all-MiniLM-L6-v2'} / ${doc.embedding_dims || 384}d / ${vectorStore}`
  }

  if (loading) {
    return <div className="p-8 text-center">Loading knowledge base...</div>
  }

  return (
    <div className="space-y-6">
      {draftConfig && embeddingOptions && (
        <div className="border border-tsushin-border rounded-lg p-4 bg-tsushin-surface">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between mb-4">
            <div>
              <h3 className="text-lg font-semibold">Index Settings</h3>
              <p className="text-sm text-tsushin-slate">
                Current contract: {draftConfig.embedding_provider} / {draftConfig.embedding_model} / {draftConfig.embedding_dims}d
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={testEmbeddingConfig}
                disabled={testingEmbedding || !draftConfig.embedding_model}
                className="px-4 py-2 rounded-md bg-tsushin-elevated hover:bg-tsushin-border text-white disabled:opacity-50"
              >
                {testingEmbedding ? 'Testing...' : 'Test Embedding'}
              </button>
              <button
                type="button"
                onClick={saveKnowledgeConfig}
                disabled={savingConfig || draftConfig.embedding_dims <= 0}
                className="btn-primary px-4 py-2 rounded-md disabled:opacity-50"
              >
                {savingConfig ? 'Saving...' : 'Save Settings'}
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            <div>
              <label className="block text-sm font-medium mb-2">Embedding Provider</label>
              <select
                value={`${draftConfig.embedding_provider}:${draftConfig.embedding_provider_instance_id ?? 'local'}`}
                onChange={(event) => handleProviderSelection(event.target.value)}
                className="w-full px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-ink text-white"
              >
                {embeddingOptions.providers.map((option) => (
                  <option
                    key={`${option.provider}:${option.provider_instance_id ?? 'local'}`}
                    value={`${option.provider}:${option.provider_instance_id ?? 'local'}`}
                  >
                    {option.instance_name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Embedding Model</label>
              <select
                value={draftConfig.embedding_model}
                onChange={(event) => handleModelSelection(event.target.value)}
                className="w-full px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-ink text-white"
              >
                {(selectedProviderOption?.models || []).map((model) => (
                  <option key={model.model} value={model.model}>
                    {model.label || model.model}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Dimensions</label>
              {selectedModelOption?.supported_dimensions?.length ? (
                <select
                  value={draftConfig.embedding_dims}
                  onChange={(event) => updateDraftConfig({ embedding_dims: Number(event.target.value) })}
                  className="w-full px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-ink text-white"
                >
                  {selectedModelOption.supported_dimensions.map((dims) => (
                    <option key={dims} value={dims}>{dims}</option>
                  ))}
                </select>
              ) : (
                <input
                  type="number"
                  min={1}
                  value={draftConfig.embedding_dims || ''}
                  onChange={(event) => updateDraftConfig({ embedding_dims: Number(event.target.value) })}
                  className="w-full px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-ink text-white"
                />
              )}
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Vector Storage</label>
              <select
                value={draftConfig.vector_store_instance_id ?? ''}
                onChange={(event) => updateDraftConfig({
                  vector_store_instance_id: event.target.value ? Number(event.target.value) : null,
                })}
                className="w-full px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-ink text-white"
              >
                <option value="">Built-in Chroma</option>
                {vectorStores.map((store) => (
                  <option key={store.id} value={store.id}>
                    {store.instance_name} ({store.vendor})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Chunking</label>
              <select
                value={draftConfig.chunk_strategy}
                onChange={(event) => updateDraftConfig({ chunk_strategy: event.target.value })}
                className="w-full px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-ink text-white"
              >
                <option value="fixed_text">Fixed text</option>
                <option value="json_structure">JSON structure</option>
                <option value="csv_rows">CSV rows</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Chunk Size</label>
              <input
                type="number"
                min={200}
                max={8000}
                value={draftConfig.chunk_size}
                onChange={(event) => updateDraftConfig({ chunk_size: Number(event.target.value) })}
                className="w-full px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-ink text-white"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Overlap</label>
              <input
                type="number"
                min={0}
                max={Math.max(0, draftConfig.chunk_size - 1)}
                value={draftConfig.chunk_overlap}
                onChange={(event) => updateDraftConfig({ chunk_overlap: Number(event.target.value) })}
                className="w-full px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-ink text-white"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Parser</label>
              <select
                value={draftConfig.parser}
                onChange={(event) => updateDraftConfig({ parser: event.target.value })}
                className="w-full px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-ink text-white"
              >
                <option value="auto">Auto</option>
                <option value="txt">TXT</option>
                <option value="csv">CSV</option>
                <option value="json">JSON</option>
                <option value="pdf">PDF</option>
                <option value="docx">DOCX</option>
              </select>
            </div>
          </div>

          {embeddingTestMessage && (
            <p className="text-sm text-tsushin-slate mt-4">{embeddingTestMessage}</p>
          )}
          {config && (
            <p className="text-xs text-tsushin-muted mt-3">
              Saved contract: {config.embedding_provider} / {config.embedding_model} / {config.embedding_dims}d. Existing documents keep their own snapshots until reprocessed.
            </p>
          )}
        </div>
      )}

      {/* Upload Section */}
      <div
        className={`border-2 border-dashed rounded-lg p-8 text-center ${
          dragActive ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20' : 'border-tsushin-border bg-tsushin-ink'
        }`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <div className="mb-4"><UploadIcon size={40} className="mx-auto text-gray-400" /></div>
        <h3 className="text-lg font-semibold mb-2">Upload Knowledge Documents</h3>
        <p className="text-sm text-tsushin-slate mb-4">
          Drag & drop files here or click to browse
        </p>
        <input
          type="file"
          id="file-upload"
          className="hidden"
          accept=".pdf,.txt,.csv,.json,.docx"
          onChange={(e) => handleUpload(e.target.files)}
          disabled={uploading}
        />
        <label
          htmlFor="file-upload"
          className="btn-primary px-6 py-3 rounded-md cursor-pointer inline-block"
        >
          {uploading ? 'Uploading...' : 'Browse Files'}
        </label>
        <p className="text-xs text-tsushin-muted mt-3">
          Supported: TXT, CSV, JSON, PDF, DOCX | Max size: 50 MB per file
        </p>
      </div>

      {/* Knowledge Search Tester */}
      <div className="border border-tsushin-border rounded-lg p-4 bg-purple-50 dark:bg-purple-900/20">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><SearchIcon size={20} /> Test Knowledge Search</h3>
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && searchKnowledge()}
            placeholder="Enter search query..."
            className="flex-1 px-4 py-2 border border-tsushin-border rounded-md"
          />
          <button
            onClick={searchKnowledge}
            disabled={searching || !searchQuery.trim()}
            className="btn-primary px-6 py-2 rounded-md disabled:opacity-50"
          >
            {searching ? 'Searching...' : 'Search'}
          </button>
        </div>

        {searchResults.length > 0 && (
          <div className="space-y-2">
            <h4 className="font-medium text-sm">Search Results:</h4>
            {searchResults.map((result, i) => (
              <div key={i} className="bg-tsushin-surface border border-tsushin-border rounded p-3">
                <div className="text-sm mb-1">
                  <span className="font-medium text-purple-600">Chunk {result.chunk_id}</span>
                  <span className="text-tsushin-muted ml-2">
                    from {result.document_name} · {(result.similarity * 100).toFixed(1)}%
                  </span>
                </div>
                <p className="text-sm text-tsushin-fog">{result.content}</p>
              </div>
            ))}
          </div>
        )}

        {searchQuery && searchResults.length === 0 && !searching && (
          <p className="text-sm text-tsushin-muted">No results found for "{searchQuery}"</p>
        )}
      </div>

      {/* Documents List */}
      <div className="border border-tsushin-border rounded-lg overflow-hidden">
        <div className="bg-tsushin-elevated px-4 py-3 border-b">
          <h3 className="text-lg font-semibold flex items-center gap-2"><BookOpenIcon size={20} /> Knowledge Base Documents</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-tsushin-ink border-b">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-medium text-tsushin-slate">Document Name</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-tsushin-slate">Type</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-tsushin-slate">Tags</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-tsushin-slate">Size</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-tsushin-slate">Chunks</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-tsushin-slate">Status</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-tsushin-slate">Embedding</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-tsushin-slate">Uploaded</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-tsushin-slate">Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-tsushin-muted">
                    No documents uploaded yet. Upload documents to build agent's knowledge base.
                  </td>
                </tr>
              ) : (
                documents.map((doc) => (
                  <tr key={doc.id} className="border-b hover:bg-tsushin-surface bg-tsushin-ink">
                    <td className="px-4 py-3 font-medium">{doc.document_name}</td>
                    <td className="px-4 py-3 text-sm">
                      <span className="px-2 py-1 bg-tsushin-elevated rounded text-xs font-mono">
                        {doc.document_type.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm">
                      {renderTags(doc.tags)}
                    </td>
                    <td className="px-4 py-3 text-sm">{formatBytes(doc.file_size_bytes)}</td>
                    <td className="px-4 py-3 text-sm">{doc.num_chunks || '-'}</td>
                    <td className="px-4 py-3">{getStatusBadge(doc.status)}</td>
                    <td className="px-4 py-3 text-xs text-tsushin-slate max-w-xs">
                      {documentContract(doc)}
                    </td>
                    <td className="px-4 py-3 text-sm text-tsushin-slate">
                      {formatDate(doc.upload_date)}
                    </td>
                    <td className="px-4 py-3 text-right space-x-2">
                      {doc.status === 'completed' && (
                        <button
                          onClick={() => viewDocument(doc)}
                          className="btn-primary px-3 py-1 text-sm rounded"
                        >
                          View
                        </button>
                      )}
                      <button
                        onClick={() => startEditDocument(doc)}
                        className="px-3 py-1 text-sm rounded bg-tsushin-elevated hover:bg-tsushin-border text-white"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => reprocessDocument(doc)}
                        disabled={reprocessingIds.has(doc.id)}
                        className="px-3 py-1 text-sm rounded bg-tsushin-elevated hover:bg-tsushin-border text-white disabled:opacity-50"
                      >
                        {reprocessingIds.has(doc.id) ? 'Queued' : 'Reprocess'}
                      </button>
                      <button
                        onClick={() => deleteDocument(doc.id)}
                        className="btn-danger px-3 py-1 text-sm rounded"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Document Detail Modal */}
      {selectedDoc && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-tsushin-surface rounded-lg max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col">
            <div className="bg-tsushin-elevated px-6 py-4 border-b flex justify-between items-center">
              <div>
                <h3 className="text-lg font-semibold">{selectedDoc.document_name}</h3>
                <p className="text-sm text-tsushin-slate">
                  {formatBytes(selectedDoc.file_size_bytes)} • {selectedDoc.num_chunks} chunks
                </p>
                <p className="text-xs text-tsushin-muted mt-1">
                  {documentContract(selectedDoc)}
                </p>
                <div className="mt-2">
                  {renderTags(selectedDoc.tags)}
                </div>
              </div>
              <button
                onClick={() => setSelectedDoc(null)}
                className="text-tsushin-slate hover:text-white"
              >
                ✕
              </button>
            </div>

            <div className="overflow-y-auto p-6 space-y-4 flex-1">
              {chunks.length === 0 ? (
                <p className="text-center text-tsushin-muted">Loading chunks...</p>
              ) : (
                chunks.map((chunk, i) => (
                  <div key={i} className="border border-tsushin-border rounded p-4 bg-tsushin-ink">
                    <div className="text-xs text-tsushin-muted mb-2">
                      Chunk {chunk.chunk_index} • {chunk.char_count} chars
                      {chunk.metadata_json?.page && ` • Page ${chunk.metadata_json.page}`}
                    </div>
                    <p className="text-sm whitespace-pre-wrap">{chunk.content}</p>
                  </div>
                ))
              )}
            </div>

            <div className="bg-tsushin-elevated px-6 py-4 border-t">
              <button
                onClick={() => setSelectedDoc(null)}
                className="px-4 py-2 bg-tsushin-elevated text-white rounded-md hover:bg-tsushin-surface"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {editingDoc && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-tsushin-surface rounded-lg max-w-xl w-full overflow-hidden">
            <div className="bg-tsushin-elevated px-6 py-4 border-b flex justify-between items-center">
              <div>
                <h3 className="text-lg font-semibold">Edit Document</h3>
                <p className="text-sm text-tsushin-slate">{editingDoc.document_name}</p>
              </div>
              <button
                onClick={closeEditDocument}
                className="text-tsushin-slate hover:text-white"
                disabled={savingEdit}
              >
                ✕
              </button>
            </div>

            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Document Name</label>
                <input
                  type="text"
                  value={editDocumentName}
                  onChange={(e) => setEditDocumentName(e.target.value)}
                  maxLength={255}
                  className="w-full px-4 py-2 border border-tsushin-border rounded-md bg-tsushin-ink text-white"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Tags</label>
                <textarea
                  value={editTagsText}
                  onChange={(e) => setEditTagsText(e.target.value)}
                  rows={3}
                  placeholder="billing, faq, onboarding"
                  className="w-full px-4 py-2 border border-tsushin-border rounded-md bg-tsushin-ink text-white"
                />
                <p className="text-xs text-tsushin-muted mt-2">
                  Separate tags with commas or line breaks. Up to {MAX_DOCUMENT_TAGS} tags, {MAX_DOCUMENT_TAG_LENGTH} characters each. Tags are normalized to lowercase and deduplicated before save.
                </p>
                <p className="text-xs text-tsushin-muted mt-1">
                  {uniqueEditTags.length}/{MAX_DOCUMENT_TAGS} tags
                </p>
                {tagValidationError && (
                  <p className="text-xs text-red-400 mt-2">{tagValidationError}</p>
                )}
              </div>
            </div>

            <div className="bg-tsushin-elevated px-6 py-4 border-t flex justify-end gap-3">
              <button
                onClick={closeEditDocument}
                className="px-4 py-2 bg-tsushin-ink text-white rounded-md hover:bg-tsushin-surface"
                disabled={savingEdit}
              >
                Cancel
              </button>
              <button
                onClick={saveDocumentMetadata}
                className="btn-primary px-4 py-2 rounded-md disabled:opacity-50"
                disabled={savingEdit || !!tagValidationError}
              >
                {savingEdit ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
