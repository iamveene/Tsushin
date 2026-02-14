from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, Float, ForeignKey, Index, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()

class Config(Base):
    __tablename__ = "config"

    id = Column(Integer, primary_key=True, default=1)

    # MCP Database Path
    messages_db_path = Column(Text, nullable=False)

    # Filter Configuration
    agent_number = Column(String(20), default="")  # Agent's WhatsApp number
    group_filters = Column(JSON, default=list)  # ["Work Group", "Family Group"]
    number_filters = Column(JSON, default=list)  # ["+5500000000001"]

    # Model Configuration
    model_provider = Column(String(20), default="gemini")  # "openai" | "anthropic" | "gemini"
    model_name = Column(Text, default="gemini-2.5-pro")

    # Memory Configuration
    memory_size = Column(Integer, default=1000)  # Updated from 10 to 1000

    # Tool Configuration - DEPRECATED: Tools migrated to Skills system
    # enable_google_search = Column(Boolean, default=False)  # REMOVED - use web_search skill
    search_provider = Column(String(20), default="brave")  # "brave" | "google" - used by SearchProviderRegistry
    # enabled_tools = Column(Text, default='[]')  # REMOVED - use AgentSkill table

    # Prompt Configuration
    system_prompt = Column(Text, default="You are a helpful assistant that can communicate in multiple languages. Detect the language the user is writing in and respond in the same language. Be concise, helpful, and adapt your tone to the context. Use tools when explicitly requested or when clearly beneficial.")
    response_template = Column(Text, default="{{answer}}")

    # Contact Mappings (JSON: {"contact_id": "display_name"})
    contact_mappings = Column(Text, default="{}")

    # Maintenance Mode
    maintenance_mode = Column(Boolean, default=False)
    maintenance_message = Column(Text, default="🔧 The bot is currently under maintenance. Please try again later.")

    # Emergency Stop (Bug Fix 2026-01-06)
    emergency_stop = Column(Boolean, default=False)

    # Conversation delay (global, WhatsApp-only)
    whatsapp_conversation_delay_seconds = Column(Float, default=5.0)

    # Group Message Context
    context_message_count = Column(Integer, default=10)  # Updated from 5 to 10
    context_char_limit = Column(Integer, default=1000)  # Already 1000, no change

    # Enhanced Trigger System
    dm_auto_mode = Column(Boolean, default=True)
    agent_phone_number = Column(String(50), default="175909696979085")
    agent_name = Column(String(100), default="Assistant")
    group_keywords = Column(Text, default="[]")  # JSON array

    # Semantic Search (Phase 4.1)
    enable_semantic_search = Column(Boolean, default=False)
    semantic_search_results = Column(Integer, default=5)
    semantic_similarity_threshold = Column(Float, default=0.3)

    # Ollama Configuration (Phase 5.2)
    ollama_base_url = Column(String(255), default="http://host.docker.internal:11434")  # Ollama server URL (Docker-friendly default)
    ollama_api_key = Column(String(500), nullable=True)  # Optional API key for remote/secured Ollama

    # Asana MCP Server Configuration (Hub Integration)
    # Dynamically registered via POST https://mcp.asana.com/register
    asana_mcp_client_id = Column(String(100), nullable=True)  # From dynamic client registration
    asana_mcp_client_secret = Column(String(500), nullable=True)  # From dynamic client registration
    asana_mcp_registered = Column(Boolean, default=False)  # True after successful registration

    # Encryption Keys (Phase 7.10: SaaS-Ready Configuration)
    # Moved from .env to enable UI configuration and per-tenant isolation
    google_encryption_key = Column(String(500), nullable=True)  # Google OAuth token encryption (Fernet key)
    asana_encryption_key = Column(String(500), nullable=True)  # Asana/Hub OAuth token encryption (Fernet key)

    # Service-specific encryption keys (MED-001 Security Fix)
    # Each service now has its own encryption key to limit blast radius if one is compromised
    telegram_encryption_key = Column(String(500), nullable=True)  # Telegram bot token encryption (Fernet key)
    amadeus_encryption_key = Column(String(500), nullable=True)  # Amadeus API credentials encryption (Fernet key)
    api_key_encryption_key = Column(String(500), nullable=True)  # LLM API key encryption (Fernet key)

    # System-Level AI Configuration (Phase 17: Tenant-Configurable System AI)
    # These settings control which AI provider/model is used for system operations
    # (intent classification, skill routing, AI summaries, flow processing)
    # This allows tenants to switch providers if one has issues (e.g., Gemini down)
    system_ai_provider = Column(String(20), default="gemini")  # gemini, anthropic, openai, openrouter
    system_ai_model = Column(String(100), default="gemini-2.5-flash")  # Default: fast/cheap model for system ops

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Memory(Base):
    __tablename__ = "memory"

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, nullable=False, index=True)  # FK to Agent - per-agent memory isolation
    sender_key = Column(String(255), nullable=False, index=True)  # chat_id or phone number
    messages_json = Column(JSON, default=list)  # [{"role": "user", "content": "...", "timestamp": "..."}]
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint: one memory per agent per sender
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class MessageCache(Base):
    __tablename__ = "message_cache"

    id = Column(Integer, primary_key=True)
    source_id = Column(Text, unique=True, nullable=False, index=True)  # MCP message ID
    chat_id = Column(Text, nullable=False, index=True)
    chat_name = Column(Text)
    sender = Column(Text)
    sender_name = Column(Text)
    body = Column(Text)
    timestamp = Column(Text, nullable=False)  # Datetime string from MCP
    is_group = Column(Boolean, default=False)
    matched_filter = Column(Boolean, default=False)
    seen_at = Column(DateTime, default=datetime.utcnow)

    # Phase 10.1.1: Channel tracking for multi-channel analytics
    channel = Column(String(20), nullable=True, index=True)  # "whatsapp" | "playground" | "telegram"

    # HIGH-012: Multi-tenancy isolation for message cache
    tenant_id = Column(String(50), nullable=True, index=True)


class Contact(Base):
    """
    Contact/Identity mapping for users and agents.
    Allows the agent to recognize users by multiple identifiers (whatsapp_id, phone, friendly name).
    Phase 4.3: Added is_dm_trigger for DM trigger selection.
    Phase 7.6.2: Added tenant_id and user_id for multi-tenancy.
    Phase 10.2: Channel identifiers being migrated to ContactChannelMapping table.
    """
    __tablename__ = "contact"

    id = Column(Integer, primary_key=True)
    friendly_name = Column(String(100), nullable=False, unique=True)  # "Alice", "Bob", "Agent1"
    whatsapp_id = Column(String(50), nullable=True, index=True)  # WhatsApp internal ID - DEPRECATED: Use channel_mappings
    phone_number = Column(String(20), nullable=True, index=True)  # Phone number - DEPRECATED: Use channel_mappings

    # Phase 10.1.1: Telegram identifiers for cross-channel memory
    telegram_id = Column(String(50), nullable=True, index=True)  # Telegram user ID (numeric) - DEPRECATED: Use channel_mappings
    telegram_username = Column(String(50), nullable=True)  # Optional: @username without @ - DEPRECATED: Use channel_mappings

    role = Column(String(20), default="user")  # "user" | "agent"
    is_active = Column(Boolean, default=True)
    is_dm_trigger = Column(Boolean, default=True)  # Phase 4.3: Trigger agent on DM from this contact (default True for fresh installs)
    notes = Column(Text)  # Optional notes about the contact

    # Phase 7.6.2: Multi-tenancy support
    tenant_id = Column(String(50), nullable=True, index=True)  # FK to tenant
    user_id = Column(Integer, nullable=True, index=True)  # FK to user who created the contact

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Phase 10.2: Relationship to channel mappings
    channel_mappings = relationship("ContactChannelMapping", back_populates="contact", cascade="all, delete-orphan")


class ContactChannelMapping(Base):
    """
    Phase 10.2: Universal mapping table for contact identifiers across all communication channels.
    Enables flexible, scalable channel support without schema changes.

    Replaces the channel-specific columns (whatsapp_id, telegram_id, phone_number) on Contact table.
    Allows one contact to have multiple identifiers across different channels (WhatsApp, Telegram, Discord, etc.).
    """
    __tablename__ = "contact_channel_mapping"

    id = Column(Integer, primary_key=True)
    contact_id = Column(Integer, ForeignKey('contact.id'), nullable=False, index=True)

    # Channel identification
    channel_type = Column(String(20), nullable=False, index=True)  # 'whatsapp', 'telegram', 'phone', 'discord', 'email', etc.
    channel_identifier = Column(String(255), nullable=False, index=True)  # The primary ID (user_id, phone, email, etc.)

    # Optional metadata for each channel (JSON) - renamed from 'metadata' to avoid SQLAlchemy reserved word
    channel_metadata = Column(JSON, nullable=True)  # {'username': '@johndoe', 'display_name': 'John Doe', etc.}

    # Multi-tenancy
    tenant_id = Column(String(50), nullable=False, index=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Constraints
    __table_args__ = (
        # One contact can have multiple channels, but identifier must be unique per channel per tenant
        UniqueConstraint('channel_type', 'channel_identifier', 'tenant_id', name='uix_channel_identifier'),
        Index('ix_contact_channel_tenant', 'contact_id', 'channel_type', 'tenant_id'),
    )

    # Relationship
    contact = relationship("Contact", back_populates="channel_mappings")


class TonePreset(Base):
    """
    Phase 4.4: Tone presets for agent personality customization.
    Defines reusable tone templates that can be injected into agent system prompts.
    Phase 7.9.2: Added tenant_id for multi-tenancy support.
    """
    __tablename__ = "tone_preset"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)  # "Friendly", "Professional", "Humorous" - unique per tenant
    description = Column(Text, nullable=False)  # The tone description to inject into system prompt
    is_system = Column(Boolean, default=False)  # True for built-in presets, False for custom

    # Phase 7.9.2: Multi-tenancy support
    tenant_id = Column(String(50), nullable=True, index=True)  # FK to tenant (NULL = shared/system preset)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Persona(Base):
    """
    Phase 5.1: Persona management for reusable agent personalities.
    Phase 5.2: Enhanced with role, skills, tools, and knowledge base capabilities.
    Phase 7.9.2: Added tenant_id for multi-tenancy support.
    Defines comprehensive personality templates that can be assigned to multiple agents,
    including tone presets, personality traits, role-playing characteristics, and specialized capabilities.
    """
    __tablename__ = "persona"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)  # "Friendly Assistant", "Professional Expert" - unique per tenant
    description = Column(Text, nullable=False)  # Description of the persona

    # Phase 5.2: Role and identity
    role = Column(String(200), nullable=True)  # "Customer Support Specialist", "Technical Expert", "Sales Representative"
    role_description = Column(Text, nullable=True)  # Detailed role expectations and responsibilities

    # Tone configuration (same as Agent had before)
    tone_preset_id = Column(Integer, nullable=True)  # FK to TonePreset, null for custom tone
    custom_tone = Column(Text, nullable=True)  # Custom tone description if tone_preset_id is null

    # Personality traits
    personality_traits = Column(Text, nullable=True)  # Additional personality characteristics (e.g., "Empathetic, patient, enthusiastic")

    # Phase 5.2: Capabilities - JSON arrays of IDs
    enabled_skills = Column(JSON, default=list)  # [skill_id1, skill_id2] - Links to Skill table
    # Note: enabled_tools (built-in) removed - was redundant with agent.enabled_tools and never used for filtering
    enabled_sandboxed_tools = Column(JSON, default=list)  # [sandboxed_tool_id1, sandboxed_tool_id2] - Links to SandboxedTool table
    enabled_knowledge_bases = Column(JSON, default=list)  # [kb_id1, kb_id2] - Links to KnowledgeBase table

    # Backward compatibility alias
    @property
    def enabled_custom_tools(self):
        return self.enabled_sandboxed_tools

    @enabled_custom_tools.setter
    def enabled_custom_tools(self, value):
        self.enabled_sandboxed_tools = value

    # Phase 5.2: Safety and constraints
    guardrails = Column(Text, nullable=True)  # Safety rules and constraints (e.g., "Never discuss sensitive information", "Always verify before making changes")

    # AI-generated summary
    ai_summary = Column(Text, nullable=True)  # Auto-generated summary of persona characteristics (custom personas only)

    # Status
    is_active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)  # True for built-in personas

    # Phase 7.9.2: Multi-tenancy support
    tenant_id = Column(String(50), nullable=True, index=True)  # FK to tenant (NULL = shared/system persona)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Agent(Base):
    """
    Phase 4.4: Multi-agent support with individual configurations.
    Phase 5.1: Updated to link Persona instead of having tone directly.
    Each agent has their own identity, system prompt, persona, keywords, and tool configuration.
    """
    __tablename__ = "agent"

    id = Column(Integer, primary_key=True)

    # Identity (linked to Contact table)
    contact_id = Column(Integer, nullable=False, unique=True)  # FK to Contact with role="agent"

    # Configuration
    system_prompt = Column(Text, nullable=False)  # Can include {{PERSONA}} or {{TONE}} placeholder
    persona_id = Column(Integer, nullable=True)  # FK to Persona (replaces tone_preset_id/custom_tone)

    # Legacy tone fields (kept for backward compatibility, will be migrated)
    tone_preset_id = Column(Integer, nullable=True)  # DEPRECATED: Use persona_id instead
    custom_tone = Column(Text, nullable=True)  # DEPRECATED: Use persona_id instead

    # Trigger keywords for group chats
    keywords = Column(JSON, default=list)  # ["help", "assistant", "bot"]

    # Tool configuration - DEPRECATED: Migrated to Skills system
    # enabled_tools removed - use AgentSkill table for skills like web_search, weather, web_scraping

    # Model configuration
    model_provider = Column(String(20), default="gemini")  # "openai" | "anthropic" | "gemini"
    model_name = Column(String(100), default="gemini-2.5-pro")

    # Response formatting
    response_template = Column(Text, default="@{agent_name}: {response}")  # Template for response formatting

    # Per-Agent Configuration (NULL = use system default)
    # Memory Configuration
    memory_size = Column(Integer, nullable=True)  # Ring buffer size per sender (NULL = use system default)
    memory_isolation_mode = Column(String(20), default="isolated")  # "isolated" | "shared" | "channel_isolated"

    # Trigger Configuration
    trigger_dm_enabled = Column(Boolean, nullable=True)  # Enable DM auto-response (NULL = use system default)
    trigger_group_filters = Column(JSON, nullable=True)  # Group names to monitor (NULL = use system default)
    trigger_number_filters = Column(JSON, nullable=True)  # Phone numbers to monitor (NULL = use system default)

    # Group Message Context
    context_message_count = Column(Integer, nullable=True)  # Messages to fetch for context (NULL = use system default)
    context_char_limit = Column(Integer, nullable=True)  # Character limit for context (NULL = use system default)

    # Semantic Search Configuration (Phase 4.8)
    enable_semantic_search = Column(Boolean, default=True)  # Enable semantic memory for this agent
    semantic_search_results = Column(Integer, default=10)  # Number of semantic results to include
    semantic_similarity_threshold = Column(Float, default=0.5)  # Minimum similarity threshold (0.0-1.0)
    chroma_db_path = Column(String(500), nullable=True)  # Per-agent ChromaDB path

    # Phase 10: Channel Configuration
    # Determines which channels this agent can interact through
    enabled_channels = Column(JSON, default=["playground", "whatsapp"])  # Available: playground, whatsapp, telegram
    whatsapp_integration_id = Column(Integer, ForeignKey("whatsapp_mcp_instance.id", ondelete="SET NULL"), nullable=True)  # Specific MCP instance
    telegram_integration_id = Column(Integer, nullable=True)  # Future: FK to TelegramBotInstance

    # Avatar
    avatar = Column(String(50), nullable=True, default=None)  # Avatar slug (e.g., "samurai", "robot", "ninja")

    # Status
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)  # Default agent for new chats

    # Phase 7.6.2: Multi-tenancy support
    tenant_id = Column(String(50), nullable=True, index=True)  # FK to tenant
    user_id = Column(Integer, nullable=True, index=True)  # FK to user who created the agent

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    # hub_integration removed - use AgentSkillIntegration for skill provider configuration
    whatsapp_integration = relationship("WhatsAppMCPInstance", foreign_keys=[whatsapp_integration_id])


