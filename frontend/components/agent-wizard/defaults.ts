/**
 * Copy, templates, and compatibility tables used by the Agent Creation Wizard.
 *
 * Text starter prompts are lifted from the legacy create-agent modal
 * (app/agents/page.tsx). Audio/Hybrid starter prompts re-export the same
 * strings as the AudioAgentsWizard (single source of truth in
 * components/audio-wizard/defaults.ts).
 */

import {
  VOICE_AGENT_DEFAULTS,
  TRANSCRIPT_AGENT_DEFAULTS,
} from '@/components/audio-wizard/defaults'
import type { AgentType } from '@/lib/agent-wizard/reducer'

export interface StarterRolePreset {
  label: string
  prompt: string
  keywords: string[]
}

const TEXT_PROMPT_GENERAL = 'You are a helpful AI assistant. Provide clear, concise answers and assist users with their questions. Be friendly, accurate, and practical.'

const TEXT_PRESETS: StarterRolePreset[] = [
  {
    label: 'Customer Support',
    prompt: 'You are a customer support agent. Help users resolve issues, answer questions about products and services, and escalate complex cases when needed. Be empathetic, professional, and solution-oriented.',
    keywords: ['support', 'help', 'issue'],
  },
  {
    label: 'Sales Outreach',
    prompt: 'You are a sales agent. Help qualify leads, answer product questions, and guide prospects through the buying process. Be consultative, professional, and focused on understanding customer needs.',
    keywords: ['sales', 'quote', 'pricing'],
  },
  {
    label: 'Technical Support',
    prompt: 'You are a technical support specialist. Help users troubleshoot technical issues, provide step-by-step solutions, and explain complex concepts in simple terms. Be patient, methodical, and thorough.',
    keywords: ['bug', 'error', 'crash'],
  },
  {
    label: 'Personal Assistant',
    prompt: 'You are a personal assistant. Help organize tasks, answer questions, set reminders, and keep the user productive. Be concise, proactive, and discreet.',
    keywords: ['remind', 'schedule'],
  },
  {
    label: 'General Assistant',
    prompt: TEXT_PROMPT_GENERAL,
    keywords: [],
  },
]

const AUDIO_PRESETS: StarterRolePreset[] = [
  {
    label: 'Voice Assistant',
    prompt: VOICE_AGENT_DEFAULTS.kokoro.system_prompt,
    keywords: ['@voice'],
  },
  {
    label: 'Phone Receptionist',
    prompt: 'You are a voice receptionist. Greet callers warmly, identify their needs, and route them to the right person or information. Keep responses short and natural (2-3 sentences max).',
    keywords: ['reception', 'desk'],
  },
  {
    label: 'Meeting Recap',
    prompt: 'You are a meeting recap assistant. Listen to audio and produce concise summaries, action items, and key decisions. Use bullets and keep wording tight.',
    keywords: ['recap', 'summary'],
  },
  {
    label: 'Narrator',
    prompt: 'You are a narrator. Read content aloud with clear pacing and expressive delivery. Match tone to the material (news, stories, or explanations).',
    keywords: [],
  },
]

const HYBRID_PRESETS: StarterRolePreset[] = [
  {
    label: 'Voice-enabled Support',
    prompt: 'You are a support agent that accepts voice and text. When replying, keep audio responses under 3 sentences; text replies can be longer with structured details.',
    keywords: ['support'],
  },
  {
    label: 'Bilingual Concierge',
    prompt: 'You are a bilingual concierge. Detect the user\'s language (Portuguese or English) and reply in the same. Voice responses: friendly and brief; text responses: complete but efficient.',
    keywords: ['concierge'],
  },
  {
    label: 'Field Dispatcher',
    prompt: 'You are a field operations dispatcher. Take voice updates from technicians, transcribe them accurately, and confirm next steps. Voice replies should be direct and under 2 sentences.',
    keywords: ['dispatch', 'field'],
  },
  {
    label: 'Personal Chief-of-Staff',
    prompt: 'You are a personal chief-of-staff. Handle scheduling, reminders, and briefings via voice or text. Voice replies are conversational and brief; text replies can include structured lists and links.',
    keywords: ['staff', 'chief'],
  },
]

export const STARTER_ROLE_PRESETS: Record<AgentType, StarterRolePreset[]> = {
  text: TEXT_PRESETS,
  audio: AUDIO_PRESETS,
  hybrid: HYBRID_PRESETS,
}

