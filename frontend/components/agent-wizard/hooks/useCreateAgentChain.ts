'use client'

import { useCallback, useState } from 'react'
import { api } from '@/lib/client'
import type { Contact } from '@/lib/client'
import { useAgentWizard } from '@/contexts/AgentWizardContext'
import { useKokoroPolling } from './useKokoroPolling'
import type { WizardDraft, AudioConfig } from '@/lib/agent-wizard/reducer'

export type ChainStage =
  | 'idle'
  | 'contact'
  | 'create_agent'
  | 'update_agent'
  | 'skills'
  | 'custom_skills'
  | 'tts_provision'
  | 'tts_wait'
  | 'tts_assign'
  | 'done'

export interface ChainResult {
  agentId: number | null
}

const STAGE_MESSAGES: Record<ChainStage, string> = {
  idle: '',
  contact: 'Resolving contact…',
  create_agent: 'Creating agent…',
  update_agent: 'Applying memory & channel config…',
  skills: 'Attaching built-in skills…',
  custom_skills: 'Attaching custom skills…',
  tts_provision: 'Preparing TTS instance…',
  tts_wait: 'Starting Kokoro container (30–90s)…',
  tts_assign: 'Binding voice to agent…',
  done: 'All set!',
}

async function wireAudioSkills(agentId: number, audio: AudioConfig, ttsInstanceId: number | null) {
  const wantsTTS = audio.capability === 'voice' || audio.capability === 'hybrid'
  const wantsTranscript = audio.capability === 'transcript' || audio.capability === 'hybrid'

  if (wantsTTS) {
    if (audio.provider === 'kokoro' && ttsInstanceId) {
      await api.assignTTSInstanceToAgent(ttsInstanceId, {
        agent_id: agentId,
        voice: audio.voice,
        speed: audio.speed,
        language: audio.language,
        response_format: audio.format,
      })
    } else {
      await api.updateAgentSkill(agentId, 'audio_tts', {
        is_enabled: true,
        config: {
          provider: audio.provider,
          voice: audio.voice,
          language: audio.language,
          speed: audio.speed,
          response_format: audio.format,
        },
      })
    }
  }

  if (wantsTranscript) {
    await api.updateAgentSkill(agentId, 'audio_transcript', {
      is_enabled: true,
      config: {
        response_mode: audio.capability === 'transcript' ? 'transcript_only' : 'conversational',
        language: audio.language,
      },
    })
  }
}

/**
 * Orchestrates the sequential API calls that turn a completed wizard draft
 * into a working agent. Error handling favors keep-agent-on-partial-failure:
 * if the agent row exists, we surface the failing stage and let the user
 * retry rather than cascade-delete.
 */