class ContactAgentMapping(Base):
    """
    Phase 4.5: Maps contacts to custom agents for personalized agent assignment.
    Allows per-user agent customization for direct messages and group mentions.
    """
    __tablename__ = "contact_agent_mapping"

    id = Column(Integer, primary_key=True)
    contact_id = Column(Integer, nullable=False, index=True)  # FK to Contact
    agent_id = Column(Integer, nullable=False)  # FK to Agent
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ApiKey(Base):
    """
    Phase 4.6: Stores API keys for LLM providers and tool services.
    Phase 7.9.2: Added tenant_id for multi-tenancy support.
    Phase SEC-001: Added encryption at rest for API keys (CRIT-003 fix).
    Allows users to configure API keys via UI instead of environment variables.
    """
    __tablename__ = "api_key"

    id = Column(Integer, primary_key=True)
    service = Column(String(50), nullable=False, index=True)  # 'anthropic', 'openai', 'gemini', 'brave_search', 'openweather'
    api_key = Column(String(500), nullable=True)  # DEPRECATED: Plaintext key (kept for migration, set to NULL after encryption)
    api_key_encrypted = Column(Text, nullable=True)  # Phase SEC-001: Encrypted API key (Fernet)
    is_active = Column(Boolean, default=True)

    # Phase 7.9.2: Multi-tenancy support
    tenant_id = Column(String(50), nullable=True, index=True)  # FK to tenant (NULL = system-wide key)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint: one key per service per tenant
    __table_args__ = (
        Index('idx_api_key_service_tenant', 'service', 'tenant_id', unique=True),
        {"sqlite_autoincrement": True},
    )


class SemanticKnowledge(Base):
    """
    Phase 4.8: Stores learned facts about users (per-agent semantic memory).
    Each agent maintains their own knowledge base about users.
    """
    __tablename__ = "semantic_knowledge"

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, nullable=False, index=True)  # FK to Agent
    user_id = Column(String(255), nullable=False, index=True)  # Sender key (phone/chat_id)
    topic = Column(String(100), nullable=False, index=True)  # "preferences", "personal_info", "history"
    key = Column(String(100), nullable=False)  # "favorite_color", "job", "birthday"
    value = Column(Text, nullable=False)  # The actual fact
    confidence = Column(Float, default=1.0)  # Confidence score (0.0-1.0)
    learned_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SharedMemory(Base):
    """
    Phase 4.8: Cross-agent shared knowledge pool with permission-based access.
    Allows agents to share common knowledge (facts, context) with explicit permissions.
    Phase 7.9.2 (CRIT-010): Added tenant_id for multi-tenancy security.
    """
    __tablename__ = "shared_memory"

    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)  # The shared knowledge/fact
    topic = Column(String(100), nullable=True, index=True)  # Optional topic categorization
    shared_by_agent = Column(Integer, nullable=False, index=True)  # FK to Agent who shared it
    accessible_to = Column(JSON, default=list)  # Agent IDs that can access, empty = all agents
    meta_data = Column(JSON, default=dict)  # Additional metadata (source, context, etc.) - renamed to avoid SQLAlchemy reserved word
    tenant_id = Column(String(50), nullable=True, index=True)  # CRIT-010: Multi-tenancy isolation
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentRun(Base):
    __tablename__ = "agent_run"

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, nullable=True)  # Phase 4.4: FK to Agent, null for backward compatibility
    triggered_by = Column(String(20), nullable=False)  # "group" | "number" | "manual" | "contact_trigger" | "auto"
    sender_key = Column(String(255), nullable=False)
    input_preview = Column(Text)  # First 200 chars
    skill_type = Column(String(50), nullable=True)  # Skill that processed this message (e.g., "flows", "asana", "audio_transcript")
    tool_used = Column(String(100))  # "google_search" or null
    tool_result = Column(Text)  # Raw tool response/results
    model_used = Column(String(100))
    token_usage_json = Column(JSON)  # {"prompt": 100, "completion": 50, "total": 150}
    output_preview = Column(Text)  # First 500 chars
    status = Column(String(20), default="success")  # "success" | "error"
    error_text = Column(Text)
    execution_time_ms = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)


class TokenUsage(Base):
    """
    Phase 7.2: Token consumption tracking for cost analytics.
    Tracks token usage per agent, model, and operation type.
    """
    __tablename__ = "token_usage"

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, nullable=True, index=True)  # FK to Agent, null for system operations
    agent_run_id = Column(Integer, nullable=True, index=True)  # FK to AgentRun if linked to a run

    # Operation details
    operation_type = Column(String(50), nullable=False, index=True)  # "message_processing", "audio_transcript", "skill_classification", etc.
    skill_type = Column(String(50), nullable=True, index=True)  # Skill that consumed tokens

    # Model details
    model_provider = Column(String(20), nullable=False, index=True)  # "openai", "anthropic", "gemini", "ollama"
    model_name = Column(String(100), nullable=False, index=True)  # "gpt-4", "claude-3-5-sonnet", "gemini-2.5-pro", etc.

    # Token counts
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)

    # Cost estimation (USD)
    estimated_cost = Column(Float, default=0.0)

    # Context
    sender_key = Column(String(255), nullable=True, index=True)  # User who triggered this
    message_id = Column(String(100), nullable=True)  # MCP message ID if applicable

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Indexes for analytics queries
    __table_args__ = (
        Index('idx_token_usage_agent_created', 'agent_id', 'created_at'),
        Index('idx_token_usage_model_created', 'model_provider', 'model_name', 'created_at'),
        Index('idx_token_usage_operation_created', 'operation_type', 'created_at'),
        {"sqlite_autoincrement": True},
    )


class ModelPricing(Base):
    """
    Configurable model pricing for cost estimation.
    Allows tenants to adjust pricing rates per model for accurate cost tracking.
    Falls back to default pricing if no custom pricing is set.
    """
    __tablename__ = "model_pricing"

    id = Column(Integer, primary_key=True)

    # Model identification
    model_provider = Column(String(20), nullable=False)  # "openai", "anthropic", "gemini", "ollama"
    model_name = Column(String(100), nullable=False)  # "gpt-4o", "claude-3-5-sonnet", etc.

    # Pricing per 1M tokens (USD)
    input_cost_per_million = Column(Float, nullable=False, default=0.0)  # Cost per 1M input tokens
    output_cost_per_million = Column(Float, nullable=False, default=0.0)  # Cost per 1M output tokens

    # Optional: Cached input pricing (some providers offer discounts)
    cached_input_cost_per_million = Column(Float, nullable=True)  # Cost per 1M cached input tokens

    # Display name for UI
    display_name = Column(String(100), nullable=True)  # "GPT-4o", "Claude 3.5 Sonnet", etc.

    # Multi-tenancy
    tenant_id = Column(String(50), nullable=True, index=True)  # NULL = default/system pricing

    # Whether this is active (can be disabled without deleting)
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint: one pricing per model per tenant
    __table_args__ = (
        UniqueConstraint('tenant_id', 'model_provider', 'model_name', name='uix_model_pricing_tenant_model'),
        Index('idx_model_pricing_model', 'model_provider', 'model_name'),
        {"sqlite_autoincrement": True},
    )


class AgentSkill(Base):
    """
    Phase 5.0: Skills System
    Stores skill configurations for each agent (audio transcription, TTS, etc.)
    """
    __tablename__ = "agent_skill"

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, nullable=False)  # FK to Agent
    skill_type = Column(String(50), nullable=False)  # "audio_transcript" | "audio_response"
    is_enabled = Column(Boolean, default=True)
    config = Column(JSON, default=dict)  # Skill-specific configuration
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint: one skill config per agent per skill type
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class AgentKnowledge(Base):
    """
    Phase 5.0: Knowledge Base System
    Stores documents/knowledge uploaded for specific agents.
    """
    __tablename__ = "agent_knowledge"

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, nullable=False, index=True)  # FK to Agent
    document_name = Column(String(255), nullable=False)
    document_type = Column(String(20), nullable=False)  # "pdf", "txt", "docx", "csv", "json"
    file_path = Column(String(500), nullable=False)  # Path to stored file
    file_size_bytes = Column(Integer, nullable=False)
    num_chunks = Column(Integer, default=0)  # Number of text chunks created
    status = Column(String(20), default="pending")  # "pending", "processing", "completed", "failed"
    error_message = Column(Text, nullable=True)
    upload_date = Column(DateTime, default=datetime.utcnow)
    processed_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KnowledgeChunk(Base):
    """
    Phase 5.0: Knowledge Base System
    Stores text chunks extracted from documents with embeddings for semantic search.
    """
    __tablename__ = "knowledge_chunk"

    id = Column(Integer, primary_key=True)
    knowledge_id = Column(Integer, nullable=False, index=True)  # FK to AgentKnowledge
    chunk_index = Column(Integer, nullable=False)  # Order of chunk in document
    content = Column(Text, nullable=False)  # Text content of the chunk
    char_count = Column(Integer, nullable=False)  # Character count
    metadata_json = Column(JSON, default=dict)  # Additional metadata (page number, section, etc.)
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================================
# Phase 14.2: Playground Document Attachments
# ============================================================================

class PlaygroundDocument(Base):
    """
    Phase 14.2: Document Attachments on Playground UI
    Stores documents uploaded during Playground conversations.
    Documents are embedded into a conversation-scoped knowledge base.
    """
    __tablename__ = "playground_document"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)  # FK to tenant
    user_id = Column(Integer, nullable=False, index=True)  # FK to user
    agent_id = Column(Integer, nullable=False, index=True)  # FK to agent
    conversation_id = Column(String(100), nullable=False, index=True)  # Unique conversation identifier
    document_name = Column(String(255), nullable=False)
    document_type = Column(String(20), nullable=False)  # pdf, txt, csv, json, xlsx, docx, md, rtf
    file_path = Column(String(500), nullable=False)  # Path to stored file
    file_size_bytes = Column(Integer, nullable=False)
    num_chunks = Column(Integer, default=0)  # Number of text chunks created
    embedding_model = Column(String(100), default="all-MiniLM-L6-v2")  # Embedding model used
    chunk_size = Column(Integer, default=500)  # Chunk size in characters
    chunk_overlap = Column(Integer, default=50)  # Overlap between chunks
    status = Column(String(20), default="pending")  # pending, processing, completed, failed
    error_message = Column(Text, nullable=True)
    upload_date = Column(DateTime, default=datetime.utcnow)
    processed_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PlaygroundDocumentChunk(Base):
    """
    Phase 14.2: Document Attachments on Playground UI
    Stores text chunks from playground documents with embeddings.
    """
    __tablename__ = "playground_document_chunk"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, nullable=False, index=True)  # FK to PlaygroundDocument
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    char_count = Column(Integer, nullable=False)
    metadata_json = Column(JSON, default=dict)  # page number, section, etc.
    created_at = Column(DateTime, default=datetime.utcnow)


