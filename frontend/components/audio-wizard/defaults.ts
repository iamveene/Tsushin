/**
 * Default configs used by the Audio Agents wizard when creating a new
 * voice / transcript / hybrid agent. Values here are the same short-response
 * system prompts that used to be shipped with the seeded Kira / Kokoro /
 * Transcript agents (removed from agent_seeding.py), preserved as templates
 * so users opting in get sensible defaults.
 */

export type AudioProvider = 'kokoro' | 'openai' | 'elevenlabs' | 'gemini'
export type AudioAgentType = 'voice' | 'transcript' | 'hybrid'

export interface VoiceAgentDefaults {
  name: string
  description: string
  system_prompt: string
  memory_size: number
  keywords: string[]
  channels: string[]
  response_template: string
}

const KOKORO_PROMPT = `You are a voice assistant.

CRITICAL RULES:
1. ALWAYS respond in the same language as the user
2. KEEP RESPONSES VERY SHORT (maximum 2-3 sentences)
3. Be direct and objective
4. Adapt to the user's language preference

GOOD EXAMPLE: Today is December 1st, 2025.
BAD EXAMPLE: Long responses with many details.`

const OPENAI_PROMPT = `You are a voice assistant. You respond in audio using Text-to-Speech.

CRITICAL RULES:
1. ALWAYS respond in the same language as the user
2. Be natural, friendly, and conversational
3. KEEP RESPONSES SHORT (maximum 200 characters) for optimal audio
4. Be direct and expressive — your voice IS your personality
5. Use simple, spoken-language phrasing (avoid complex written constructs)

Remember: Your responses will be converted to speech, so write as you would speak.`

const TRANSCRIPT_PROMPT = `You are a transcription agent.

Your ONLY job is to transcribe audio messages accurately.

RULES:
1. Transcribe audio word-for-word, preserving the original language
2. Do NOT add commentary, interpretation, or conversation
3. Do NOT respond to the content of the audio — only transcribe it
4. If the audio is unclear, note it with [inaudible] markers
5. Preserve speaker tone indicators where relevant (e.g., [laughs], [whispers])`

export const VOICE_AGENT_DEFAULTS: Record<AudioProvider, VoiceAgentDefaults> = {
  kokoro: {
    name: 'Voice Assistant',
    description: 'Voice assistant with Kokoro TTS (free/local)',
    system_prompt: KOKORO_PROMPT,
    memory_size: 10,
    keywords: ['@voice'],
    channels: ['playground', 'whatsapp'],
    response_template: '@{agent_name}: {response}',
  },
  openai: {
    name: 'Voice Assistant',
    description: 'Voice assistant with OpenAI TTS',
    system_prompt: OPENAI_PROMPT,
    memory_size: 20,
    keywords: ['@voice'],
    channels: ['playground', 'whatsapp'],
    response_template: '@{agent_name}: {response}',
  },
  elevenlabs: {
    name: 'Voice Assistant',
    description: 'Voice assistant with ElevenLabs TTS',
    system_prompt: OPENAI_PROMPT,
    memory_size: 20,
    keywords: ['@voice'],
    channels: ['playground', 'whatsapp'],
    response_template: '@{agent_name}: {response}',
  },
  gemini: {
    name: 'Voice Assistant',
    description: 'Voice assistant with Google Gemini TTS (preview)',
    system_prompt: OPENAI_PROMPT,
    memory_size: 20,
    keywords: ['@voice'],
    channels: ['playground', 'whatsapp'],
    response_template: '@{agent_name}: {response}',
  },
}

export const TRANSCRIPT_AGENT_DEFAULTS: VoiceAgentDefaults = {
  name: 'Transcript',
  description: 'Audio transcription agent',
  system_prompt: TRANSCRIPT_PROMPT,
  memory_size: 10,
  keywords: [],
  channels: ['playground', 'whatsapp'],
  response_template: '@{agent_name}: {response}',
}

