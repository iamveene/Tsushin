import {
  CalendarIcon, MailIcon, SearchIcon, MicrophoneIcon, TerminalIcon,
  WrenchIcon, BotIcon, FileTextIcon, RocketIcon, PlugIcon,
  GlobeIcon, BrainIcon, GitHubIcon,
  IconProps,
} from '@/components/ui/icons'

export type SkillCategory = 'communication' | 'search_web' | 'audio_media' | 'automation_tools' | 'intelligence' | 'travel'

export interface SkillDisplayInfo {
  displayName: string
  description: string
  category: SkillCategory
  configType: 'provider' | 'audio' | 'shell' | 'standard'
  icon: React.FC<IconProps>
  /** Skills that are rendered as part of another composite skill (e.g., audio_tts is part of "Audio") */
  compositeParent?: string
  /** Provider key for provider-based skills */
  providerKey?: 'scheduler' | 'email' | 'web_search' | 'ticket_management' | 'code_repository'
}

export const SKILL_CATEGORIES: Record<SkillCategory, { label: string; icon: React.FC<IconProps> }> = {
  communication: { label: 'Communication', icon: MailIcon },
  search_web: { label: 'Search & Web', icon: SearchIcon },
  audio_media: { label: 'Audio & Media', icon: MicrophoneIcon },
  automation_tools: { label: 'Automation & Tools', icon: WrenchIcon },
  intelligence: { label: 'Intelligence', icon: BotIcon },
  travel: { label: 'Travel', icon: GlobeIcon },
}

export const SKILL_DISPLAY_INFO: Record<string, SkillDisplayInfo> = {
  flows: {
    displayName: 'Scheduler',
    description: 'Create events, reminders, and schedule AI conversations. Choose between built-in Flows, Google Calendar, or Asana.',
    category: 'communication',
    configType: 'provider',
    icon: CalendarIcon,
    providerKey: 'scheduler',
  },
  gmail: {
    displayName: 'Email',
    description: 'Read, search, send, reply to, and draft emails. Connect your Gmail account to enable email access.',
    category: 'communication',
    configType: 'provider',
    icon: MailIcon,
    providerKey: 'email',
  },
  web_search: {
    displayName: 'Web Search',
    description: 'Search the web for information. Choose between Brave Search, SearXNG, or Google Search (via SerpAPI).',
    category: 'search_web',
    configType: 'provider',
    icon: SearchIcon,
    providerKey: 'web_search',
  },
  browser_automation: {
    displayName: 'Browser Automation',
    description: 'Control a web browser to perform automated web interactions.',
    category: 'search_web',
    configType: 'standard',
    icon: GlobeIcon,
  },
  audio_tts: {
    displayName: 'Text-to-Speech',
    description: 'Generate spoken audio responses using Kokoro (free) or OpenAI.',
    category: 'audio_media',
    configType: 'audio',
    icon: MicrophoneIcon,
    compositeParent: 'audio',
  },
  audio_transcript: {
    displayName: 'Speech-to-Text',
    description: 'Transcribe audio messages using Whisper.',
    category: 'audio_media',
    configType: 'audio',
    icon: MicrophoneIcon,
    compositeParent: 'audio',
  },
  image: {
    displayName: 'Image Generation',
    description: 'Generate and edit images using Gemini, Imagen, and OpenAI GPT Image models.',
    category: 'audio_media',
    configType: 'standard',
    icon: RocketIcon,
  },
  image_analysis: {
    displayName: 'Image Analysis',
    description: 'Describe, analyze, or answer questions about an incoming image.',
    category: 'audio_media',
    configType: 'standard',
    icon: RocketIcon,
  },
  shell: {
    displayName: 'Shell',
    description: 'Execute remote shell commands on connected beacons. Supports programmatic and agentic modes.',
    category: 'automation_tools',
    configType: 'shell',
    icon: TerminalIcon,
  },
  automation: {
    displayName: 'Automation',
    description: 'Multi-step workflow automation for complex tasks.',
    category: 'automation_tools',
    configType: 'standard',
    icon: RocketIcon,
  },
  sandboxed_tools: {
    displayName: 'Sandboxed Tools',
    description: 'Access sandboxed security and network tools (nmap, dig, nuclei, etc.).',
    category: 'automation_tools',
    configType: 'standard',
    icon: WrenchIcon,
  },
  adaptive_personality: {
    displayName: 'Adaptive Personality',
    description: 'Dynamically adapt the agent personality based on conversation context.',
    category: 'intelligence',
    configType: 'standard',
    icon: BotIcon,
  },
  knowledge_sharing: {
    displayName: 'Knowledge Sharing',
    description: 'Integrate and share knowledge base content across conversations.',
    category: 'intelligence',
    configType: 'standard',
    icon: FileTextIcon,
  },
  agent_switcher: {
    displayName: 'Agent Switcher',
    description: 'Allow users to switch between different agents in direct messages.',
    category: 'intelligence',
    configType: 'standard',
    icon: BotIcon,
  },
  agent_communication: {
    displayName: 'Agent Communication',
    description: 'Ask other agents questions, discover available agents, or delegate tasks.',
    category: 'intelligence',
    configType: 'standard',
    icon: BotIcon,
  },
  okg_term_memory: {
    displayName: 'OKG Term Memory',
    description: 'Structured long-term memory with ontological metadata (subject/relation/type).',
    category: 'intelligence',
    configType: 'standard',
    icon: BrainIcon,
  },
  flight_search: {
    displayName: 'Flight Search',
    description: 'Search for flights using Amadeus or Google Flights via SerpAPI.',
    category: 'travel',
    configType: 'standard',
    icon: GlobeIcon,
  },
  ticket_management: {
    displayName: 'Ticket Management',
    description: 'Search, read, and (when enabled) act on tickets in a connected ticketing system. Today: Atlassian Jira via REST API.',
    category: 'automation_tools',
    configType: 'provider',
    icon: WrenchIcon,
    providerKey: 'ticket_management',
  },
  code_repository: {
    displayName: 'Code Repository',
    description: 'Search repos, list pull requests and issues, read PR details, and (when enabled) open issues or comment on PRs. Today: GitHub via REST API.',
    category: 'automation_tools',
    configType: 'provider',
    icon: GitHubIcon,
    providerKey: 'code_repository',
  },
}