class PlaygroundUserSettings(Base):
    """
    Phase 14.3: Playground Settings
    Stores user-specific playground settings per tenant.
    """
    __tablename__ = "playground_user_settings"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    settings_json = Column(JSON, default=dict)  # All settings as JSON
    # Default settings structure:
    # {
    #   "documentProcessing": {
    #     "embeddingModel": "all-MiniLM-L6-v2",
    #     "chunkSize": 500,
    #     "chunkOverlap": 50,
    #     "maxDocuments": 10
    #   },
    #   "audioSettings": {
    #     "ttsProvider": "kokoro",
    #     "ttsVoice": "pf_dora",
    #     "autoPlayResponses": false
    #   }
    # }
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('tenant_id', 'user_id', name='uq_playground_user_settings'),
    )


# ============================================================================
# Phase 14.4: Projects System
# ============================================================================

class Project(Base):
    """
    Phase 14.4: Projects on Playground UI
    Phase 15: Changed to tenant-wide access (not per-user ownership)

    Isolated workspaces with dedicated knowledge bases, conversation history, and tool configurations.
    Projects are now accessible to all users within a tenant, with creator tracked for audit.
    """
    __tablename__ = "project"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)

    # Phase 15: Changed from user-owned to tenant-wide with creator audit
    # user_id is deprecated, use creator_id instead (kept for backward compatibility)
    user_id = Column(Integer, nullable=True, index=True)  # DEPRECATED: Use creator_id
    creator_id = Column(Integer, nullable=True, index=True)  # Who created it (audit trail)

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(50), default="folder")  # emoji or icon name
    color = Column(String(20), default="blue")  # teal, indigo, purple, pink, orange, etc.
    agent_id = Column(Integer, nullable=True)  # Default agent for project

    # Project-specific settings
    system_prompt_override = Column(Text, nullable=True)  # Custom instructions
    enabled_tools = Column(JSON, default=list)  # Built-in tool IDs
    enabled_sandboxed_tools = Column(JSON, default=list)  # Sandboxed tool IDs

    # Backward compatibility alias
    @property
    def enabled_custom_tools(self):
        return self.enabled_sandboxed_tools

    @enabled_custom_tools.setter
    def enabled_custom_tools(self, value):
        self.enabled_sandboxed_tools = value

    # Phase 16: Knowledge Base Configuration
    kb_chunk_size = Column(Integer, default=500)  # Characters per chunk
    kb_chunk_overlap = Column(Integer, default=50)  # Overlap between chunks
    kb_embedding_model = Column(String(100), default="all-MiniLM-L6-v2")  # Embedding model

    # Phase 16: Memory Configuration
    enable_semantic_memory = Column(Boolean, default=True)  # Enable episodic memory with embeddings
    semantic_memory_results = Column(Integer, default=10)  # Max results from semantic search
    semantic_similarity_threshold = Column(Float, default=0.5)  # Min similarity score (0.0-1.0)
    enable_factual_memory = Column(Boolean, default=True)  # Enable factual extraction
    factual_extraction_threshold = Column(Integer, default=5)  # Messages before fact extraction

    # Status
    is_archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_project_tenant', 'tenant_id'),
        Index('idx_project_creator', 'creator_id'),
    )


class ProjectKnowledge(Base):
    """
    Phase 14.4: Project-specific Knowledge Base
    Documents uploaded to a project, isolated from global agent knowledge.
    """
    __tablename__ = "project_knowledge"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)  # FK to Project
    document_name = Column(String(255), nullable=False)
    document_type = Column(String(20), nullable=False)  # pdf, txt, csv, json, etc.
    file_path = Column(String(500), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    num_chunks = Column(Integer, default=0)
    status = Column(String(20), default="pending")  # pending, processing, completed, failed
    error_message = Column(Text, nullable=True)
    upload_date = Column(DateTime, default=datetime.utcnow)
    processed_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProjectKnowledgeChunk(Base):
    """
    Phase 14.4: Project Knowledge Chunks
    Text chunks from project documents.
    """
    __tablename__ = "project_knowledge_chunk"

    id = Column(Integer, primary_key=True)
    knowledge_id = Column(Integer, nullable=False, index=True)  # FK to ProjectKnowledge
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    char_count = Column(Integer, nullable=False)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProjectConversation(Base):
    """
    Phase 14.4: Project Conversations
    Multiple conversations per project with full history.
    """
    __tablename__ = "project_conversation"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)  # FK to Project
    title = Column(String(200), nullable=True)  # Auto-generated from first message
    messages_json = Column(JSON, default=list)  # List of {role, content, timestamp}
    is_archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================================================
# Phase 16: Project Memory System - Semantic & Factual Memory
# ============================================================================

class ProjectSemanticMemory(Base):
    """
    Phase 16: Project-level episodic memory with semantic search.
    Stores conversation history with embeddings for each project.
    Separate from agent memory - combined at query time.
    """
    __tablename__ = "project_semantic_memory"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False, index=True)
    sender_key = Column(String(100), nullable=False, index=True)  # Who sent this message
    content = Column(Text, nullable=False)  # Message content
    role = Column(String(20), nullable=False)  # "user" | "assistant"
    embedding_id = Column(String(100), nullable=True)  # ChromaDB reference ID
    metadata_json = Column(JSON, default=dict)  # Additional metadata
    timestamp = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_proj_semantic_project', 'project_id'),
        Index('idx_proj_semantic_sender', 'project_id', 'sender_key'),
        {"sqlite_autoincrement": True},
    )


class ProjectFactMemory(Base):
    """
    Phase 16: Project-level factual memory.
    Learned facts about project context, users, and documents.
    Can be manually added or AI-extracted from conversations.
    """
    __tablename__ = "project_fact_memory"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False, index=True)
    sender_key = Column(String(100), nullable=True, index=True)  # NULL = project-wide fact
    topic = Column(String(100), nullable=False)  # Category: company_info, preferences, etc.
    key = Column(String(255), nullable=False)  # Fact key: company_name, favorite_color
    value = Column(Text, nullable=False)  # Fact value
    confidence = Column(Float, default=1.0)  # 0.0 - 1.0 confidence score
    source = Column(String(50), default="manual")  # "manual" | "conversation" | "document"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_proj_fact_project', 'project_id'),
        Index('idx_proj_fact_topic', 'project_id', 'topic'),
        Index('idx_proj_fact_sender', 'project_id', 'sender_key'),
        UniqueConstraint('project_id', 'sender_key', 'topic', 'key', name='uq_project_fact'),
        {"sqlite_autoincrement": True},
    )


# ============================================================================
# Phase 16: Slash Command System
# ============================================================================

class SlashCommand(Base):
    """
    Phase 16: Centralized slash command registry.
    Defines available commands with multilingual support and custom handlers.
    Works across all channels (WhatsApp, Playground, Telegram).
    """
    __tablename__ = "slash_command"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)  # "_system" for defaults
    category = Column(String(30), nullable=False)  # project, agent, tool, memory, system
    command_name = Column(String(50), nullable=False)  # "project enter", "invoke", etc.
    language_code = Column(String(10), default="en")  # en, pt, es, etc.
    pattern = Column(String(300), nullable=False)  # Regex pattern for matching
    aliases = Column(JSON, default=list)  # Alternative triggers ["p", "proj"]
    description = Column(Text, nullable=True)  # User-facing description
    help_text = Column(Text, nullable=True)  # Detailed help
    permission_required = Column(String(50), nullable=True)  # Required permission
    is_enabled = Column(Boolean, default=True)
    handler_type = Column(String(30), default="built-in")  # built-in, custom, webhook
    handler_config = Column(JSON, default=dict)  # Handler-specific configuration
    sort_order = Column(Integer, default=0)  # Display order in command palette
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_slash_cmd_tenant', 'tenant_id'),
        Index('idx_slash_cmd_category', 'tenant_id', 'category'),
        UniqueConstraint('tenant_id', 'command_name', 'language_code', name='uq_slash_command'),
        {"sqlite_autoincrement": True},
    )


# ============================================================================
# Phase 15: Skill Projects - Cross-Channel Project Interaction
# ============================================================================

class AgentProjectAccess(Base):
    """
    Phase 15: Skill Projects - Agent-Project Permission System
    Controls which agents can interact with which projects.

    When creating a project, select which agents have access (multi-select in UI).
    Agents NOT in AgentProjectAccess for a project cannot interact with it.
    This prevents memory contamination by design - unauthorized agents never see project data.
    """
    __tablename__ = "agent_project_access"

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey("agent.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False, index=True)
    can_write = Column(Boolean, default=True)  # Can upload documents via commands
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('agent_id', 'project_id', name='uq_agent_project'),
        Index('idx_agent_project_agent', 'agent_id'),
        Index('idx_agent_project_project', 'project_id'),
        {"sqlite_autoincrement": True},
    )


class UserProjectSession(Base):
    """
    Phase 15: Skill Projects - User Project Session Tracking
    Tracks which project a user is currently working in per channel.

    Users can only be in ONE project at a time per agent+channel combination.
    This enables cross-channel project interaction via text commands.

    Example:
        User sends "acessar projeto ACME" via WhatsApp
        → Creates session: UserProjectSession(sender_key="5500000000001", project_id=5, channel="whatsapp")
        → All subsequent messages from this user go to project context
        → User sends "sair do projeto" to exit
    """
    __tablename__ = "user_project_session"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    sender_key = Column(String(100), nullable=False)  # Normalized identity (phone or user_id)
    agent_id = Column(Integer, ForeignKey("agent.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=True)  # NULL = not in project
    channel = Column(String(20), nullable=False)  # "whatsapp" | "playground" | "telegram"
    conversation_id = Column(Integer, ForeignKey("project_conversation.id"), nullable=True)
    entered_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        # One active session per user+agent+channel
        UniqueConstraint('tenant_id', 'sender_key', 'agent_id', 'channel', name='uq_user_project_session'),
        Index('idx_session_lookup', 'tenant_id', 'sender_key', 'channel'),
        {"sqlite_autoincrement": True},
    )


class ProjectCommandPattern(Base):
    """
    Phase 15: Skill Projects - Multilingual Command System
    Configurable command patterns for project interactions, supporting multiple languages.

    Command detection flow:
    1. Incoming message checked against all active patterns for tenant
    2. Patterns matched in order: enter → exit → upload → list → help
    3. If match found, execute command handler
    4. If no match and user is in project, process as project conversation
    5. If no match and not in project, process as standard agent conversation

    Default patterns support PT and EN for: enter, exit, upload, list, help commands.
    """
    __tablename__ = "project_command_pattern"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    command_type = Column(String(30), nullable=False)  # "enter" | "exit" | "upload" | "list" | "help"
    language_code = Column(String(10), nullable=False)  # "en" | "pt" | "es" | "fr" | etc.
    pattern = Column(String(200), nullable=False)  # Regex or template with {project_name}
    response_template = Column(Text, nullable=True)  # Response message template
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('tenant_id', 'command_type', 'language_code', name='uq_command_pattern'),
        Index('idx_command_pattern_tenant', 'tenant_id'),
        {"sqlite_autoincrement": True},
    )


# ============================================================================
# Sandboxed Tools System (formerly CustomTools - renamed in Phase 6 of Skills-as-Tools)
# Tools that run in isolated Docker containers
# ============================================================================

class SandboxedTool(Base):
    """
    Sandboxed Tools System (formerly CustomTool).
    Phase 6.1: Original implementation as CustomTools
    Phase 7.9: Added tenant_id for multi-tenancy
    Phase: Custom Tools Hub - Added execution_mode for container execution
    Skills-as-Tools Phase 6: Renamed from CustomTool to SandboxedTool for clarity

    Defines tools that run in isolated Docker containers (nmap, nuclei, etc.).
    Distinct from Skills which run in-process.
    """
    __tablename__ = "sandboxed_tools"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), nullable=True, index=True)  # FK to tenant (Phase 7.9)
    name = Column(String(100), nullable=False)  # e.g., "nuclei", "nmap" - unique within tenant
    tool_type = Column(String(20), nullable=False)  # 'command', 'webhook', 'http'
    system_prompt = Column(Text, nullable=False)  # Custom prompt with placeholders
    # DEPRECATED: workspace_dir is not used - execution always uses /workspace in container
    # Kept for backward compatibility, will be removed in future version
    workspace_dir = Column(String(255))  # DEPRECATED - not used, see sandboxed_tool_service.py
    execution_mode = Column(String(20), default='container')  # 'local' | 'container' (default: container)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SandboxedToolCommand(Base):
    """
    Sandboxed Tools System (formerly CustomToolCommand).
    Defines commands available for a sandboxed tool.
    """
    __tablename__ = "sandboxed_tool_commands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tool_id = Column(Integer, nullable=False, index=True)  # FK to SandboxedTool
    command_name = Column(String(100), nullable=False)  # e.g., "start_scan", "check_results"
    command_template = Column(Text, nullable=False)  # e.g., "nuclei -u <url> -o <output_file>"
    is_long_running = Column(Boolean, default=False)
    timeout_seconds = Column(Integer, default=30)
    created_at = Column(DateTime, default=datetime.utcnow)


