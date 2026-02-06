'use client'

import { useEffect, useState, useCallback } from 'react'
import { api, AgentKnowledge, KnowledgeChunk } from '@/lib/client'
import { formatDate } from '@/lib/dateUtils'
import { UploadIcon, SearchIcon, BookOpenIcon } from '@/components/ui/icons'

interface Props {
  agentId: number
}

export default function AgentKnowledgeManager({ agentId }: Props) {
  const [documents, setDocuments] = useState<AgentKnowledge[]>([])
  const [selectedDoc, setSelectedDoc] = useState<AgentKnowledge | null>(null)
  const [chunks, setChunks] = useState<KnowledgeChunk[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [dragActive, setDragActive] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<KnowledgeChunk[]>([])
  const [searching, setSearching] = useState(false)

  useEffect(() => {
    loadDocuments()
  }, [agentId])

  const loadDocuments = async () => {
    setLoading(true)
    try {
      const docs = await api.getAgentKnowledge(agentId)
      setDocuments(docs)
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

    // Validate file size (10 MB max)
    if (file.size > 10 * 1024 * 1024) {
      alert('File too large. Maximum size is 10 MB.')
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

  if (loading) {
    return <div className="p-8 text-center">Loading knowledge base...</div>
  }

  return (
    <div className="space-y-6">
      {/* Upload Section */}
      <div
        className={`border-2 border-dashed rounded-lg p-8 text-center ${
          dragActive ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20' : 'border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900'
        }`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <div className="mb-4"><UploadIcon size={40} className="mx-auto text-gray-400" /></div>
        <h3 className="text-lg font-semibold mb-2">Upload Knowledge Documents</h3>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
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
          className="px-6 py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 cursor-pointer inline-block"
        >
          {uploading ? 'Uploading...' : 'Browse Files'}
        </label>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-3">
          Supported: TXT, CSV, JSON, PDF, DOCX | Max size: 10 MB per file
        </p>
      </div>

      {/* Knowledge Search Tester */}
      <div className="border dark:border-gray-700 rounded-lg p-4 bg-purple-50 dark:bg-purple-900/20">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><SearchIcon size={20} /> Test Knowledge Search</h3>
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && searchKnowledge()}
            placeholder="Enter search query..."
            className="flex-1 px-4 py-2 border dark:border-gray-700 rounded-md"
          />
          <button
            onClick={searchKnowledge}
            disabled={searching || !searchQuery.trim()}
            className="px-6 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50"
          >
            {searching ? 'Searching...' : 'Search'}
          </button>
        </div>

        {searchResults.length > 0 && (
          <div className="space-y-2">
            <h4 className="font-medium text-sm">Search Results:</h4>
            {searchResults.map((result, i) => (
              <div key={i} className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded p-3">
                <div className="text-sm mb-1">
                  <span className="font-medium text-purple-600">Chunk {result.chunk_id}</span>
                  {result.metadata.source && (
                    <span className="text-gray-500 dark:text-gray-400 ml-2">from {result.metadata.source}</span>
                  )}
                </div>
                <p className="text-sm text-gray-700 dark:text-gray-300">{result.content}</p>
              </div>
            ))}
          </div>
        )}

        {searchQuery && searchResults.length === 0 && !searching && (
          <p className="text-sm text-gray-500 dark:text-gray-400">No results found for "{searchQuery}"</p>
        )}
      </div>

      {/* Documents List */}
      <div className="border dark:border-gray-700 rounded-lg overflow-hidden">
        <div className="bg-gray-100 dark:bg-gray-800 px-4 py-3 border-b">
          <h3 className="text-lg font-semibold flex items-center gap-2"><BookOpenIcon size={20} /> Knowledge Base Documents</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 dark:bg-gray-900 border-b">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-600 dark:text-gray-400">Document Name</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-600 dark:text-gray-400">Type</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-600 dark:text-gray-400">Size</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-600 dark:text-gray-400">Chunks</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-600 dark:text-gray-400">Status</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-600 dark:text-gray-400">Uploaded</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-gray-600 dark:text-gray-400">Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                    No documents uploaded yet. Upload documents to build agent's knowledge base.
                  </td>
                </tr>
              ) : (
                documents.map((doc) => (
                  <tr key={doc.id} className="border-b hover:bg-gray-50 dark:hover:bg-gray-700 dark:bg-gray-900">
                    <td className="px-4 py-3 font-medium">{doc.document_name}</td>
                    <td className="px-4 py-3 text-sm">
                      <span className="px-2 py-1 bg-gray-100 dark:bg-gray-800 rounded text-xs font-mono">
                        {doc.document_type.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm">{formatBytes(doc.file_size_bytes)}</td>
                    <td className="px-4 py-3 text-sm">{doc.num_chunks || '-'}</td>
                    <td className="px-4 py-3">{getStatusBadge(doc.status)}</td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                      {formatDate(doc.upload_date)}
                    </td>
                    <td className="px-4 py-3 text-right space-x-2">
                      {doc.status === 'completed' && (
                        <button
                          onClick={() => viewDocument(doc)}
                          className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
                        >
                          View
                        </button>
                      )}
                      <button
                        onClick={() => deleteDocument(doc.id)}
                        className="px-3 py-1 bg-red-600 text-white text-sm rounded hover:bg-red-700"
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
          <div className="bg-white dark:bg-gray-800 rounded-lg max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col">
            <div className="bg-gray-100 dark:bg-gray-800 px-6 py-4 border-b flex justify-between items-center">
              <div>
                <h3 className="text-lg font-semibold">{selectedDoc.document_name}</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  {formatBytes(selectedDoc.file_size_bytes)} • {selectedDoc.num_chunks} chunks
                </p>
              </div>
              <button
                onClick={() => setSelectedDoc(null)}
                className="text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 dark:text-gray-200"
              >
                ✕
              </button>
            </div>

            <div className="overflow-y-auto p-6 space-y-4 flex-1">
              {chunks.length === 0 ? (
                <p className="text-center text-gray-500 dark:text-gray-400">Loading chunks...</p>
              ) : (
                chunks.map((chunk, i) => (
                  <div key={i} className="border dark:border-gray-700 rounded p-4 bg-gray-50 dark:bg-gray-900">
                    <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                      Chunk {chunk.chunk_index} • {chunk.char_count} chars
                      {chunk.metadata_json?.page && ` • Page ${chunk.metadata_json.page}`}
                    </div>
                    <p className="text-sm whitespace-pre-wrap">{chunk.content}</p>
                  </div>
                ))
              )}
            </div>

            <div className="bg-gray-100 dark:bg-gray-800 px-6 py-4 border-t">
              <button
                onClick={() => setSelectedDoc(null)}
                className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
