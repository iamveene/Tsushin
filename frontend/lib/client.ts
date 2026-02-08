const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8081'

/**
 * Helper function to handle API response errors with user-friendly messages
 */
async function handleApiError(res: Response, defaultMessage: string): Promise<never> {
  if (res.status === 403) {
    throw new Error('Permission denied. You do not have access to perform this action.')
  }
  if (res.status === 401) {
    throw new Error('Session expired. Please log in again.')
  }
  if (res.status === 404) {
    throw new Error('Resource not found.')
  }
  if (res.status === 409) {
    throw new Error('Conflict: This resource already exists or cannot be modified.')
  }
  // Try to extract error message from response
  try {
    const data = await res.json()
    if (data.detail) {
      throw new Error(data.detail)
    }
  } catch {
    // If JSON parsing fails, use default message
  }
  throw new Error(defaultMessage)
}

/**
 * Helper function to create authenticated fetch requests
 * Automatically adds Authorization header if token is present in localStorage
 */
function authenticatedFetch(url: string, options: RequestInit = {}): Promise<Response> {
  // Get token from localStorage (only in browser)
  const token = typeof window !== 'undefined' ? localStorage.getItem('tsushin_auth_token') : null

  const headers: HeadersInit = {
    ...options.headers,
  }

  // Add Authorization header if token exists
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  // Add Content-Type for JSON requests if not already set
  // IMPORTANT: Do NOT set Content-Type for FormData - browser sets it with boundary
  if (options.body && typeof options.body === 'string' && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }

  // Debug logging for project uploads
  if (url.includes('/projects/') && url.includes('/knowledge')) {
    console.log('[authenticatedFetch] URL:', url)
    console.log('[authenticatedFetch] Method:', options.method)
    console.log('[authenticatedFetch] Body type:', options.body?.constructor.name)
    console.log('[authenticatedFetch] Headers:', headers)
    console.log('[authenticatedFetch] Has token:', !!token)
  }

  return fetch(url, {
    ...options,
    headers,
  })
}

export interface Config {
  id: number
  messages_db_path: string
  agent_number: string
  group_filters: string[]
  number_filters: string[]
  model_provider: string
  model_name: string
  memory_size: number
  enable_google_search: boolean
  search_provider: string
  system_prompt: string
  response_template: string
  contact_mappings: Record<string, string>
  // Phase 3 fields
  maintenance_mode: boolean
  maintenance_message: string
  context_message_count: number
  context_char_limit: number
  dm_auto_mode: boolean
  agent_phone_number: string
  agent_name: string
  group_keywords: string[]
  // enabled_tools removed - use AgentSkill table for web_search, weather, etc.
  // Phase 4.1 fields
  enable_semantic_search: boolean
  semantic_search_results: number
  semantic_similarity_threshold: number
  // Phase 5.2 fields
  ollama_base_url: string
  ollama_api_key: string | null
  // Phase 18: Global WhatsApp conversation delay
  whatsapp_conversation_delay_seconds: number
}

export interface Message {
  id: number
  source_id: string
  chat_name?: string
  sender_name?: string
  body: string
  timestamp: number
  is_group: boolean
  matched_filter: boolean
  seen_at: string
  channel?: 'whatsapp' | 'playground' | 'telegram'  // Phase 10.1.1: Channel tracking
}

// Sandboxed Tools (formerly CustomTools - renamed in Skills-as-Tools Phase 6)
export interface SandboxedTool {
  id: number
  name: string
  tool_type: string
  system_prompt: string
  workspace_dir: string | null
  execution_mode: string
  is_enabled: boolean
  created_at: string
  updated_at: string
  commands?: SandboxedToolCommand[]
}

export interface SandboxedToolCommand {
  id: number
  tool_id: number
  command_name: string
  command_template: string
  is_long_running: boolean
  timeout_seconds: number
  created_at: string
  parameters?: SandboxedToolParameter[]
}

export interface SandboxedToolParameter {
  id: number
  command_id: number
  parameter_name: string
  is_mandatory: boolean
  default_value: string | null
  description: string | null
  created_at: string
}

// Backward compatibility aliases (deprecated)
export type CustomTool = SandboxedTool
export type CustomToolCommand = SandboxedToolCommand
export type CustomToolParameter = SandboxedToolParameter

// Toolbox Container Types (Custom Tools Hub)
export interface ToolboxContainerStatus {
  tenant_id: string
  container_name: string
  status: string  // 'running', 'stopped', 'not_created', 'error'
  container_id: string | null
  image: string | null
  created_at: string | null
  started_at: string | null
  health: string
  error: string | null
}

export interface ToolboxPackage {
  id: number
  package_name: string
  package_type: string  // 'pip' | 'apt'
  version: string | null
  installed_at: string | null
  is_committed: boolean
}

export interface ToolboxCommandResult {
  success: boolean
  exit_code: number
  stdout: string
  stderr: string
  execution_time_ms: number
  command: string
  tenant_id: string
}

export interface ToolboxCommitResult {
  success: boolean
  image_tag: string
  image_id: string
  committed_at: string
}

export interface ToolboxResetResult {
  success: boolean
  message: string
  container_status: ToolboxContainerStatus
}

export interface AvailableToolboxTool {
  name: string
  description: string
  commands: string[]
}

export interface SandboxedToolExecution {
  id: number
  tool_id: number
  command_id: number
  rendered_command: string
  status: string
  output: string | null
  error: string | null
  execution_time_ms: number | null
  created_at: string
  completed_at: string | null
}

export interface AgentSandboxedTool {
  id: number
  agent_id: number
  sandboxed_tool_id: number
  tool_name: string
  tool_type: string
  is_enabled: boolean
  created_at: string
  updated_at: string
}

// Backward compatibility aliases (deprecated)
export type CustomToolExecution = SandboxedToolExecution
export type AgentCustomTool = AgentSandboxedTool

export interface AgentRun {
  id: number
  agent_id?: number
  agent_name?: string  // Agent's friendly name
  triggered_by: string
  sender_key: string
  input_preview: string
  skill_type?: string  // Skill that processed this message (e.g., "flows", "asana", "audio_transcript")
  tool_used?: string
  tool_result?: string  // Raw tool API response
  model_used: string
  output_preview: string
  status: string
  error_text?: string
  execution_time_ms?: number
  created_at: string
}

export interface TonePreset {
  id: number
  name: string
  description: string
  is_system: boolean
  tenant_id?: string | null
  usage_count?: number
  created_at: string
  updated_at: string
}

// Prompts Admin UI Types
export interface PromptConfig {
  system_prompt: string
  response_template: string
  updated_at?: string | null
}

export interface SlashCommandDetail {
  id: number
  tenant_id: string
  category: string
  command_name: string
  language_code: string
  pattern: string
  aliases: string[]
  description?: string | null
  handler_type: string
  handler_config: Record<string, any>
  is_enabled: boolean
  is_system: boolean
  created_at: string
  updated_at: string
}

export interface ProjectCommandPattern {
  id: number
  tenant_id: string
  command_type: string
  language_code: string
  pattern: string
  response_template: string
  is_active: boolean
  is_system: boolean
  created_at: string
  updated_at: string
}

// Phase 19: Shell Security Pattern Types
export interface SecurityPattern {
  id: number
  tenant_id: string | null
  pattern: string
  pattern_type: 'blocked' | 'high_risk'
  risk_level: string | null
  description: string
  category: string | null
  is_system_default: boolean
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface SecurityPatternCreate {
  pattern: string
  pattern_type: 'blocked' | 'high_risk'
  risk_level?: string
  description: string
  category?: string
  is_active?: boolean
}

export interface SecurityPatternUpdate {
  pattern?: string
  pattern_type?: 'blocked' | 'high_risk'
  risk_level?: string
  description?: string
  category?: string
  is_active?: boolean
}

export interface PatternTestResult {
  pattern: string
  is_valid: boolean
  error: string | null
  matches: Array<{
    command: string
    matched: boolean
    match_text: string | null
  }>
}

export interface SecurityPatternStats {
  patterns: {
    total: number
    system_default: number
    tenant_custom: number
    blocked: number
    high_risk: number
    active: number
    inactive: number
  }
  cache: {
    total_cached: number
    active_caches: number
    expired_caches: number
    cache_ttl_seconds: number
  }
}

// Phase 20: Sentinel Security Agent Types
export interface SentinelConfig {
  id: number
  tenant_id: string | null
  is_enabled: boolean
  enable_prompt_analysis: boolean
  enable_tool_analysis: boolean
  enable_shell_analysis: boolean
  detect_prompt_injection: boolean
  detect_agent_takeover: boolean
  detect_poisoning: boolean
  detect_shell_malicious_intent: boolean
  aggressiveness_level: number
  llm_provider: string
  llm_model: string
  llm_max_tokens: number
  llm_temperature: number
  cache_ttl_seconds: number
  max_input_chars: number
  timeout_seconds: number
  block_on_detection: boolean
  log_all_analyses: boolean
  // Phase 20 Enhancement: Detection mode and slash command toggle
  detection_mode: 'block' | 'warn_only' | 'detect_only' | 'off'
  enable_slash_command_analysis: boolean
  // Notification settings
  enable_notifications: boolean
  notification_on_block: boolean
  notification_on_detect: boolean
  notification_recipient: string | null
  notification_message_template: string | null
  has_custom_prompts: boolean
  created_at: string | null
  updated_at: string | null
}

export interface SentinelConfigUpdate {
  is_enabled?: boolean
  enable_prompt_analysis?: boolean
  enable_tool_analysis?: boolean
  enable_shell_analysis?: boolean
  detect_prompt_injection?: boolean
  detect_agent_takeover?: boolean
  detect_poisoning?: boolean
  detect_shell_malicious_intent?: boolean
  aggressiveness_level?: number
  llm_provider?: string
  llm_model?: string
  llm_max_tokens?: number
  llm_temperature?: number
  cache_ttl_seconds?: number
  max_input_chars?: number
  timeout_seconds?: number
  block_on_detection?: boolean
  log_all_analyses?: boolean
  // Phase 20 Enhancement
  detection_mode?: 'block' | 'detect_only' | 'off'
  enable_slash_command_analysis?: boolean
  // Notification settings
  enable_notifications?: boolean
  notification_on_block?: boolean
  notification_on_detect?: boolean
  notification_recipient?: string | null
  notification_message_template?: string | null
}

export interface SentinelAgentConfig {
  id: number
  agent_id: number
  is_enabled: boolean | null
  enable_prompt_analysis: boolean | null
  enable_tool_analysis: boolean | null
  enable_shell_analysis: boolean | null
  aggressiveness_level: number | null
  created_at: string
  updated_at: string
}

export interface SentinelAgentConfigUpdate {
  is_enabled?: boolean | null
  enable_prompt_analysis?: boolean | null
  enable_tool_analysis?: boolean | null
  enable_shell_analysis?: boolean | null
  aggressiveness_level?: number | null
}

export interface SentinelLog {
  id: number
  tenant_id: string
  agent_id: number | null
  analysis_type: string
  detection_type: string
  input_content: string
  is_threat_detected: boolean
  threat_score: number | null
  threat_reason: string | null
  action_taken: string
  llm_provider: string | null
  llm_model: string | null
  llm_response_time_ms: number | null
  sender_key: string | null
  message_id: string | null
  // Phase 20 Enhancement: Exception tracking
  exception_applied: boolean
  exception_id: number | null
  exception_name: string | null
  detection_mode_used: string | null
  created_at: string
}

export interface SentinelStats {
  total_analyses: number
  threats_detected: number
  threats_blocked: number
  detection_rate: number
  by_detection_type: Record<string, number>
  period_days: number
}

export interface SentinelTestResult {
  is_threat_detected: boolean
  threat_score: number
  threat_reason: string | null
  action: string
  detection_type: string
  analysis_type: string
  response_time_ms: number
}

export interface SentinelPrompt {
  detection_type: string
  has_custom_prompt: boolean
  custom_prompt: string | null
  default_prompt: string
}

export interface SentinelLLMProvider {
  name: string
  display_name: string
  models: string[]
}

export interface SentinelLLMTestResult {
  success: boolean
  message: string
  response_time_ms: number
}

export interface SentinelDetectionType {
  name: string
  description: string
  severity: string
  applies_to: string[]
  default_enabled: boolean
}

// Phase 20 Enhancement: Sentinel Exception Types
export interface SentinelException {
  id: number
  tenant_id: string | null
  agent_id: number | null
  name: string
  description: string | null
  detection_types: string
  exception_type: 'pattern' | 'domain' | 'tool' | 'network_target'
  pattern: string
  match_mode: 'regex' | 'glob' | 'exact'
  action: 'skip_llm' | 'allow'
  is_active: boolean
  priority: number
  created_by: number | null
  created_at: string
  updated_by: number | null
  updated_at: string
}

export interface SentinelExceptionCreate {
  name: string
  description?: string
  detection_types?: string
  exception_type: 'pattern' | 'domain' | 'tool' | 'network_target'
  pattern: string
  match_mode?: 'regex' | 'glob' | 'exact'
  action?: 'skip_llm' | 'allow'
  agent_id?: number
  priority?: number
}

export interface SentinelExceptionUpdate {
  name?: string
  description?: string
  detection_types?: string
  exception_type?: 'pattern' | 'domain' | 'tool' | 'network_target'
  pattern?: string
  match_mode?: 'regex' | 'glob' | 'exact'
  action?: 'skip_llm' | 'allow'
  agent_id?: number
  priority?: number
  is_active?: boolean
}

export interface SentinelExceptionTestRequest {
  test_content: string
  tool_name?: string
  target_domain?: string
}

export interface SentinelExceptionTestResult {
  matches: boolean
  would_skip_analysis: boolean
  exception_id: number
  exception_name: string
  exception_type: string
  pattern: string
  match_mode: string
  extracted_targets?: string[]
  extracted_domains?: string[]
}

// Sentinel Security Profiles (v1.6.0)
export interface SentinelProfile {
  id: number
  name: string
  slug: string
  description: string | null
  tenant_id: string | null
  is_system: boolean
  is_default: boolean
  is_enabled: boolean
  detection_mode: 'block' | 'detect_only' | 'off'
  aggressiveness_level: number
  enable_prompt_analysis: boolean
  enable_tool_analysis: boolean
  enable_shell_analysis: boolean
  enable_slash_command_analysis: boolean
  llm_provider: string
  llm_model: string
  llm_max_tokens: number
  llm_temperature: number
  cache_ttl_seconds: number
  max_input_chars: number
  timeout_seconds: number
  block_on_detection: boolean
  log_all_analyses: boolean
  enable_notifications: boolean
  notification_on_block: boolean
  notification_on_detect: boolean
  notification_recipient: string | null
  notification_message_template: string | null
  created_by: number | null
  updated_by: number | null
  created_at: string | null
  updated_at: string | null
}

export interface DetectionConfigItem {
  detection_type: string
  name: string
  description: string
  severity: string
  applies_to: string[]
  enabled: boolean
  custom_prompt: string | null
  source: 'explicit' | 'registry_default'
}

export interface SentinelProfileDetail extends SentinelProfile {
  detection_overrides_raw: string
  resolved_detections: DetectionConfigItem[]
}

export interface SentinelProfileCreate {
  name: string
  slug: string
  description?: string
  is_default?: boolean
  is_enabled?: boolean
  detection_mode?: 'block' | 'detect_only' | 'off'
  aggressiveness_level?: number
  enable_prompt_analysis?: boolean
  enable_tool_analysis?: boolean
  enable_shell_analysis?: boolean
  enable_slash_command_analysis?: boolean
  llm_provider?: string
  llm_model?: string
  llm_max_tokens?: number
  llm_temperature?: number
  cache_ttl_seconds?: number
  max_input_chars?: number
  timeout_seconds?: number
  block_on_detection?: boolean
  log_all_analyses?: boolean
  enable_notifications?: boolean
  notification_on_block?: boolean
  notification_on_detect?: boolean
  notification_recipient?: string | null
  notification_message_template?: string | null
  detection_overrides?: string
}

export interface SentinelProfileUpdate extends Partial<SentinelProfileCreate> {}

export interface SentinelProfileCloneRequest {
  name: string
  slug: string
}

export interface SentinelProfileAssignment {
  id: number
  tenant_id: string
  agent_id: number | null
  skill_type: string | null
  profile_id: number
  assigned_by: number | null
  assigned_at: string | null
  profile_name: string | null
  profile_slug: string | null
}

export interface SentinelProfileAssignRequest {
  profile_id: number
  agent_id?: number
  skill_type?: string
}

export interface DetectionEffectiveItem {
  detection_type: string
  name: string
  enabled: boolean
  custom_prompt: string | null
  source: 'explicit' | 'registry_default'
}

export interface SentinelEffectiveConfig {
  profile_id: number
  profile_name: string
  profile_source: 'skill' | 'agent' | 'tenant' | 'system' | 'legacy'
  is_enabled: boolean
  detection_mode: string
  aggressiveness_level: number
  enable_prompt_analysis: boolean
  enable_tool_analysis: boolean
  enable_shell_analysis: boolean
  enable_slash_command_analysis: boolean
  llm_provider: string
  llm_model: string
  llm_max_tokens: number
  llm_temperature: number
  cache_ttl_seconds: number
  max_input_chars: number
  timeout_seconds: number
  block_on_detection: boolean
  log_all_analyses: boolean
  enable_notifications: boolean
  notification_on_block: boolean
  notification_on_detect: boolean
  notification_recipient: string | null
  notification_message_template: string | null
  detections: DetectionEffectiveItem[]
}

export interface SentinelHierarchyProfile {
  id: number
  name: string
  slug: string
  source?: string
  detection_mode?: 'block' | 'detect_only' | 'off'
  aggressiveness_level?: number
  is_enabled?: boolean
}

export interface SentinelHierarchySkill {
  skill_type: string
  name: string
  is_enabled: boolean
  profile: SentinelHierarchyProfile | null
  effective_profile: SentinelHierarchyProfile | null
}

export interface SentinelHierarchyAgent {
  id: number
  name: string
  is_active: boolean
  profile: SentinelHierarchyProfile | null
  effective_profile: SentinelHierarchyProfile | null
  skills: SentinelHierarchySkill[]
}

export interface SentinelHierarchy {
  tenant: {
    id: string
    name: string
    profile: SentinelHierarchyProfile | null
    agents: SentinelHierarchyAgent[]
  } | null
}

export interface Persona {
  id: number
  name: string
  description: string
  role?: string
  role_description?: string
  tone_preset_id?: number
  tone_preset_name?: string
  custom_tone?: string
  personality_traits?: string
  enabled_skills: number[]
  enabled_custom_tools: number[]
  enabled_knowledge_bases: number[]
  guardrails?: string
  ai_summary?: string  // AI-generated summary
  is_active: boolean
  is_system: boolean
  created_at: string
  updated_at: string
}

export interface Agent {
  id: number
  contact_id: number
  contact_name: string
  system_prompt: string
  persona_id?: number  // Phase 5.1: Link to Persona
  persona_name?: string  // Phase 5.1: For display
  // Legacy fields (deprecated, kept for backward compatibility)
  tone_preset_id?: number
  tone_preset_name?: string
  custom_tone?: string
  keywords: string[]
  // enabled_tools removed - use AgentSkill table for web_search, weather, etc.
  model_provider: string
  model_name: string
  response_template: string
  memory_isolation_mode?: string  // Memory isolation: "isolated" | "shared" | "channel_isolated"