class SandboxedToolParameter(Base):
    """
    Sandboxed Tools System (formerly CustomToolParameter).
    Defines parameters for sandboxed tool commands.
    """
    __tablename__ = "sandboxed_tool_parameters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    command_id = Column(Integer, nullable=False, index=True)  # FK to SandboxedToolCommand
    parameter_name = Column(String(100), nullable=False)  # e.g., "url", "output_file"
    is_mandatory = Column(Boolean, default=False)
    default_value = Column(Text)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentSandboxedTool(Base):
    """
    Agent-Sandboxed Tool Mapping (formerly AgentCustomTool).
    Maps which sandboxed tools are enabled for each agent.
    Similar to AgentSkill pattern.
    """
    __tablename__ = "agent_sandboxed_tool"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, nullable=False, index=True)  # FK to Agent
    sandboxed_tool_id = Column(Integer, nullable=False, index=True)  # FK to SandboxedTool
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SandboxedToolExecution(Base):
    """
    Sandboxed Tools System (formerly CustomToolExecution).
    Tracks execution history of sandboxed tools.
    """
    __tablename__ = "sandboxed_tool_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_run_id = Column(Integer, index=True)  # FK to AgentRun (nullable for manual executions)
    tool_id = Column(Integer, nullable=False, index=True)  # FK to SandboxedTool
    command_id = Column(Integer, nullable=False, index=True)  # FK to SandboxedToolCommand
    rendered_command = Column(Text, nullable=False)  # Full command with placeholders filled
    status = Column(String(20), nullable=False)  # 'pending', 'running', 'completed', 'failed'
    output = Column(Text)  # Command stdout
    error = Column(Text)  # Command stderr or error message
    execution_time_ms = Column(Integer)  # Execution duration in milliseconds
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)


class ToolboxContainer(Base):
    """
    Phase: Custom Tools Hub Integration
    Tracks per-tenant toolbox container state.
    Each tenant gets their own Docker container for custom tool execution.
    """
    __tablename__ = "toolbox_containers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), unique=True, nullable=False, index=True)  # FK to tenant
    container_id = Column(String(64))  # Docker container ID
    status = Column(String(20), default='stopped')  # 'running', 'stopped', 'error'
    image_tag = Column(String(100), default='base')  # 'base' or tenant-specific tag
    last_started_at = Column(DateTime)
    last_commit_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ToolboxPackage(Base):
    """
    Phase: Custom Tools Hub Integration
    Tracks packages installed in tenant toolbox containers.
    Supports both pip (Python) and apt (system) packages.
    """
    __tablename__ = "toolbox_packages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), nullable=False, index=True)  # FK to tenant
    package_name = Column(String(100), nullable=False)
    package_type = Column(String(10), nullable=False)  # 'pip', 'apt', 'binary'
    version = Column(String(50))  # Optional version specifier
    installed_at = Column(DateTime, default=datetime.utcnow)
    is_committed = Column(Boolean, default=False)  # True if included in committed image


class ScheduledEvent(Base):
    """
    Phase 6.4: Enhanced Scheduler System
    Phase 7.9: Added tenant_id for multi-tenancy
    Stores scheduled events for messages, tasks, conversations, and notifications.
    Supports one-time and recurring events with conversation state tracking.
    """
    __tablename__ = "scheduled_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), nullable=True, index=True)  # FK to tenant (Phase 7.9)
    creator_type = Column(String(10), nullable=False)  # 'USER', 'AGENT'
    creator_id = Column(Integer, nullable=False)  # user_id or agent_id
    event_type = Column(String(20), nullable=False)  # 'MESSAGE', 'TASK', 'CONVERSATION', 'NOTIFICATION'
    scheduled_at = Column(DateTime, nullable=False)
    status = Column(String(20), default='PENDING')  # 'PENDING', 'ACTIVE', 'COMPLETED', 'FAILED', 'CANCELLED', 'PAUSED'
    payload = Column(Text, nullable=False)  # JSON: event details
    recurrence_rule = Column(Text)  # JSON: cron-like recurrence config
    last_executed_at = Column(DateTime)
    next_execution_at = Column(DateTime)
    execution_count = Column(Integer, default=0)
    max_executions = Column(Integer)  # NULL for infinite

    # Conversation tracking (Phase 6.4 Enhanced)
    conversation_state = Column(Text)  # JSON: conversation context and history
    requires_intervention = Column(Boolean, default=False)  # Flag when agent needs guidance
    intervention_message = Column(Text)  # Message to send to user for guidance

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime)
    error_message = Column(Text)

    # Indexes for efficient querying
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class ConversationLog(Base):
    """
    Phase 6.4: Enhanced Scheduler - Conversation Logging
    Tracks individual messages in autonomous conversations.
    Provides complete audit trail of agent-conducted conversations.
    """
    __tablename__ = "conversation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheduled_event_id = Column(Integer, nullable=False, index=True)  # FK to ScheduledEvent
    agent_id = Column(Integer, nullable=False)  # FK to Agent
    recipient = Column(String(50), nullable=False)  # Phone number or contact ID

    # Message tracking
    message_direction = Column(String(10), nullable=False)  # 'SENT', 'RECEIVED'
    message_content = Column(Text, nullable=False)
    message_timestamp = Column(DateTime, default=datetime.utcnow)

    # Conversation context
    conversation_turn = Column(Integer, default=1)  # Turn number in conversation
    is_impersonating = Column(Boolean, default=False)  # Agent impersonating someone
    impersonation_identity = Column(String(100))  # Who agent is impersonating

    # Analysis (optional, computed by AI)
    sentiment = Column(String(20))  # 'POSITIVE', 'NEUTRAL', 'NEGATIVE'
    topic_alignment = Column(String(20))  # 'ON_TRACK', 'DEVIATING', 'ACHIEVED'

    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class FlowDefinition(Base):
    """
    Phase 6.6: Multi-Step Flows - Flow Definition
    Phase 6.11: Unified Flows - Added initiator tracking and flow type categorization
    Phase 7.9: Added tenant_id for multi-tenancy
    Phase 8.0: Unified Flow Architecture - Merged with ScheduledEvent functionality

    Stores reusable flow templates with versioning.
    Supports both programmatic (UI-created) and agentic (AI-created) flows.
    Now supports execution scheduling (immediate, scheduled, recurring).
    """
    __tablename__ = "flow_definition"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), nullable=True, index=True)  # FK to tenant (Phase 7.9)
    name = Column(String(200), nullable=False)
    description = Column(Text)

    # Phase 8.0: Execution Configuration (adapted from asm-platform)
    execution_method = Column(String(20), default='immediate')  # 'immediate' | 'scheduled' | 'recurring'
    scheduled_at = Column(DateTime, nullable=True)  # For scheduled execution
    recurrence_rule = Column(JSON, nullable=True)  # Cron-like config: {frequency, interval, days_of_week, timezone}

    # Phase 8.0: Default agent for the flow (can be overridden per step)
    default_agent_id = Column(Integer, nullable=True)  # FK to Agent

    # Phase 6.11: Initiator tracking
    initiator_type = Column(String(20), default='programmatic')  # 'agentic' | 'programmatic'
    initiator_metadata = Column(JSON, default=dict)  # {
        # 'natural_language_request': 'Remind me to...',
        # 'sender': '5500000000001',
        # 'timestamp': '2025-10-09T15:20:00',
        # 'agent_id': 1
    # }

    # Phase 6.11: Flow type categorization
    flow_type = Column(String(20), default='workflow')  # 'notification' | 'conversation' | 'workflow' | 'task'

    # Existing fields
    is_active = Column(Boolean, default=True)
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Phase 8.0: Execution tracking
    last_executed_at = Column(DateTime, nullable=True)
    next_execution_at = Column(DateTime, nullable=True)
    execution_count = Column(Integer, default=0)

    # Relationships
    steps = relationship("FlowNode", back_populates="flow", cascade="all, delete-orphan", order_by="FlowNode.position")
    runs = relationship("FlowRun", back_populates="flow", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_flow_execution_method", "execution_method"),
        Index("idx_flow_next_execution", "next_execution_at"),
        {"sqlite_autoincrement": True},
    )


class FlowNode(Base):
    """
    Phase 6.6: Multi-Step Flows - Flow Node (also known as FlowStep)
    Phase 8.0: Unified Flow Architecture - Enhanced with asm-platform patterns

    Stores individual steps within a flow.
    Step types: 'notification' | 'message' | 'tool' | 'conversation'
    """
    __tablename__ = "flow_node"

    id = Column(Integer, primary_key=True, autoincrement=True)
    flow_definition_id = Column(Integer, ForeignKey("flow_definition.id"), nullable=False, index=True)

    # Phase 8.0: Step Identity (from asm-platform pattern)
    name = Column(String(200), nullable=True)  # Human-readable step name (optional for backward compat)
    step_description = Column(Text, nullable=True)  # Step-specific description

    # Step Configuration
    type = Column(String(50), nullable=False)  # 'notification' | 'message' | 'tool' | 'conversation'
    position = Column(Integer, nullable=False)  # Execution order (1-based)
    config_json = Column(Text, nullable=False)  # JSON config, typed by step type
    next_node_id = Column(Integer)  # FK to flow_node (nullable for last node) - legacy, kept for compat

    # Phase 8.0: Execution Settings (from asm-platform pattern)
    timeout_seconds = Column(Integer, default=300)  # Step timeout (5 min default)
    retry_on_failure = Column(Boolean, default=False)
    max_retries = Column(Integer, default=0)
    retry_delay_seconds = Column(Integer, default=1)  # Base delay for exponential backoff

    # Phase 8.0: Flow Control (from asm-platform pattern)
    condition = Column(JSON, nullable=True)  # Conditional execution logic
    on_success = Column(String(50), nullable=True)  # Action on success: 'continue' | 'skip_to:{step}' | 'end'
    on_failure = Column(String(50), nullable=True)  # Action on failure: 'continue' | 'retry' | 'end' | 'skip'

    # Phase 8.0: Conversation Settings (for conversation steps)
    allow_multi_turn = Column(Boolean, default=False)  # Enable multi-turn conversation
    max_turns = Column(Integer, default=20)  # Max conversation turns
    conversation_objective = Column(Text, nullable=True)  # What the conversation should achieve

    # Phase 8.0: Agent Assignment (can override flow-level defaults)
    agent_id = Column(Integer, nullable=True)  # Override flow-level agent
    persona_id = Column(Integer, nullable=True)  # Optional persona injection

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    flow = relationship("FlowDefinition", back_populates="steps")
    step_runs = relationship("FlowNodeRun", back_populates="step", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('flow_definition_id', 'position', name='uq_flow_node_position'),
        {"sqlite_autoincrement": True},
    )


class FlowRun(Base):
    """
    Phase 6.6: Multi-Step Flows - Flow Run
    Phase 8.0: Unified Flow Architecture - Enhanced execution tracking

    Tracks execution instances of a FlowDefinition.
    """
    __tablename__ = "flow_run"

    id = Column(Integer, primary_key=True, autoincrement=True)
    flow_definition_id = Column(Integer, ForeignKey("flow_definition.id"), nullable=False, index=True)
    tenant_id = Column(String(50), nullable=True, index=True)  # FK to tenant

    # Execution status
    status = Column(String(50), default='pending')  # 'pending', 'running', 'completed', 'failed', 'cancelled', 'paused', 'timeout'
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Trigger info
    initiator = Column(String(50))  # 'agent', 'system', 'api', 'scheduler'
    trigger_type = Column(String(20))  # 'immediate', 'scheduled', 'recurring', 'manual'
    triggered_by = Column(String(100))  # User ID or system identifier

    # Step tracking (from asm-platform pattern)
    total_steps = Column(Integer, default=0)
    completed_steps = Column(Integer, default=0)
    failed_steps = Column(Integer, default=0)

    # Context and results
    trigger_context_json = Column(Text)  # Initial trigger data / input variables
    final_report_json = Column(Text)  # Aggregated summary / output
    error_text = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    flow = relationship("FlowDefinition", back_populates="runs")
    step_runs = relationship("FlowNodeRun", back_populates="run", cascade="all, delete-orphan", order_by="FlowNodeRun.id")

    __table_args__ = (
        Index("idx_flow_run_status", "status"),
        Index("idx_flow_run_tenant_status", "tenant_id", "status"),
        {"sqlite_autoincrement": True},
    )


class FlowNodeRun(Base):
    """
    Phase 6.6: Multi-Step Flows - Flow Node Run (also known as FlowStepRun)
    Phase 8.0: Unified Flow Architecture - Enhanced step execution tracking

    Tracks per-step execution within a FlowRun.
    """
    __tablename__ = "flow_node_run"

    id = Column(Integer, primary_key=True, autoincrement=True)
    flow_run_id = Column(Integer, ForeignKey("flow_run.id"), nullable=False, index=True)
    flow_node_id = Column(Integer, ForeignKey("flow_node.id"), nullable=False, index=True)

    # Execution status
    status = Column(String(50), default='pending')  # 'pending', 'running', 'completed', 'failed', 'skipped', 'cancelled', 'timeout'
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Retry tracking (from asm-platform pattern)
    retry_count = Column(Integer, default=0)

    # Input/Output
    input_json = Column(Text)  # Normalized inputs
    output_json = Column(Text)  # Normalized outputs / step results
    error_text = Column(Text)

    # Performance metrics
    execution_time_ms = Column(Integer)
    token_usage_json = Column(Text)  # {prompt_tokens, completion_tokens, total_tokens}
    tool_used = Column(String(100))

    # Idempotency
    idempotency_key = Column(String(255), unique=True)

    # Relationships
    run = relationship("FlowRun", back_populates="step_runs")
    step = relationship("FlowNode", back_populates="step_runs")
    # Note: No cascade delete - active conversations should persist even if flow run is deleted
    # Orphan threads will be cleaned up by scheduler or manually
    conversation_threads = relationship("ConversationThread", back_populates="step_run")

    __table_args__ = (
        Index("idx_step_run_status", "status"),
        {"sqlite_autoincrement": True},
    )