export const DEFAULT_SYSTEM_PROMPT: Record<AgentType, string> = {
  text: TEXT_PROMPT_GENERAL,
  audio: VOICE_AGENT_DEFAULTS.kokoro.system_prompt,
  hybrid: HYBRID_PRESETS[0].prompt,
}

export const DEFAULT_CHANNELS: Record<AgentType, string[]> = {
  text: ['playground'],
  audio: ['playground', 'whatsapp'],
  hybrid: ['playground', 'whatsapp'],
}

export interface BuiltInSkillDef {
  type: string
  label: string
  description: string
  /** Agent types where this skill is applicable. */
  appliesTo: AgentType[]
  /** If true, the skill is auto-enabled and locked for matching types. */
  autoEnabledFor?: AgentType[]
}

// FALLBACK ONLY. The Agent Wizard → Step Skills now fetches its catalog live
// from /api/skills/available (which emits `wizard_visible`, `applies_to`, and
// `auto_enabled_for` per skill). This array is rendered only when that API
// call fails (offline / auth issue). A CI test at
// backend/tests/test_wizard_drift.py asserts this array stays in sync with
// backend SkillManager and with SKILL_DISPLAY_INFO. Provider-based skills
// (flows/gmail) and channel-gated skills (shell) are intentionally omitted —
// they're marked wizard_visible=False on the backend.
export const BUILT_IN_SKILLS: BuiltInSkillDef[] = [
  {
    type: 'web_search',
    label: 'Web Search',
    description: 'Let the agent search the web for up-to-date information.',
    appliesTo: ['text', 'audio', 'hybrid'],
  },
  {
    type: 'agent_switcher',
    label: 'Agent Switcher',
    description: 'Allow seamless handoff between agents mid-conversation.',
    appliesTo: ['text', 'audio', 'hybrid'],
  },
  {
    type: 'image',
    label: 'Image Generation',
    description: 'Generate and edit images with Gemini Nano Banana / Pro.',
    appliesTo: ['text', 'audio', 'hybrid'],
  },
  {
    type: 'image_analysis',
    label: 'Image Analysis',
    description: 'Describe, analyze, or answer questions about an incoming image.',
    appliesTo: ['text', 'audio', 'hybrid'],
  },
  {
    type: 'browser_automation',
    label: 'Browser Automation',
    description: 'Drive a web browser to perform automated web interactions.',
    appliesTo: ['text', 'hybrid'],
  },
  {
    type: 'sandboxed_tools',
    label: 'Sandboxed Tools',
    description: 'Run security / network tools (nmap, dig, nuclei, etc.) in a sandbox.',
    appliesTo: ['text', 'audio', 'hybrid'],
  },
  {
    type: 'automation',
    label: 'Automation',
    description: 'Multi-step workflow automation for complex tasks.',
    appliesTo: ['text', 'hybrid'],
  },
  {
    type: 'flight_search',
    label: 'Flight Search',
    description: 'Look up flights via Amadeus or Google Flights (SerpAPI).',
    appliesTo: ['text', 'audio', 'hybrid'],
  },
  {
    type: 'knowledge_sharing',
    label: 'Knowledge Sharing',
    description: 'Integrate and share knowledge-base content across conversations.',
    appliesTo: ['text', 'audio', 'hybrid'],
  },
  {
    type: 'adaptive_personality',
    label: 'Adaptive Personality',
    description: 'Dynamically adapt the agent tone based on conversation context.',
    appliesTo: ['text', 'audio', 'hybrid'],
  },
  {
    type: 'okg_term_memory',
    label: 'OKG Term Memory',
    description: 'Structured long-term memory with ontological metadata.',
    appliesTo: ['text', 'audio', 'hybrid'],
  },
  {
    type: 'audio_tts',
    label: 'Audio Response (TTS)',
    description: 'Reply with synthesized speech via your TTS provider.',
    appliesTo: ['audio', 'hybrid'],
    autoEnabledFor: ['audio', 'hybrid'],
  },
  {
    type: 'audio_transcript',
    label: 'Audio Transcription',
    description: 'Transcribe incoming voice messages to text.',
    appliesTo: ['audio', 'hybrid'],
    autoEnabledFor: ['audio', 'hybrid'],
  },
]

export const DEFAULT_AGENT_NAME: Record<AgentType, string> = {
  text: 'My Assistant',
  audio: 'Voice Assistant',
  hybrid: 'Hybrid Assistant',
}

export { TRANSCRIPT_AGENT_DEFAULTS, VOICE_AGENT_DEFAULTS }
