'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { api, PlaygroundSettings, EmbeddingModel } from '@/lib/client'

interface PlaygroundSettingsModalProps {
  isOpen: boolean
  onClose: () => void
  onSettingsChange?: (settings: PlaygroundSettings) => void
}

export default function PlaygroundSettingsModal({
  isOpen,
  onClose,
  onSettingsChange
}: PlaygroundSettingsModalProps) {
  const [settings, setSettings] = useState<PlaygroundSettings>({
    documentProcessing: {
      embeddingModel: 'all-MiniLM-L6-v2',
      chunkSize: 500,
      chunkOverlap: 50,
      maxDocuments: 10
    },
    audioSettings: {
      ttsProvider: 'kokoro',
      ttsVoice: 'pf_dora',
      autoPlayResponses: false
    }
  })
  const [embeddingModels, setEmbeddingModels] = useState<EmbeddingModel[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Load settings and embedding models
  useEffect(() => {
    if (isOpen) {
      loadData()
    }
  }, [isOpen])

  const loadData = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const [settingsData, modelsData] = await Promise.all([
        api.getPlaygroundSettings(),
        api.getAvailableEmbeddingModels()
      ])

      setSettings({
        documentProcessing: settingsData.documentProcessing || settings.documentProcessing,
        audioSettings: settingsData.audioSettings || settings.audioSettings
      })
      setEmbeddingModels(modelsData.models || [])
    } catch (err: any) {
      setError(err.message || 'Failed to load settings')
    } finally {
      setIsLoading(false)
    }
  }

  const handleSave = useCallback(async () => {
    setIsSaving(true)
    setError(null)
    setSuccessMessage(null)

    try {
      const updated = await api.updatePlaygroundSettings(settings)
      setSuccessMessage('Settings saved successfully')
      onSettingsChange?.(updated)

      setTimeout(() => {
        setSuccessMessage(null)
      }, 2000)
    } catch (err: any) {
      setError(err.message || 'Failed to save settings')
    } finally {
      setIsSaving(false)
    }
  }, [settings, onSettingsChange])

  const updateDocumentProcessing = (key: string, value: any) => {
    setSettings(prev => ({
      ...prev,
      documentProcessing: {
        ...prev.documentProcessing!,
        [key]: value
      }
    }))
  }

  const updateAudioSettings = (key: string, value: any) => {
    setSettings(prev => ({
      ...prev,
      audioSettings: {
        ...prev.audioSettings!,
        [key]: value
      }
    }))
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="glass-card w-full max-w-lg max-h-[80vh] overflow-hidden rounded-2xl shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-tsushin-border">
          <h2 className="text-lg font-semibold text-tsushin-pearl flex items-center gap-2">
            <svg className="w-5 h-5 text-tsushin-indigo" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            Playground Settings
          </h2>
          <button
            onClick={onClose}
            className="p-2 text-tsushin-slate hover:text-tsushin-pearl hover:bg-tsushin-surface rounded-lg transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-4 overflow-y-auto max-h-[60vh]">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="w-8 h-8 border-2 border-tsushin-teal/30 border-t-tsushin-teal rounded-full animate-spin"></div>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Document Processing Settings */}
              <div>
                <h3 className="text-sm font-semibold text-tsushin-pearl mb-3 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-tsushin-teal rounded-full"></span>
                  Document Processing
                </h3>
                <div className="space-y-4">
                  {/* Embedding Model */}
                  <div>
                    <label className="block text-xs text-tsushin-slate mb-1.5">
                      Embedding Model
                    </label>
                    <select
                      value={settings.documentProcessing?.embeddingModel || 'all-MiniLM-L6-v2'}
                      onChange={(e) => updateDocumentProcessing('embeddingModel', e.target.value)}
                      className="input w-full text-sm"
                    >
                      {embeddingModels.map((model) => (
                        <option key={model.id} value={model.id}>
                          {model.name} - {model.description}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Chunk Size */}
                  <div>
                    <label className="block text-xs text-tsushin-slate mb-1.5">
                      Chunk Size (characters): {settings.documentProcessing?.chunkSize || 500}
                    </label>
                    <input
                      type="range"
                      min="200"
                      max="2000"
                      step="100"
                      value={settings.documentProcessing?.chunkSize || 500}
                      onChange={(e) => updateDocumentProcessing('chunkSize', parseInt(e.target.value))}
                      className="w-full accent-tsushin-teal"
                    />
                    <div className="flex justify-between text-2xs text-tsushin-muted mt-1">
                      <span>200</span>
                      <span>2000</span>
                    </div>
                  </div>

                  {/* Chunk Overlap */}
                  <div>
                    <label className="block text-xs text-tsushin-slate mb-1.5">
                      Chunk Overlap: {settings.documentProcessing?.chunkOverlap || 50}
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="200"
                      step="10"
                      value={settings.documentProcessing?.chunkOverlap || 50}
                      onChange={(e) => updateDocumentProcessing('chunkOverlap', parseInt(e.target.value))}
                      className="w-full accent-tsushin-teal"
                    />
                    <div className="flex justify-between text-2xs text-tsushin-muted mt-1">
                      <span>0</span>
                      <span>200</span>
                    </div>
                  </div>

                  {/* Max Documents */}
                  <div>
                    <label className="block text-xs text-tsushin-slate mb-1.5">
                      Max Documents per Conversation: {settings.documentProcessing?.maxDocuments || 10}
                    </label>
                    <input
                      type="range"
                      min="1"
                      max="20"
                      step="1"
                      value={settings.documentProcessing?.maxDocuments || 10}
                      onChange={(e) => updateDocumentProcessing('maxDocuments', parseInt(e.target.value))}
                      className="w-full accent-tsushin-teal"
                    />
                    <div className="flex justify-between text-2xs text-tsushin-muted mt-1">
                      <span>1</span>
                      <span>20</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Audio Settings */}
              <div>
                <h3 className="text-sm font-semibold text-tsushin-pearl mb-3 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-tsushin-indigo rounded-full"></span>
                  Audio Settings
                </h3>
                <div className="space-y-4">
                  {/* TTS Provider */}
                  <div>
                    <label className="block text-xs text-tsushin-slate mb-1.5">
                      TTS Provider
                    </label>
                    <select
                      value={settings.audioSettings?.ttsProvider || 'kokoro'}
                      onChange={(e) => updateAudioSettings('ttsProvider', e.target.value)}
                      className="input w-full text-sm"
                    >
                      <option value="kokoro">Kokoro TTS (Free)</option>
                      <option value="openai">OpenAI TTS</option>
                      <option value="elevenlabs">ElevenLabs (Coming Soon)</option>
                    </select>
                  </div>

                  {/* TTS Voice */}
                  <div>
                    <label className="block text-xs text-tsushin-slate mb-1.5">
                      Default Voice
                    </label>
                    <select
                      value={settings.audioSettings?.ttsVoice || 'pf_dora'}
                      onChange={(e) => updateAudioSettings('ttsVoice', e.target.value)}
                      className="input w-full text-sm"
                    >
                      {settings.audioSettings?.ttsProvider === 'openai' ? (
                        <>
                          <option value="alloy">Alloy</option>
                          <option value="echo">Echo</option>
                          <option value="fable">Fable</option>
                          <option value="onyx">Onyx</option>
                          <option value="nova">Nova</option>
                          <option value="shimmer">Shimmer</option>
                        </>
                      ) : (
                        <>
                          <option value="pf_dora">Dora (Female)</option>
                          <option value="pm_alex">Alex (Male)</option>
                          <option value="pm_santa">Santa (Male)</option>
                          <option value="bf_emma">Emma (Female, British)</option>
                          <option value="bm_george">George (Male, British)</option>
                        </>
                      )}
                    </select>
                  </div>

                  {/* Auto-play Responses */}
                  <div className="flex items-center justify-between">
                    <label className="text-xs text-tsushin-slate">
                      Auto-play Audio Responses
                    </label>
                    <button
                      onClick={() => updateAudioSettings('autoPlayResponses', !settings.audioSettings?.autoPlayResponses)}
                      className={`
                        relative w-11 h-6 rounded-full transition-colors
                        ${settings.audioSettings?.autoPlayResponses
                          ? 'bg-tsushin-teal'
                          : 'bg-tsushin-surface border border-tsushin-border'
                        }
                      `}
                    >
                      <span className={`
                        absolute top-1 w-4 h-4 rounded-full transition-transform
                        ${settings.audioSettings?.autoPlayResponses
                          ? 'translate-x-6 bg-white'
                          : 'translate-x-1 bg-tsushin-slate'
                        }
                      `} />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div className="mt-4 p-3 bg-tsushin-vermilion/10 border border-tsushin-vermilion/20 rounded-lg">
              <p className="text-sm text-tsushin-vermilion">{error}</p>
            </div>
          )}

          {/* Success Message */}
          {successMessage && (
            <div className="mt-4 p-3 bg-green-500/10 border border-green-500/20 rounded-lg">
              <p className="text-sm text-green-400">{successMessage}</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-tsushin-border flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-tsushin-slate hover:text-tsushin-pearl hover:bg-tsushin-surface rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving || isLoading}
            className="px-4 py-2 text-sm btn-primary rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? (
              <span className="flex items-center gap-2">
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                Saving...
              </span>
            ) : (
              'Save Settings'
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