class ConversationThread(Base):
    """
    Phase 8.0: Unified Flow Architecture - Conversation Thread
    Phase 14.1: Extended to support Playground conversation threads

    Tracks multi-turn conversation state for both:
    - Flow executions (flow_step_run_id is set)
    - Playground conversations (user_id and agent_id are set)
    """
    __tablename__ = "conversation_thread"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Phase 14.1: Made nullable to support playground threads
    flow_step_run_id = Column(Integer, ForeignKey("flow_node_run.id"), nullable=True, index=True)

    # Phase 14.1: Playground-specific fields
    tenant_id = Column(String(50), nullable=True, index=True)  # FK to tenant (for playground)
    user_id = Column(Integer, nullable=True, index=True)  # FK to user (for playground)
    thread_type = Column(String(20), default='flow', index=True)  # 'flow' or 'playground'
    title = Column(String(200), nullable=True)  # Thread name (auto-generated or user-set)
    folder = Column(String(100), nullable=True)  # Organization folder (e.g., "Work", "Personal")
    is_archived = Column(Boolean, default=False, index=True)  # Archive status

    # Thread State
    status = Column(String(20), default='active')  # 'active' | 'paused' | 'completed' | 'timeout' | 'goal_achieved'
    current_turn = Column(Integer, default=0)
    max_turns = Column(Integer, default=20)

    # Participant Info
    recipient = Column(String(100), nullable=False)  # Phone number or contact identifier (or sender_key for playground)
    agent_id = Column(Integer, nullable=False)  # FK to Agent
    persona_id = Column(Integer, nullable=True)  # Optional persona used

    # Conversation Objective
    objective = Column(Text, nullable=True)  # What the conversation should achieve

    # State Persistence
    conversation_history = Column(JSON, default=list)  # [{role: 'agent'|'user', content: str, timestamp: str}]
    context_data = Column(JSON, default=dict)  # Extracted data from conversation (for use in subsequent steps)

    # Goal tracking
    goal_achieved = Column(Boolean, default=False)
    goal_summary = Column(Text, nullable=True)  # AI-generated summary of conversation outcome

    # Timestamps
    started_at = Column(DateTime, default=datetime.utcnow)
    last_activity_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    timeout_at = Column(DateTime, nullable=True)  # When the conversation will timeout
    created_at = Column(DateTime, default=datetime.utcnow)  # Phase 14.1: Added for consistency
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # Phase 14.1: Added

    # Relationships
    step_run = relationship("FlowNodeRun", back_populates="conversation_threads")

    __table_args__ = (
        Index("idx_conversation_thread_status", "status"),
        Index("idx_conversation_thread_recipient", "recipient"),
        Index("idx_conversation_thread_active", "status", "recipient"),
        Index("idx_conversation_thread_playground", "tenant_id", "user_id", "agent_id", "thread_type"),
        Index("idx_conversation_thread_archived", "is_archived"),
        {"sqlite_autoincrement": True},
    )


# ============================================================================
# Phase 6.x: Hub Integration System (Asana, Slack, Linear, etc.)
# ============================================================================

class HubIntegration(Base):
    """
    Hub Integration System - Base model for all external integrations.
    Phase 7.9.2: Added tenant_id for multi-tenancy support.
    Uses single-table inheritance (polymorphic) for different integration types.

    Supported integrations:
    - Asana (task management via MCP)
    - Slack (future)
    - Linear (future)
    - GitHub (future)
    """
    __tablename__ = "hub_integration"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(50), nullable=False)  # 'asana', 'slack', 'linear', 'gmail', 'calendar', etc.
    name = Column(String(200), nullable=False)  # Auto-generated name (e.g., "Gmail - user@gmail.com")
    display_name = Column(String(200), nullable=True)  # User-friendly name (e.g., "Work Gmail", "Team Calendar")
    is_active = Column(Boolean, default=True, nullable=False)

    # Phase 7.9.2: Multi-tenancy support
    tenant_id = Column(String(50), nullable=True, index=True)  # FK to tenant (NULL = system-wide integration)

    # Polymorphic configuration
    __mapper_args__ = {
        'polymorphic_on': type,
        'polymorphic_identity': 'base',
        'with_polymorphic': '*'
    }

    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now())

    # Health monitoring
    last_health_check = Column(DateTime)
    health_status = Column(String(20), default="unknown")  # "healthy", "degraded", "unavailable"
    health_status_reason = Column(String(500), nullable=True)  # Why the status changed (e.g., "invalid_grant")

    # Relationships
    tokens = relationship("OAuthToken", back_populates="integration", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_hub_integration_type_active", "type", "is_active"),
        Index("idx_hub_integration_health", "health_status"),
        Index("idx_hub_integration_tenant", "tenant_id"),
        {"sqlite_autoincrement": True},
    )


class AsanaIntegration(HubIntegration):
    """
    Asana MCP Server Integration.
    Stores workspace-specific configuration for Asana integration.
    """
    __tablename__ = "asana_integration"

    id = Column(Integer, ForeignKey("hub_integration.id"), primary_key=True)
    workspace_gid = Column(String(50), unique=True, nullable=False, index=True)
    workspace_name = Column(String(200), nullable=False)

    # OAuth metadata
    authorized_by_user_gid = Column(String(50), nullable=False, index=True)
    authorized_at = Column(DateTime, nullable=False)

    # Default assignee configuration
    default_assignee_name = Column(String(200), nullable=True)  # User-friendly name (e.g., "Marcos Vinicios")
    default_assignee_gid = Column(String(50), nullable=True)    # Resolved Asana user GID (cached)

    # Polymorphic configuration
    __mapper_args__ = {
        'polymorphic_identity': 'asana',
    }

    __table_args__ = (
        Index("idx_asana_workspace_gid", "workspace_gid"),
        Index("idx_asana_user_gid", "authorized_by_user_gid"),
        {"sqlite_autoincrement": True},
    )


class AmadeusIntegration(HubIntegration):
    """
    Amadeus Flight Search API Integration.
    Stores configuration for Amadeus flight search provider.
    Uses OAuth2 client credentials flow for authentication.
    """
    __tablename__ = "amadeus_integration"

    id = Column(Integer, ForeignKey("hub_integration.id"), primary_key=True)

    # Environment configuration
    environment = Column(String(20), nullable=False, default="test")  # "test" or "production"

    # API Configuration
    api_key = Column(String(100), nullable=False)  # Client ID
    api_secret_encrypted = Column(Text, nullable=False)  # Client Secret (encrypted)

    # Default search settings
    default_currency = Column(String(3), default="BRL")
    max_results = Column(Integer, default=5)

    # Rate limiting tracking (Amadeus: 150 requests/min)
    requests_last_minute = Column(Integer, default=0)
    last_request_window = Column(DateTime)

    # Token management
    current_access_token_encrypted = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)

    # Polymorphic configuration
    __mapper_args__ = {
        'polymorphic_identity': 'amadeus',
    }

    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


# ============================================================================
# Phase 18: Shell Skill - Remote Command Execution (C2 Architecture)
# ============================================================================

class ShellIntegration(HubIntegration):
    """
    Shell Skill Integration - Remote command execution via beacon agents.

    Implements a C2 (Command & Control) architecture where:
    - Backend queues commands in the database
    - Remote beacons poll for commands and report results
    - Supports both HTTP polling (beacon mode) and WebSocket (interactive mode)

    Each ShellIntegration represents one registered beacon/host.

    Example:
        Tenant "acme-corp" has:
        - ShellIntegration 1: server-001 (Linux production server)
        - ShellIntegration 2: dev-machine (Developer workstation)
    """
    __tablename__ = "shell_integration"

    id = Column(Integer, ForeignKey("hub_integration.id"), primary_key=True)

    # Authentication - API key for beacon authentication
    # Stored as SHA-256 hash for security
    api_key_hash = Column(String(128), nullable=False)

    # C2 Configuration
    poll_interval = Column(Integer, default=15)  # Seconds between beacon check-ins (increased from 5 for stability)
    mode = Column(String(20), default="beacon")  # 'interactive' (WebSocket) or 'beacon' (HTTP polling)

    # Security Controls (Phase 1)
    allowed_commands = Column(JSON, default=list)  # ["ls", "cat", "grep", "df"] - empty = all allowed
    allowed_paths = Column(JSON, default=list)     # ["/tmp", "/var/log"] - empty = all allowed

    # YOLO Mode - Auto-approve high-risk commands (CRIT-005 security fix)
    # When enabled, high-risk commands execute immediately without approval
    # BLOCKED commands are still rejected even in YOLO mode
    yolo_mode = Column(Boolean, default=False, nullable=False)

    # Host Identification (set during registration)
    hostname = Column(String(255), nullable=True)
    remote_ip = Column(String(45), nullable=True)  # IPv6 support

    # Registration flow
    registration_token_hash = Column(String(128), nullable=True)  # For initial registration
    registered_at = Column(DateTime, nullable=True)

    # Status Information
    os_info = Column(JSON, nullable=True)  # {"name": "Linux", "version": "5.15.0", "arch": "x86_64"}
    last_checkin = Column(DateTime, nullable=True)

    # Result retention configuration (nullable = keep forever)
    retention_days = Column(Integer, nullable=True)  # Days to keep completed command results

    # Phase 20: Sentinel Security Agent protection indicator
    sentinel_protected = Column(Boolean, default=True, nullable=False)

    # Polymorphic configuration
    __mapper_args__ = {
        'polymorphic_identity': 'shell',
    }

    @property
    def is_online(self) -> bool:
        """
        Check if beacon is online based on last check-in time.

        Uses 5x multiplier of poll_interval to allow for network jitter
        and temporary connection issues. With default poll_interval=15s,
        beacon is considered offline after 75 seconds of no check-in.
        """
        from datetime import timedelta
        if not self.last_checkin:
            return False
        # Use 5x multiplier for stability (was 3x, caused false offline status)
        timeout = timedelta(seconds=self.poll_interval * 5)
        return datetime.utcnow() - self.last_checkin < timeout

    __table_args__ = (
        Index("idx_shell_hostname", "hostname"),
        Index("idx_shell_last_checkin", "last_checkin"),
        {"sqlite_autoincrement": True},
    )


class ShellCommand(Base):
    """
    Shell Command Queue - Tracks command lifecycle for C2 execution.

    Commands flow through states:
    1. queued: Initial state, waiting for beacon to pick up
    2. sent: Dispatched to beacon
    3. executing: Beacon acknowledged, running command
    4. completed: Execution finished successfully
    5. failed: Execution failed
    6. timeout: Beacon didn't respond in time
    7. cancelled: Cancelled before execution

    Supports:
    - Stacked commands (multiple commands in one request)
    - Approval workflow for high-risk commands (Phase 5)
    - Full audit trail with initiator tracking
    """
    __tablename__ = "shell_command"

    id = Column(String(36), primary_key=True)  # UUID
    shell_id = Column(Integer, ForeignKey("shell_integration.id"), nullable=False, index=True)
    tenant_id = Column(String(50), nullable=False, index=True)

    # Request Details
    commands = Column(JSON, nullable=False)  # ["cd /tmp", "ls -la"] - stacked commands
    initiated_by = Column(String(100), nullable=False)  # "agent:1", "user:alice", "api:key_xxxx"
    executed_by_agent_id = Column(Integer, ForeignKey("agent.id"), nullable=True)  # If initiated by agent

    # Status Tracking
    status = Column(String(20), default="queued", nullable=False, index=True)
    # Status values: queued, sent, executing, completed, failed, timeout, cancelled

    queued_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Timeout Configuration
    timeout_seconds = Column(Integer, default=300)  # 5 minutes default

    # Approval Workflow (Phase 5 prep)
    approval_required = Column(Boolean, default=False)
    approved_by_user_id = Column(Integer, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Execution Results
    exit_code = Column(Integer, nullable=True)
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)
    execution_time_ms = Column(Integer, nullable=True)

    # Detailed per-command results for stacked execution
    # Format: [{"command": "cd /tmp", "exit_code": 0, "stdout": "", "stderr": "", "time_ms": 5}, ...]
    full_result_json = Column(JSON, nullable=True)

    # Working directory tracking for stacked commands
    final_working_dir = Column(String(500), nullable=True)  # Working dir after all commands

    # Error details
    error_message = Column(Text, nullable=True)  # Human-readable error message

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    shell = relationship("ShellIntegration", backref="commands")
    agent = relationship("Agent", backref="shell_commands")

    __table_args__ = (
        Index("idx_shell_command_status", "status"),
        Index("idx_shell_command_shell_status", "shell_id", "status"),
        Index("idx_shell_command_tenant", "tenant_id"),
        Index("idx_shell_command_queued", "queued_at"),
        {"sqlite_autoincrement": True},
    )