/** Skills that should never be shown (removed from system, or alias for an already-rendered skill).
 * `find_similar_past_cases` is the v0.7.0 Trigger Case Memory MVP skill —
 * it has no UI in the MVP per `.private/TRIGGER_MEMORY_RESEARCH.md` §3.
 * It registers in the backend SkillManager only when TSN_CASE_MEMORY_ENABLED
 * is true and is intentionally not rendered in Studio's skill picker; listing
 * it here keeps the wizard-drift test green regardless of the flag state. */
export const HIDDEN_SKILLS = new Set<string>(['weather', 'web_scraping', 'scheduler', 'find_similar_past_cases'])

/** Skills rendered as a composite group (Audio = TTS + Transcript) */
export const COMPOSITE_SKILLS: Record<string, { displayName: string; skillTypes: string[]; icon: React.FC<IconProps>; description: string }> = {
  audio: {
    displayName: 'Audio',
    skillTypes: ['audio_tts', 'audio_transcript'],
    icon: MicrophoneIcon,
    description: 'Audio processing: Text-to-Speech responses and Speech-to-Text transcription.',
  },
}

/** Provider skill mapping (moved from inline definition) */
export const PROVIDER_SKILLS: Record<string, { displayName: string; skillType: string; providerKey: string }> = {
  scheduler: { displayName: 'Scheduler', skillType: 'flows', providerKey: 'scheduler' },
  email: { displayName: 'Email', skillType: 'gmail', providerKey: 'email' },
  web_search: { displayName: 'Web Search', skillType: 'web_search', providerKey: 'web_search' },
  ticket_management: { displayName: 'Ticket Management', skillType: 'ticket_management', providerKey: 'ticket_management' },
  code_repository: { displayName: 'Code Repository', skillType: 'code_repository', providerKey: 'code_repository' },
}

/** Skills handled by special card renderers (not the generic standard card) */
export const SPECIAL_RENDERED_SKILLS = new Set<string>([
  'flows', 'gmail', 'web_search', 'ticket_management', 'code_repository',  // Provider skills
  'audio_tts', 'audio_transcript', // Composite audio
  'shell',                          // Dedicated shell card
])

/** Get the display info for a skill, with fallbacks from the backend definition */
export function getSkillDisplay(skillType: string, backendName?: string, backendDescription?: string): { displayName: string; description: string; icon: React.FC<IconProps>; category: SkillCategory } {
  const info = SKILL_DISPLAY_INFO[skillType]
  if (info) {
    return {
      displayName: info.displayName,
      description: info.description,
      icon: info.icon,
      category: info.category,
    }
  }
  return {
    displayName: backendName || skillType.replace(/_/g, ' '),
    description: backendDescription || '',
    icon: PlugIcon,
    category: 'automation_tools',
  }
}