export function useCreateAgentChain() {
  const wiz = useAgentWizard()
  const { poll: pollKokoro, cancel: cancelKokoroPolling } = useKokoroPolling()
  const [stage, setStage] = useState<ChainStage>('idle')
  const [agentId, setAgentId] = useState<number | null>(null)

  const run = useCallback(async (): Promise<ChainResult> => {
    const draft: WizardDraft = wiz.state.draft
    if (!draft.type) throw new Error('Select an agent type first')

    wiz.setProgress({ status: 'running', failedStep: null, message: STAGE_MESSAGES.contact })
    setStage('contact')

    let contactId = 0

    try {
      // 1. Contact
      const contacts = await api.getContacts()
      const existing = contacts.find(c => c.friendly_name.toLowerCase() === draft.basics.agent_name.toLowerCase())
      if (existing) {
        contactId = existing.id
      } else {
        const phoneDigits = draft.basics.agent_phone.replace(/\s/g, '')
        const created: Contact = await api.createContact({
          friendly_name: draft.basics.agent_name,
          phone_number: phoneDigits || undefined,
          role: 'agent',
          is_active: true,
          notes: `Created via Agent Wizard (${draft.type})`,
        })
        contactId = created.id
      }
    } catch (e: any) {
      wiz.setProgress({ status: 'error', failedStep: 'contact', message: e?.message || 'Failed to create/find contact' })
      return { agentId: null }
    }

    // 2. Create agent (minimal payload the internal API accepts)
    let newAgentId = 0
    try {
      setStage('create_agent')
      wiz.setProgress({ message: STAGE_MESSAGES.create_agent })
      const personality = draft.personality
      const payload: any = {
        contact_id: contactId,
        system_prompt: personality.system_prompt || 'You are a helpful assistant.',
        keywords: [],
        model_provider: draft.basics.model_provider,
        model_name: draft.basics.model_name,
        is_active: true,
        is_default: false,
      }
      if (!personality.skip_persona && personality.persona_id) {
        payload.persona_id = personality.persona_id
      }
      if (personality.custom_tone) {
        payload.custom_tone = personality.custom_tone
      } else if (personality.tone_preset_id) {
        payload.tone_preset_id = personality.tone_preset_id
      }
      const agent = await api.createAgent(payload)
      newAgentId = agent.id
      setAgentId(agent.id)
      wiz.setCreatedAgent(agent.id)
    } catch (e: any) {
      wiz.setProgress({ status: 'error', failedStep: 'create_agent', message: e?.message || 'Failed to create agent' })
      return { agentId: null }
    }

    // From here on, we keep the agent on failure and surface a retry.
    // 3. Update agent with the extended config (memory / channels / vector store / persona_id if set)
    try {
      setStage('update_agent')
      wiz.setProgress({ message: STAGE_MESSAGES.update_agent })
      const update: any = {
        memory_size: draft.memory.memory_size,
        memory_isolation_mode: draft.memory.memory_isolation_mode,
        enable_semantic_search: draft.memory.enable_semantic_search,
        enabled_channels: draft.channels,
      }
      if (!draft.personality.skip_persona && draft.personality.persona_id) {
        update.persona_id = draft.personality.persona_id
      }
      if (draft.memory.mode === 'vector' && draft.memory.vector_store_instance_id) {
        update.vector_store_instance_id = draft.memory.vector_store_instance_id
        update.vector_store_mode = draft.memory.vector_store_mode
      }
      await api.updateAgent(newAgentId, update)
    } catch (e: any) {
      wiz.setProgress({ status: 'error', failedStep: 'update_agent', message: e?.message || 'Agent created, but applying extended config failed.' })
      return { agentId: newAgentId }
    }

    // 4. Built-in skills fan-out
    try {
      setStage('skills')
      wiz.setProgress({ message: STAGE_MESSAGES.skills })
      for (const [skillType, cfg] of Object.entries(draft.skills.builtIns)) {
        if (!cfg.is_enabled) continue
        // Audio skills are handled via the audio chain below (with TTS binding).
        if (skillType === 'audio_tts' || skillType === 'audio_transcript' || skillType === 'audio_response') continue
        await api.updateAgentSkill(newAgentId, skillType, { is_enabled: true, config: cfg.config || {} })
      }
    } catch (e: any) {
      wiz.setProgress({ status: 'error', failedStep: 'skills', message: e?.message || 'Agent created, but attaching a built-in skill failed.' })
      return { agentId: newAgentId }
    }

    // 5. Custom skills
    try {
      setStage('custom_skills')
      wiz.setProgress({ message: STAGE_MESSAGES.custom_skills })
      for (const cid of draft.skills.customIds) {
        await api.assignCustomSkillToAgent(newAgentId, cid)
      }
    } catch (e: any) {
      wiz.setProgress({ status: 'error', failedStep: 'custom_skills', message: e?.message || 'Agent created, but attaching a custom skill failed.' })
      return { agentId: newAgentId }
    }

    // 6. Audio wiring — Kokoro provisioning + skill assignment
    if (draft.audio && (draft.type === 'audio' || draft.type === 'hybrid')) {
      try {
        let ttsInstanceId: number | null = null
        const wantsTTS = draft.audio.capability === 'voice' || draft.audio.capability === 'hybrid'

        if (wantsTTS && draft.audio.provider === 'kokoro') {
          setStage('tts_provision')
          wiz.setProgress({ message: STAGE_MESSAGES.tts_provision })
          const existing = (await api.getTTSInstances().catch(() => [])).find(t => t.vendor === 'kokoro' && t.is_active)
          if (existing) {
            ttsInstanceId = existing.id
          } else {
            const inst = await api.createTTSInstance({
              vendor: 'kokoro',
              instance_name: 'Kokoro TTS',
              auto_provision: draft.audio.autoProvision,
              mem_limit: draft.audio.autoProvision ? draft.audio.memLimit : undefined,
              default_voice: draft.audio.voice,
              default_language: draft.audio.language,
              default_speed: draft.audio.speed,
              default_format: draft.audio.format,
              is_default: draft.audio.setAsDefaultTTS,
            })
            ttsInstanceId = inst.id
            if (draft.audio.setAsDefaultTTS) {
              try { await api.setDefaultTTSInstance(inst.id) } catch { /* non-fatal */ }
            }
            if (draft.audio.autoProvision) {
              setStage('tts_wait')
              wiz.setProgress({ message: STAGE_MESSAGES.tts_wait })
              await new Promise<void>((resolve, reject) => {
                pollKokoro(inst.id, {
                  onReady: resolve,
                  onError: (msg) => reject(new Error(msg)),
                  onProgress: (msg) => wiz.setProgress({ message: msg }),
                })
                setTimeout(() => reject(new Error('Kokoro container did not report ready in time.')), 7 * 60 * 1000)
              })
            }
          }
        }

        setStage('tts_assign')
        wiz.setProgress({ message: STAGE_MESSAGES.tts_assign })
        await wireAudioSkills(newAgentId, draft.audio, ttsInstanceId)
      } catch (e: any) {
        cancelKokoroPolling()
        wiz.setProgress({ status: 'error', failedStep: 'audio', message: e?.message || 'Audio wiring failed.' })
        return { agentId: newAgentId }
      }
    }

    setStage('done')
    wiz.setProgress({ status: 'done', message: STAGE_MESSAGES.done, failedStep: null })
    wiz.fireComplete(newAgentId)
    return { agentId: newAgentId }
  }, [wiz, pollKokoro, cancelKokoroPolling])

  return { run, stage, agentId }
}