class ShellSecurityPattern(Base):
    """
    Phase 19: Shell Security Pattern Customization

    Stores blocked and high-risk patterns for shell command validation.
    System defaults (is_system_default=True) come from hardcoded patterns.
    Tenants can add custom patterns or toggle system defaults.

    Pattern Types:
    - 'blocked': Always rejected, even in YOLO mode (e.g., fork bombs, rm -rf /)
    - 'high_risk': Require approval or auto-execute in YOLO mode

    Risk Levels (for high_risk only):
    - 'low': Minor risk, logged but usually allowed
    - 'medium': Moderate risk, may require approval
    - 'high': High risk, typically requires approval
    - 'critical': Critical risk, blocks unless YOLO mode enabled
    """
    __tablename__ = "shell_security_pattern"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=True, index=True)  # NULL = system default

    # Pattern Definition
    pattern = Column(String(500), nullable=False)  # Regex pattern
    pattern_type = Column(String(20), nullable=False)  # 'blocked', 'high_risk'
    risk_level = Column(String(20), nullable=True)  # 'low', 'medium', 'high', 'critical'
    description = Column(String(255), nullable=False)  # Human-readable description

    # Categorization
    category = Column(String(50), nullable=True)  # 'filesystem', 'network', 'system', etc.

    # Flags
    is_system_default = Column(Boolean, default=False)  # True = from hardcoded defaults
    is_active = Column(Boolean, default=True)  # False = disabled (not used in checks)

    # Audit
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by], backref="created_security_patterns")
    updater = relationship("User", foreign_keys=[updated_by], backref="updated_security_patterns")

    __table_args__ = (
        Index("idx_security_pattern_tenant_active", "tenant_id", "is_active"),
        Index("idx_security_pattern_type", "pattern_type", "is_active"),
        {"sqlite_autoincrement": True},
    )


# ============================================================================
# Phase 20: Sentinel Security Agent
# ============================================================================

class SentinelConfig(Base):
    """
    System/Tenant-level Sentinel configuration.

    Sentinel is a built-in AI-powered security layer that detects:
    - Prompt injection attempts
    - Agent takeover attempts
    - Poisoning attacks (gradual manipulation)
    - Malicious shell command intent

    Configuration hierarchy:
    1. System default (tenant_id=NULL) - ships with fresh installs
    2. Tenant override (tenant_id=<id>) - per-organization settings
    3. Agent override (via SentinelAgentConfig) - per-agent settings

    Sentinel cannot be deleted, only disabled.
    """
    __tablename__ = "sentinel_config"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=True, index=True)  # NULL = system default

    # Master toggle (cannot delete Sentinel, only disable)
    is_enabled = Column(Boolean, default=True, nullable=False)

    # Component toggles - which types of content to analyze
    enable_prompt_analysis = Column(Boolean, default=True, nullable=False)
    enable_tool_analysis = Column(Boolean, default=True, nullable=False)
    enable_shell_analysis = Column(Boolean, default=True, nullable=False)

    # Detection type toggles - which threats to detect
    detect_prompt_injection = Column(Boolean, default=True, nullable=False)
    detect_agent_takeover = Column(Boolean, default=True, nullable=False)
    detect_poisoning = Column(Boolean, default=True, nullable=False)
    detect_shell_malicious_intent = Column(Boolean, default=True, nullable=False)
    detect_memory_poisoning = Column(Boolean, default=True, nullable=False)

    # Aggressiveness: 0=Off, 1=Moderate, 2=Aggressive, 3=Extra Aggressive
    aggressiveness_level = Column(Integer, default=1, nullable=False)

    # LLM configuration for analysis
    llm_provider = Column(String(20), default="gemini", nullable=False)
    llm_model = Column(String(100), default="gemini-2.5-flash-lite", nullable=False)
    llm_max_tokens = Column(Integer, default=256, nullable=False)
    llm_temperature = Column(Float, default=0.1, nullable=False)

    # Custom analysis prompts (NULL = use default prompts from sentinel_detections.py)
    prompt_injection_prompt = Column(Text, nullable=True)
    agent_takeover_prompt = Column(Text, nullable=True)
    poisoning_prompt = Column(Text, nullable=True)
    shell_intent_prompt = Column(Text, nullable=True)
    memory_poisoning_prompt = Column(Text, nullable=True)

    # Performance settings
    cache_ttl_seconds = Column(Integer, default=300, nullable=False)  # 5-minute cache
    max_input_chars = Column(Integer, default=5000, nullable=False)
    timeout_seconds = Column(Float, default=5.0, nullable=False)

    # Action settings
    block_on_detection = Column(Boolean, default=True, nullable=False)
    log_all_analyses = Column(Boolean, default=False, nullable=False)  # If True, log even allowed messages

    # Detection mode: 'block', 'detect_only', 'off'
    # - block: Analyze and block detected threats
    # - detect_only: Analyze and log threats without blocking (default for fresh installs)
    # - off: Disable Sentinel analysis entirely
    detection_mode = Column(String(20), default="detect_only", nullable=False)

    # Slash command inspection toggle
    # When False, slash commands bypass Sentinel analysis (trusted internal commands)
    enable_slash_command_analysis = Column(Boolean, default=True, nullable=False)

    # Notification settings for Sentinel events
    # When enabled, sends alerts to a configured recipient when threats are detected
    enable_notifications = Column(Boolean, default=True, nullable=False)
    notification_on_block = Column(Boolean, default=True, nullable=False)  # Notify when messages are blocked
    notification_on_detect = Column(Boolean, default=False, nullable=False)  # Notify in detect_only mode
    notification_recipient = Column(String(100), nullable=True)  # Phone number/chat ID (e.g., 5511999999999@s.whatsapp.net)
    notification_message_template = Column(Text, nullable=True)  # Custom message template (NULL = use default)

    # Audit
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by], backref="created_sentinel_configs")
    updater = relationship("User", foreign_keys=[updated_by], backref="updated_sentinel_configs")

    __table_args__ = (
        UniqueConstraint('tenant_id', name='uq_sentinel_config_tenant'),
        {"sqlite_autoincrement": True},
    )


class SentinelAgentConfig(Base):
    """
    Per-Agent Sentinel overrides.

    Allows agents to have different Sentinel settings than their tenant default.
    NULL values = inherit from tenant/system config.

    Example:
        Agent "customer-support" might have aggressiveness_level=3 (Extra Aggressive)
        while the tenant default is 1 (Moderate).
    """
    __tablename__ = "sentinel_agent_config"

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey("agent.id"), unique=True, index=True, nullable=False)

    # Override toggles (NULL = inherit from tenant/system)
    is_enabled = Column(Boolean, nullable=True)
    enable_prompt_analysis = Column(Boolean, nullable=True)
    enable_tool_analysis = Column(Boolean, nullable=True)
    enable_shell_analysis = Column(Boolean, nullable=True)
    aggressiveness_level = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationship
    agent = relationship("Agent", backref="sentinel_agent_config")

    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class SentinelAnalysisLog(Base):
    """
    Audit trail for all Sentinel analyses.

    Displayed in Watcher > Security tab for centralized security monitoring.
    Records both threats detected and allowed messages (if log_all_analyses=True).

    Event types include:
    - prompt_injection: Detected prompt override attempt
    - agent_takeover: Detected identity hijack attempt
    - poisoning: Detected gradual manipulation
    - shell_malicious: Detected malicious shell intent
    """
    __tablename__ = "sentinel_analysis_log"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    agent_id = Column(Integer, nullable=True, index=True)

    # Analysis classification
    analysis_type = Column(String(30), nullable=False)  # 'prompt', 'tool', 'shell'
    detection_type = Column(String(30), nullable=False)  # 'prompt_injection', 'agent_takeover', etc.

    # Input data (truncated for storage)
    input_content = Column(Text, nullable=False)  # First 500 chars of input
    input_hash = Column(String(64), nullable=False, index=True)  # SHA-256 for cache lookup

    # Analysis results
    is_threat_detected = Column(Boolean, nullable=False)
    threat_score = Column(Float, nullable=True)  # 0.0-1.0 confidence score
    threat_reason = Column(Text, nullable=True)  # LLM's explanation
    action_taken = Column(String(30), nullable=False)  # 'allowed', 'blocked', 'warned'

    # LLM metadata
    llm_provider = Column(String(20), nullable=True)
    llm_model = Column(String(100), nullable=True)
    llm_response_time_ms = Column(Integer, nullable=True)

    # Context
    sender_key = Column(String(255), nullable=True, index=True)  # User identifier
    message_id = Column(String(100), nullable=True)  # Original message ID

    # Exception tracking (Phase 20 Enhancement)
    exception_applied = Column(Boolean, default=False, nullable=False)  # Was an exception rule matched?
    exception_id = Column(Integer, nullable=True)  # ID of matched exception rule
    exception_name = Column(String(100), nullable=True)  # Name of matched exception for audit
    detection_mode_used = Column(String(20), nullable=True)  # Detection mode at time of analysis

    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)

    __table_args__ = (
        Index("idx_sentinel_log_tenant_threat", "tenant_id", "is_threat_detected", "created_at"),
        Index("idx_sentinel_log_detection_type", "detection_type", "created_at"),
        {"sqlite_autoincrement": True},
    )


class SentinelAnalysisCache(Base):
    """
    Performance cache for Sentinel analysis results.

    Avoids redundant LLM calls for identical inputs with the same settings.
    Cache key = (tenant_id, input_hash, analysis_type, detection_type, aggressiveness_level)

    Expired entries are cleaned up periodically.
    """
    __tablename__ = "sentinel_analysis_cache"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)

    # Cache key components
    input_hash = Column(String(64), nullable=False)  # SHA-256 of input
    analysis_type = Column(String(30), nullable=False)
    detection_type = Column(String(30), nullable=False)
    aggressiveness_level = Column(Integer, nullable=False)

    # Cached results
    is_threat_detected = Column(Boolean, nullable=False)
    threat_score = Column(Float, nullable=True)
    threat_reason = Column(Text, nullable=True)

    # Expiration
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('tenant_id', 'input_hash', 'analysis_type', 'detection_type',
                         'aggressiveness_level', name='uq_sentinel_cache'),
        Index("idx_sentinel_cache_expires", "expires_at"),
        {"sqlite_autoincrement": True},
    )


class SentinelException(Base):
    """
    Granular exception rules for Sentinel analysis (Phase 20 Enhancement).

    Exceptions allow specific patterns/domains/tools to bypass LLM analysis.
    This reduces false positives for known-safe operations like:
    - nmap scans on approved test targets (scanme.nmap.org)
    - HTTP testing against httpbin.org
    - Internal tool calls from trusted skills

    Exception hierarchy (evaluated in order):
    1. System defaults (tenant_id=NULL) - ships with fresh installs
    2. Tenant exceptions (tenant_id=<id>) - per-organization rules
    3. Agent exceptions (agent_id=<id>) - per-agent overrides

    Higher priority exceptions are evaluated first.

    Design: NO hardcoded detection patterns here. The LLM handles threat
    detection semantically. Exceptions only whitelist known-safe operations
    to skip the LLM call for performance and reduce false positives.
    """
    __tablename__ = "sentinel_exception"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=True, index=True)  # NULL = system-level exception
    agent_id = Column(Integer, ForeignKey("agent.id"), nullable=True, index=True)

    # Exception identity
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Scope: comma-separated detection types or "*" for all
    # e.g., "shell_malicious", "prompt_injection,agent_takeover", or "*"
    detection_types = Column(String(255), default="*", nullable=False)

    # Exception type determines what to match against
    # - 'pattern': Match against input content (regex/glob/exact)
    # - 'domain': Match against extracted domain from URLs
    # - 'tool': Match against tool name being called
    # - 'network_target': Match against extracted hosts/IPs/domains in content
    exception_type = Column(String(30), nullable=False)

    # The pattern to match (interpreted based on match_mode)
    pattern = Column(Text, nullable=False)

    # Match mode: 'regex', 'glob', 'exact'
    match_mode = Column(String(20), default="regex", nullable=False)

    # Action when matched:
    # - 'skip_llm': Skip LLM analysis, allow the content (logged)
    # - 'allow': Allow without any logging (silent bypass)
    action = Column(String(20), default="skip_llm", nullable=False)

    # Control
    is_active = Column(Boolean, default=True, nullable=False)
    priority = Column(Integer, default=100, nullable=False)  # Higher = evaluated first

    # Audit
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    agent = relationship("Agent", backref="sentinel_exceptions")
    creator = relationship("User", foreign_keys=[created_by], backref="created_sentinel_exceptions")
    updater = relationship("User", foreign_keys=[updated_by], backref="updated_sentinel_exceptions")

    __table_args__ = (
        Index("idx_sentinel_exc_tenant_agent", "tenant_id", "agent_id"),
        Index("idx_sentinel_exc_active_priority", "is_active", "priority"),
        {"sqlite_autoincrement": True},
    )


# ============================================================================
# Phase v1.6.0: Sentinel Security Profiles
# ============================================================================