  // Per-agent configuration (Item 10)
  memory_size?: number  // Messages per sender (1-50)
  trigger_dm_enabled?: boolean  // Enable DM auto-response
  trigger_group_filters?: string[]  // Group names to monitor
  trigger_number_filters?: string[]  // Phone numbers to monitor
  context_message_count?: number  // Group context messages (1-100)
  context_char_limit?: number  // Context character limit
  enable_semantic_search?: boolean  // Semantic search skill

  // Hub integration (Phase 5.5)
  hub_integration_id?: number  // Link to Hub integration (Asana, Slack, etc.)
  default_asana_assignee_gid?: string  // Default Asana user GID

  // Phase 10: Channel Configuration
  enabled_channels?: string[]  // ["playground", "whatsapp", "telegram"]
  whatsapp_integration_id?: number  // Specific MCP instance
  telegram_integration_id?: number  // Future: Telegram bot instance

  // Agent avatar
  avatar?: string | null

  is_active: boolean
  is_default: boolean
  skills_count?: number  // Number of enabled skills
  created_at: string
  updated_at: string
}

// Phase 6 - Graph View: Batch endpoint types
export interface AgentGraphPreviewItem {
  id: number
  contact_name: string
  is_active: boolean
  is_default: boolean
  model_provider: string
  model_name: string
  memory_isolation_mode: string
  enabled_channels: string[]
  whatsapp_integration_id: number | null
  telegram_integration_id: number | null
  skills_count: number
  knowledge_doc_count: number
  knowledge_chunk_count: number
  sentinel_enabled: boolean
  avatar?: string | null
}

export interface WhatsAppChannelInfo {
  id: number
  phone_number: string | null
  status: string
  health_status: string
}

export interface TelegramChannelInfo {
  id: number
  bot_username: string
  status: string
  health_status: string
}

export interface GraphPreviewResponse {
  agents: AgentGraphPreviewItem[]
  channels: {
    whatsapp: WhatsAppChannelInfo[]
    telegram: TelegramChannelInfo[]
  }
}

export interface SkillExpandInfo {
  id: number
  skill_type: string
  skill_name: string
  skill_description: string
  category: string
  is_enabled: boolean
  provider_name: string | null
  provider_type: string | null  // e.g., "gmail", "google_calendar", "brave"
  integration_id: number | null  // The configured integration ID
  config: Record<string, unknown> | null
}

export interface KnowledgeSummary {
  total_documents: number
  total_chunks: number
  total_size_bytes: number
  document_types: Record<string, number>
  status_counts: Record<string, number>
  all_completed: boolean
}

export interface AgentExpandDataResponse {
  agent_id: number
  skills: SkillExpandInfo[]
  knowledge_summary: KnowledgeSummary
}

// Phase I: Agent Builder Batch Endpoints
export interface BuilderDataResponse {
  agent: {
    id: number
    contact_name: string
    persona_id: number | null
    persona_name: string | null
    model_provider: string
    model_name: string
    is_active: boolean
    is_default: boolean
    enabled_channels: string[]
    whatsapp_integration_id: number | null
    telegram_integration_id: number | null
    memory_size: number | null
    memory_isolation_mode: string
    enable_semantic_search: boolean
    avatar: string | null
  }
  skills: SkillExpandInfo[]
  knowledge: AgentKnowledge[]
  sentinel_assignments: SentinelProfileAssignment[]
  tool_mappings: AgentSandboxedTool[]
  globals?: {
    agents: Array<{ id: number; contact_name: string; is_active: boolean; is_default: boolean; model_provider: string; model_name: string }>
    personas: Persona[]
    sandboxed_tools: SandboxedTool[]
    sentinel_profiles: SentinelProfile[]
  }
}

export interface BuilderSaveRequest {
  agent?: {
    persona_id?: number | null
    enabled_channels?: string[]
    memory_size?: number
    memory_isolation_mode?: string
    enable_semantic_search?: boolean
    avatar?: string | null
  }
  skills?: Array<{
    skill_type: string
    is_enabled: boolean
    config?: Record<string, any>
  }>
  tool_overrides?: Array<{
    mapping_id: number
    is_enabled: boolean
  }>
  sentinel?: {
    action: 'assign' | 'remove' | 'unchanged'
    profile_id?: number
    assignment_id?: number
  }
}

export interface BuilderSaveResponse {
  success: boolean
  agent_id: number
  changes: Record<string, any>
}

// Phase 10.2: Channel Mapping
export interface ChannelMapping {
  id: number
  channel_type: string  // 'whatsapp' | 'telegram' | 'phone' | 'discord' | 'email' | 'sms' | etc.
  channel_identifier: string
  channel_metadata?: { username?: string; [key: string]: any } | null
  created_at: string
  updated_at: string
}

export interface Contact {
  id: number
  friendly_name: string
  whatsapp_id?: string
  phone_number?: string
  telegram_id?: string  // Phase 10.1.1: Telegram user ID
  telegram_username?: string  // Phase 10.1.1: Telegram @username
  role: string
  is_active: boolean
  is_dm_trigger: boolean
  notes?: string
  created_at: string
  updated_at: string
  // Linked system user fields
  linked_user_id?: number | null
  linked_user_email?: string | null
  linked_user_name?: string | null
  // Phase 10.2: Channel mappings
  channel_mappings?: ChannelMapping[]
}

export interface ContactAgentMapping {
  id: number
  contact_id: number
  contact_name: string
  agent_id: number
  agent_name: string
  created_at: string
  updated_at: string
}

// Phase 5.0: Memory Management
export interface MemoryStats {
  total_conversations: number
  total_messages: number
  total_embeddings: number
  storage_size_mb: number
}

export interface ConversationSummary {
  sender_key: string
  sender_name?: string
  message_count: number
  last_activity: string
}

// Phase 5.5: Hub Integrations
export interface HubIntegration {
  id: number
  type: string
  name: string
  is_active: boolean
  health_status: string
  workspace_gid?: string
  workspace_name?: string
}

export interface ConversationDetails {
  sender_key: string
  working_memory: Array<{ role: string; content: string; timestamp: string }>
  episodic_memory: Array<{ content: string; similarity: number; timestamp: string }>
  semantic_facts: Record<string, any>
}

// Phase 5.0: Skills System
export interface AgentSkill {
  id: number
  agent_id: number
  skill_type: string
  is_enabled: boolean
  config: Record<string, any>
  created_at: string
  updated_at: string
}

// Skill Integrations (Provider Configuration)
export interface SkillIntegration {
  id: number
  agent_id: number
  skill_type: string
  integration_id: number | null
  scheduler_provider: string | null
  config: Record<string, any> | null
  integration_name?: string
  integration_email?: string
  integration_health?: string
}

export interface SkillProviderIntegration {
  integration_id: number
  name: string
  email?: string
  workspace?: string
  health_status: string
}

export interface SkillProvider {
  provider_type: string
  provider_name: string
  description: string
  requires_integration: boolean
  available_integrations: SkillProviderIntegration[]
}

// TTS Provider types
export interface TTSVoice {
  voice_id: string
  name: string
  language: string
  gender?: string
  description?: string
  provider?: string
}

export interface TTSProviderInfo {
  id: string
  name: string
  class_name: string
  supported: boolean
  requires_api_key: boolean
  is_free: boolean
  status: string  // "available" | "coming_soon"
  voice_count: number
  default_voice: string
  supported_formats: string[]
  supported_languages: string[]
  pricing: {
    cost_per_1k_chars?: number
    currency?: string
    is_free?: boolean
  }
}

export interface TTSProviderStatus {
  provider: string
  status: string  // "healthy" | "degraded" | "unavailable" | "not_configured"
  message: string
  available: boolean
  latency_ms?: number
  details: Record<string, any>
}

export interface AgentTTSConfig {
  provider?: string
  voice?: string
  language?: string
  response_format?: string
  speed?: number
}

export interface SkillDefinition {
  skill_type: string
  skill_name: string
  skill_description: string
  config_schema: Record<string, any>
}

// Phase 5.0: Knowledge Management
export interface AgentKnowledge {
  id: number
  agent_id: number
  document_name: string
  document_type: string
  file_path: string
  file_size_bytes: number
  num_chunks: number
  status: string
  error_message?: string
  upload_date: string
  processed_date?: string
}

export interface KnowledgeChunk {
  id: number
  knowledge_id: number
  chunk_index: number
  content: string
  char_count: number
  metadata_json: Record<string, any>
}

// Task 3: Shared Knowledge
export interface SharedKnowledge {
  id: number
  content: string
  topic?: string
  shared_by_agent: number
  accessible_to: number[]
  meta_data: Record<string, any>
  created_at: string
  updated_at: string
}

export interface SharedMemoryStats {
  total_shared: number
  by_topic: Record<string, number>
  by_access_level: Record<string, number>
  sharing_agents: number
}

// Phase 6.4: Scheduler System
export interface ScheduledEvent {
  id: number
  event_type: string
  status: string
  scheduled_at: string
  executed_at?: string
  next_execution?: string
  payload: Record<string, any>
  conversation_state?: Record<string, any>
  recurrence_rule?: Record<string, any>
  created_at: string
  updated_at: string
  creator_type?: string
  creator_id?: number
}

export interface ConversationLog {
  id: number
  event_id: number
  turn_number: number
  direction: string
  sender: string
  recipient: string
  content: string
  timestamp: string
}

export interface SchedulerStats {
  total_events: number
  by_type: Record<string, number>
  by_status: Record<string, number>
  active_conversations: number
  pending_executions: number
}

// Phase 6.6-6.7: Multi-Step Flows
// Phase 8.0: Unified Flow Architecture
export interface FlowDefinition {
  id: number
  name: string
  description: string | null
  is_active: boolean
  version: number
  created_at: string
  updated_at: string
  node_count?: number
  // Phase 8.0 fields
  execution_method?: 'immediate' | 'scheduled' | 'recurring'
  scheduled_at?: string | null
  recurrence_rule?: Record<string, any> | null
  flow_type?: 'notification' | 'conversation' | 'workflow' | 'task'
  default_agent_id?: number | null
  last_executed_at?: string | null
  next_execution_at?: string | null
  execution_count?: number
}

export interface FlowNode {
  id: number
  flow_definition_id: number
  type: string
  position: number
  config_json: Record<string, any>
  next_node_id: number | null
  // Phase 8.0 fields
  name?: string | null
  step_description?: string | null
  timeout_seconds?: number
  retry_on_failure?: boolean
  max_retries?: number
  retry_delay_seconds?: number
  condition?: Record<string, any> | null
  on_success?: string | null
  on_failure?: string | null
  allow_multi_turn?: boolean
  max_turns?: number
  conversation_objective?: string | null
  agent_id?: number | null
  persona_id?: number | null
}

// Phase 8.0: Conversation Thread for multi-turn conversations
export interface ConversationThread {
  id: number
  flow_step_run_id: number
  flow_definition_id?: number | null  // Added for UI badges
  flow_name?: string | null  // Added for display
  status: 'active' | 'paused' | 'completed' | 'timeout' | 'goal_achieved'
  current_turn: number
  max_turns: number
  recipient: string
  agent_id: number
  persona_id?: number | null
  objective?: string | null
  conversation_history: Array<{
    role: 'agent' | 'user'
    content: string
    timestamp: string
  }>
  context_data: Record<string, any>
  goal_achieved: boolean
  goal_summary?: string | null
  started_at: string
  last_activity_at: string
  completed_at?: string | null
  timeout_at?: string | null
}

// Phase 8.0: Flow creation types
export type ExecutionMethod = 'immediate' | 'scheduled' | 'recurring'
export type FlowType = 'notification' | 'conversation' | 'workflow' | 'task'
export type StepType = 'notification' | 'message' | 'tool' | 'conversation' | 'skill' | 'summarization' | 'slash_command'

// Summarization output format options
export type SummarizationOutputFormat = 'brief' | 'detailed' | 'structured' | 'minimal'
// Summarization prompt mode options
export type SummarizationPromptMode = 'append' | 'replace'

export interface FlowStepConfig {
  channel?: 'whatsapp' | 'telegram'
  recipient?: string
  message_template?: string
  content?: string
  tool_name?: string
  tool_parameters?: Record<string, any>
  objective?: string
  initial_prompt?: string
  context?: Record<string, any>
  // Summarization step config
  source_step?: string
  output_format?: SummarizationOutputFormat
  prompt_mode?: SummarizationPromptMode
  summary_prompt?: string
  model?: string
  // Slash command step config
  command?: string
}

export interface CreateFlowStepData {
  name: string
  description?: string
  type: StepType
  position: number
  config: FlowStepConfig
  timeout_seconds?: number
  retry_on_failure?: boolean
  max_retries?: number
  retry_delay_seconds?: number
  condition?: Record<string, any>
  on_success?: string
  on_failure?: string
  allow_multi_turn?: boolean
  max_turns?: number
  conversation_objective?: string
  agent_id?: number
  persona_id?: number
}

export interface CreateFlowData {
  name: string
  description?: string
  execution_method?: ExecutionMethod
  scheduled_at?: string
  recurrence_rule?: {
    frequency: 'daily' | 'weekly' | 'monthly'
    interval?: number
    days_of_week?: number[]
    timezone?: string
    cron_expression?: string
  }
  flow_type?: FlowType
  default_agent_id?: number
  steps?: CreateFlowStepData[]
}

// Unified type for editing steps (both new and existing)
export interface EditableStepData {
  id?: number  // undefined = new step, number = existing step
  name: string
  description?: string
  type: StepType
  position: number
  config: FlowStepConfig
  timeout_seconds?: number
  retry_on_failure?: boolean
  max_retries?: number
  retry_delay_seconds?: number
  condition?: Record<string, any>
  on_success?: string
  on_failure?: string
  allow_multi_turn?: boolean
  max_turns?: number
  conversation_objective?: string
  agent_id?: number | null
  persona_id?: number | null
  _saving?: boolean  // UI state: currently saving
  _error?: string | null  // UI state: last error
}

// Convert FlowNode (from backend) to EditableStepData (for UI)
export function flowNodeToEditable(node: FlowNode): EditableStepData {
  return {
    id: node.id,
    name: node.name || `Step ${node.position}`,
    description: node.step_description || undefined,
    type: node.type as StepType,
    position: node.position,
    config: node.config_json as FlowStepConfig || {},
    timeout_seconds: node.timeout_seconds,
    retry_on_failure: node.retry_on_failure,
    max_retries: node.max_retries,
    retry_delay_seconds: node.retry_delay_seconds,
    condition: node.condition || undefined,
    on_success: node.on_success || undefined,
    on_failure: node.on_failure || undefined,
    allow_multi_turn: node.allow_multi_turn,
    max_turns: node.max_turns,
    conversation_objective: node.conversation_objective || undefined,
    agent_id: node.agent_id,
    persona_id: node.persona_id,
  }
}

// Convert EditableStepData to payload for API update
export function editableToUpdatePayload(step: EditableStepData): Record<string, any> {
  return {
    name: step.name,
    description: step.description,
    type: step.type,
    position: step.position,
    config_json: step.config,
    timeout_seconds: step.timeout_seconds,
    retry_on_failure: step.retry_on_failure,
    max_retries: step.max_retries,
    retry_delay_seconds: step.retry_delay_seconds,
    condition: step.condition,
    on_success: step.on_success,
    on_failure: step.on_failure,
    allow_multi_turn: step.allow_multi_turn,
    max_turns: step.max_turns,
    conversation_objective: step.conversation_objective,
    agent_id: step.agent_id,
    persona_id: step.persona_id,
  }
}

// Convert EditableStepData to payload for API create
export function editableToCreatePayload(step: EditableStepData): Record<string, any> {
  return {
    name: step.name,
    description: step.description,
    type: step.type,
    position: step.position,
    config_json: step.config,
    timeout_seconds: step.timeout_seconds,
    retry_on_failure: step.retry_on_failure,
    max_retries: step.max_retries,
    retry_delay_seconds: step.retry_delay_seconds,
    allow_multi_turn: step.allow_multi_turn,
    max_turns: step.max_turns,
    conversation_objective: step.conversation_objective,
    agent_id: step.agent_id,
    persona_id: step.persona_id,
  }
}

export interface FlowRun {
  id: number
  flow_definition_id: number
  status: string
  started_at: string
  completed_at: string | null
  initiator: string
  trigger_context_json: Record<string, any> | null
  final_report_json: Record<string, any> | null
  error_text: string | null
  // Phase 8.0 fields
  tenant_id?: string | null
  trigger_type?: string | null
  triggered_by?: string | null
  total_steps?: number
  completed_steps?: number
  failed_steps?: number
}

export interface FlowNodeRun {
  id: number
  flow_run_id: number
  flow_node_id: number
  status: string
  started_at: string
  completed_at: string | null
  input_json: Record<string, any> | null
  output_json: Record<string, any> | null
  error_text: string | null
  execution_time_ms: number | null
  token_usage_json: Record<string, any> | null
  tool_used: string | null
  idempotency_key: string
  // Phase 8.0 fields
  retry_count?: number
}

// Phase 8.0: Flow statistics
export interface FlowStats {
  flows: {
    total: number
    active: number
    inactive: number
  }
  runs: {
    total: number
    completed: number
    failed: number
    running: number
  }
  conversations: {
    active_threads: number
  }
}

// Tool metadata for flow configuration
export interface ToolParameter {
  name: string
  required: boolean
  description: string
  default?: string
}

export interface ToolCommand {
  id: string | number
  name: string
  description?: string
  parameters: ToolParameter[]
}

export interface ToolMetadata {
  id: string | number
  name: string
  tool_type?: string
  commands: ToolCommand[]
}

// Phase 8: Multi-Tenant MCP Containerization
export interface WhatsAppMCPInstance {
  id: number
  tenant_id: string
  container_name: string
  phone_number: string
  instance_type: 'agent' | 'tester'
  mcp_api_url: string
  mcp_port: number
  messages_db_path: string
  session_data_path: string
  status: string
  health_status: string
  container_id: string | null
  is_group_handler: boolean  // Phase 10: Group message deduplication
  // Phase 17: Instance-Level Message Filtering
  group_filters: string[] | null
  number_filters: string[] | null
  group_keywords: string[] | null
  dm_auto_mode: boolean
  created_at: string
  last_started_at: string | null
  last_stopped_at: string | null
}

export interface WhatsAppInstanceFiltersUpdate {
  group_filters?: string[]
  number_filters?: string[]
  group_keywords?: string[]
  dm_auto_mode?: boolean
}

export interface MCPHealthStatus {
  status: string
  container_state: string
  api_reachable: boolean
  connected: boolean
  authenticated: boolean
  needs_reauth?: boolean
  is_reconnecting?: boolean
  reconnect_attempts?: number
  session_age_sec?: number
  last_activity_sec?: number
  error: string | null
}

export interface QRCodeResponse {
  qr_code: string | null
  message: string | null
}

export interface LogoutResponse {
  success: boolean
  message: string
  qr_code_ready: boolean
  backup_path?: string
}

// Phase 10.1.1: Telegram Bot Integration
export interface TelegramBotInstance {
  id: number
  tenant_id: string
  bot_username: string
  bot_name: string | null
  bot_id: string | null
  status: 'inactive' | 'active' | 'error'
  health_status: string
  use_webhook: boolean
  created_at: string
  updated_at: string
}

export interface TelegramHealthStatus {
  status: string
  bot_username: string
  api_reachable: boolean
  error: string | null
}

// Playground Feature
export interface PlaygroundAgentInfo {
  id: number
  name: string
  description: string | null
  is_active: boolean
}

export interface PlaygroundChatRequest {
  agent_id: number
  message: string
}

export interface KBUsageItem {
  document_name: string
  similarity: number
  chunk_index: number
  source_type?: 'agent' | 'project'  // KB source attribution
  project_name?: string              // Project name if source is project
}

export interface PlaygroundChatResponse {
  status: string
  message: string | null
  error: string | null
  tool_used: string | null
  execution_time: number | null
  agent_name: string | null
  timestamp: string
  thread_renamed?: boolean
  new_thread_title?: string
  kb_used?: KBUsageItem[]  // KB usage tracking
}

export interface PlaygroundMessage {
  role: string  // "user" or "assistant"
  content: string
  timestamp: string
  audio_url?: string  // Phase 14.1: TTS audio response URL
  audio_duration?: number  // Phase 14.1: Audio duration in seconds
  message_id?: string  // Phase 14.2: Message ID for operations
  is_edited?: boolean  // Phase 14.2: Edited flag
  edited_at?: string  // Phase 14.2: Edit timestamp
  original_content?: string  // Phase 14.2: Original content before edit
  is_deleted?: boolean  // Phase 14.2: Soft delete flag
  deleted_at?: string  // Phase 14.2: Delete timestamp
  is_bookmarked?: boolean  // Phase 14.2: Bookmark flag
  bookmarked_at?: string  // Phase 14.2: Bookmark timestamp
  kb_used?: KBUsageItem[]  // KB usage tracking
}

// Phase 14.0: Audio capabilities response
export interface AudioCapabilities {
  has_transcript: boolean
  has_tts: boolean
  transcript_mode: string
}

// Phase 14.0: Audio upload response
export interface PlaygroundAudioResponse {
  status: string
  transcript?: string
  message?: string
  error?: string
  response_mode?: string
  audio_url?: string
  audio_duration?: number
  timestamp: string
}

// Phase 14.2: Document attachments
export interface PlaygroundDocument {
  id: number
  name: string
  type: string
  size_bytes: number
  num_chunks: number
  status: string
  error?: string
  upload_date?: string
}

export interface DocumentUploadResponse {
  status: string
  document?: PlaygroundDocument
  error?: string
}

export interface DocumentSearchResult {
  content: string
  metadata: Record<string, any>
  similarity: number
}

// Phase 14.1: Thread Management
export interface PlaygroundThread {
  id: number
  title: string | null
  folder: string | null
  status: string
  is_archived: boolean
  agent_id: number
  recipient?: string  // sender_key for Memory Inspector filtering
  message_count?: number
  last_message_preview?: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ThreadCreateRequest {
  agent_id: number
  title?: string
  folder?: string
}

export interface ThreadUpdateRequest {
  title?: string
  folder?: string
  is_archived?: boolean
}

export interface ThreadExport {
  thread_id: number
  title: string | null
  agent_name: string
  agent_id: number
  created_at: string | null
  updated_at: string | null
  message_count: number
  messages: PlaygroundMessage[]
  exported_at: string
}

// Phase 14.2: Message Operations
export interface MessageEditRequest {
  message_id: string
  new_content: string
  regenerate: boolean
}

export interface MessageRegenerateRequest {
  message_id: string
}

export interface MessageDeleteRequest {
  message_id: string
  delete_subsequent: boolean
}

export interface MessageBookmarkRequest {
  message_id: string
  bookmarked: boolean
}

export interface MessageBranchRequest {
  message_id: string
  new_thread_title?: string
}

// Phase 14.3: Playground Settings
export interface PlaygroundSettings {
  documentProcessing?: {
    embeddingModel: string
    chunkSize: number
    chunkOverlap: number
    maxDocuments: number
  }
  audioSettings?: {
    ttsProvider: string
    ttsVoice: string
    autoPlayResponses: boolean
  }
  // BUG-007 Fix: Per-agent model configuration for playground sessions
  modelSettings?: {
    [agentId: string]: {
      temperature: number
      maxTokens: number
      streamResponse: boolean
    }
  }
}

export interface EmbeddingModel {
  id: string
  name: string
  description: string
  dimensions: number
  requires_api_key?: boolean
}

// BUG-010 Fix: Organization/Tenant interfaces
export interface OrganizationData {
  id: string
  name: string
  slug: string
  plan: string
  max_users: number
  max_agents: number
  max_monthly_requests: number
  is_active: boolean
  status: string
  user_count: number
  agent_count: number
  created_at?: string
  updated_at?: string
}

export interface OrganizationStats {
  tenant_id: string
  users: {
    current: number
    limit: number
    percentage: number
  }
  agents: {
    current: number
    limit: number
    percentage: number
  }
  monthly_requests: {
    current: number
    limit: number
    percentage: number
  }
  plan: string
  status: string
}

// Phase 14.4: Projects
export interface Project {
  id: number
  name: string
  description?: string
  icon: string
  color: string
  agent_id?: number
  system_prompt_override?: string
  enabled_tools: string[]
  enabled_custom_tools: number[]
  is_archived: boolean
  conversation_count?: number
  document_count?: number
  // Phase 16: KB Configuration
  kb_chunk_size?: number
  kb_chunk_overlap?: number
  kb_embedding_model?: string
  // Phase 16: Memory Configuration
  enable_semantic_memory?: boolean
  semantic_memory_results?: number
  semantic_similarity_threshold?: number
  enable_factual_memory?: boolean
  factual_extraction_threshold?: number
  // Phase 16: Memory stats
  fact_count?: number
  semantic_memory_count?: number
  created_at?: string
  updated_at?: string
}

// Phase 16: Slash Commands
export interface SlashCommand {
  id: number
  category: string
  command_name: string
  language_code: string
  pattern: string
  aliases: string[]
  description?: string
  help_text?: string
  is_enabled: boolean
  handler_type: string
  sort_order: number
}

export interface SlashCommandResult {
  status: string
  action?: string
  message?: string
  data?: Record<string, any>
}

export interface SlashCommandSuggestion {
  command_name: string
  description: string
  category: string
  aliases: string[]
}

// Phase 16: Project Memory
export interface ProjectMemoryStats {
  semantic_memory_count: number
  fact_count: number
  kb_document_count: number
  conversation_count: number
  unique_users: number
  fact_topics: Record<string, number>
}

export interface ProjectFact {
  id: number
  topic: string
  key: string
  value: string
  sender_key?: string
  confidence: number
  source: string
  created_at?: string
  updated_at?: string
}

export interface ProjectSemanticMemoryEntry {
  id: number
  sender_key: string
  content: string
  role: string
  timestamp?: string
  metadata: Record<string, any>
}

export interface ProjectMemoryExport {
  project_id: number
  exported_at: string
  semantic_memory?: ProjectSemanticMemoryEntry[]
  facts?: ProjectFact[]
}

export interface ProjectCreate {
  name: string
  description?: string
  icon?: string
  color?: string
  agent_id?: number
  system_prompt_override?: string
}

export interface ProjectConversation {
  id: number
  project_id: number
  title?: string
  message_count: number
  messages: Array<{ role: string; content: string; timestamp: string }>
  is_archived: boolean
  created_at?: string
  updated_at?: string
}

export interface ProjectDocument {
  id: number
  name: string
  type: string
  size_bytes: number
  num_chunks: number
  status: string
  error?: string
  upload_date?: string
}

// Phase 15: Skill Projects - Session Management
export interface ProjectSession {
  session_id?: number
  project_id?: number
  project_name?: string
  agent_id: number
  channel: string
  conversation_id?: number
  entered_at?: string
  is_in_project: boolean
}

export interface EnterProjectRequest {
  agent_id: number
  project_id?: number
  project_name?: string
  channel?: string
}

export interface ProjectAgentAccess {
  agent_id: number
  agent_name: string
  can_write: boolean
}

export interface CommandPattern {
  id: number
  command_type: string
  language_code: string
  pattern: string
  response_template?: string
  is_active: boolean
}

export interface PlaygroundHistoryResponse {
  messages: PlaygroundMessage[]
  agent_name: string
}

export interface UserContactMappingResponse {
  user_id: number
  contact_id: number
  contact_name: string
  contact_phone: string | null
  contact_whatsapp_id: string | null
  created_at: string
}

export interface UserContactMappingStatus {
  has_mapping: boolean
  mapping: UserContactMappingResponse | null
}

// Phase 7.9: RBAC Types
export interface TenantInfo {
  id: string
  name: string
  slug: string
  plan: string
  max_users: number
  max_agents: number
  max_monthly_requests: number
  is_active: boolean
  status: string
  user_count: number
  agent_count: number
  created_at: string | null
  updated_at: string | null
}

export interface TenantStats {
  tenant_id: string
  users: {
    current: number
    limit: number
    percentage: number
  }
  agents: {
    current: number
    limit: number
    percentage: number
  }
  monthly_requests: {
    current: number
    limit: number
    percentage: number
  }
  plan: string
  status: string
}

export interface TeamMember {
  id: number
  email: string
  full_name: string | null
  role: string
  role_display_name: string
  is_active: boolean
  email_verified: boolean
  auth_provider: string
  avatar_url: string | null
  created_at: string | null
  last_login_at: string | null
}

export interface TeamInvitation {
  id: number
  email: string
  role: string
  role_display_name: string
  invited_by_name: string
  expires_at: string
  created_at: string
  invitation_link?: string
}

export interface RoleInfo {
  name: string
  display_name: string
  description: string | null
  can_assign: boolean
}

export interface InvitationInfo {
  email: string
  tenant_name: string
  role: string
  role_display_name: string
  inviter_name: string
  expires_at: string
  is_valid: boolean
}

// Subscription Plans
export interface SubscriptionPlan {
  id: number
  name: string
  display_name: string
  description: string | null
  price_monthly: number
  price_yearly: number
  max_users: number
  max_agents: number
  max_monthly_requests: number
  max_knowledge_docs: number
  max_flows: number
  max_mcp_instances: number
  features: string[]
  is_active: boolean
  is_public: boolean
  sort_order: number
  tenant_count: number
  created_at: string | null
  updated_at: string | null
}

export interface PlanCreate {
  name: string
  display_name: string
  description?: string
  price_monthly?: number
  price_yearly?: number
  max_users?: number
  max_agents?: number
  max_monthly_requests?: number
  max_knowledge_docs?: number
  max_flows?: number
  max_mcp_instances?: number
  features?: string[]
  is_active?: boolean
  is_public?: boolean
  sort_order?: number
}

export interface PlanUpdate {
  display_name?: string
  description?: string
  price_monthly?: number
  price_yearly?: number
  max_users?: number
  max_agents?: number
  max_monthly_requests?: number
  max_knowledge_docs?: number
  max_flows?: number
  max_mcp_instances?: number
  features?: string[]
  is_active?: boolean
  is_public?: boolean
  sort_order?: number
}

export interface PlanStats {
  total_plans: number
  active_plans: number
  public_plans: number
  tenants_per_plan: Record<string, number>
}

// Google SSO Types
export interface GoogleSSOStatus {
  enabled: boolean
  platform_configured: boolean
  tenant_configured: boolean
  tenant_slug: string | null
}

export interface GoogleAuthURL {
  auth_url: string
}

// SSO Config Types
export interface SSOConfig {
  id: number
  tenant_id: string
  google_sso_enabled: boolean
  google_client_id: string | null
  has_client_secret: boolean
  allowed_domains: string[]
  auto_provision_users: boolean
  default_role_id: number | null
  default_role_name: string | null
  created_at: string | null
  updated_at: string | null
}

export interface SSOConfigUpdate {
  google_sso_enabled?: boolean
  google_client_id?: string
  google_client_secret?: string
  allowed_domains?: string[]
  auto_provision_users?: boolean
  default_role_id?: number | null
}

export interface PlatformSSOStatus {
  platform_sso_available: boolean
  tenant_can_use_platform_sso: boolean
  tenant_has_custom_credentials: boolean
}

// Global User Management Types
export interface GlobalUser {
  id: number
  email: string
  full_name: string | null
  tenant_id: string | null
  tenant_name: string | null
  is_global_admin: boolean
  is_active: boolean
  email_verified: boolean
  auth_provider: string
  has_google_linked: boolean
  avatar_url: string | null
  role: string | null
  role_display_name: string | null
  created_at: string | null
  last_login_at: string | null
}

export interface GlobalUserListResponse {
  users: GlobalUser[]
  total: number
  page: number
  page_size: number
  filters: Record<string, any>
}

export interface GlobalUserStats {
  total_users: number
  active_users: number
  global_admins: number
  google_sso_users: number
  local_users: number
  users_per_tenant: Record<string, number>
  users_per_role: Record<string, number>
}

export interface UserCreateRequest {
  email: string
  password: string
  full_name: string
  tenant_id: string
  role_name?: string
  is_active?: boolean
}

export interface UserUpdateRequest {
  full_name?: string
  is_active?: boolean
  email_verified?: boolean
  tenant_id?: string
  role_name?: string
}

export const api = {
  async getConfig(): Promise<Config> {
    const res = await authenticatedFetch(`${API_URL}/api/config`)
    if (!res.ok) throw new Error('Failed to fetch config')
    return res.json()
  },

  async updateConfig(update: Partial<Config>): Promise<Config> {
    const res = await authenticatedFetch(`${API_URL}/api/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    })
    if (!res.ok) throw new Error('Failed to update config')
    return res.json()
  },

  async getMessages(limit = 100, after?: string): Promise<Message[]> {
    const params = new URLSearchParams({ limit: limit.toString() })
    if (after) params.append('after', after)

    const res = await authenticatedFetch(`${API_URL}/api/messages?${params}`)
    if (!res.ok) throw new Error('Failed to fetch messages')
    return res.json()
  },

  async getMessageCount(): Promise<{ total: number }> {
    const res = await authenticatedFetch(`${API_URL}/api/messages/count`)
    if (!res.ok) throw new Error('Failed to fetch message count')
    return res.json()
  },

  async getAgentRuns(limit = 100): Promise<AgentRun[]> {
    const res = await authenticatedFetch(`${API_URL}/api/agent-runs?limit=${limit}`)
    if (!res.ok) throw new Error('Failed to fetch agent runs')
    return res.json()
  },

  async getAgentRunsCount(): Promise<{ total: number }> {
    const res = await authenticatedFetch(`${API_URL}/api/agent-runs/count`)
    if (!res.ok) throw new Error('Failed to fetch agent runs count')
    return res.json()
  },

  async testTrigger(text: string, senderKey: string) {
    const res = await authenticatedFetch(`${API_URL}/api/trigger/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, sender_key: senderKey }),
    })
    if (!res.ok) throw new Error('Failed to trigger test')
    return res.json()
  },

  async health(): Promise<{ status: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/health`)
    if (!res.ok) throw new Error('Health check failed')
    return res.json()
  },

  async getMemoryStats(): Promise<{
    semantic_search_enabled: boolean
    ring_buffer_size: number
    senders_in_memory: number
    total_messages_cached: number
    vector_store?: {
      total_embeddings: number
      collection_name: string
      persist_directory: string
    }
  }> {
    const res = await authenticatedFetch(`${API_URL}/api/stats/memory`)
    if (!res.ok) throw new Error('Failed to fetch memory stats')
    return res.json()
  },

  // Tone Presets
  async getTonePresets(): Promise<TonePreset[]> {
    const res = await authenticatedFetch(`${API_URL}/api/tones`)
    if (!res.ok) throw new Error('Failed to fetch tone presets')
    return res.json()
  },

  async getTonePreset(id: number): Promise<TonePreset> {
    const res = await authenticatedFetch(`${API_URL}/api/tones/${id}`)
    if (!res.ok) throw new Error('Failed to fetch tone preset')
    return res.json()
  },

  async createTonePreset(tone: { name: string; description: string }): Promise<TonePreset> {
    const res = await authenticatedFetch(`${API_URL}/api/tones`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(tone),
    })
    if (!res.ok) throw new Error('Failed to create tone preset')
    return res.json()
  },

  async updateTonePreset(id: number, tone: Partial<{ name: string; description: string }>): Promise<TonePreset> {
    const res = await authenticatedFetch(`${API_URL}/api/tones/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(tone),
    })
    if (!res.ok) throw new Error('Failed to update tone preset')
    return res.json()
  },

  async deleteTonePreset(id: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/tones/${id}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete tone preset')
  },

  // Phase 5.1: Personas
  async getPersonas(activeOnly = false): Promise<Persona[]> {
    const params = new URLSearchParams()
    if (activeOnly) params.append('active_only', 'true')

    const res = await authenticatedFetch(`${API_URL}/api/personas/?${params}`)
    if (!res.ok) throw new Error('Failed to fetch personas')
    return res.json()
  },

  async getPersona(id: number): Promise<Persona> {
    const res = await authenticatedFetch(`${API_URL}/api/personas/${id}`)
    if (!res.ok) throw new Error('Failed to fetch persona')
    return res.json()
  },

  async createPersona(persona: {
    name: string
    description: string
    tone_preset_id?: number
    custom_tone?: string
    personality_traits?: string
    is_active?: boolean
  }): Promise<Persona> {
    const res = await authenticatedFetch(`${API_URL}/api/personas/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(persona),
    })
    if (!res.ok) throw new Error('Failed to create persona')
    return res.json()
  },

  async updatePersona(id: number, persona: Partial<{
    name: string
    description: string
    tone_preset_id: number
    custom_tone: string
    personality_traits: string
    is_active: boolean
  }>): Promise<Persona> {
    const res = await authenticatedFetch(`${API_URL}/api/personas/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(persona),
    })
    if (!res.ok) throw new Error('Failed to update persona')
    return res.json()
  },

  async deletePersona(id: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/personas/${id}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete persona')
  },

  // Prompts & Patterns Admin
  async getPromptConfig(): Promise<PromptConfig> {
    const res = await authenticatedFetch(`${API_URL}/api/prompts/config`)
    if (!res.ok) await handleApiError(res, 'Failed to fetch prompt config')
    return res.json()
  },

  async updatePromptConfig(config: Partial<PromptConfig>): Promise<PromptConfig> {
    const res = await authenticatedFetch(`${API_URL}/api/prompts/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    })
    if (!res.ok) await handleApiError(res, 'Failed to update prompt config')
    return res.json()
  },

  async getTonePresets(search?: string): Promise<TonePreset[]> {
    const params = new URLSearchParams()
    if (search) params.append('search', search)
    const res = await authenticatedFetch(`${API_URL}/api/prompts/tone-presets?${params}`)
    if (!res.ok) await handleApiError(res, 'Failed to fetch tone presets')
    return res.json()
  },

  async createTonePreset(preset: { name: string; description: string }): Promise<TonePreset> {
    const res = await authenticatedFetch(`${API_URL}/api/prompts/tone-presets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(preset),
    })
    if (!res.ok) await handleApiError(res, 'Failed to create tone preset')
    return res.json()
  },

  async updateTonePreset(id: number, preset: Partial<{ name: string; description: string }>): Promise<TonePreset> {
    const res = await authenticatedFetch(`${API_URL}/api/prompts/tone-presets/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(preset),
    })
    if (!res.ok) await handleApiError(res, 'Failed to update tone preset')
    return res.json()
  },

  async deleteTonePreset(id: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/prompts/tone-presets/${id}`, {
      method: 'DELETE',
    })
    if (!res.ok) await handleApiError(res, 'Failed to delete tone preset')
  },

  async getSlashCommands(filters?: { search?: string; category?: string; is_active?: boolean }): Promise<SlashCommandDetail[]> {
    const params = new URLSearchParams()
    if (filters?.search) params.append('search', filters.search)
    if (filters?.category) params.append('category', filters.category)
    if (filters?.is_active !== undefined) params.append('is_active', filters.is_active.toString())
    const res = await authenticatedFetch(`${API_URL}/api/prompts/slash-commands?${params}`)
    if (!res.ok) await handleApiError(res, 'Failed to fetch slash commands')
    return res.json()
  },

  async createSlashCommand(command: {
    category: string
    command_name: string
    language_code?: string
    pattern: string
    aliases?: string[]
    description?: string
    handler_type?: string
    handler_config?: Record<string, any>
    is_active?: boolean
  }): Promise<SlashCommandDetail> {
    const res = await authenticatedFetch(`${API_URL}/api/prompts/slash-commands`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(command),
    })
    if (!res.ok) await handleApiError(res, 'Failed to create slash command')
    return res.json()
  },

  async updateSlashCommand(id: number, command: Partial<{
    category: string
    command_name: string
    language_code: string
    pattern: string
    aliases: string[]
    description: string
    handler_type: string
    handler_config: Record<string, any>
    is_active: boolean
  }>): Promise<SlashCommandDetail> {
    const res = await authenticatedFetch(`${API_URL}/api/prompts/slash-commands/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(command),
    })
    if (!res.ok) await handleApiError(res, 'Failed to update slash command')
    return res.json()
  },

  async deleteSlashCommand(id: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/prompts/slash-commands/${id}`, {
      method: 'DELETE',
    })
    if (!res.ok) await handleApiError(res, 'Failed to delete slash command')
  },

  async getProjectPatterns(filters?: { search?: string; command_type?: string; is_active?: boolean }): Promise<ProjectCommandPattern[]> {
    const params = new URLSearchParams()
    if (filters?.search) params.append('search', filters.search)
    if (filters?.command_type) params.append('command_type', filters.command_type)
    if (filters?.is_active !== undefined) params.append('is_active', filters.is_active.toString())
    const res = await authenticatedFetch(`${API_URL}/api/prompts/project-patterns?${params}`)
    if (!res.ok) await handleApiError(res, 'Failed to fetch project patterns')
    return res.json()
  },

  async createProjectPattern(pattern: {
    command_type: string
    language_code?: string
    pattern: string
    response_template: string
    is_active?: boolean
  }): Promise<ProjectCommandPattern> {
    const res = await authenticatedFetch(`${API_URL}/api/prompts/project-patterns`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(pattern),
    })
    if (!res.ok) await handleApiError(res, 'Failed to create project pattern')
    return res.json()
  },

  async updateProjectPattern(id: number, pattern: Partial<{
    command_type: string
    language_code: string
    pattern: string
    response_template: string
    is_active: boolean
  }>): Promise<ProjectCommandPattern> {
    const res = await authenticatedFetch(`${API_URL}/api/prompts/project-patterns/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(pattern),
    })
    if (!res.ok) await handleApiError(res, 'Failed to update project pattern')
    return res.json()
  },

  async deleteProjectPattern(id: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/prompts/project-patterns/${id}`, {
      method: 'DELETE',
    })
    if (!res.ok) await handleApiError(res, 'Failed to delete project pattern')
  },

  // Agents
  async getAgents(activeOnly = false): Promise<Agent[]> {
    const params = new URLSearchParams()
    if (activeOnly) params.append('active_only', 'true')

    const res = await authenticatedFetch(`${API_URL}/api/agents?${params}`)
    if (!res.ok) throw new Error('Failed to fetch agents')
    return res.json()
  },

  async getAgent(id: number): Promise<Agent> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${id}`)
    if (!res.ok) throw new Error('Failed to fetch agent')
    return res.json()
  },

  async createAgent(agent: {
    contact_id: number
    system_prompt: string
    tone_preset_id?: number
    custom_tone?: string
    keywords?: string[]
    // enabled_tools removed - use AgentSkill table for web_search, weather, etc.
    model_provider?: string
    model_name?: string
    is_active?: boolean
    is_default?: boolean
  }): Promise<Agent> {
    const res = await authenticatedFetch(`${API_URL}/api/agents`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(agent),
    })
    if (!res.ok) throw new Error('Failed to create agent')
    return res.json()
  },

  async updateAgent(id: number, agent: Partial<{
    contact_id: number
    system_prompt: string
    tone_preset_id: number
    custom_tone: string
    persona_id: number | null
    keywords: string[]
    model_provider: string
    model_name: string
    response_template: string
    memory_size: number
    memory_isolation_mode: string
    enable_semantic_search: boolean
    enabled_channels: string[]
    whatsapp_integration_id: number | null
    telegram_integration_id: number | null
    is_active: boolean
    is_default: boolean
  }>): Promise<Agent> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(agent),
    })
    if (!res.ok) throw new Error('Failed to update agent')
    return res.json()
  },

  async deleteAgent(id: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${id}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete agent')
  },

  // Phase 6 - Graph View: Batch endpoints for performance
  async getAgentsGraphPreview(): Promise<GraphPreviewResponse> {
    const res = await authenticatedFetch(`${API_URL}/api/v2/agents/graph-preview`)
    if (!res.ok) throw new Error('Failed to fetch agents graph preview')
    return res.json()
  },

  async getAgentExpandData(agentId: number): Promise<AgentExpandDataResponse> {
    const res = await authenticatedFetch(`${API_URL}/api/v2/agents/${agentId}/expand-data`)
    if (!res.ok) throw new Error('Failed to fetch agent expand data')
    return res.json()
  },

  // Phase I: Agent Builder Batch Endpoints
  async getAgentBuilderData(agentId: number, includeGlobals = false): Promise<BuilderDataResponse> {
    const params = includeGlobals ? '?include_globals=true' : ''
    const res = await authenticatedFetch(`${API_URL}/api/v2/agents/${agentId}/builder-data${params}`)
    if (!res.ok) throw new Error('Failed to fetch builder data')
    return res.json()
  },

  async saveAgentBuilderData(agentId: number, data: BuilderSaveRequest): Promise<BuilderSaveResponse> {
    const res = await authenticatedFetch(`${API_URL}/api/v2/agents/${agentId}/builder-save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error('Failed to save builder data')
    return res.json()
  },

  // Contacts
  async getContacts(): Promise<Contact[]> {
    const res = await authenticatedFetch(`${API_URL}/api/contacts/`)
    if (!res.ok) throw new Error('Failed to fetch contacts')
    return res.json()
  },

  async createContact(contact: {
    friendly_name: string
    phone_number?: string
    whatsapp_id?: string
    telegram_id?: string
    telegram_username?: string
    role: string
    is_active?: boolean
    is_dm_trigger?: boolean
    notes?: string
    linked_user_id?: number | null
  }): Promise<Contact> {
    const res = await authenticatedFetch(`${API_URL}/api/contacts/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(contact),
    })
    if (!res.ok) throw new Error('Failed to create contact')
    return res.json()
  },

  async updateContact(contactId: number, contact: {
    friendly_name?: string
    phone_number?: string
    whatsapp_id?: string
    telegram_id?: string
    telegram_username?: string
    role?: string
    is_active?: boolean
    is_dm_trigger?: boolean
    notes?: string
    linked_user_id?: number | null
  }): Promise<Contact> {
    const res = await authenticatedFetch(`${API_URL}/api/contacts/${contactId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(contact),
    })
    if (!res.ok) {
      const error = await res.json()
      throw new Error(error.detail || 'Failed to update contact')
    }
    return res.json()
  },

  async deleteContact(contactId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/contacts/${contactId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete contact')
  },

  // Phase 10.2: Channel Mappings
  async addChannelMapping(contactId: number, mapping: {
    channel_type: string
    channel_identifier: string
    channel_metadata?: any
  }): Promise<ChannelMapping> {
    const res = await authenticatedFetch(`${API_URL}/api/contacts/${contactId}/channels`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(mapping),
    })
    if (!res.ok) throw new Error('Failed to add channel mapping')
    return res.json()
  },

  async removeChannelMapping(contactId: number, mappingId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/contacts/${contactId}/channels/${mappingId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to remove channel mapping')
  },

  async updateChannelMappingMetadata(contactId: number, mappingId: number, metadata: any): Promise<ChannelMapping> {
    const res = await authenticatedFetch(`${API_URL}/api/contacts/${contactId}/channels/${mappingId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(metadata),
    })
    if (!res.ok) throw new Error('Failed to update channel mapping metadata')
    return res.json()
  },

  // WhatsApp ID Resolution
  async resolveContactWhatsApp(contactId: number, force: boolean = false): Promise<{
    success: boolean
    contact_id?: number
    whatsapp_id?: string
    message: string
  }> {
    const res = await authenticatedFetch(`${API_URL}/api/contacts/${contactId}/resolve-whatsapp?force=${force}`, {
      method: 'POST',
    })
    if (!res.ok) throw new Error('Failed to resolve WhatsApp ID')
    return res.json()
  },

  async resolveAllContactsWhatsApp(): Promise<{
    success: boolean
    resolved: number
    failed: number
    skipped: number
    total: number
    message?: string
  }> {
    const res = await authenticatedFetch(`${API_URL}/api/contacts/resolve-all-whatsapp`, {
      method: 'POST',
    })
    if (!res.ok) throw new Error('Failed to resolve WhatsApp IDs')
    return res.json()
  },

  // Contact-Agent Mappings
  async getContactAgentMappings(): Promise<ContactAgentMapping[]> {
    const res = await authenticatedFetch(`${API_URL}/api/contact-agent-mappings`)
    if (!res.ok) throw new Error('Failed to fetch contact-agent mappings')
    return res.json()
  },

  async getContactAgentMapping(contactId: number): Promise<ContactAgentMapping | null> {
    const res = await authenticatedFetch(`${API_URL}/api/contact-agent-mappings/contact/${contactId}`)
    if (res.status === 404) return null
    if (!res.ok) throw new Error('Failed to fetch contact-agent mapping')
    return res.json()
  },

  async setContactAgentMapping(contactId: number, agentId: number): Promise<ContactAgentMapping> {
    const res = await authenticatedFetch(`${API_URL}/api/contact-agent-mappings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contact_id: contactId, agent_id: agentId }),
    })
    if (!res.ok) throw new Error('Failed to set contact-agent mapping')
    return res.json()
  },

  async deleteContactAgentMapping(contactId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/contact-agent-mappings/contact/${contactId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete contact-agent mapping')
  },

  // Phase 5.0: Memory Management
  async getAgentMemoryStats(agentId: number): Promise<MemoryStats> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/memory/stats`)
    if (!res.ok) throw new Error('Failed to fetch memory stats')
    return res.json()
  },

  async getAgentConversations(agentId: number): Promise<ConversationSummary[]> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/memory/conversations`)
    if (!res.ok) throw new Error('Failed to fetch conversations')
    return res.json()
  },

  async getConversationDetails(agentId: number, senderKey: string): Promise<ConversationDetails> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/memory/conversation/${encodeURIComponent(senderKey)}`)
    if (!res.ok) throw new Error('Failed to fetch conversation details')
    return res.json()
  },

  async deleteConversation(agentId: number, senderKey: string): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/memory/conversation/${encodeURIComponent(senderKey)}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete conversation')
  },

  async cleanOldMessages(agentId: number, olderThanDays: number, dryRun = true): Promise<{ deleted_count: number; preview: string[] }> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/memory/clean`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ older_than_days: olderThanDays, dry_run: dryRun }),
    })
    if (!res.ok) throw new Error('Failed to clean old messages')
    return res.json()
  },

  async resetAgentMemory(agentId: number, confirmToken: string): Promise<{ success: boolean; message: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/memory/reset`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirm_token: confirmToken }),
    })
    if (!res.ok) throw new Error('Failed to reset agent memory')
    return res.json()
  },

  // Phase 5.0: Skills System
  async getAvailableSkills(): Promise<SkillDefinition[]> {
    const res = await authenticatedFetch(`${API_URL}/api/skills/available`)
    if (!res.ok) throw new Error('Failed to fetch available skills')
    const data = await res.json()
    return data.skills || []
  },

  async getAgentSkills(agentId: number): Promise<AgentSkill[]> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/skills`)
    if (!res.ok) throw new Error('Failed to fetch agent skills')
    const data = await res.json()
    return data.skills || []
  },

  async getAgentSkill(agentId: number, skillType: string): Promise<AgentSkill> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/skills/${skillType}`)
    if (!res.ok) throw new Error('Failed to fetch agent skill')
    return res.json()
  },

  async updateAgentSkill(agentId: number, skillType: string, update: Partial<{ is_enabled: boolean; config: Record<string, any> }>): Promise<AgentSkill> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/skills/${skillType}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    })
    if (!res.ok) throw new Error('Failed to update agent skill')
    return res.json()
  },

  async disableAgentSkill(agentId: number, skillType: string): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/skills/${skillType}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to disable agent skill')
  },

  // Skill Integrations (Provider Configuration)
  async getAgentSkillIntegrations(agentId: number): Promise<SkillIntegration[]> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/skill-integrations`)
    if (!res.ok) throw new Error('Failed to fetch skill integrations')
    const data = await res.json()
    return data.integrations || []
  },

  async getSkillIntegration(agentId: number, skillType: string): Promise<SkillIntegration | null> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/skill-integrations/${skillType}`)
    if (!res.ok) throw new Error('Failed to fetch skill integration')
    const data = await res.json()
    return data.exists ? data : null
  },

  async updateSkillIntegration(
    agentId: number,
    skillType: string,
    update: { integration_id?: number | null; scheduler_provider?: string | null; config?: Record<string, any> }
  ): Promise<SkillIntegration> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/skill-integrations/${skillType}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    })
    if (!res.ok) throw new Error('Failed to update skill integration')
    return res.json()
  },

  async deleteSkillIntegration(agentId: number, skillType: string): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/skill-integrations/${skillType}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete skill integration')
  },

  async getSkillProviders(skillType: string): Promise<SkillProvider[]> {
    const res = await authenticatedFetch(`${API_URL}/api/skill-providers/${skillType}`)
    if (!res.ok) throw new Error('Failed to fetch skill providers')
    const data = await res.json()
    return data.providers || []
  },

  // TTS Provider Management
  async getTTSProviders(): Promise<TTSProviderInfo[]> {
    const res = await authenticatedFetch(`${API_URL}/api/tts-providers`)
    if (!res.ok) throw new Error('Failed to fetch TTS providers')
    return res.json()
  },

  async getTTSProviderStatus(providerName: string): Promise<TTSProviderStatus> {
    const res = await authenticatedFetch(`${API_URL}/api/tts-providers/${providerName}/status`)
    if (!res.ok) throw new Error('Failed to fetch TTS provider status')
    return res.json()
  },

  async getTTSProviderVoices(providerName: string): Promise<TTSVoice[]> {
    const res = await authenticatedFetch(`${API_URL}/api/tts-providers/${providerName}/voices`)
    if (!res.ok) throw new Error('Failed to fetch TTS provider voices')
    return res.json()
  },

  async getAgentTTSProvider(agentId: number): Promise<AgentTTSConfig> {
    const res = await authenticatedFetch(`${API_URL}/api/tts-providers/agents/${agentId}/provider`)
    if (!res.ok) throw new Error('Failed to fetch agent TTS config')
    return res.json()
  },

  async updateAgentTTSProvider(agentId: number, config: AgentTTSConfig): Promise<{ success: boolean; message: string; provider: string; config: AgentTTSConfig }> {
    const res = await authenticatedFetch(`${API_URL}/api/tts-providers/agents/${agentId}/provider`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    })
    if (!res.ok) throw new Error('Failed to update agent TTS config')
    return res.json()
  },

  // Phase 5.0: Knowledge Management
  async getAgentKnowledge(agentId: number): Promise<AgentKnowledge[]> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/knowledge-base`)
    if (!res.ok) throw new Error('Failed to fetch agent knowledge')
    return res.json()
  },

  async getKnowledgeDocument(agentId: number, docId: number): Promise<AgentKnowledge> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/knowledge-base/${docId}`)
    if (!res.ok) throw new Error('Failed to fetch knowledge document')
    return res.json()
  },

  async uploadKnowledgeDocument(agentId: number, file: File): Promise<AgentKnowledge> {
    const formData = new FormData()
    formData.append('file', file)

    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/knowledge-base/upload`, {
      method: 'POST',
      body: formData,
    })
    if (!res.ok) throw new Error('Failed to upload knowledge document')
    return res.json()
  },

  async deleteKnowledgeDocument(agentId: number, docId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/knowledge-base/${docId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete knowledge document')
  },

  async getKnowledgeChunks(agentId: number, docId: number): Promise<KnowledgeChunk[]> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/knowledge-base/${docId}/chunks`)
    if (!res.ok) throw new Error('Failed to fetch knowledge chunks')
    return res.json()
  },

  async searchAgentKnowledge(agentId: number, query: string, maxResults = 5): Promise<KnowledgeChunk[]> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/knowledge-base/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, max_results: maxResults }),
    })
    if (!res.ok) throw new Error('Failed to search agent knowledge')
    return res.json()
  },

  // Sandboxed Tools (Phase 6.1, renamed from Custom Tools in Skills-as-Tools Phase 6)
  async getSandboxedTools(): Promise<SandboxedTool[]> {
    const res = await authenticatedFetch(`${API_URL}/api/custom-tools/`)
    if (!res.ok) throw new Error('Failed to fetch sandboxed tools')
    return res.json()
  },

  async getSandboxedToolExecutions(limit = 50): Promise<SandboxedToolExecution[]> {
    const res = await authenticatedFetch(`${API_URL}/api/custom-tools/executions/?limit=${limit}`)
    if (!res.ok) throw new Error('Failed to fetch tool executions')
    return res.json()
  },

  async executeSandboxedTool(toolId: number, commandId: number, parameters: Record<string, any>): Promise<SandboxedToolExecution> {
    const res = await authenticatedFetch(`${API_URL}/api/custom-tools/execute/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool_id: toolId, command_id: commandId, parameters }),
    })
    if (!res.ok) throw new Error('Failed to execute custom tool')
    return res.json()
  },

  async updateSandboxedTool(toolId: number, data: {
    name?: string
    tool_type?: string
    system_prompt?: string
    is_enabled?: boolean
  }): Promise<SandboxedTool> {
    const res = await authenticatedFetch(`${API_URL}/api/custom-tools/${toolId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error('Failed to update custom tool')
    return res.json()
  },

  async getToolCommands(toolId: number): Promise<CustomToolCommand[]> {
    const res = await authenticatedFetch(`${API_URL}/api/custom-tools/${toolId}/commands`)
    if (!res.ok) throw new Error('Failed to fetch tool commands')
    return res.json()
  },

  async createToolCommand(data: {
    tool_id: number
    command_name: string
    command_template: string
    is_long_running?: boolean
    timeout_seconds?: number
  }): Promise<CustomToolCommand> {
    const res = await authenticatedFetch(`${API_URL}/api/custom-tools/commands/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error('Failed to create tool command')
    return res.json()
  },

  async deleteToolCommand(commandId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/custom-tools/commands/${commandId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete tool command')
  },

  async getCommandParameters(commandId: number): Promise<CustomToolParameter[]> {
    const res = await authenticatedFetch(`${API_URL}/api/custom-tools/commands/${commandId}/parameters`)
    if (!res.ok) throw new Error('Failed to fetch command parameters')
    return res.json()
  },

  async createToolParameter(data: {
    command_id: number
    parameter_name: string
    is_mandatory?: boolean
    default_value?: string
    description?: string
  }): Promise<CustomToolParameter> {
    const res = await authenticatedFetch(`${API_URL}/api/custom-tools/parameters/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error('Failed to create tool parameter')
    return res.json()
  },

  async deleteToolParameter(parameterId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/custom-tools/parameters/${parameterId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete tool parameter')
  },

  // Phase 6.2: Agent Sandboxed Tool Management (renamed from Custom Tools)
  async getAgentSandboxedTools(agentId: number): Promise<AgentSandboxedTool[]> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/custom-tools`)
    if (!res.ok) throw new Error('Failed to fetch agent sandboxed tools')
    return res.json()
  },

  async addAgentSandboxedTool(agentId: number, data: { sandboxed_tool_id: number; is_enabled: boolean }): Promise<AgentSandboxedTool> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/custom-tools`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error('Failed to add sandboxed tool to agent')
    return res.json()
  },

  async updateAgentSandboxedTool(agentId: number, mappingId: number, data: { is_enabled: boolean }): Promise<AgentSandboxedTool> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/custom-tools/${mappingId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error('Failed to update agent sandboxed tool')
    return res.json()
  },

  async deleteAgentSandboxedTool(agentId: number, mappingId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/agents/${agentId}/custom-tools/${mappingId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to remove sandboxed tool from agent')
  },

  // Phase 6.4: Scheduler System
  async getScheduledEvents(params?: {
    event_type?: string
    status?: string
    limit?: number
    offset?: number
  }): Promise<ScheduledEvent[]> {
    const searchParams = new URLSearchParams()
    if (params?.event_type) searchParams.append('event_type', params.event_type)
    if (params?.status) searchParams.append('status', params.status)
    if (params?.limit) searchParams.append('limit', params.limit.toString())
    if (params?.offset) searchParams.append('offset', params.offset.toString())

    const res = await authenticatedFetch(`${API_URL}/api/scheduler/?${searchParams}`)
    if (!res.ok) throw new Error('Failed to fetch scheduled events')
    return res.json()
  },

  async getScheduledEvent(eventId: number): Promise<ScheduledEvent> {
    const res = await authenticatedFetch(`${API_URL}/api/scheduler/${eventId}`)
    if (!res.ok) throw new Error('Failed to fetch scheduled event')
    return res.json()
  },

  async createScheduledEvent(event: {
    event_type: string
    scheduled_at: string
    payload: Record<string, any>
    recurrence_rule?: Record<string, any>
  }): Promise<ScheduledEvent> {
    const res = await authenticatedFetch(`${API_URL}/api/scheduler/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(event),
    })
    if (!res.ok) throw new Error('Failed to create scheduled event')
    return res.json()
  },

  async createConversation(conversation: {
    agent_id: number
    recipient: string
    objective: string
    scheduled_at: string
    context?: Record<string, any>
    max_turns?: number
    timeout_hours?: number
    impersonate?: Record<string, any>
  }): Promise<ScheduledEvent> {
    const res = await authenticatedFetch(`${API_URL}/api/scheduler/conversation`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(conversation),
    })
    if (!res.ok) throw new Error('Failed to create conversation')
    return res.json()
  },

  async createNotification(notification: {
    agent_id: number
    recipient_raw: string
    reminder_text: string
    scheduled_at: string
    message_template?: string
    recurrence?: Record<string, any>
  }): Promise<ScheduledEvent> {
    const res = await authenticatedFetch(`${API_URL}/api/scheduler/notification`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(notification),
    })
    if (!res.ok) throw new Error('Failed to create notification')
    return res.json()
  },

  async updateScheduledEvent(eventId: number, update: {
    scheduled_at?: string
    status?: string
    payload?: Record<string, any>
  }): Promise<ScheduledEvent> {
    const res = await authenticatedFetch(`${API_URL}/api/scheduler/${eventId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    })
    if (!res.ok) throw new Error('Failed to update scheduled event')
    return res.json()
  },

  async cancelScheduledEvent(eventId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/scheduler/${eventId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to cancel scheduled event')
  },

  async getConversationLogs(eventId: number, limit = 100): Promise<ConversationLog[]> {
    const res = await authenticatedFetch(`${API_URL}/api/scheduler/conversation/${eventId}/logs?limit=${limit}`)
    if (!res.ok) throw new Error('Failed to fetch conversation logs')
    return res.json()
  },

  async provideConversationGuidance(eventId: number, guidance: string): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/scheduler/conversation/${eventId}/guidance`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ guidance_text: guidance }),
    })
    if (!res.ok) throw new Error('Failed to provide conversation guidance')
  },

  async cancelConversation(eventId: number, reason?: string): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/scheduler/conversation/${eventId}/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cancellation_reason: reason }),
    })
    if (!res.ok) throw new Error('Failed to cancel conversation')
  },

  async getSchedulerStats(): Promise<SchedulerStats> {
    const res = await authenticatedFetch(`${API_URL}/api/scheduler/stats/summary`)
    if (!res.ok) throw new Error('Failed to fetch scheduler stats')
    return res.json()
  },

  async cleanupEvents(statuses: string[]): Promise<{ message: string; deleted_count: number }> {
    const statusParams = statuses.map(s => `statuses=${encodeURIComponent(s)}`).join('&')
    const res = await authenticatedFetch(`${API_URL}/api/scheduler/cleanup?${statusParams}`, {
      method: 'POST'
    })
    if (!res.ok) throw new Error('Failed to cleanup events')
    return res.json()
  },

  // Phase 6.6-6.7: Multi-Step Flows API
  async getFlows(): Promise<FlowDefinition[]> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/`)
    if (!res.ok) throw new Error('Failed to fetch flows')
    return res.json()
  },

  async getFlow(flowId: number): Promise<FlowDefinition> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/${flowId}`)
    if (!res.ok) throw new Error('Failed to fetch flow')
    return res.json()
  },

  async createFlow(flow: { name: string; description?: string }): Promise<FlowDefinition> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(flow),
    })
    if (!res.ok) throw new Error('Failed to create flow')
    return res.json()
  },

  async updateFlow(flowId: number, update: Partial<FlowDefinition>): Promise<FlowDefinition> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/${flowId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    })
    if (!res.ok) throw new Error('Failed to update flow')
    return res.json()
  },

  async deleteFlow(flowId: number, force: boolean = false): Promise<void> {
    const url = force
      ? `${API_URL}/api/flows/${flowId}?force=true`
      : `${API_URL}/api/flows/${flowId}`
    const res = await authenticatedFetch(url, {
      method: 'DELETE',
    })
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({ detail: 'Failed to delete flow' }))
      const errorMessage = errorData.detail || 'Failed to delete flow'
      throw new Error(errorMessage)
    }
  },

  async getFlowNodes(flowId: number): Promise<FlowNode[]> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/${flowId}/nodes`)
    if (!res.ok) throw new Error('Failed to fetch flow nodes')
    return res.json()
  },

  async createFlowNode(flowId: number, node: {
    type: string
    position: number
    config_json: Record<string, any>
  }): Promise<FlowNode> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/${flowId}/nodes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(node),
    })
    if (!res.ok) throw new Error('Failed to create flow node')
    return res.json()
  },

  async updateFlowNode(flowId: number, nodeId: number, update: Partial<FlowNode>): Promise<FlowNode> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/${flowId}/nodes/${nodeId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    })
    if (!res.ok) throw new Error('Failed to update flow node')
    return res.json()
  },

  async deleteFlowNode(flowId: number, nodeId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/${flowId}/nodes/${nodeId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete flow node')
  },

  async validateFlow(flowId: number): Promise<{ valid: boolean; errors: string[] }> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/${flowId}/validate`)
    if (!res.ok) throw new Error('Failed to validate flow')
    return res.json()
  },

  async runFlow(flowId: number, triggerContext?: Record<string, any>): Promise<FlowRun> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/${flowId}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trigger_context: triggerContext || {} }),
    })
    if (!res.ok) throw new Error('Failed to run flow')
    return res.json()
  },

  async getFlowRuns(flowId?: number, limit = 50): Promise<FlowRun[]> {
    const params = new URLSearchParams({ limit: limit.toString() })
    if (flowId) params.append('flow_definition_id', flowId.toString())

    const res = await authenticatedFetch(`${API_URL}/api/flows/runs?${params}`)
    if (!res.ok) throw new Error('Failed to fetch flow runs')
    return res.json()
  },

  async getFlowRun(runId: number): Promise<FlowRun> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/runs/${runId}`)
    if (!res.ok) throw new Error('Failed to fetch flow run')
    return res.json()
  },

  async getFlowNodeRuns(runId: number): Promise<FlowNodeRun[]> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/runs/${runId}/nodes`)
    if (!res.ok) throw new Error('Failed to fetch flow node runs')
    return res.json()
  },

  async getFlowToolMetadata(toolType: 'built_in' | 'custom', toolId?: string): Promise<ToolMetadata> {
    const params = new URLSearchParams({ tool_type: toolType })
    if (toolId) params.append('tool_id', toolId)

    const res = await authenticatedFetch(`${API_URL}/api/flows/tool-metadata?${params}`)
    if (!res.ok) throw new Error('Failed to fetch tool metadata')
    return res.json()
  },

  async cancelFlowRun(runId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/runs/${runId}/cancel`, {
      method: 'POST',
    })
    if (!res.ok) throw new Error('Failed to cancel flow run')
  },

  // Phase 8.0: Unified Flow API (enhanced methods)
  async createFlowV2(flow: CreateFlowData): Promise<FlowDefinition> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(flow),
    })
    if (!res.ok) throw new Error('Failed to create flow')
    return res.json()
  },

  async getFlowDetail(flowId: number): Promise<FlowDefinition & { steps: FlowNode[] }> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/${flowId}/detail`)
    if (!res.ok) throw new Error('Failed to fetch flow detail')
    return res.json()
  },

  async patchFlow(flowId: number, update: Partial<{
    name: string
    description: string
    execution_method: ExecutionMethod
    scheduled_at: string
    recurrence_rule: Record<string, any>
    flow_type: FlowType
    default_agent_id: number
    is_active: boolean
  }>): Promise<FlowDefinition> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/${flowId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    })
    if (!res.ok) throw new Error('Failed to patch flow')
    return res.json()
  },

  async executeFlow(flowId: number, triggerContext?: Record<string, any>): Promise<FlowRun> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/${flowId}/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trigger_context_json: triggerContext }),
    })
    if (!res.ok) throw new Error('Failed to execute flow')
    return res.json()
  },

  // Phase 8.0: Flow Steps (unified terminology)
  async getFlowSteps(flowId: number): Promise<FlowNode[]> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/${flowId}/steps`)
    if (!res.ok) throw new Error('Failed to fetch flow steps')
    return res.json()
  },

  async createFlowStep(flowId: number, step: {
    type: string
    position: number
    config_json: Record<string, any>
    name?: string
    description?: string
    timeout_seconds?: number
    retry_on_failure?: boolean
    max_retries?: number
    allow_multi_turn?: boolean
    max_turns?: number
    conversation_objective?: string
    agent_id?: number
    persona_id?: number
  }): Promise<FlowNode> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/${flowId}/steps`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(step),
    })
    if (!res.ok) throw new Error('Failed to create flow step')
    return res.json()
  },

  async updateFlowStep(flowId: number, stepId: number, update: Partial<FlowNode>): Promise<FlowNode> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/${flowId}/steps/${stepId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    })
    if (!res.ok) throw new Error('Failed to update flow step')
    return res.json()
  },

  async deleteFlowStep(flowId: number, stepId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/${flowId}/steps/${stepId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete flow step')
  },

  // Phase 8.0: Conversation Threads
  async getActiveConversationThreads(recipient?: string): Promise<ConversationThread[]> {
    const params = new URLSearchParams()
    if (recipient) params.append('recipient', recipient)

    const res = await authenticatedFetch(`${API_URL}/api/flows/conversations/active?${params}`)
    if (!res.ok) throw new Error('Failed to fetch active conversation threads')
    return res.json()
  },

  async getConversationThread(threadId: number): Promise<ConversationThread> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/conversations/${threadId}`)
    if (!res.ok) throw new Error('Failed to fetch conversation thread')
    return res.json()
  },

  async completeConversationThread(threadId: number, goalAchieved: boolean = true, summary?: string): Promise<void> {
    const params = new URLSearchParams({ goal_achieved: goalAchieved.toString() })
    if (summary) params.append('summary', summary)

    const res = await authenticatedFetch(`${API_URL}/api/flows/conversations/${threadId}/complete?${params}`, {
      method: 'POST',
    })
    if (!res.ok) throw new Error('Failed to complete conversation thread')
  },

  // Phase 8.0: Flow Stats
  async getFlowStats(): Promise<FlowStats> {
    const res = await authenticatedFetch(`${API_URL}/api/flows/stats`)
    if (!res.ok) throw new Error('Failed to fetch flow stats')
    return res.json()
  },

  // Task 3: Shared Knowledge Management
  async getSharedKnowledge(agentId: number, params?: {
    topic?: string
    min_confidence?: number
    limit?: number
  }): Promise<SharedKnowledge[]> {
    const searchParams = new URLSearchParams({ agent_id: agentId.toString() })
    if (params?.topic) searchParams.append('topic', params.topic)
    if (params?.min_confidence) searchParams.append('min_confidence', params.min_confidence.toString())
    if (params?.limit) searchParams.append('limit', params.limit.toString())

    const res = await authenticatedFetch(`${API_URL}/api/shared-memory?${searchParams}`)
    if (!res.ok) throw new Error('Failed to fetch shared knowledge')
    return res.json()
  },

  async shareKnowledge(data: {
    content: string
    topic?: string
    shared_by_agent: number
    accessible_to?: number[]
    access_level?: string
    meta_data?: Record<string, any>
  }): Promise<{ success: boolean; knowledge_id: number }> {
    const res = await authenticatedFetch(`${API_URL}/api/shared-memory`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error('Failed to share knowledge')
    return res.json()
  },

  async getSharedMemoryStats(agentId: number): Promise<SharedMemoryStats> {
    const res = await authenticatedFetch(`${API_URL}/api/shared-memory/stats?agent_id=${agentId}`)
    if (!res.ok) throw new Error('Failed to fetch shared memory stats')
    return res.json()
  },

  async getSharedMemoryTopics(agentId: number): Promise<string[]> {
    const res = await authenticatedFetch(`${API_URL}/api/shared-memory/topics?agent_id=${agentId}`)
    if (!res.ok) throw new Error('Failed to fetch shared memory topics')
    return res.json()
  },

  async searchSharedKnowledge(agentId: number, query: string, params?: {
    topic?: string
    limit?: number
  }): Promise<SharedKnowledge[]> {
    const searchParams = new URLSearchParams({
      agent_id: agentId.toString(),
      query
    })
    if (params?.topic) searchParams.append('topic', params.topic)
    if (params?.limit) searchParams.append('limit', params.limit.toString())

    const res = await authenticatedFetch(`${API_URL}/api/shared-memory/search?${searchParams}`)
    if (!res.ok) throw new Error('Failed to search shared knowledge')
    return res.json()
  },

  // Phase 5.5: Hub Integrations
  async getHubIntegrations(activeOnly = true): Promise<HubIntegration[]> {
    const params = new URLSearchParams()
    if (activeOnly) params.append('active_only', 'true')

    const res = await authenticatedFetch(`${API_URL}/api/hub/integrations?${params}`)
    if (!res.ok) throw new Error('Failed to fetch hub integrations')
    return res.json()
  },

  async getAgentIntegration(agentId: number): Promise<{ integration_id: number | null; type?: string; name?: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/hub/agents/${agentId}/integration`)
    if (!res.ok) throw new Error('Failed to fetch agent integration')
    return res.json()
  },

  async assignIntegrationToAgent(agentId: number, integrationId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/hub/agents/${agentId}/integration/${integrationId}`, {
      method: 'PUT',
    })
    if (!res.ok) throw new Error('Failed to assign integration')
  },

  async removeIntegrationFromAgent(agentId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/hub/agents/${agentId}/integration`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to remove integration')
  },

  // Phase 7.6: Authentication
  async login(email: string, password: string): Promise<{
    access_token: string
    token_type: string
    user: {
      id: number
      email: string
      full_name: string
      tenant_id: number
      is_global_admin: boolean
    }
  }> {
    const res = await authenticatedFetch(`${API_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Login failed' }))

      // Handle Pydantic validation errors (array format)
      if (Array.isArray(error.detail)) {
        const firstError = error.detail[0]
        throw new Error(firstError?.msg || 'Validation error')
      }

      // Handle string or object detail
      const errorMessage = typeof error.detail === 'string'
        ? error.detail
        : error.detail?.message || 'Login failed'

      throw new Error(errorMessage)
    }
    return res.json()
  },

  async signup(data: {
    email: string
    password: string
    full_name: string
    org_name: string
  }): Promise<{
    access_token: string
    token_type: string
    user: {
      id: number
      email: string
      full_name: string
      tenant_id: number
      is_global_admin: boolean
    }
  }> {
    const res = await authenticatedFetch(`${API_URL}/api/auth/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Signup failed' }))
      throw new Error(error.detail || 'Signup failed')
    }
    return res.json()
  },

  async getCurrentUser(token: string): Promise<{
    id: number
    email: string
    full_name: string
    tenant_id: number
    is_global_admin: boolean
    is_active: boolean
    email_verified: boolean
    permissions: string[]
    created_at: string | null
    last_login_at: string | null
  }> {
    const res = await authenticatedFetch(`${API_URL}/api/auth/me`, {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    })
    if (!res.ok) throw new Error('Failed to fetch current user')
    return res.json()
  },

  async requestPasswordReset(email: string): Promise<{ message: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/auth/password-reset/request`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    })
    if (!res.ok) throw new Error('Failed to request password reset')
    return res.json()
  },

  async confirmPasswordReset(token: string, new_password: string): Promise<{ message: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/auth/password-reset/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, new_password }),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Password reset failed' }))
      throw new Error(error.detail || 'Password reset failed')
    }
    return res.json()
  },

  async logout(token: string): Promise<{ message: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/auth/logout`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    })
    if (!res.ok) throw new Error('Failed to logout')
    return res.json()
  },

  // Phase 8: Multi-Tenant MCP Containerization
  async getMCPInstances(): Promise<WhatsAppMCPInstance[]> {
    const res = await authenticatedFetch(`${API_URL}/api/mcp/instances/`)
    if (!res.ok) throw new Error('Failed to fetch MCP instances')
    return res.json()
  },

  async getMCPInstance(id: number): Promise<WhatsAppMCPInstance> {
    const res = await authenticatedFetch(`${API_URL}/api/mcp/instances/${id}`)
    if (!res.ok) throw new Error('Failed to fetch MCP instance')
    return res.json()
  },

  async createMCPInstance(phone_number: string, instance_type: 'agent' | 'tester' = 'agent'): Promise<WhatsAppMCPInstance> {
    const res = await authenticatedFetch(`${API_URL}/api/mcp/instances/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone_number, instance_type }),
    })
    if (!res.ok) throw new Error('Failed to create MCP instance')
    return res.json()
  },

  async startMCPInstance(id: number): Promise<{ success: boolean; message: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/mcp/instances/${id}/start`, {
      method: 'POST',
    })
    if (!res.ok) throw new Error('Failed to start MCP instance')
    return res.json()
  },

  async stopMCPInstance(id: number): Promise<{ success: boolean; message: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/mcp/instances/${id}/stop`, {
      method: 'POST',
    })
    if (!res.ok) throw new Error('Failed to stop MCP instance')
    return res.json()
  },

  async restartMCPInstance(id: number): Promise<{ success: boolean; message: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/mcp/instances/${id}/restart`, {
      method: 'POST',
    })
    if (!res.ok) throw new Error('Failed to restart MCP instance')
    return res.json()
  },

  // Phase 10: Set MCP instance as group handler
  async setMCPGroupHandler(id: number, isGroupHandler: boolean): Promise<{ success: boolean; message: string; is_group_handler: boolean }> {
    const res = await authenticatedFetch(`${API_URL}/api/mcp/instances/${id}/group-handler`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_group_handler: isGroupHandler }),
    })
    if (!res.ok) throw new Error('Failed to set group handler')
    return res.json()
  },

  // Phase 17: Update MCP instance message filters
  async updateMCPInstanceFilters(id: number, filters: WhatsAppInstanceFiltersUpdate): Promise<WhatsAppMCPInstance> {
    const res = await authenticatedFetch(`${API_URL}/api/mcp/instances/${id}/filters`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(filters),
    })
    if (!res.ok) throw new Error('Failed to update instance filters')
    return res.json()
  },

  async deleteMCPInstance(id: number, removeData: boolean = false): Promise<{ success: boolean; message: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/mcp/instances/${id}?remove_data=${removeData}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete MCP instance')
    return res.json()
  },

  async getMCPHealth(id: number): Promise<MCPHealthStatus> {
    const res = await authenticatedFetch(`${API_URL}/api/mcp/instances/${id}/health`)
    if (!res.ok) throw new Error('Failed to fetch MCP health')
    return res.json()
  },

  async getMCPQRCode(id: number): Promise<QRCodeResponse> {
    const res = await authenticatedFetch(`${API_URL}/api/mcp/instances/${id}/qr-code`)
    if (!res.ok) throw new Error('Failed to fetch QR code')
    return res.json()
  },

  async logoutMCPInstance(id: number, backup: boolean = true): Promise<LogoutResponse> {
    const res = await authenticatedFetch(
      `${API_URL}/api/mcp/instances/${id}/logout?backup=${backup}`,
      { method: 'POST' }
    )
    if (!res.ok) {
      const error = await res.json()
      throw new Error(error.detail || 'Failed to logout MCP instance')
    }
    return res.json()
  },

  // Phase 10.1.1: Telegram Bot Integration
  async getTelegramInstances(): Promise<TelegramBotInstance[]> {
    const res = await authenticatedFetch(`${API_URL}/api/telegram/instances`)
    if (!res.ok) throw new Error('Failed to fetch Telegram instances')
    return res.json()
  },

  async getTelegramInstance(id: number): Promise<TelegramBotInstance> {
    const res = await authenticatedFetch(`${API_URL}/api/telegram/instances/${id}`)
    if (!res.ok) throw new Error('Failed to fetch Telegram instance')
    return res.json()
  },

  async createTelegramInstance(bot_token: string): Promise<TelegramBotInstance> {
    const res = await authenticatedFetch(`${API_URL}/api/telegram/instances`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bot_token }),
    })
    if (!res.ok) {
      const error = await res.json()
      throw new Error(error.detail || 'Failed to create Telegram instance')
    }
    return res.json()
  },

  async startTelegramInstance(id: number): Promise<{ success: boolean; message: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/telegram/instances/${id}/start`, {
      method: 'POST',
    })
    if (!res.ok) throw new Error('Failed to start Telegram instance')
    return res.json()
  },

  async stopTelegramInstance(id: number): Promise<{ success: boolean; message: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/telegram/instances/${id}/stop`, {
      method: 'POST',
    })
    if (!res.ok) throw new Error('Failed to stop Telegram instance')
    return res.json()
  },

  async deleteTelegramInstance(id: number): Promise<{ success: boolean; message: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/telegram/instances/${id}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete Telegram instance')
    return res.json()
  },

  async getTelegramHealth(id: number): Promise<TelegramHealthStatus> {
    const res = await authenticatedFetch(`${API_URL}/api/telegram/instances/${id}/health`)
    if (!res.ok) throw new Error('Failed to fetch Telegram health')
    return res.json()
  },

  // Playground Feature
  async getPlaygroundAgents(): Promise<PlaygroundAgentInfo[]> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/agents`)
    if (!res.ok) throw new Error('Failed to fetch playground agents')
    return res.json()
  },

  async sendPlaygroundMessage(agent_id: number, message: string, thread_id?: number): Promise<PlaygroundChatResponse> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id, message, thread_id }),
    })
    if (!res.ok) throw new Error('Failed to send playground message')
    return res.json()
  },

  async getPlaygroundHistory(agent_id: number, limit: number = 50): Promise<PlaygroundHistoryResponse> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/history/${agent_id}?limit=${limit}`)
    if (!res.ok) throw new Error('Failed to fetch playground history')
    return res.json()
  },

  async clearPlaygroundHistory(agent_id: number): Promise<{ success: boolean; message: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/history/${agent_id}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to clear playground history')
    return res.json()
  },

  // Phase 14.0: Audio capabilities and upload
  async getAgentAudioCapabilities(agent_id: number): Promise<AudioCapabilities> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/agents/${agent_id}/audio-capabilities`)
    if (!res.ok) throw new Error('Failed to fetch audio capabilities')
    return res.json()
  },

  async sendPlaygroundAudio(agent_id: number, audioBlob: Blob): Promise<PlaygroundAudioResponse> {
    const formData = new FormData()
    formData.append('audio', audioBlob, 'recording.webm')

    const token = typeof window !== 'undefined' ? localStorage.getItem('tsushin_auth_token') : null

    const res = await fetch(`${API_URL}/api/playground/audio?agent_id=${agent_id}`, {
      method: 'POST',
      headers: token ? { 'Authorization': `Bearer ${token}` } : {},
      body: formData,
    })
    if (!res.ok) throw new Error('Failed to upload audio')
    return res.json()
  },

  getPlaygroundAudioUrl(audio_id: string): string {
    return `${API_URL}/api/playground/audio/${audio_id}`
  },

  // Phase 14.2: Document attachments
  async uploadPlaygroundDocument(agent_id: number, file: File, options?: {
    chunkSize?: number
    chunkOverlap?: number
  }): Promise<DocumentUploadResponse> {
    const formData = new FormData()
    formData.append('file', file)

    const params = new URLSearchParams({ agent_id: agent_id.toString() })
    if (options?.chunkSize) params.append('chunk_size', options.chunkSize.toString())
    if (options?.chunkOverlap) params.append('chunk_overlap', options.chunkOverlap.toString())

    const token = typeof window !== 'undefined' ? localStorage.getItem('tsushin_auth_token') : null

    const res = await fetch(`${API_URL}/api/playground/documents?${params}`, {
      method: 'POST',
      headers: token ? { 'Authorization': `Bearer ${token}` } : {},
      body: formData,
    })
    if (!res.ok) throw new Error('Failed to upload document')
    return res.json()
  },

  async getPlaygroundDocuments(agent_id: number): Promise<{ documents: PlaygroundDocument[] }> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/documents?agent_id=${agent_id}`)
    if (!res.ok) throw new Error('Failed to fetch documents')
    return res.json()
  },

  async deletePlaygroundDocument(doc_id: number): Promise<{ status: string; message?: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/documents/${doc_id}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete document')
    return res.json()
  },

  async clearPlaygroundDocuments(agent_id: number): Promise<{ status: string; message?: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/documents?agent_id=${agent_id}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to clear documents')
    return res.json()
  },

  async searchPlaygroundDocuments(agent_id: number, query: string, maxResults: number = 5): Promise<{ results: DocumentSearchResult[] }> {
    const params = new URLSearchParams({
      agent_id: agent_id.toString(),
      query,
      max_results: maxResults.toString()
    })
    const res = await authenticatedFetch(`${API_URL}/api/playground/documents/search?${params}`, {
      method: 'POST',
    })
    if (!res.ok) throw new Error('Failed to search documents')
    return res.json()
  },

  // Phase 14.3: Playground Settings
  async getPlaygroundSettings(): Promise<PlaygroundSettings> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/settings`)
    if (!res.ok) throw new Error('Failed to fetch settings')
    return res.json()
  },

  async updatePlaygroundSettings(settings: Partial<PlaygroundSettings>): Promise<PlaygroundSettings> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    })
    if (!res.ok) throw new Error('Failed to update settings')
    return res.json()
  },

  async getAvailableEmbeddingModels(): Promise<{ models: EmbeddingModel[] }> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/embedding-models`)
    if (!res.ok) throw new Error('Failed to fetch embedding models')
    return res.json()
  },

  // BUG-010 Fix: Organization API
  async getCurrentOrganization(): Promise<OrganizationData> {
    const res = await authenticatedFetch(`${API_URL}/api/tenants/current`)
    if (!res.ok) throw new Error('Failed to fetch organization')
    return res.json()
  },

  async getOrganizationStats(tenantId: string): Promise<OrganizationStats> {
    const res = await authenticatedFetch(`${API_URL}/api/tenants/${tenantId}/stats`)
    if (!res.ok) throw new Error('Failed to fetch organization stats')
    return res.json()
  },

  async updateOrganization(tenantId: string, data: { name?: string }): Promise<OrganizationData> {
    const res = await authenticatedFetch(`${API_URL}/api/tenants/${tenantId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error('Failed to update organization')
    return res.json()
  },

  // Phase 14.4: Projects API
  async getProjects(includeArchived: boolean = false): Promise<Project[]> {
    const params = new URLSearchParams()
    if (includeArchived) params.append('include_archived', 'true')
    const res = await authenticatedFetch(`${API_URL}/api/projects?${params}`)
    if (!res.ok) throw new Error('Failed to fetch projects')
    return res.json()
  },

  async createProject(data: ProjectCreate): Promise<Project> {
    const res = await authenticatedFetch(`${API_URL}/api/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error('Failed to create project')
    return res.json()
  },

  async getProject(projectId: number): Promise<Project> {
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}`)
    if (!res.ok) throw new Error('Failed to fetch project')
    return res.json()
  },

  async updateProject(projectId: number, data: Partial<ProjectCreate & { is_archived?: boolean }>): Promise<Project> {
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error('Failed to update project')
    return res.json()
  },

  async deleteProject(projectId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete project')
  },

  // Project Knowledge
  async uploadProjectDocument(projectId: number, file: File): Promise<ProjectDocument> {
    const formData = new FormData()
    formData.append('file', file)

    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}/knowledge/upload`, {
      method: 'POST',
      body: formData,
    })
    if (!res.ok) throw new Error('Failed to upload document')
    return res.json()
  },

  async getProjectDocuments(projectId: number): Promise<ProjectDocument[]> {
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}/knowledge`)
    if (!res.ok) throw new Error('Failed to fetch documents')
    return res.json()
  },

  async deleteProjectDocument(projectId: number, docId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}/knowledge/${docId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete document')
  },

  async getProjectKnowledgeChunks(projectId: number, docId: number): Promise<KnowledgeChunk[]> {
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}/knowledge/${docId}/chunks`)
    if (!res.ok) throw new Error('Failed to fetch knowledge chunks')
    return res.json()
  },

  // Project Conversations
  async getProjectConversations(projectId: number, includeArchived: boolean = false): Promise<ProjectConversation[]> {
    const params = new URLSearchParams()
    if (includeArchived) params.append('include_archived', 'true')
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}/conversations?${params}`)
    if (!res.ok) throw new Error('Failed to fetch conversations')
    return res.json()
  },

  async createProjectConversation(projectId: number, title?: string): Promise<ProjectConversation> {
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    })
    if (!res.ok) throw new Error('Failed to create conversation')
    return res.json()
  },

  async getProjectConversation(projectId: number, conversationId: number): Promise<ProjectConversation> {
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}/conversations/${conversationId}`)
    if (!res.ok) throw new Error('Failed to fetch conversation')
    return res.json()
  },

  async sendProjectMessage(projectId: number, conversationId: number, message: string): Promise<{ status: string; message: string; conversation: ProjectConversation }> {
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}/conversations/${conversationId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    })
    if (!res.ok) throw new Error('Failed to send message')
    return res.json()
  },

  async deleteProjectConversation(projectId: number, conversationId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}/conversations/${conversationId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete conversation')
  },

  // Phase 15: Skill Projects - Session Management
  async getProjectSession(agentId: number, channel: string = 'playground'): Promise<ProjectSession> {
    const params = new URLSearchParams()
    params.append('agent_id', agentId.toString())
    params.append('channel', channel)
    const res = await authenticatedFetch(`${API_URL}/api/playground/project-session?${params}`)
    if (!res.ok) throw new Error('Failed to fetch project session')
    return res.json()
  },

  async enterProjectSession(data: EnterProjectRequest): Promise<ProjectSession> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/project-session/enter`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...data, channel: data.channel || 'playground' }),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to enter project' }))
      throw new Error(error.detail || 'Failed to enter project')
    }
    return res.json()
  },

  async exitProjectSession(agentId: number, channel: string = 'playground'): Promise<{ status: string; message: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/project-session/exit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: agentId, channel }),
    })
    if (!res.ok) throw new Error('Failed to exit project')
    return res.json()
  },

  // Phase 15: Project Agent Access
  async getProjectAgents(projectId: number): Promise<ProjectAgentAccess[]> {
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}/agents`)
    if (!res.ok) throw new Error('Failed to fetch project agents')
    return res.json()
  },

  async updateProjectAgents(projectId: number, agentIds: number[]): Promise<{ status: string; agent_ids: number[] }> {
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}/agents`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_ids: agentIds }),
    })
    if (!res.ok) throw new Error('Failed to update project agents')
    return res.json()
  },

  // Phase 15: Command Patterns
  async getCommandPatterns(): Promise<CommandPattern[]> {
    const res = await authenticatedFetch(`${API_URL}/api/project-commands`)
    if (!res.ok) throw new Error('Failed to fetch command patterns')
    return res.json()
  },

  async createCommandPattern(data: { command_type: string; language_code: string; pattern: string; response_template?: string }): Promise<CommandPattern> {
    const res = await authenticatedFetch(`${API_URL}/api/project-commands`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error('Failed to create command pattern')
    return res.json()
  },

  async deleteCommandPattern(patternId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/project-commands/${patternId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete command pattern')
  },

  // User-Contact Mapping
  async getUserContactMapping(): Promise<UserContactMappingStatus> {
    const res = await authenticatedFetch(`${API_URL}/api/user-contact-mapping`)
    if (!res.ok) throw new Error('Failed to fetch user-contact mapping')
    return res.json()
  },

  async setUserContactMapping(contact_id: number): Promise<UserContactMappingResponse> {
    const res = await authenticatedFetch(`${API_URL}/api/user-contact-mapping`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contact_id }),
    })
    if (!res.ok) throw new Error('Failed to set user-contact mapping')
    return res.json()
  },

  async deleteUserContactMapping(): Promise<{ success: boolean; message: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/user-contact-mapping`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete user-contact mapping')
    return res.json()
  },

  // Phase 5: Get all user-contact mappings for the tenant (admin-only)
  async getAllUserContactMappings(): Promise<UserContactMappingResponse[]> {
    const res = await authenticatedFetch(`${API_URL}/api/user-contact-mappings`)
    if (!res.ok) throw new Error('Failed to fetch user-contact mappings')
    return res.json()
  },

  // Phase 7.9: Tenant Management API
  async getTenants(params?: {
    page?: number
    page_size?: number
    search?: string
    status?: string
    plan?: string
  }): Promise<{
    tenants: TenantInfo[]
    total: number
    page: number
    page_size: number
  }> {
    const searchParams = new URLSearchParams()
    if (params?.page) searchParams.append('page', params.page.toString())
    if (params?.page_size) searchParams.append('page_size', params.page_size.toString())
    if (params?.search) searchParams.append('search', params.search)
    if (params?.status) searchParams.append('status', params.status)
    if (params?.plan) searchParams.append('plan', params.plan)

    const res = await authenticatedFetch(`${API_URL}/api/tenants?${searchParams}`)
    if (!res.ok) throw new Error('Failed to fetch tenants')
    return res.json()
  },

  async getTenant(id: string): Promise<TenantInfo> {
    const res = await authenticatedFetch(`${API_URL}/api/tenants/${id}`)
    if (!res.ok) throw new Error('Failed to fetch tenant')
    return res.json()
  },

  async getCurrentTenant(): Promise<TenantInfo> {
    const res = await authenticatedFetch(`${API_URL}/api/tenants/current`)
    if (!res.ok) throw new Error('Failed to fetch current tenant')
    return res.json()
  },

  async createTenant(data: {
    name: string
    owner_email: string
    owner_password: string
    owner_name: string
    plan?: string
    max_users?: number
    max_agents?: number
    max_monthly_requests?: number
  }): Promise<TenantInfo> {
    const res = await authenticatedFetch(`${API_URL}/api/tenants`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to create tenant' }))
      throw new Error(error.detail || 'Failed to create tenant')
    }
    return res.json()
  },

  async updateTenant(id: string, data: {
    name?: string
    plan?: string
    max_users?: number
    max_agents?: number
    max_monthly_requests?: number
    status?: string
  }): Promise<TenantInfo> {
    const res = await authenticatedFetch(`${API_URL}/api/tenants/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error('Failed to update tenant')
    return res.json()
  },

  async deleteTenant(id: string): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/tenants/${id}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete tenant')
  },

  async getTenantStats(id: string): Promise<TenantStats> {
    const res = await authenticatedFetch(`${API_URL}/api/tenants/${id}/stats`)
    if (!res.ok) throw new Error('Failed to fetch tenant stats')
    return res.json()
  },

  // Phase 7.9: Team Management API
  async getTeamMembers(params?: {
    page?: number
    page_size?: number
    search?: string
    role?: string
    is_active?: boolean
  }): Promise<{
    members: TeamMember[]
    total: number
    page: number
    page_size: number
  }> {
    const searchParams = new URLSearchParams()
    if (params?.page) searchParams.append('page', params.page.toString())
    if (params?.page_size) searchParams.append('page_size', params.page_size.toString())
    if (params?.search) searchParams.append('search', params.search)
    if (params?.role) searchParams.append('role', params.role)
    if (params?.is_active !== undefined) searchParams.append('is_active', params.is_active.toString())

    const res = await authenticatedFetch(`${API_URL}/api/team/?${searchParams}`)
    if (!res.ok) throw new Error('Failed to fetch team members')
    return res.json()
  },

  async getTeamMember(userId: number): Promise<TeamMember> {
    const res = await authenticatedFetch(`${API_URL}/api/team/${userId}`)
    if (!res.ok) throw new Error('Failed to fetch team member')
    return res.json()
  },

  async changeTeamMemberRole(userId: number, role: string): Promise<TeamMember> {
    const res = await authenticatedFetch(`${API_URL}/api/team/${userId}/role`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role }),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to change role' }))
      throw new Error(error.detail || 'Failed to change role')
    }
    return res.json()
  },

  async removeTeamMember(userId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/team/${userId}`, {
      method: 'DELETE',
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to remove team member' }))
      throw new Error(error.detail || 'Failed to remove team member')
    }
  },

  async inviteTeamMember(data: {
    email: string
    role?: string
    message?: string
  }): Promise<TeamInvitation> {
    const res = await authenticatedFetch(`${API_URL}/api/team/invite`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to send invitation' }))
      throw new Error(error.detail || 'Failed to send invitation')
    }
    return res.json()
  },

  async getTeamInvitations(): Promise<{
    invitations: TeamInvitation[]
    total: number
  }> {
    const res = await authenticatedFetch(`${API_URL}/api/team/invitations`)
    if (!res.ok) throw new Error('Failed to fetch invitations')
    return res.json()
  },

  async cancelInvitation(invitationId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/team/invitations/${invitationId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to cancel invitation')
  },

  async resendInvitation(invitationId: number): Promise<TeamInvitation> {
    const res = await authenticatedFetch(`${API_URL}/api/team/invitations/${invitationId}/resend`, {
      method: 'POST',
    })
    if (!res.ok) throw new Error('Failed to resend invitation')
    return res.json()
  },

  async getAvailableRoles(): Promise<{
    roles: RoleInfo[]
  }> {
    const res = await authenticatedFetch(`${API_URL}/api/team/roles`)
    if (!res.ok) throw new Error('Failed to fetch roles')
    return res.json()
  },

  // Invitation acceptance (public endpoints)
  async getInvitationInfo(token: string): Promise<InvitationInfo> {
    const res = await fetch(`${API_URL}/api/auth/invitation/${token}`)
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Invalid invitation' }))
      throw new Error(error.detail || 'Invalid invitation')
    }
    return res.json()
  },

  async acceptInvitation(token: string, data: {
    password: string
    full_name: string
  }): Promise<{
    access_token: string
    token_type: string
    user: {
      id: number
      email: string
      full_name: string
      tenant_id: string
      is_global_admin: boolean
    }
  }> {
    const res = await fetch(`${API_URL}/api/auth/invitation/${token}/accept`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to accept invitation' }))
      throw new Error(error.detail || 'Failed to accept invitation')
    }
    return res.json()
  },

  // ========================================================================
  // Google SSO API
  // ========================================================================

  async getGoogleSSOStatus(tenantSlug?: string): Promise<GoogleSSOStatus> {
    const params = new URLSearchParams()
    if (tenantSlug) params.append('tenant_slug', tenantSlug)

    const res = await fetch(`${API_URL}/api/auth/google/status?${params}`)
    if (!res.ok) throw new Error('Failed to get SSO status')
    return res.json()
  },

  async getGoogleAuthURL(options?: {
    tenantSlug?: string
    redirectAfter?: string
    invitationToken?: string
  }): Promise<GoogleAuthURL> {
    const params = new URLSearchParams()
    if (options?.tenantSlug) params.append('tenant_slug', options.tenantSlug)
    if (options?.redirectAfter) params.append('redirect_after', options.redirectAfter)
    if (options?.invitationToken) params.append('invitation_token', options.invitationToken)

    const res = await authenticatedFetch(`${API_URL}/api/auth/google/authorize?${params}`)
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to get Google auth URL' }))
      throw new Error(error.detail || 'Failed to get Google auth URL')
    }
    return res.json()
  },

  async linkGoogleAccount(): Promise<GoogleAuthURL> {
    const res = await authenticatedFetch(`${API_URL}/api/auth/google/link`, {
      method: 'POST',
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to link Google account' }))
      throw new Error(error.detail || 'Failed to link Google account')
    }
    return res.json()
  },

  async unlinkGoogleAccount(): Promise<{ message: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/auth/google/unlink`, {
      method: 'DELETE',
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to unlink Google account' }))
      throw new Error(error.detail || 'Failed to unlink Google account')
    }
    return res.json()
  },

  // ========================================================================
  // SSO Configuration API
  // ========================================================================

  async getPlatformSSOStatus(): Promise<PlatformSSOStatus> {
    const res = await authenticatedFetch(`${API_URL}/api/settings/sso/status`)
    if (!res.ok) throw new Error('Failed to get platform SSO status')
    return res.json()
  },

  async getSSOConfig(): Promise<SSOConfig> {
    const res = await authenticatedFetch(`${API_URL}/api/settings/sso/`)
    if (!res.ok) throw new Error('Failed to get SSO configuration')
    return res.json()
  },

  async updateSSOConfig(data: SSOConfigUpdate): Promise<SSOConfig> {
    const res = await authenticatedFetch(`${API_URL}/api/settings/sso/`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to update SSO configuration' }))
      throw new Error(error.detail || 'Failed to update SSO configuration')
    }
    return res.json()
  },

  async deleteSSOCredentials(): Promise<{ message: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/settings/sso/credentials`, {
      method: 'DELETE',
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to delete SSO credentials' }))
      throw new Error(error.detail || 'Failed to delete SSO credentials')
    }
    return res.json()
  },

  async getSSOAvailableRoles(): Promise<Array<{
    id: number
    name: string
    display_name: string
    description: string | null
  }>> {
    const res = await authenticatedFetch(`${API_URL}/api/settings/sso/roles`)
    if (!res.ok) throw new Error('Failed to get available roles')
    return res.json()
  },

  // ========================================================================
  // Global User Management API (Admin Only)
  // ========================================================================

  async getGlobalUsers(options?: {
    search?: string
    tenant_id?: string
    role?: string
    status?: 'active' | 'inactive' | 'all'
    auth_provider?: 'local' | 'google'
    is_global_admin?: boolean
    page?: number
    page_size?: number
  }): Promise<GlobalUserListResponse> {
    const params = new URLSearchParams()
    if (options?.search) params.append('search', options.search)
    if (options?.tenant_id) params.append('tenant_id', options.tenant_id)
    if (options?.role) params.append('role', options.role)
    if (options?.status) params.append('status', options.status)
    if (options?.auth_provider) params.append('auth_provider', options.auth_provider)
    if (options?.is_global_admin !== undefined) params.append('is_global_admin', String(options.is_global_admin))
    if (options?.page) params.append('page', String(options.page))
    if (options?.page_size) params.append('page_size', String(options.page_size))

    const res = await authenticatedFetch(`${API_URL}/api/admin/users?${params}`)
    if (!res.ok) throw new Error('Failed to fetch users')
    return res.json()
  },

  async getGlobalUserStats(): Promise<GlobalUserStats> {
    const res = await authenticatedFetch(`${API_URL}/api/admin/users/stats`)
    if (!res.ok) throw new Error('Failed to fetch user stats')
    return res.json()
  },

  async getGlobalUser(userId: number): Promise<GlobalUser> {
    const res = await authenticatedFetch(`${API_URL}/api/admin/users/${userId}`)
    if (!res.ok) throw new Error('Failed to fetch user')
    return res.json()
  },

  async createGlobalUser(data: UserCreateRequest): Promise<GlobalUser> {
    const res = await authenticatedFetch(`${API_URL}/api/admin/users`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to create user' }))
      throw new Error(error.detail || 'Failed to create user')
    }
    return res.json()
  },

  async updateGlobalUser(userId: number, data: UserUpdateRequest): Promise<GlobalUser> {
    const res = await authenticatedFetch(`${API_URL}/api/admin/users/${userId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to update user' }))
      throw new Error(error.detail || 'Failed to update user')
    }
    return res.json()
  },

  async deleteGlobalUser(userId: number, hardDelete: boolean = false): Promise<void> {
    const params = new URLSearchParams()
    if (hardDelete) params.append('hard_delete', 'true')

    const res = await authenticatedFetch(`${API_URL}/api/admin/users/${userId}?${params}`, {
      method: 'DELETE',
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to delete user' }))
      throw new Error(error.detail || 'Failed to delete user')
    }
  },

  async adminResetPassword(userId: number, newPassword: string): Promise<{ message: string }> {
    const params = new URLSearchParams({ new_password: newPassword })
    const res = await authenticatedFetch(`${API_URL}/api/admin/users/${userId}/reset-password?${params}`, {
      method: 'POST',
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to reset password' }))
      throw new Error(error.detail || 'Failed to reset password')
    }
    return res.json()
  },

  async toggleGlobalAdmin(userId: number): Promise<{ message: string; is_global_admin: boolean }> {
    const res = await authenticatedFetch(`${API_URL}/api/admin/users/${userId}/toggle-admin`, {
      method: 'POST',
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to toggle admin status' }))
      throw new Error(error.detail || 'Failed to toggle admin status')
    }
    return res.json()
  },

  // ========================================================================
  // Subscription Plans API
  // ========================================================================

  async getPlans(includePrivate: boolean = false): Promise<{
    plans: SubscriptionPlan[]
    total: number
  }> {
    const params = new URLSearchParams()
    if (includePrivate) params.append('include_private', 'true')

    const res = await authenticatedFetch(`${API_URL}/api/plans?${params}`)
    if (!res.ok) throw new Error('Failed to fetch plans')
    return res.json()
  },

  async getAllPlans(includeInactive: boolean = false): Promise<{
    plans: SubscriptionPlan[]
    total: number
  }> {
    const params = new URLSearchParams()
    if (includeInactive) params.append('include_inactive', 'true')

    const res = await authenticatedFetch(`${API_URL}/api/plans/all?${params}`)
    if (!res.ok) throw new Error('Failed to fetch plans')
    return res.json()
  },

  async getPlan(planId: number): Promise<SubscriptionPlan> {
    const res = await authenticatedFetch(`${API_URL}/api/plans/${planId}`)
    if (!res.ok) throw new Error('Failed to fetch plan')
    return res.json()
  },

  async getPlanStats(): Promise<PlanStats> {
    const res = await authenticatedFetch(`${API_URL}/api/plans/stats`)
    if (!res.ok) throw new Error('Failed to fetch plan stats')
    return res.json()
  },

  async createPlan(data: PlanCreate): Promise<SubscriptionPlan> {
    const res = await authenticatedFetch(`${API_URL}/api/plans`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to create plan' }))
      throw new Error(error.detail || 'Failed to create plan')
    }
    return res.json()
  },

  async updatePlan(planId: number, data: PlanUpdate): Promise<SubscriptionPlan> {
    const res = await authenticatedFetch(`${API_URL}/api/plans/${planId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to update plan' }))
      throw new Error(error.detail || 'Failed to update plan')
    }
    return res.json()
  },

  async deletePlan(planId: number, force: boolean = false): Promise<void> {
    const params = new URLSearchParams()
    if (force) params.append('force', 'true')

    const res = await authenticatedFetch(`${API_URL}/api/plans/${planId}?${params}`, {
      method: 'DELETE',
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to delete plan' }))
      throw new Error(error.detail || 'Failed to delete plan')
    }
  },

  async duplicatePlan(planId: number, newName: string, newDisplayName: string): Promise<SubscriptionPlan> {
    const params = new URLSearchParams({
      new_name: newName,
      new_display_name: newDisplayName,
    })

    const res = await authenticatedFetch(`${API_URL}/api/plans/${planId}/duplicate?${params}`, {
      method: 'POST',
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to duplicate plan' }))
      throw new Error(error.detail || 'Failed to duplicate plan')
    }
    return res.json()
  },

  // ========================================================================
  // Toolbox Container API (Custom Tools Hub)
  // ========================================================================

  async getToolboxStatus(): Promise<ToolboxContainerStatus> {
    const res = await authenticatedFetch(`${API_URL}/api/toolbox/status`)
    if (!res.ok) throw new Error('Failed to fetch toolbox status')
    return res.json()
  },

  async startToolbox(): Promise<ToolboxContainerStatus> {
    const res = await authenticatedFetch(`${API_URL}/api/toolbox/start`, {
      method: 'POST',
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to start toolbox' }))
      throw new Error(error.detail || 'Failed to start toolbox')
    }
    return res.json()
  },

  async stopToolbox(): Promise<ToolboxContainerStatus> {
    const res = await authenticatedFetch(`${API_URL}/api/toolbox/stop`, {
      method: 'POST',
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to stop toolbox' }))
      throw new Error(error.detail || 'Failed to stop toolbox')
    }
    return res.json()
  },

  async restartToolbox(): Promise<ToolboxContainerStatus> {
    const res = await authenticatedFetch(`${API_URL}/api/toolbox/restart`, {
      method: 'POST',
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to restart toolbox' }))
      throw new Error(error.detail || 'Failed to restart toolbox')
    }
    return res.json()
  },

  async executeToolboxCommand(command: string, timeout?: number, workdir?: string): Promise<ToolboxCommandResult> {
    const res = await authenticatedFetch(`${API_URL}/api/toolbox/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command, timeout, workdir }),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Command execution failed' }))
      throw new Error(error.detail || 'Command execution failed')
    }
    return res.json()
  },

  async getToolboxPackages(): Promise<ToolboxPackage[]> {
    const res = await authenticatedFetch(`${API_URL}/api/toolbox/packages`)
    if (!res.ok) throw new Error('Failed to fetch packages')
    return res.json()
  },

  async installToolboxPackage(packageName: string, packageType: 'pip' | 'apt'): Promise<ToolboxCommandResult> {
    const res = await authenticatedFetch(`${API_URL}/api/toolbox/packages/install`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ package_name: packageName, package_type: packageType }),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to install package' }))
      throw new Error(error.detail || 'Failed to install package')
    }
    return res.json()
  },

  async commitToolbox(): Promise<ToolboxCommitResult> {
    const res = await authenticatedFetch(`${API_URL}/api/toolbox/commit`, {
      method: 'POST',
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to commit toolbox' }))
      throw new Error(error.detail || 'Failed to commit toolbox')
    }
    return res.json()
  },

  async resetToolbox(): Promise<ToolboxResetResult> {
    const res = await authenticatedFetch(`${API_URL}/api/toolbox/reset`, {
      method: 'POST',
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to reset toolbox' }))
      throw new Error(error.detail || 'Failed to reset toolbox')
    }
    return res.json()
  },

  async getAvailableToolboxTools(): Promise<{ tools: AvailableToolboxTool[] }> {
    const res = await authenticatedFetch(`${API_URL}/api/toolbox/available-tools`)
    if (!res.ok) throw new Error('Failed to fetch available tools')
    return res.json()
  },

  // Phase 16: Slash Commands API
  async getSlashCommands(category?: string, languageCode: string = 'en'): Promise<SlashCommand[]> {
    const params = new URLSearchParams()
    params.append('language_code', languageCode)
    if (category) params.append('category', category)
    const res = await authenticatedFetch(`${API_URL}/api/commands?${params}`)
    if (!res.ok) throw new Error('Failed to fetch slash commands')
    return res.json()
  },

  async getSlashCommandsByCategory(languageCode: string = 'en'): Promise<{ categories: Record<string, SlashCommand[]> }> {
    const params = new URLSearchParams()
    params.append('language_code', languageCode)
    const res = await authenticatedFetch(`${API_URL}/api/commands/by-category?${params}`)
    if (!res.ok) throw new Error('Failed to fetch commands by category')
    return res.json()
  },

  async executeSlashCommand(data: { message: string; agent_id: number; channel?: string; sender_key?: string; thread_id?: number }): Promise<SlashCommandResult> {
    const res = await authenticatedFetch(`${API_URL}/api/commands/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...data, channel: data.channel || 'playground' }),
    })
    if (!res.ok) throw new Error('Failed to execute command')
    return res.json()
  },

  async autocompleteCommands(query: string, limit: number = 10): Promise<{ suggestions: SlashCommandSuggestion[] }> {
    const params = new URLSearchParams()
    params.append('query', query)
    params.append('limit', limit.toString())
    const res = await authenticatedFetch(`${API_URL}/api/commands/autocomplete?${params}`)
    if (!res.ok) throw new Error('Failed to autocomplete commands')
    return res.json()
  },

  // Phase 16: Project Memory API
  async getProjectMemoryStats(projectId: number): Promise<ProjectMemoryStats> {
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}/memory/stats`)
    if (!res.ok) throw new Error('Failed to fetch memory stats')
    return res.json()
  },

  async getProjectFacts(projectId: number, topic?: string, senderKey?: string): Promise<ProjectFact[]> {
    const params = new URLSearchParams()
    if (topic) params.append('topic', topic)
    if (senderKey) params.append('sender_key', senderKey)
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}/memory/facts?${params}`)
    if (!res.ok) throw new Error('Failed to fetch facts')
    return res.json()
  },

  async addProjectFact(projectId: number, data: { topic: string; key: string; value: string; sender_key?: string; confidence?: number; source?: string }): Promise<{ status: string; fact_id: number; action: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}/memory/facts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error('Failed to add fact')
    return res.json()
  },

  async deleteProjectFact(projectId: number, factId: number): Promise<{ status: string; deleted_id: number }> {
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}/memory/facts/${factId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete fact')
    return res.json()
  },

  async clearProjectFacts(projectId: number, topic?: string, senderKey?: string): Promise<{ status: string; deleted_count: number }> {
    const params = new URLSearchParams()
    if (topic) params.append('topic', topic)
    if (senderKey) params.append('sender_key', senderKey)
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}/memory/facts?${params}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to clear facts')
    return res.json()
  },

  async getProjectSemanticMemory(projectId: number, senderKey?: string, limit: number = 100, offset: number = 0): Promise<{ total: number; memories: ProjectSemanticMemoryEntry[] }> {
    const params = new URLSearchParams()
    params.append('limit', limit.toString())
    params.append('offset', offset.toString())
    if (senderKey) params.append('sender_key', senderKey)
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}/memory/semantic?${params}`)
    if (!res.ok) throw new Error('Failed to fetch semantic memory')
    return res.json()
  },

  async clearProjectSemanticMemory(projectId: number, senderKey?: string): Promise<{ status: string; deleted_count: number }> {
    const params = new URLSearchParams()
    if (senderKey) params.append('sender_key', senderKey)
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}/memory/semantic?${params}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to clear semantic memory')
    return res.json()
  },

  async exportProjectMemory(projectId: number, includeSemantic: boolean = true, includeFacts: boolean = true): Promise<ProjectMemoryExport> {
    const params = new URLSearchParams()
    params.append('include_semantic', includeSemantic.toString())
    params.append('include_facts', includeFacts.toString())
    const res = await authenticatedFetch(`${API_URL}/api/projects/${projectId}/memory/export?${params}`)
    if (!res.ok) throw new Error('Failed to export memory')
    return res.json()
  },

  // Phase 14.1: Thread Management API
  async listThreads(agentId?: number, includeArchived: boolean = false, folder?: string): Promise<{ threads: PlaygroundThread[] }> {
    const params = new URLSearchParams()
    if (agentId) params.append('agent_id', agentId.toString())
    if (includeArchived) params.append('include_archived', 'true')
    if (folder) params.append('folder', folder)
    const res = await authenticatedFetch(`${API_URL}/api/playground/threads?${params}`)
    if (!res.ok) throw new Error('Failed to list threads')
    return res.json()
  },

  async createThread(request: ThreadCreateRequest): Promise<PlaygroundThread> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/threads`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
    if (!res.ok) throw new Error('Failed to create thread')
    return res.json()
  },

  async getThread(threadId: number, options?: { signal?: AbortSignal }): Promise<{ id: number; title: string | null; folder: string | null; status: string; is_archived: boolean; agent_id: number; messages: PlaygroundMessage[]; created_at: string | null; updated_at: string | null; error_code?: string; error_message?: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/threads/${threadId}`, {
      signal: options?.signal
    })
    if (!res.ok) throw new Error('Failed to get thread')
    return res.json()
  },

  async updateThread(threadId: number, request: ThreadUpdateRequest): Promise<PlaygroundThread> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/threads/${threadId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
    if (!res.ok) throw new Error('Failed to update thread')
    return res.json()
  },

  async deleteThread(threadId: number): Promise<{ status: string; message: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/threads/${threadId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete thread')
    return res.json()
  },

  async exportThread(threadId: number): Promise<ThreadExport> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/threads/${threadId}/export`)
    if (!res.ok) throw new Error('Failed to export thread')
    return res.json()
  },

  // Phase 14.2: Message Operations API
  async editMessage(agentId: number, threadId: number, request: MessageEditRequest): Promise<{ status: string; message: string; new_response?: string; messages: PlaygroundMessage[] }> {
    const params = new URLSearchParams()
    params.append('agent_id', agentId.toString())
    params.append('thread_id', threadId.toString())
    const res = await authenticatedFetch(`${API_URL}/api/playground/messages/edit?${params}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
    if (!res.ok) throw new Error('Failed to edit message')
    return res.json()
  },

  async regenerateMessage(agentId: number, threadId: number, request: MessageRegenerateRequest): Promise<{ status: string; message: string; new_response: string; messages: PlaygroundMessage[] }> {
    const params = new URLSearchParams()
    params.append('agent_id', agentId.toString())
    params.append('thread_id', threadId.toString())
    const res = await authenticatedFetch(`${API_URL}/api/playground/messages/regenerate?${params}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
    if (!res.ok) throw new Error('Failed to regenerate message')
    return res.json()
  },

  async deleteMessage(agentId: number, threadId: number, request: MessageDeleteRequest): Promise<{ status: string; message: string; messages: PlaygroundMessage[] }> {
    const params = new URLSearchParams()
    params.append('agent_id', agentId.toString())
    params.append('thread_id', threadId.toString())
    const res = await authenticatedFetch(`${API_URL}/api/playground/messages/delete?${params}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
    if (!res.ok) throw new Error('Failed to delete message')
    return res.json()
  },

  async bookmarkMessage(agentId: number, threadId: number, request: MessageBookmarkRequest): Promise<{ status: string; message: string; is_bookmarked: boolean }> {
    const params = new URLSearchParams()
    params.append('agent_id', agentId.toString())
    params.append('thread_id', threadId.toString())
    const res = await authenticatedFetch(`${API_URL}/api/playground/messages/bookmark?${params}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
    if (!res.ok) throw new Error('Failed to bookmark message')
    return res.json()
  },

  async branchConversation(agentId: number, threadId: number, request: MessageBranchRequest): Promise<{ status: string; message: string; new_thread: PlaygroundThread }> {
    const params = new URLSearchParams()
    params.append('agent_id', agentId.toString())
    params.append('thread_id', threadId.toString())
    const res = await authenticatedFetch(`${API_URL}/api/playground/messages/branch?${params}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
    if (!res.ok) throw new Error('Failed to branch conversation')
    return res.json()
  },

  async copyMessage(agentId: number, threadId: number, messageId: string): Promise<{ status: string; content: string }> {
    const params = new URLSearchParams()
    params.append('agent_id', agentId.toString())
    params.append('thread_id', threadId.toString())
    params.append('message_id', messageId)
    const res = await authenticatedFetch(`${API_URL}/api/playground/messages/copy?${params}`)
    if (!res.ok) throw new Error('Failed to copy message')
    return res.json()
  },

  // Phase 14.5: Conversation Search API
  async searchConversations(query: string, filters?: any): Promise<any> {
    const params = new URLSearchParams()
    params.append('q', query)
    if (filters?.agent_id) params.append('agent_id', filters.agent_id.toString())
    if (filters?.thread_id) params.append('thread_id', filters.thread_id.toString())
    if (filters?.date_from) params.append('date_from', filters.date_from)
    if (filters?.date_to) params.append('date_to', filters.date_to)
    if (filters?.limit) params.append('limit', filters.limit.toString())
    if (filters?.offset) params.append('offset', filters.offset.toString())

    const res = await authenticatedFetch(`${API_URL}/api/playground/search?${params}`)
    if (!res.ok) throw new Error('Search failed')
    return res.json()
  },

  async searchConversationsSemantic(query: string, agentId?: number, limit?: number): Promise<any> {
    const params = new URLSearchParams()
    params.append('q', query)
    if (agentId) params.append('agent_id', agentId.toString())
    if (limit) params.append('limit', limit.toString())

    const res = await authenticatedFetch(`${API_URL}/api/playground/search/semantic?${params}`)
    if (!res.ok) throw new Error('Semantic search failed')
    return res.json()
  },

  async searchConversationsCombined(query: string, filters?: any): Promise<any> {
    const params = new URLSearchParams()
    params.append('q', query)
    if (filters?.agent_id) params.append('agent_id', filters.agent_id.toString())
    if (filters?.thread_id) params.append('thread_id', filters.thread_id.toString())
    if (filters?.date_from) params.append('date_from', filters.date_from)
    if (filters?.date_to) params.append('date_to', filters.date_to)
    if (filters?.limit) params.append('limit', filters.limit.toString())

    const res = await authenticatedFetch(`${API_URL}/api/playground/search/combined?${params}`)
    if (!res.ok) throw new Error('Combined search failed')
    return res.json()
  },

  async getSearchSuggestions(query: string, limit: number = 5): Promise<{ suggestions: string[] }> {
    const params = new URLSearchParams()
    params.append('q', query)
    params.append('limit', limit.toString())

    const res = await authenticatedFetch(`${API_URL}/api/playground/search/suggestions?${params}`)
    if (!res.ok) throw new Error('Failed to get search suggestions')
    return res.json()
  },

  // Phase 14.6: Knowledge Extraction API
  async extractThreadKnowledge(threadId: number, agentId: number): Promise<any> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/threads/${threadId}/extract-knowledge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: agentId }),
    })
    if (!res.ok) throw new Error('Failed to extract knowledge')
    return res.json()
  },

  async getThreadKnowledge(threadId: number): Promise<any> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/threads/${threadId}/knowledge`)
    if (!res.ok) throw new Error('Failed to get thread knowledge')
    return res.json()
  },

  async listTags(threadId?: number): Promise<{ tags: any[] }> {
    const params = new URLSearchParams()
    if (threadId) params.append('thread_id', threadId.toString())

    const res = await authenticatedFetch(`${API_URL}/api/playground/tags?${params}`)
    if (!res.ok) throw new Error('Failed to list tags')
    return res.json()
  },

  async updateTag(tagId: number, tag: string | null, color: string | null): Promise<any> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/tags/${tagId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tag, color }),
    })
    if (!res.ok) throw new Error('Failed to update tag')
    return res.json()
  },

  async deleteTag(tagId: number): Promise<any> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/tags/${tagId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete tag')
    return res.json()
  },

  async updateInsight(insightId: number, updates: {
    insight_text?: string
    insight_type?: string
    confidence?: number
  }): Promise<any> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/insights/${insightId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    })
    if (!res.ok) throw new Error('Failed to update insight')
    return res.json()
  },

  async deleteInsight(insightId: number): Promise<any> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/insights/${insightId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete insight')
    return res.json()
  },

  async deleteConversationLink(linkId: number): Promise<any> {
    const res = await authenticatedFetch(`${API_URL}/api/playground/links/${linkId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete conversation link')
    return res.json()
  },

  async getThreadInsights(threadId: number, insightType?: string): Promise<{ insights: any[] }> {
    const params = new URLSearchParams()
    if (insightType) params.append('insight_type', insightType)

    const res = await authenticatedFetch(`${API_URL}/api/playground/threads/${threadId}/insights?${params}`)
    if (!res.ok) throw new Error('Failed to get insights')
    return res.json()
  },

  async getRelatedThreads(threadId: number, limit: number = 5): Promise<{ related_threads: any[] }> {
    const params = new URLSearchParams()
    params.append('limit', limit.toString())

    const res = await authenticatedFetch(`${API_URL}/api/playground/threads/${threadId}/related?${params}`)
    if (!res.ok) throw new Error('Failed to get related threads')
    return res.json()
  },

  async exportThreadKnowledge(threadId: number, format: string = 'json'): Promise<any> {
    const params = new URLSearchParams()
    params.append('format', format)

    const res = await authenticatedFetch(`${API_URL}/api/playground/threads/${threadId}/export-knowledge?${params}`)
    if (!res.ok) throw new Error('Failed to export knowledge')
    return res.json()
  },

  // ============================================================================
  // Phase 19: Shell Security Pattern Management
  // ============================================================================

  async getSecurityPatterns(includeInactive: boolean = false): Promise<SecurityPattern[]> {
    const params = new URLSearchParams()
    if (includeInactive) params.append('include_inactive', 'true')

    const res = await authenticatedFetch(`${API_URL}/api/shell/security-patterns?${params}`)
    if (!res.ok) throw new Error('Failed to fetch security patterns')
    return res.json()
  },

  async createSecurityPattern(data: SecurityPatternCreate): Promise<SecurityPattern> {
    const res = await authenticatedFetch(`${API_URL}/api/shell/security-patterns`, {
      method: 'POST',
      body: JSON.stringify(data)
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to create security pattern' }))
      throw new Error(error.detail || 'Failed to create security pattern')
    }
    return res.json()
  },

  async updateSecurityPattern(id: number, data: SecurityPatternUpdate): Promise<SecurityPattern> {
    const res = await authenticatedFetch(`${API_URL}/api/shell/security-patterns/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data)
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to update security pattern' }))
      throw new Error(error.detail || 'Failed to update security pattern')
    }
    return res.json()
  },

  async deleteSecurityPattern(id: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/shell/security-patterns/${id}`, {
      method: 'DELETE'
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to delete security pattern' }))
      throw new Error(error.detail || 'Failed to delete security pattern')
    }
  },

  async testSecurityPattern(pattern: string, testCommands: string[]): Promise<PatternTestResult> {
    const res = await authenticatedFetch(`${API_URL}/api/shell/security-patterns/test`, {
      method: 'POST',
      body: JSON.stringify({ pattern, test_commands: testCommands })
    })
    if (!res.ok) throw new Error('Failed to test pattern')
    return res.json()
  },

  async getSecurityPatternStats(): Promise<SecurityPatternStats> {
    const res = await authenticatedFetch(`${API_URL}/api/shell/security-patterns/stats`)
    if (!res.ok) throw new Error('Failed to get pattern stats')
    return res.json()
  },

  // =========================================================================
  // Phase 20: Sentinel Security Agent API
  // =========================================================================

  async getSentinelConfig(): Promise<SentinelConfig> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/config`)
    if (!res.ok) throw new Error('Failed to get Sentinel config')
    return res.json()
  },

  async updateSentinelConfig(update: SentinelConfigUpdate): Promise<SentinelConfig> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/config`, {
      method: 'PUT',
      body: JSON.stringify(update),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to update Sentinel config' }))
      throw new Error(error.detail || 'Failed to update Sentinel config')
    }
    return res.json()
  },

  async getSentinelAgentConfig(agentId: number): Promise<SentinelAgentConfig | null> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/config/agent/${agentId}`)
    if (res.status === 404) return null
    if (!res.ok) throw new Error('Failed to get agent Sentinel config')
    return res.json()
  },

  async updateSentinelAgentConfig(agentId: number, update: SentinelAgentConfigUpdate): Promise<SentinelAgentConfig> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/config/agent/${agentId}`, {
      method: 'PUT',
      body: JSON.stringify(update),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to update agent Sentinel config' }))
      throw new Error(error.detail || 'Failed to update agent Sentinel config')
    }
    return res.json()
  },

  async deleteSentinelAgentConfig(agentId: number): Promise<{ deleted: boolean; message: string }> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/config/agent/${agentId}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete agent Sentinel config')
    return res.json()
  },

  async getSentinelLogs(params?: {
    limit?: number
    offset?: number
    threat_only?: boolean
    detection_type?: string
    analysis_type?: string
    agent_id?: number
  }): Promise<SentinelLog[]> {
    const searchParams = new URLSearchParams()
    if (params?.limit) searchParams.set('limit', params.limit.toString())
    if (params?.offset) searchParams.set('offset', params.offset.toString())
    if (params?.threat_only) searchParams.set('threat_only', 'true')
    if (params?.detection_type) searchParams.set('detection_type', params.detection_type)
    if (params?.analysis_type) searchParams.set('analysis_type', params.analysis_type)
    if (params?.agent_id) searchParams.set('agent_id', params.agent_id.toString())

    const url = `${API_URL}/api/sentinel/logs${searchParams.toString() ? `?${searchParams}` : ''}`
    const res = await authenticatedFetch(url)
    if (!res.ok) throw new Error('Failed to get Sentinel logs')
    return res.json()
  },

  async getSentinelStats(days: number = 7): Promise<SentinelStats> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/stats?days=${days}`)
    if (!res.ok) throw new Error('Failed to get Sentinel stats')
    return res.json()
  },

  async testSentinelAnalysis(inputText: string, detectionType: string = 'prompt_injection'): Promise<SentinelTestResult> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/test`, {
      method: 'POST',
      body: JSON.stringify({ input_text: inputText, detection_type: detectionType }),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to test Sentinel analysis' }))
      throw new Error(error.detail || 'Failed to test Sentinel analysis')
    }
    return res.json()
  },

  async getSentinelPrompts(): Promise<SentinelPrompt[]> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/prompts`)
    if (!res.ok) throw new Error('Failed to get Sentinel prompts')
    return res.json()
  },

  async updateSentinelPrompt(detectionType: string, prompt: string | null): Promise<{ success: boolean }> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/prompts/${detectionType}`, {
      method: 'PUT',
      body: JSON.stringify({ prompt }),
    })
    if (!res.ok) throw new Error('Failed to update Sentinel prompt')
    return res.json()
  },

  async getSentinelLLMProviders(): Promise<SentinelLLMProvider[]> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/llm/providers`)
    if (!res.ok) throw new Error('Failed to get LLM providers')
    return res.json()
  },

  async getSentinelLLMModels(provider: string): Promise<{ provider: string; models: string[] }> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/llm/models/${provider}`)
    if (!res.ok) throw new Error('Failed to get LLM models')
    return res.json()
  },

  async testSentinelLLMConnection(provider: string, model: string): Promise<SentinelLLMTestResult> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/llm/test`, {
      method: 'POST',
      body: JSON.stringify({ provider, model }),
    })
    if (!res.ok) throw new Error('Failed to test LLM connection')
    return res.json()
  },

  async getSentinelDetectionTypes(): Promise<Record<string, SentinelDetectionType>> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/detection-types`)
    if (!res.ok) throw new Error('Failed to get detection types')
    return res.json()
  },

  // =========================================================================
  // Phase 20 Enhancement: Sentinel Exceptions API
  // =========================================================================

  async getSentinelExceptions(params?: {
    agent_id?: number
    exception_type?: string
    active_only?: boolean
    include_system?: boolean
  }): Promise<SentinelException[]> {
    const searchParams = new URLSearchParams()
    if (params?.agent_id) searchParams.set('agent_id', params.agent_id.toString())
    if (params?.exception_type) searchParams.set('exception_type', params.exception_type)
    if (params?.active_only) searchParams.set('active_only', 'true')
    if (params?.include_system !== undefined) searchParams.set('include_system', params.include_system.toString())

    const url = `${API_URL}/api/sentinel/exceptions${searchParams.toString() ? `?${searchParams}` : ''}`
    const res = await authenticatedFetch(url)
    if (!res.ok) throw new Error('Failed to get Sentinel exceptions')
    return res.json()
  },

  async getSentinelException(exceptionId: number): Promise<SentinelException> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/exceptions/${exceptionId}`)
    if (!res.ok) throw new Error('Failed to get Sentinel exception')
    return res.json()
  },

  async createSentinelException(data: SentinelExceptionCreate): Promise<SentinelException> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/exceptions`, {
      method: 'POST',
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to create exception' }))
      throw new Error(error.detail || 'Failed to create Sentinel exception')
    }
    return res.json()
  },

  async updateSentinelException(exceptionId: number, data: SentinelExceptionUpdate): Promise<SentinelException> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/exceptions/${exceptionId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to update exception' }))
      throw new Error(error.detail || 'Failed to update Sentinel exception')
    }
    return res.json()
  },

  async deleteSentinelException(exceptionId: number): Promise<{ deleted: boolean; id: number }> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/exceptions/${exceptionId}`, {
      method: 'DELETE',
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to delete exception' }))
      throw new Error(error.detail || 'Failed to delete Sentinel exception')
    }
    return res.json()
  },

  async testSentinelException(exceptionId: number, data: SentinelExceptionTestRequest): Promise<SentinelExceptionTestResult> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/exceptions/${exceptionId}/test`, {
      method: 'POST',
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to test exception' }))
      throw new Error(error.detail || 'Failed to test Sentinel exception')
    }
    return res.json()
  },

  async toggleSentinelException(exceptionId: number): Promise<SentinelException> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/exceptions/${exceptionId}/toggle`, {
      method: 'PATCH',
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Failed to toggle exception' }))
      throw new Error(error.detail || 'Failed to toggle Sentinel exception')
    }
    return res.json()
  },

  // ─── Sentinel Security Profiles (v1.6.0) ─────────────────────────────

  async getSentinelProfiles(includeSystem = true): Promise<SentinelProfile[]> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/profiles?include_system=${includeSystem}`)
    if (!res.ok) await handleApiError(res, 'Failed to fetch security profiles')
    return res.json()
  },

  async getSentinelProfile(profileId: number): Promise<SentinelProfileDetail> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/profiles/${profileId}`)
    if (!res.ok) await handleApiError(res, 'Failed to fetch security profile')
    return res.json()
  },

  async createSentinelProfile(data: SentinelProfileCreate): Promise<SentinelProfile> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/profiles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) await handleApiError(res, 'Failed to create security profile')
    return res.json()
  },

  async updateSentinelProfile(profileId: number, data: SentinelProfileUpdate): Promise<SentinelProfile> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/profiles/${profileId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) await handleApiError(res, 'Failed to update security profile')
    return res.json()
  },

  async deleteSentinelProfile(profileId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/profiles/${profileId}`, {
      method: 'DELETE',
    })
    if (!res.ok) await handleApiError(res, 'Failed to delete security profile')
  },

  async cloneSentinelProfile(profileId: number, data: SentinelProfileCloneRequest): Promise<SentinelProfile> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/profiles/${profileId}/clone`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) await handleApiError(res, 'Failed to clone security profile')
    return res.json()
  },

  async getSentinelProfileAssignments(agentId?: number, skillType?: string): Promise<SentinelProfileAssignment[]> {
    const params = new URLSearchParams()
    if (agentId !== undefined) params.set('agent_id', agentId.toString())
    if (skillType) params.set('skill_type', skillType)
    const qs = params.toString()
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/profiles/assignments${qs ? `?${qs}` : ''}`)
    if (!res.ok) await handleApiError(res, 'Failed to fetch profile assignments')
    return res.json()
  },

  async assignSentinelProfile(data: SentinelProfileAssignRequest): Promise<SentinelProfileAssignment> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/profiles/assign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) await handleApiError(res, 'Failed to assign security profile')
    return res.json()
  },

  async removeSentinelProfileAssignment(assignmentId: number): Promise<void> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/profiles/assignments/${assignmentId}`, {
      method: 'DELETE',
    })
    if (!res.ok) await handleApiError(res, 'Failed to remove profile assignment')
  },

  async getSentinelEffectiveConfig(agentId?: number, skillType?: string): Promise<SentinelEffectiveConfig> {
    const params = new URLSearchParams()
    if (agentId !== undefined) params.set('agent_id', agentId.toString())
    if (skillType) params.set('skill_type', skillType)
    const qs = params.toString()
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/profiles/effective${qs ? `?${qs}` : ''}`)
    if (!res.ok) await handleApiError(res, 'Failed to fetch effective security config')
    return res.json()
  },

  async getSentinelHierarchy(): Promise<SentinelHierarchy> {
    const res = await authenticatedFetch(`${API_URL}/api/sentinel/profiles/hierarchy`)
    if (!res.ok) await handleApiError(res, 'Failed to fetch security hierarchy')
    return res.json()
  },
}

// Default export for convenience (used by prompts page and others)
export default api
