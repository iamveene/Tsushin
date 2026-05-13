'use client'

/**
 * PlaygroundMiniPanel — the visible card that appears when the Mini is open.
 * Composes MiniHeader / MiniMessageList / MiniComposer around the
 * `usePlaygroundMini` hook.
 */

import React, { useEffect, useId, useRef } from 'react'
import MiniHeader from './MiniHeader'
import MiniMessageList from './MiniMessageList'
import MiniComposer, { MiniComposerHandle } from './MiniComposer'
import { UsePlaygroundMiniResult } from './usePlaygroundMini'

interface PlaygroundMiniPanelProps {
  data: UsePlaygroundMiniResult
  onClose: () => void
  panelRef?: React.RefObject<HTMLDivElement>
}

export default function PlaygroundMiniPanel({ data, onClose, panelRef }: PlaygroundMiniPanelProps) {
  const composerRef = useRef<MiniComposerHandle>(null)
  const titleId = useId()

  // Focus the composer when the panel opens
  useEffect(() => {
    composerRef.current?.focus()
  }, [])

  const agent = data.agents.find(a => a.id === data.selectedAgentId) || null
  const agentName = agent?.name || null

  const composerDisabled = !data.selectedAgentId || data.agents.length === 0

  return (
    <div
      ref={panelRef}
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
      className="fixed z-[70] animate-scale-in bg-tsushin-surface border border-tsushin-border rounded-xl shadow-2xl flex flex-col overflow-hidden bottom-24 right-6 w-[380px] h-[min(560px,calc(100vh-8rem))] max-sm:inset-x-4 max-sm:bottom-4 max-sm:top-16 max-sm:w-auto max-sm:h-auto"
    >
      <MiniHeader
        agents={data.agents}
        projects={data.projects}
        threads={data.threads}
        selectedAgentId={data.selectedAgentId}
        selectedProjectId={data.selectedProjectId}
        activeThreadId={data.activeThreadId}
        activeThreadIdRef={data.activeThreadIdRef}
        activeThread={data.activeThread}
        onSelectAgent={data.selectAgent}
        onSelectProject={data.selectProject}
        onSelectThread={id => void data.selectThread(id)}
        onNewThread={() => void data.newThread()}
        onClose={onClose}
        titleId={titleId}
      />

      {data.agents.length === 0 && !data.isLoadingAgents ? (
        <div className="flex-1 flex flex-col items-center justify-center px-6 text-center">
          <p className="text-sm text-gray-200 font-medium">No agents available</p>
          <p className="text-xs text-tsushin-slate mt-1">Create an agent in the Studio first.</p>
        </div>
      ) : (
        <>
          <MiniMessageList
            messages={data.messages}
            isSending={data.isSending}
            isLoadingMessages={data.isLoadingMessages}
            sendError={data.sendError}
            agentName={agentName}
          />
          <MiniComposer
            ref={composerRef}
            disabled={composerDisabled}
            isSending={data.isSending}
            onSend={text => void data.sendMessage(text)}
          />
        </>
      )}
    </div>
  )
}