export const KOKORO_VOICES: { id: string; label: string; lang: string }[] = [
  { id: 'pf_dora', label: 'Dora — Brazilian PT (female)', lang: 'pt' },
  { id: 'pm_alex', label: 'Alex — Brazilian PT (male)', lang: 'pt' },
  { id: 'pm_santa', label: 'Santa — Brazilian PT (male)', lang: 'pt' },
  { id: 'af_bella', label: 'Bella — American EN (female)', lang: 'en' },
  { id: 'af_sarah', label: 'Sarah — American EN (female)', lang: 'en' },
  { id: 'af_nicole', label: 'Nicole — American EN (female)', lang: 'en' },
  { id: 'af_sky', label: 'Sky — American EN (female)', lang: 'en' },
  { id: 'am_adam', label: 'Adam — American EN (male)', lang: 'en' },
  { id: 'am_michael', label: 'Michael — American EN (male)', lang: 'en' },
  { id: 'bf_emma', label: 'Emma — British EN (female)', lang: 'en' },
  { id: 'bf_alice', label: 'Alice — British EN (female)', lang: 'en' },
  { id: 'bm_george', label: 'George — British EN (male)', lang: 'en' },
  { id: 'bm_daniel', label: 'Daniel — British EN (male)', lang: 'en' },
  { id: 'bm_lewis', label: 'Lewis — British EN (male)', lang: 'en' },
]

export const OPENAI_VOICES: { id: string; label: string }[] = [
  { id: 'nova', label: 'Nova — Warm, friendly (female)' },
  { id: 'alloy', label: 'Alloy — Neutral' },
  { id: 'echo', label: 'Echo — Calm (male)' },
  { id: 'fable', label: 'Fable — Expressive (male)' },
  { id: 'onyx', label: 'Onyx — Deep (male)' },
  { id: 'shimmer', label: 'Shimmer — Soft (female)' },
]

// Google Gemini TTS (gemini-3.1-flash-tts-preview). 30 prebuilt voices.
// Voice names are case-sensitive — must be sent to the API as proper nouns.
export const GEMINI_VOICES: { id: string; label: string }[] = [
  { id: 'Zephyr', label: 'Zephyr — Bright' },
  { id: 'Puck', label: 'Puck — Upbeat' },
  { id: 'Charon', label: 'Charon — Informative' },
  { id: 'Kore', label: 'Kore — Firm' },
  { id: 'Fenrir', label: 'Fenrir — Excitable' },
  { id: 'Leda', label: 'Leda — Youthful' },
  { id: 'Orus', label: 'Orus — Firm' },
  { id: 'Aoede', label: 'Aoede — Breezy' },
  { id: 'Callirrhoe', label: 'Callirrhoe — Easy-going' },
  { id: 'Autonoe', label: 'Autonoe — Bright' },
  { id: 'Enceladus', label: 'Enceladus — Breathy' },
  { id: 'Iapetus', label: 'Iapetus — Clear' },
  { id: 'Umbriel', label: 'Umbriel — Easy-going' },
  { id: 'Algieba', label: 'Algieba — Smooth' },
  { id: 'Despina', label: 'Despina — Smooth' },
  { id: 'Erinome', label: 'Erinome — Clear' },
  { id: 'Algenib', label: 'Algenib — Gravelly' },
  { id: 'Rasalgethi', label: 'Rasalgethi — Informative' },
  { id: 'Laomedeia', label: 'Laomedeia — Upbeat' },
  { id: 'Achernar', label: 'Achernar — Soft' },
  { id: 'Alnilam', label: 'Alnilam — Firm' },
  { id: 'Schedar', label: 'Schedar — Even' },
  { id: 'Gacrux', label: 'Gacrux — Mature' },
  { id: 'Pulcherrima', label: 'Pulcherrima — Forward' },
  { id: 'Achird', label: 'Achird — Friendly' },
  { id: 'Zubenelgenubi', label: 'Zubenelgenubi — Casual' },
  { id: 'Vindemiatrix', label: 'Vindemiatrix — Gentle' },
  { id: 'Sadachbia', label: 'Sadachbia — Lively' },
  { id: 'Sadaltager', label: 'Sadaltager — Knowledgeable' },
  { id: 'Sulafat', label: 'Sulafat — Warm' },
]

export const LANGUAGES = [
  { value: 'pt', label: 'Portuguese (pt)' },
  { value: 'en', label: 'English (en)' },
  { value: 'es', label: 'Spanish (es)' },
]

export const MEM_LIMITS = ['1g', '1.5g', '2g']