class SentinelProfile(Base):
    """
    Named, reusable security policy for Sentinel.

    Profiles are self-contained security policy documents that can be assigned
    at three levels: Tenant -> Agent -> Skill, with hierarchical fallback.

    Replaces the flat column-per-setting approach in SentinelConfig/SentinelAgentConfig
    with an extensible profile system.

    Key features:
    - System built-in profiles (off, permissive, moderate, aggressive)
    - Tenant-created custom profiles
    - JSON-based detection_overrides for zero-migration extensibility
    - One default profile per tenant (partial unique index enforced)

    Example:
        System profile "Moderate" (is_system=True, is_default=True):
        - detection_mode='block', aggressiveness_level=1
        - detection_overrides='{}' (all detections use registry defaults)

        Tenant custom profile "Sales Team Permissive":
        - detection_mode='detect_only', aggressiveness_level=1
        - detection_overrides='{"shell_malicious": {"enabled": false}}'
    """
    __tablename__ = "sentinel_profile"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Identity
    name = Column(String(100), nullable=False)
    slug = Column(String(100), nullable=False)  # URL-friendly (e.g. "aggressive")
    description = Column(Text, nullable=True)
    tenant_id = Column(String(50), nullable=True)  # NULL = system built-in
    is_system = Column(Boolean, default=False, nullable=False)  # System profiles: cannot delete/rename
    is_default = Column(Boolean, default=False, nullable=False)  # Default fallback for this tenant

    # Global settings
    is_enabled = Column(Boolean, default=True, nullable=False)
    detection_mode = Column(String(20), default="block", nullable=False)  # 'block' | 'detect_only' | 'off'
    aggressiveness_level = Column(Integer, default=1, nullable=False)  # 0=Off, 1=Moderate, 2=Aggressive, 3=Extra

    # Component toggles
    enable_prompt_analysis = Column(Boolean, default=True, nullable=False)
    enable_tool_analysis = Column(Boolean, default=True, nullable=False)
    enable_shell_analysis = Column(Boolean, default=True, nullable=False)
    enable_slash_command_analysis = Column(Boolean, default=True, nullable=False)

    # LLM configuration
    llm_provider = Column(String(20), default="gemini", nullable=False)
    llm_model = Column(String(100), default="gemini-2.5-flash-lite", nullable=False)
    llm_max_tokens = Column(Integer, default=256, nullable=False)
    llm_temperature = Column(Float, default=0.1, nullable=False)

    # Performance
    cache_ttl_seconds = Column(Integer, default=300, nullable=False)
    max_input_chars = Column(Integer, default=5000, nullable=False)
    timeout_seconds = Column(Float, default=5.0, nullable=False)

    # Actions
    block_on_detection = Column(Boolean, default=True, nullable=False)
    log_all_analyses = Column(Boolean, default=False, nullable=False)

    # Notifications
    enable_notifications = Column(Boolean, default=True, nullable=False)
    notification_on_block = Column(Boolean, default=True, nullable=False)
    notification_on_detect = Column(Boolean, default=False, nullable=False)
    notification_recipient = Column(String(100), nullable=True)
    notification_message_template = Column(Text, nullable=True)

    # Extensible per-detection config (JSON)
    # Structure: {"prompt_injection": {"enabled": true, "custom_prompt": null}, ...}
    # Keys absent from this JSON inherit defaults from DETECTION_REGISTRY.
    detection_overrides = Column(Text, default="{}", nullable=False)

    # Audit
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by], backref="created_sentinel_profiles")
    updater = relationship("User", foreign_keys=[updated_by], backref="updated_sentinel_profiles")

    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_sentinel_profile_tenant_slug"),
        Index("idx_sentinel_profile_tenant", "tenant_id"),
        Index("idx_sentinel_profile_system", "is_system"),
        {"sqlite_autoincrement": True},
    )


class SentinelProfileAssignment(Base):
    """
    Maps a Sentinel profile to a specific scope level.

    Scope semantics (determines hierarchy level):
    - (tenant, NULL, NULL)    = Tenant-level: applies to all agents
    - (tenant, agent, NULL)   = Agent-level: applies to specific agent
    - (tenant, agent, skill)  = Skill-level: applies to specific skill on agent

    At most ONE assignment per unique (tenant_id, agent_id, skill_type) tuple.
    The profile resolution walks: Skill -> Agent -> Tenant -> System Default.

    Example:
        Tenant "acme-corp" has:
        - Tenant-level: "Moderate" profile (all agents inherit this)
        - Agent 5: "Aggressive" profile (overrides tenant for this agent)
        - Agent 5 + Shell: "Permissive" profile (overrides agent for shell skill only)
    """
    __tablename__ = "sentinel_profile_assignment"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Scope (determines hierarchy level)
    tenant_id = Column(String(50), nullable=False)
    agent_id = Column(Integer, ForeignKey("agent.id", ondelete="CASCADE"), nullable=True)
    skill_type = Column(String(50), nullable=True)  # NULL = agent-level (requires agent_id)

    profile_id = Column(Integer, ForeignKey("sentinel_profile.id", ondelete="CASCADE"), nullable=False)

    # Audit
    assigned_by = Column(Integer, nullable=True)
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    profile = relationship("SentinelProfile", backref="assignments")
    agent = relationship("Agent", backref="sentinel_profile_assignments")

    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_id", "skill_type", name="uq_sentinel_profile_assignment_scope"),
        Index("idx_profile_assign_tenant", "tenant_id"),
        Index("idx_profile_assign_agent", "agent_id"),
        Index("idx_profile_assign_profile", "profile_id"),
        {"sqlite_autoincrement": True},
    )


class OAuthState(Base):
    """
    OAuth state tokens for CSRF protection.
    Stores temporary state tokens generated during OAuth authorization flow.
    Tokens are validated once and then deleted (one-time use).

    Security Fix HIGH-004: Persistent OAuth state storage (replaces in-memory dict).
    """
    __tablename__ = "oauth_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    state_token = Column(String(64), unique=True, nullable=False, index=True)
    integration_type = Column(String(50), nullable=False)  # 'asana', 'slack', 'google_sso', etc.

    # Tenant that initiated the OAuth flow
    tenant_id = Column(String(50), nullable=True, index=True)

    # Expiration (10-minute default)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False)

    # Optional: Store redirect URL for post-auth redirect
    redirect_url = Column(String(500))

    # Additional metadata (tenant_slug, invitation_token for SSO, etc.)
    # HIGH-004: Supports SSO-specific data without schema changes per integration
    metadata_json = Column(Text, default="{}")

    __table_args__ = (
        Index("idx_oauth_state_token", "state_token"),
        Index("idx_oauth_state_expires", "expires_at"),
        {"sqlite_autoincrement": True},
    )


class OAuthToken(Base):
    """
    Encrypted OAuth tokens with per-workspace key derivation.
    Stores access and refresh tokens for external integrations using Fernet encryption.
    Each workspace uses a derived key for additional security (PBKDF2).
    """
    __tablename__ = "oauth_token"

    id = Column(Integer, primary_key=True, autoincrement=True)
    integration_id = Column(Integer, ForeignKey("hub_integration.id"), nullable=False)

    # Encrypted tokens (using per-workspace Fernet encryption)
    access_token_encrypted = Column(Text, nullable=False)
    refresh_token_encrypted = Column(Text, nullable=False)

    # Token metadata
    token_type = Column(String(20), default="Bearer", nullable=False)
    expires_at = Column(DateTime, nullable=False)
    scope = Column(Text)  # Space-separated OAuth scopes

    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now())
    last_refreshed_at = Column(DateTime)

    # Relationships
    integration = relationship("HubIntegration", back_populates="tokens")

    __table_args__ = (
        Index("idx_oauth_token_integration", "integration_id"),
        Index("idx_oauth_token_expires", "expires_at"),
        {"sqlite_autoincrement": True},
    )


class UserAgentSession(Base):
    """
    Phase 7.3: Agent Switcher Persistence

    Stores user's agent preference when they use the agent switcher skill.
    Allows agent selection to persist across messages until user switches again.

    Example:
        User: "quero falar com @kira"
        → Creates/updates: UserAgentSession(user_identifier="5500000000001", agent_id=11)
        → Next message: Router checks this table first before keyword/default logic
    """
    __tablename__ = "user_agent_session"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_identifier = Column(String, unique=True, nullable=False, index=True)  # Phone or chat_id (sender_key)
    agent_id = Column(Integer, ForeignKey("agent.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    agent = relationship("Agent", backref="user_sessions")

    __table_args__ = (
        Index("idx_user_agent_session_identifier", "user_identifier"),
        {"sqlite_autoincrement": True},
    )


class UserContactMapping(Base):
    """
    Playground Feature: Maps RBAC users to contacts for identity resolution.

    Allows UI users to be linked to contacts so that when they use the Playground,
    the agent recognizes them with the same memory/context as their WhatsApp interactions.

    Example:
        User "john@company.com" → Contact "John Smith" (phone: +5500000000001)
        → Agent memory persists across Playground and WhatsApp
    """
    __tablename__ = "user_contact_mapping"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=False, unique=True, index=True)
    contact_id = Column(Integer, ForeignKey('contact.id'), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_user_contact_mapping_user", "user_id"),
        Index("idx_user_contact_mapping_contact", "contact_id"),
        {"sqlite_autoincrement": True},
    )


class WhatsAppMCPInstance(Base):
    """
    Phase 8: Multi-Tenant WhatsApp MCP Containerization

    Manages Docker containers for WhatsApp MCP instances.
    Each tenant can have multiple MCP instances (e.g., support + sales lines).

    Example:
        Tenant "acme-corp" → MCP Instance 1 (+5500000000001) on port 8080
                          → MCP Instance 2 (+5500000000002) on port 8081
    """
    __tablename__ = "whatsapp_mcp_instance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey('tenant.id'), nullable=False, index=True)

    # Container identification
    container_name = Column(String(100), unique=True, nullable=False)  # e.g., "mcp-tenant123-1699999999"
    phone_number = Column(String(20), nullable=False)  # WhatsApp phone number
    instance_type = Column(String(20), default="agent", nullable=False)  # "agent" or "tester"

    # Networking
    mcp_api_url = Column(String(200), nullable=False)  # http://127.0.0.1:DYNAMIC_PORT/api
    mcp_port = Column(Integer, unique=True, nullable=False)  # Dynamic port allocation (8080-8180)

    # Paths
    messages_db_path = Column(Text, nullable=False)  # /path/to/messages.db (container volume)
    session_data_path = Column(Text, nullable=False)  # /path/to/session (WhatsApp auth data)

    # Status
    status = Column(String(20), default="stopped")  # stopped, starting, running, error
    health_status = Column(String(20), default="unknown")  # unknown, healthy, unhealthy
    last_health_check = Column(DateTime, nullable=True)

    # QR Code for WhatsApp authentication
    qr_code_data = Column(Text, nullable=True)  # Base64-encoded QR code image
    qr_code_expires_at = Column(DateTime, nullable=True)

    # Container metadata
    container_id = Column(String(100), nullable=True)  # Docker container ID
    created_by = Column(Integer, ForeignKey('user.id'), nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_started_at = Column(DateTime, nullable=True)
    last_stopped_at = Column(DateTime, nullable=True)

    # Phase 10: Group Handler Configuration
    # Only one instance per tenant should be the group handler to prevent duplicate responses
    is_group_handler = Column(Boolean, default=False)

    # Phase 17: Instance-Level Message Filtering
    # These settings are WhatsApp-specific and allow per-instance configuration
    group_filters = Column(JSON, nullable=True)  # WhatsApp group names to monitor ["Group1", "Group2"]
    number_filters = Column(JSON, nullable=True)  # Phone numbers for DM allowlist ["+5500000000001"]
    group_keywords = Column(JSON, nullable=True)  # Keywords that trigger responses ["help", "bot"]
    dm_auto_mode = Column(Boolean, default=True)  # Auto-reply to unknown DMs (enabled by default for fresh installs)

    # Security - API Authentication (Phase Security-1: SSRF Prevention)
    # Token-based auth to prevent cross-tenant MCP access
    api_secret = Column(String(64), nullable=True)  # 32-byte hex-encoded secret
    api_secret_created_at = Column(DateTime, nullable=True)  # For rotation tracking

    # Relationships
    # tenant = relationship("Tenant")  # Requires models_rbac import
    # creator = relationship("User")   # Requires models_rbac import

    __table_args__ = (
        Index("idx_mcp_instance_tenant", "tenant_id"),
        Index("idx_mcp_instance_status", "status"),
        Index("idx_mcp_instance_port", "mcp_port"),
        {"sqlite_autoincrement": True},
    )


class TelegramBotInstance(Base):
    """
    Phase 10.1.1: Telegram Bot Integration

    Manages Telegram bot instances per tenant.
    Unlike WhatsApp MCP, no Docker container is needed - direct API calls.

    Example:
        Tenant "acme-corp" → Bot @AcmeSupportBot (token: 123456:ABC...)
    """
    __tablename__ = "telegram_bot_instance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey('tenant.id'), nullable=False, index=True)

    # Bot identification
    bot_token_encrypted = Column(Text, nullable=False)  # Fernet encrypted
    bot_username = Column(String(100), nullable=False)  # @username without @
    bot_name = Column(String(100), nullable=True)  # Display name
    bot_id = Column(String(50), nullable=True)  # Telegram bot user ID

    # Status
    status = Column(String(20), default="inactive")  # inactive, active, error
    health_status = Column(String(20), default="unknown")  # unknown, healthy, unhealthy
    last_health_check = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    # Webhook configuration (optional, polling is default)
    use_webhook = Column(Boolean, default=False)
    webhook_url = Column(String(500), nullable=True)
    webhook_secret_encrypted = Column(Text, nullable=True)  # MED-002 Security Fix: Fernet encrypted

    # Polling state
    last_update_id = Column(Integer, default=0)  # For getUpdates offset

    # Metadata
    created_by = Column(Integer, ForeignKey('user.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_telegram_instance_tenant", "tenant_id"),
        Index("idx_telegram_instance_status", "status"),
        Index("idx_telegram_instance_username", "bot_username"),
        {"sqlite_autoincrement": True},
    )


# ============================================================================
# Phase 9: Google Integration Models (Gmail, Calendar)
# ============================================================================

class GoogleOAuthCredentials(Base):
    """
    Per-tenant Google OAuth credentials (BYOT - Bring Your Own Token).

    Each tenant configures their own Google Cloud OAuth application credentials.
    This enables multi-tenant isolation where each organization uses their own
    Google Cloud project for Gmail and Calendar integrations.

    Example:
        Tenant "acme-corp" configures their Google Cloud project:
        - client_id: "123456.apps.googleusercontent.com"
        - client_secret: (encrypted)

        Users in this tenant can then connect Gmail/Calendar using these credentials.
    """
    __tablename__ = "google_oauth_credentials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey('tenant.id'), nullable=False, unique=True, index=True)

    # OAuth Application Credentials
    client_id = Column(String(200), nullable=False)
    client_secret_encrypted = Column(Text, nullable=False)  # Fernet encrypted

    # Optional: Custom redirect URI (defaults to system redirect)
    redirect_uri = Column(String(500), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, ForeignKey('user.id'), nullable=True)

    __table_args__ = (
        Index("idx_google_oauth_tenant", "tenant_id"),
        {"sqlite_autoincrement": True},
    )


class GmailIntegration(HubIntegration):
    """
    Gmail Integration - Read-only email access for agents.

    Multiple Gmail integrations per tenant are supported, allowing different
    agents to access different email accounts (e.g., support@company.com, sales@company.com).

    Features:
        - Read emails (inbox, search, specific messages)
        - List labels
        - Search by query

    Note: Write operations (send, draft) are not supported in this version.

    Example:
        Tenant "acme-corp" has:
        - GmailIntegration 1: support@acme.com (used by Support Bot)
        - GmailIntegration 2: sales@acme.com (used by Sales Assistant)
    """
    __tablename__ = "gmail_integration"

    id = Column(Integer, ForeignKey("hub_integration.id"), primary_key=True)

    # Gmail-specific fields
    email_address = Column(String(255), nullable=False)  # Connected email address
    authorized_at = Column(DateTime, nullable=False)

    # OAuth user info
    google_user_id = Column(String(100), nullable=True)  # Google's user ID

    # Polymorphic configuration
    __mapper_args__ = {
        'polymorphic_identity': 'gmail',
    }

    __table_args__ = (
        Index("idx_gmail_email", "email_address"),
        {"sqlite_autoincrement": True},
    )


class CalendarIntegration(HubIntegration):
    """
    Google Calendar Integration - Full calendar management for agents.

    Multiple Calendar integrations per tenant are supported, allowing different
    agents to manage different calendars (e.g., team calendar, personal calendar).

    Features:
        - List events
        - Create events
        - Update events
        - Delete events
        - Check free/busy status

    Used as a scheduler provider for the FlowsSkill.

    Example:
        Tenant "acme-corp" has:
        - CalendarIntegration 1: "Team Calendar" (team@acme.com)
        - CalendarIntegration 2: "Sales Calendar" (sales@acme.com)

        Support Bot uses Team Calendar for scheduling.
        Sales Assistant uses Sales Calendar for scheduling.
    """
    __tablename__ = "calendar_integration"

    id = Column(Integer, ForeignKey("hub_integration.id"), primary_key=True)

    # Calendar-specific fields
    email_address = Column(String(255), nullable=False)  # Connected email address
    default_calendar_id = Column(String(255), default='primary')  # Calendar ID to use
    timezone = Column(String(50), default='America/Sao_Paulo')  # Default timezone for events
    authorized_at = Column(DateTime, nullable=False)

    # OAuth user info
    google_user_id = Column(String(100), nullable=True)  # Google's user ID

    # Polymorphic configuration
    __mapper_args__ = {
        'polymorphic_identity': 'calendar',
    }

    __table_args__ = (
        Index("idx_calendar_email", "email_address"),
        {"sqlite_autoincrement": True},
    )


class GoogleFlightsIntegration(HubIntegration):
    """
    Google Flights Integration (via SerpApi).

    Uses SerpApi to scrape Google Flights results.
    Requires a SerpApi API key.

    Features:
        - Search flights (one-way, round-trip)
        - Filter by class, stops, etc.
    """
    __tablename__ = "google_flights_integration"

    id = Column(Integer, ForeignKey("hub_integration.id"), primary_key=True)

    # SerpApi Configuration
    api_key_encrypted = Column(Text, nullable=False)  # SerpApi Key (encrypted)

    # Defaults
    default_currency = Column(String(3), default="USD")
    default_language = Column(String(5), default="en")  # 'en', 'pt-br'

    # Polymorphic configuration
    __mapper_args__ = {
        'polymorphic_identity': 'google_flights',
    }

    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class BrowserAutomationIntegration(HubIntegration):
    """
    Browser Automation Integration.

    Phase 14.5: Browser Automation Skill

    Stores configuration for browser automation providers (Playwright, MCP Browser).
    Supports both container mode (isolated browser) and host mode (user's browser).

    Features:
        - Container mode: Secure, isolated browser for public websites
        - Host mode: Access user's authenticated sessions (Phase 8)
        - Configurable viewport, timeout, user agent
        - Multi-tenant support with per-user access control
    """
    __tablename__ = "browser_automation_integration"

    id = Column(Integer, ForeignKey("hub_integration.id"), primary_key=True)

    # Provider settings
    provider_type = Column(String(50), default="playwright")  # "playwright" or "mcp_browser"
    mode = Column(String(20), default="container")  # "container" or "host"

    # Browser configuration
    browser_type = Column(String(20), default="chromium")  # "chromium", "firefox", "webkit"
    headless = Column(Boolean, default=True)
    timeout_seconds = Column(Integer, default=30)
    viewport_width = Column(Integer, default=1280)
    viewport_height = Column(Integer, default=720)
    max_concurrent_sessions = Column(Integer, default=3)
    user_agent = Column(Text, nullable=True)
    proxy_url = Column(Text, nullable=True)

    # Host mode settings (Phase 8)
    allowed_user_keys_json = Column(Text, nullable=True)  # JSON array of WhatsApp numbers
    require_approval_per_action = Column(Boolean, default=False)
    blocked_domains_json = Column(Text, nullable=True)  # JSON array of blocked domains

    # Polymorphic configuration
    __mapper_args__ = {
        'polymorphic_identity': 'browser_automation',
    }

    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class AgentSkillIntegration(Base):
    """
    Maps which integration each agent skill uses.

    Allows per-agent configuration of:
    - Which Gmail account the Gmail skill uses
    - Which Calendar/Asana/Flows the scheduler uses
    - Provider selection for multi-provider skills

    Example:
        Agent "Support Bot" (ID 1):
        - gmail skill → uses GmailIntegration 5 (support@acme.com)
        - flows skill → uses CalendarIntegration 3 (team@acme.com) as provider

        Agent "Sales Assistant" (ID 2):
        - gmail skill → uses GmailIntegration 6 (sales@acme.com)
        - flows skill → uses AsanaIntegration 1 (Sales Workspace) as provider
    """
    __tablename__ = "agent_skill_integration"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey('agent.id'), nullable=False, index=True)
    skill_type = Column(String(50), nullable=False)  # 'gmail', 'flows', 'asana', etc.

    # Integration assignment (NULL for built-in providers like Flows)
    integration_id = Column(Integer, ForeignKey('hub_integration.id'), nullable=True)

    # For scheduler skill: which provider type to use
    # Values: 'flows' (default), 'google_calendar', 'asana'
    scheduler_provider = Column(String(50), nullable=True)

    # Additional skill-specific configuration (JSON)
    config = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    agent = relationship("Agent", backref="skill_integrations")
    integration = relationship("HubIntegration")

    __table_args__ = (
        Index("idx_agent_skill_integration", "agent_id", "skill_type", unique=True),
        Index("idx_skill_integration_type", "skill_type"),
        {"sqlite_autoincrement": True},
    )


# ============================================================================
# Phase 14.5 & 14.6: Conversation Search & Knowledge Extraction
# ============================================================================

class ConversationTag(Base):
    """
    Phase 14.6: Tags for conversation threads (AI-generated or user-defined).
    Used to categorize and search conversations by topic.
    """
    __tablename__ = "conversation_tag"

    id = Column(Integer, primary_key=True)
    thread_id = Column(Integer, ForeignKey("conversation_thread.id", ondelete="CASCADE"), nullable=False, index=True)
    tag = Column(String(100), nullable=False, index=True)
    source = Column(String(10), default="ai")  # 'ai' or 'user'
    color = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Multi-tenancy
    tenant_id = Column(String(50), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)

    # Relationships
    thread = relationship("ConversationThread", backref="tags")

    __table_args__ = (
        Index("idx_conversation_tag_tenant_user", "tenant_id", "user_id"),
        {"sqlite_autoincrement": True},
    )


class ConversationInsight(Base):
    """
    Phase 14.6: AI-extracted insights from conversations.
    Captures key learnings, decisions, facts, and action items.
    """
    __tablename__ = "conversation_insight"

    id = Column(Integer, primary_key=True)
    thread_id = Column(Integer, ForeignKey("conversation_thread.id", ondelete="CASCADE"), nullable=False, index=True)
    insight_text = Column(Text, nullable=False)
    insight_type = Column(String(50), default="fact", index=True)  # fact, conclusion, decision, action_item, question
    confidence = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Multi-tenancy
    tenant_id = Column(String(50), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)

    # Relationships
    thread = relationship("ConversationThread", backref="insights")

    __table_args__ = (
        Index("idx_conversation_insight_tenant_user", "tenant_id", "user_id"),
        {"sqlite_autoincrement": True},
    )


class ConversationLink(Base):
    """
    Phase 14.6: Links between related conversation threads.
    AI-suggested relationships based on semantic similarity.
    """
    __tablename__ = "conversation_link"

    id = Column(Integer, primary_key=True)
    source_thread_id = Column(Integer, ForeignKey("conversation_thread.id", ondelete="CASCADE"), nullable=False, index=True)
    target_thread_id = Column(Integer, ForeignKey("conversation_thread.id", ondelete="CASCADE"), nullable=False, index=True)
    relationship_type = Column(String(50), default="related")
    confidence = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Multi-tenancy
    tenant_id = Column(String(50), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)

    # Relationships
    source_thread = relationship("ConversationThread", foreign_keys=[source_thread_id], backref="outgoing_links")
    target_thread = relationship("ConversationThread", foreign_keys=[target_thread_id], backref="incoming_links")

    __table_args__ = (
        Index("idx_conversation_link_tenant_user", "tenant_id", "user_id"),
        {"sqlite_autoincrement": True},
    )


# ============================================================================
# Phase 8 (Browser Automation): Host Browser Audit Logging
# ============================================================================

class HostBrowserAuditLog(Base):
    """
    Audit log for host browser automation actions (security compliance).

    Phase 8: Security audit logging for host mode browser operations.

    All host mode browser actions MUST be logged for:
    - Tracking actions on user's authenticated sessions
    - Security investigation and incident response
    - Compliance with data protection policies

    Note: Container mode actions are NOT logged here (isolated environment).
    """
    __tablename__ = "host_browser_audit_log"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Multi-tenancy and user context
    tenant_id = Column(String(50), nullable=False)
    user_key = Column(String(100), nullable=False)  # WhatsApp number or user identifier
    agent_id = Column(Integer, ForeignKey('agent.id'), nullable=True)

    # Action details
    action = Column(String(50), nullable=False)  # navigate, click, fill, extract, screenshot, execute_script
    url = Column(Text, nullable=True)  # Sanitized (sensitive query params redacted)
    target_element = Column(String(255), nullable=True)  # CSS selector or element reference

    # MCP details
    mcp_tool = Column(String(100), nullable=False)  # Full MCP tool name used
    mcp_params_hash = Column(String(64), nullable=True)  # SHA256 of params (privacy)

    # Execution result
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # Security context
    session_id = Column(String(100), nullable=True)  # Browser session identifier
    ip_address = Column(String(45), nullable=True)  # Client IP (IPv4 or IPv6)

    # Relationships
    agent = relationship("Agent", backref="host_browser_audit_logs")

    __table_args__ = (
        Index("idx_host_browser_audit_timestamp", "timestamp"),
        Index("idx_host_browser_audit_tenant", "tenant_id"),
        Index("idx_host_browser_audit_user", "user_key"),
        Index("idx_host_browser_audit_action", "action"),
        {"sqlite_autoincrement": True},
    )


# ============================================================================
# Backward Compatibility Aliases (deprecated - use Sandboxed* names instead)
# Skills-as-Tools Phase 6: CustomTools renamed to SandboxedTools
# ============================================================================
CustomTool = SandboxedTool
CustomToolCommand = SandboxedToolCommand
CustomToolParameter = SandboxedToolParameter
AgentCustomTool = AgentSandboxedTool
CustomToolExecution = SandboxedToolExecution
