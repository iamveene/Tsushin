import os

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, Float, ForeignKey, Index, UniqueConstraint, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()


def get_remote_access_stack_name() -> str:
    """Return the current Compose stack name for Remote Access defaults."""
    return (os.getenv("TSN_STACK_NAME") or "tsushin").strip() or "tsushin"


def get_remote_access_proxy_target_url() -> str:
    """Return the stack-scoped Caddy proxy target used by Remote Access."""
    return f"http://{get_remote_access_stack_name()}-proxy:80"

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
    model_provider = Column(String(20), default="gemini")  # "openai" | "anthropic" | "gemini" | "groq" | "grok"
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

    # Sentinel fail behavior (LOG-020): "open" allows messages on Sentinel error, "closed" blocks them
    sentinel_fail_behavior = Column(String(10), default="open")

    # Conversation delay (global, WhatsApp-only)
    whatsapp_conversation_delay_seconds = Column(Float, default=5.0)

    # Agentic loop platform bounds (Track F / v0.7.0)
    platform_min_agentic_rounds = Column(Integer, nullable=True, default=1)
    platform_max_agentic_rounds = Column(Integer, nullable=True, default=8)

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
    slack_encryption_key = Column(String(500), nullable=True)  # Slack token encryption (Fernet key) — v0.6.0 Item 33
    discord_encryption_key = Column(String(500), nullable=True)  # Discord token encryption (Fernet key) — v0.6.0 Item 34
    webhook_encryption_key = Column(String(500), nullable=True)  # Webhook HMAC secret encryption (Fernet key) — v0.6.0
    remote_access_encryption_key = Column(String(500), nullable=True)  # Cloudflare Tunnel token encryption (Fernet key) — v0.6.0 Remote Access

    # System-Level AI Configuration (Phase 17: Tenant-Configurable System AI)
    # These settings control which AI provider/model is used for system operations
    # (intent classification, skill routing, AI summaries, flow processing)
    # This allows tenants to switch providers if one has issues (e.g., Gemini down)
    system_ai_provider = Column(String(20), default="gemini")  # Legacy fallback — used only when provider_instance_id is NULL
    system_ai_model = Column(String(100), default="gemini-2.5-flash")  # Default: fast/cheap model for system ops
    system_ai_provider_instance_id = Column(
        Integer,
        ForeignKey("provider_instance.id", ondelete="SET NULL"),
        nullable=True
    )  # Points to a ProviderInstance — preferred over system_ai_provider/model

    # v0.6.0: Default Vector Store (tenant-wide)
    default_vector_store_instance_id = Column(
        Integer,
        ForeignKey("vector_store_instance.id", ondelete="SET NULL"),
        nullable=True
    )

    # v0.6.0-patch.5: Default TTS instance (tenant-wide) — pull-forward from v0.7.0 roadmap K8
    default_tts_instance_id = Column(
        Integer,
        ForeignKey("tts_instance.id", ondelete="SET NULL"),
        nullable=True
    )

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Memory(Base):
    __tablename__ = "memory"

    id = Column(Integer, primary_key=True)
    # BUG-LOG-015: tenant_id enforces isolation at the DB level alongside agent_id.
    # Backfilled from Agent.tenant_id by alembic 0024.
    tenant_id = Column(String(50), nullable=False, index=True)
    agent_id = Column(Integer, nullable=False, index=True)  # FK to Agent - per-agent memory isolation
    sender_key = Column(String(255), nullable=False, index=True)  # chat_id or phone number
    messages_json = Column(JSON, default=list)  # [{"role": "user", "content": "...", "timestamp": "..."}]
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_memory_tenant_agent_sender', 'tenant_id', 'agent_id', 'sender_key'),
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
    friendly_name = Column(String(100), nullable=False)  # "Alice", "Bob", "Agent1"
    whatsapp_id = Column(String(50), nullable=True, index=True)  # WhatsApp internal ID - DEPRECATED: Use channel_mappings
    phone_number = Column(String(20), nullable=True, index=True)  # Phone number - DEPRECATED: Use channel_mappings

    # Phase 10.1.1: Telegram identifiers for cross-channel memory
    telegram_id = Column(String(50), nullable=True, index=True)  # Telegram user ID (numeric) - DEPRECATED: Use channel_mappings
    telegram_username = Column(String(50), nullable=True)  # Optional: @username without @ - DEPRECATED: Use channel_mappings

    role = Column(String(20), default="user")  # "user" | "agent"
    is_active = Column(Boolean, default=True)
    is_dm_trigger = Column(Boolean, default=True)  # Phase 4.3: Trigger agent on DM from this contact (default True for fresh installs)
    slash_commands_enabled = Column(Boolean, nullable=True, default=None)  # Feature #12: NULL = use tenant default, True/False = explicit override
    notes = Column(Text)  # Optional notes about the contact

    # Phase 7.6.2: Multi-tenancy support
    tenant_id = Column(String(50), nullable=True, index=True)  # FK to tenant
    user_id = Column(Integer, nullable=True, index=True)  # FK to user who created the contact

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Phase 10.2: Relationship to channel mappings
    channel_mappings = relationship("ContactChannelMapping", back_populates="contact", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('friendly_name', 'tenant_id', name='uq_contact_friendly_name_tenant'),
    )


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
    description = Column(Text, nullable=True)  # Short human-readable description of the agent
    persona_id = Column(Integer, nullable=True)  # FK to Persona (replaces tone_preset_id/custom_tone)

    # Legacy tone fields (kept for backward compatibility, will be migrated)
    tone_preset_id = Column(Integer, nullable=True)  # DEPRECATED: Use persona_id instead
    custom_tone = Column(Text, nullable=True)  # DEPRECATED: Use persona_id instead

    # Trigger keywords for group chats
    keywords = Column(JSON, default=list)  # ["help", "assistant", "bot"]

    # Tool configuration - DEPRECATED: Migrated to Skills system
    # enabled_tools removed - use AgentSkill table for skills like web_search, web_scraping

    # Model configuration
    model_provider = Column(String(20), default="gemini")  # "openai" | "anthropic" | "gemini" | "groq" | "grok"
    model_name = Column(String(100), default="gemini-2.5-pro")

    # Response formatting
    response_template = Column(Text, default="@{agent_name}: {response}")  # Template for response formatting

    # Per-Agent Configuration (NULL = use system default)
    # Memory Configuration
    memory_size = Column(Integer, nullable=True)  # Ring buffer size per sender (NULL = use system default)
    # Values constrained to constants.agent_config.MEMORY_ISOLATION_MODES
    # (currently: "isolated" | "shared" | "channel_isolated"). Default kept
    # here as a literal so Alembic autogenerate does not trip on imports.
    memory_isolation_mode = Column(String(20), default="isolated")

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

    # v0.6.0 Item 37: Temporal Memory Decay
    memory_decay_enabled = Column(Boolean, default=False)  # Master switch (existing agents unaffected)
    memory_decay_lambda = Column(Float, default=0.01)  # Exponential decay rate (0.01 ≈ 69-day half-life)
    memory_decay_archive_threshold = Column(Float, default=0.05)  # Auto-archive below this effective score
    memory_decay_mmr_lambda = Column(Float, default=0.5)  # MMR diversity weight (0=max diversity, 1=pure relevance)

    # v0.7.0 Track F: bounded outer agentic loop configuration
    max_agentic_rounds = Column(Integer, nullable=True, default=1)
    max_agentic_loop_bytes = Column(Integer, nullable=True, default=8192)

    # Phase 10: Channel Configuration
    # Determines which channels this agent can interact through
    enabled_channels = Column(JSON, default=["playground", "whatsapp"])  # Available: playground, whatsapp, telegram, slack, discord, webhook
    whatsapp_integration_id = Column(Integer, ForeignKey("whatsapp_mcp_instance.id", ondelete="SET NULL"), nullable=True)  # Specific MCP instance
    telegram_integration_id = Column(Integer, nullable=True)  # Future: FK to TelegramBotInstance
    slack_integration_id = Column(Integer, ForeignKey("slack_integration.id", ondelete="SET NULL"), nullable=True)  # v0.6.0 Item 33: FK to SlackIntegration
    discord_integration_id = Column(Integer, ForeignKey("discord_integration.id", ondelete="SET NULL"), nullable=True)  # v0.6.0 Item 34: FK to DiscordIntegration
    webhook_integration_id = Column(Integer, ForeignKey("webhook_integration.id", ondelete="SET NULL"), nullable=True)  # v0.6.0: FK to WebhookIntegration
    provider_instance_id = Column(Integer, ForeignKey("provider_instance.id", ondelete="SET NULL"), nullable=True)

    # v0.6.0: Vector Store Configuration
    vector_store_instance_id = Column(Integer, ForeignKey("vector_store_instance.id", ondelete="SET NULL"), nullable=True)
    vector_store_mode = Column(String(20), default="override")  # "override" | "complement" | "shadow"

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
    tenant_id = Column(String(100), nullable=True, index=True)  # BUG-LOG-012: Tenant isolation
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserChannelDefaultAgent(Base):
    """Per-user default agent override for a channel within a tenant."""

    __tablename__ = "user_channel_default_agent"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_type = Column(String(32), nullable=False, index=True)
    user_identifier = Column(String(256), nullable=False)
    agent_id = Column(Integer, ForeignKey("agent.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "channel_type", "user_identifier", name="uq_user_channel_default_agent"),
    )


class ApiKey(Base):
    """
    Phase 4.6: Stores API keys for LLM providers and tool services.
    Phase 7.9.2: Added tenant_id for multi-tenancy support.
    Phase SEC-001: Added encryption at rest for API keys (CRIT-003 fix).
    Allows users to configure API keys via UI instead of environment variables.
    """
    __tablename__ = "api_key"

    id = Column(Integer, primary_key=True)
    service = Column(String(50), nullable=False, index=True)  # 'anthropic', 'openai', 'gemini', 'brave_search'
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
    )


class ProviderInstance(Base):
    """
    Phase 21: Multi-instance provider support.
    Each tenant can configure multiple provider endpoints (e.g., multiple OpenAI-compatible
    servers, Ollama instances, or custom LLM gateways) with independent API keys, base URLs,
    and model availability. Agents reference a specific provider instance via FK.
    """
    __tablename__ = "provider_instance"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    vendor = Column(String(30), nullable=False)  # 'openai'|'anthropic'|'gemini'|'groq'|'grok'|'openrouter'|'vertex_ai'|'ollama'|'custom'
    instance_name = Column(String(100), nullable=False)
    base_url = Column(String(500), nullable=True)  # NULL = vendor default
    api_key_encrypted = Column(Text, nullable=True)  # Fernet-encrypted
    extra_config = Column(JSON, default=dict)  # Vendor-specific: vertex_ai stores project_id, region, sa_email
    available_models = Column(JSON, default=list)
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    health_status = Column(String(20), default='unknown')  # healthy|degraded|unavailable|unknown
    health_status_reason = Column(String(500), nullable=True)
    last_health_check = Column(DateTime, nullable=True)

    # v0.6.0-patch.5: Auto-provisioning (pull-forward from v0.7.0 roadmap O1)
    # Ollama gets container lifecycle columns so a tenant can opt into a
    # tsushin-managed Ollama container instead of pointing at host Ollama.
    # All columns are nullable / safe-default so host-Ollama rows
    # (is_auto_provisioned=False) are unaffected.
    is_auto_provisioned = Column(Boolean, default=False, nullable=False)
    container_name = Column(String(200), nullable=True)
    container_id = Column(String(80), nullable=True)
    container_port = Column(Integer, nullable=True)
    container_status = Column(String(20), default='none', nullable=False)  # none|creating|running|stopped|error
    container_image = Column(String(200), nullable=True)
    volume_name = Column(String(150), nullable=True)
    gpu_enabled = Column(Boolean, default=False, nullable=False)
    pulled_models = Column(JSON, default=list, nullable=True)  # list[str] of pulled Ollama model names
    mem_limit = Column(String(20), nullable=True)
    cpu_quota = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('tenant_id', 'instance_name', name='uq_provider_instance_tenant_name'),
        Index('idx_pi_tenant_vendor', 'tenant_id', 'vendor'),
    )


class ProviderUrlPolicy(Base):
    """
    Phase 21: URL allowlist/blocklist for provider base URLs.
    Admins can restrict which base URLs tenants may connect to, preventing
    SSRF and enforcing corporate proxy / gateway policies.
    Scope can be 'global' (system-wide) or 'tenant' (per-tenant override).
    """
    __tablename__ = "provider_url_policy"

    id = Column(Integer, primary_key=True)
    scope = Column(String(10), nullable=False)  # 'global' | 'tenant'
    tenant_id = Column(String(50), nullable=True)  # NULL when scope='global'
    policy_type = Column(String(10), nullable=False)  # 'allowlist' | 'blocklist'
    url_pattern = Column(String(500), nullable=False)
    description = Column(String(255), nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProviderConnectionAudit(Base):
    """
    Phase 21: Audit trail for provider connection events.
    Logs every connection attempt (health checks, model discovery, chat requests)
    including the resolved IP address for SSRF post-incident analysis.
    """
    __tablename__ = "provider_connection_audit"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False)
    user_id = Column(Integer, nullable=True)
    provider_instance_id = Column(Integer, nullable=False)
    action = Column(String(30), nullable=False)  # 'test_connection'|'model_discovery'|'chat_request'
    resolved_ip = Column(String(45), nullable=True)
    base_url = Column(String(500), nullable=True)
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ApiClient(Base):
    """
    Public API v1: OAuth2 client credentials for programmatic API access.
    Each API client belongs to a tenant and has a role-based permission scope.
    Secret is hashed with Argon2 (same as user passwords).
    """
    __tablename__ = "api_client"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey('tenant.id'), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    client_id = Column(String(50), unique=True, nullable=False, index=True)  # tsn_ci_<random>
    client_secret_hash = Column(String(255), nullable=False)  # Argon2 hash of tsn_cs_<random>
    client_secret_prefix = Column(String(12), nullable=False)  # First 12 chars for display/lookup
    secret_rotated_at = Column(DateTime, nullable=True)  # tracks last rotation for JWT invalidation
    role = Column(String(30), default='api_agent_only')  # api_owner, api_admin, api_member, api_readonly, api_agent_only, custom
    custom_scopes = Column(JSON, nullable=True)  # Only when role='custom': ["agents.read", "agents.execute"]
    is_active = Column(Boolean, default=True)
    rate_limit_rpm = Column(Integer, default=60)  # Requests per minute
    expires_at = Column(DateTime, nullable=True)  # Optional expiry date
    last_used_at = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey('user.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('uq_api_client_tenant_name', 'tenant_id', 'name', unique=True),
    )


class ApiClientToken(Base):
    """
    Public API v1: Tracks issued JWT access tokens for audit and revocation.
    Tokens are short-lived (1h TTL) and tied to a specific API client.
    """
    __tablename__ = "api_client_token"

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_client_id = Column(Integer, ForeignKey('api_client.id', ondelete='CASCADE'), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, index=True)  # SHA-256 of the JWT
    scopes = Column(JSON, nullable=False)  # Scopes granted for this token
    issued_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    ip_address = Column(String(45), nullable=True)  # Client IP for audit


class ApiRequestLog(Base):
    """
    Public API v1: Request audit log for tracking API usage per client.
    """
    __tablename__ = "api_request_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_client_id = Column(Integer, ForeignKey('api_client.id'), nullable=False, index=True)
    method = Column(String(10), nullable=False)  # GET, POST, PUT, DELETE
    path = Column(String(500), nullable=False)  # /api/v1/agents
    status_code = Column(Integer, nullable=False)
    response_time_ms = Column(Integer, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


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
    last_accessed_at = Column(DateTime, default=datetime.utcnow)  # v0.6.0 Item 37: Temporal Decay


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
    last_accessed_at = Column(DateTime, default=datetime.utcnow)  # v0.6.0 Item 37: Temporal Decay


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
    auto_inject_results = Column(Boolean, nullable=True, default=True)
    skip_ai_on_data_fetch = Column(Boolean, nullable=True, default=False)
    max_result_bytes = Column(Integer, nullable=True, default=2048)
    max_results_retained = Column(Integer, nullable=True, default=2)
    max_turns_lookback = Column(Integer, nullable=True, default=6)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CustomSkill(Base):
    """
    Phase 22: Custom Skills Foundation
    Stores tenant-created custom skills that can be assigned to agents.
    Supports instruction-based, script-based, and MCP server skill types.
    """
    __tablename__ = "custom_skill"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    source = Column(String(20), nullable=False, default='tenant')  # tenant|marketplace|builtin
    slug = Column(String(100), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(10), nullable=True)  # emoji
    skill_type_variant = Column(String(20), nullable=False, default='instruction')  # instruction|script|mcp_server
    execution_mode = Column(String(20), nullable=False, default='tool')  # tool|hybrid|passive
    instructions_md = Column(Text, nullable=True)
    script_entrypoint = Column(String(50), nullable=True)
    script_content = Column(Text, nullable=True)
    script_language = Column(String(20), nullable=True)  # python|bash|nodejs
    script_content_hash = Column(String(64), nullable=True)
    input_schema = Column(JSON, default=dict)
    output_schema = Column(JSON, nullable=True)
    config_schema = Column(JSON, default=list)
    trigger_mode = Column(String(20), default='llm_decided')  # keyword|always_on|llm_decided
    trigger_keywords = Column(JSON, default=list)
    priority = Column(Integer, default=50)
    sentinel_profile_id = Column(Integer, nullable=True)
    timeout_seconds = Column(Integer, nullable=False, default=30)
    is_enabled = Column(Boolean, nullable=False, default=True)
    is_system_owned = Column(Boolean, nullable=False, default=False)
    editable_by_tenant = Column(Boolean, nullable=False, default=True)
    deletable_by_tenant = Column(Boolean, nullable=False, default=True)
    scan_status = Column(String(20), default='pending')  # pending|clean|rejected
    last_scan_result = Column(JSON, nullable=True)
    version = Column(String(20), nullable=False, default='1.0.0')
    mcp_server_id = Column(Integer, ForeignKey("mcp_server_config.id", ondelete="SET NULL"), nullable=True)
    mcp_tool_name = Column(String(200), nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint('tenant_id', 'slug', name='uq_custom_skill_tenant_slug'),)


class CustomSkillVersion(Base):
    """
    Phase 22: Custom Skills Foundation
    Stores version snapshots of custom skills for audit and rollback.
    """
    __tablename__ = "custom_skill_version"

    id = Column(Integer, primary_key=True)
    custom_skill_id = Column(Integer, ForeignKey("custom_skill.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(String(20), nullable=False)
    snapshot_json = Column(JSON, nullable=False)
    changed_by = Column(Integer, nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow)


class AgentCustomSkill(Base):
    """
    Phase 22: Custom Skills Foundation
    Maps custom skills to agents with per-agent configuration overrides.
    """
    __tablename__ = "agent_custom_skill"

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey("agent.id", ondelete="CASCADE"), nullable=False, index=True)
    custom_skill_id = Column(Integer, ForeignKey("custom_skill.id", ondelete="CASCADE"), nullable=False, index=True)
    is_enabled = Column(Boolean, default=True)
    config = Column(JSON, default=dict)
    priority_override = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint('agent_id', 'custom_skill_id', name='uq_agent_custom_skill'),)


class CustomSkillExecution(Base):
    """
    Phase 22: Custom Skills Foundation
    Logs execution history for custom skills for analytics and debugging.
    """
    __tablename__ = "custom_skill_execution"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    agent_id = Column(Integer, nullable=True)
    custom_skill_id = Column(Integer, ForeignKey("custom_skill.id", ondelete="SET NULL"), nullable=True)
    skill_name = Column(String(200), nullable=True)
    input_json = Column(JSON, nullable=True)
    output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default='pending')  # pending|running|completed|failed
    execution_time_ms = Column(Integer, nullable=True)
    sentinel_result = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class MCPServerConfig(Base):
    """
    Phase 22.4: MCP Server Integration
    Stores external MCP server configurations for tenant tool providers.
    Supports SSE, Streamable HTTP, and stdio transport types.
    """
    __tablename__ = "mcp_server_config"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    server_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    transport_type = Column(String(20), nullable=False)  # 'sse'|'streamable_http'|'stdio'
    server_url = Column(String(500), nullable=True)  # For SSE/HTTP transports
    auth_type = Column(String(20), default='none')  # 'none'|'bearer'|'header'|'api_key'
    auth_token_encrypted = Column(Text, nullable=True)
    auth_header_name = Column(String(100), nullable=True)
    stdio_binary = Column(String(100), nullable=True)  # For stdio transport
    stdio_args = Column(JSON, default=list)
    trust_level = Column(String(20), default='untrusted')  # 'system'|'verified'|'untrusted'
    connection_status = Column(String(20), default='disconnected')  # disconnected|connecting|healthy|degraded
    max_retries = Column(Integer, default=3)
    timeout_seconds = Column(Integer, default=30)
    idle_timeout_seconds = Column(Integer, default=300)
    is_active = Column(Boolean, default=True)
    last_connected_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('tenant_id', 'server_name', name='uq_mcp_server_tenant_name'),
    )


class MCPDiscoveredTool(Base):
    """
    Phase 22.4: MCP Server Integration
    Stores tools discovered from connected MCP servers.
    Uses namespaced names ({server_name}__{tool_name}) to avoid collisions.
    """
    __tablename__ = "mcp_discovered_tool"

    id = Column(Integer, primary_key=True)
    server_id = Column(Integer, ForeignKey("mcp_server_config.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    tool_name = Column(String(200), nullable=False)
    namespaced_name = Column(String(300), nullable=False)  # {server_name}__{tool_name}
    description = Column(Text, nullable=True)
    input_schema = Column(JSON, default=dict)
    is_enabled = Column(Boolean, default=True)
    scan_status = Column(String(20), default='pending')
    discovered_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('server_id', 'tool_name', name='uq_mcp_tool_server_name'),
    )


class MCPServerHealth(Base):
    """
    Phase 22.4: MCP Server Integration
    Stores health check history for MCP server connections.
    """
    __tablename__ = "mcp_server_health"

    id = Column(Integer, primary_key=True)
    server_id = Column(Integer, ForeignKey("mcp_server_config.id", ondelete="CASCADE"), nullable=False, index=True)
    check_type = Column(String(20), nullable=False)  # 'ping'|'list_tools'|'manual'
    success = Column(Boolean, nullable=False)
    latency_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    checked_at = Column(DateTime, default=datetime.utcnow)


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

    __table_args__ = (
        UniqueConstraint('tool_id', 'command_name', name='uq_sandboxed_tool_command_name'),
    )


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

    __table_args__ = (
        UniqueConstraint('command_id', 'parameter_name', name='uq_sandboxed_tool_param_name'),
    )


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
    # BUG-614 FIX: tenant_id column added (alembic 0042) so the playground
    # debug panel (routes_playground.py) can scope tool-execution history
    # to the caller's tenant. Before this column existed the debug query
    # silently returned zero rows OR crashed depending on the ORM version
    # because it referenced a column that did not exist in the real
    # PostgreSQL schema. Backfilled from ``agent_run.agent_id`` →
    # ``agent.tenant_id`` when possible; otherwise NULL (legacy rows
    # predate multi-tenancy).
    tenant_id = Column(String(50), nullable=True, index=True)  # FK to tenant (soft-ref)
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
    execution_method = Column(String(20), default='immediate')  # 'immediate' | 'scheduled' | 'recurring' | 'keyword'
    scheduled_at = Column(DateTime, nullable=True)  # For scheduled execution
    recurrence_rule = Column(JSON, nullable=True)  # Cron-like config: {frequency, interval, days_of_week, timezone}

    # BUG-336: Keyword trigger support — list of keywords/commands that fire this flow
    # e.g. ["/testflow", "start report", "run workflow"]
    trigger_keywords = Column(JSON, default=list, nullable=True)

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
    is_system_owned = Column(Boolean, nullable=False, default=False)
    editable_by_tenant = Column(Boolean, nullable=False, default=True)
    deletable_by_tenant = Column(Boolean, nullable=False, default=True)
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
    # v0.7.0: Triggers↔Flows Unification — bindings to one or more triggers.
    bindings = relationship(
        "FlowTriggerBinding",
        back_populates="flow",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("idx_flow_execution_method", "execution_method"),
        Index("idx_flow_next_execution", "next_execution_at"),
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

    # v0.7.0: Triggers↔Flows Unification — correlation back to the
    # WakeEvent that woke this flow (for triggered flows). NULL for
    # manual / scheduled / API-driven runs. SET NULL on wake_event
    # delete (audit retention boundary).
    trigger_event_id = Column(
        Integer,
        ForeignKey("wake_event.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    flow = relationship("FlowDefinition", back_populates="runs")
    step_runs = relationship("FlowNodeRun", back_populates="run", cascade="all, delete-orphan", order_by="FlowNodeRun.id")

    __table_args__ = (
        Index("idx_flow_run_status", "status"),
        Index("idx_flow_run_tenant_status", "tenant_id", "status"),
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
    api_client_id = Column(String(100), nullable=True, index=True)  # BUG-367: API v1 client isolation
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
    agentic_scratchpad = Column(JSON, nullable=True)  # Bounded multi-round agentic loop trace

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
    - Discord (Phase 23: bot with per-integration public_key — BUG-311/313)
    - Slack (Phase 23: workspace with per-integration signing_secret — BUG-312)
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


class JiraIntegration(HubIntegration):
    """
    Jira Tool API Integration.
    Stores tenant-scoped Jira Cloud connection settings for Jira triggers.
    """
    __tablename__ = "jira_integration"

    id = Column(Integer, ForeignKey("hub_integration.id", ondelete="CASCADE"), primary_key=True)
    site_url = Column(String(500), nullable=False)
    project_key = Column(String(64), nullable=True)
    auth_email = Column(String(255), nullable=True)
    api_token_encrypted = Column(Text, nullable=True)
    api_token_preview = Column(String(32), nullable=True)
    # 'programmatic' = REST API + token (shipped); 'agentic' = Atlassian Remote
    # MCP (OAuth 2.1) — UI exposes the option as "coming soon" but backend
    # rejects this value with 400 until the agentic transport ships.
    provider_mode = Column(String(16), nullable=False, server_default="programmatic")

    __mapper_args__ = {
        'polymorphic_identity': 'jira',
    }

    __table_args__ = (
        Index("idx_jira_integration_site_url", "site_url"),
        Index("idx_jira_integration_auth_email", "auth_email"),
    )


class GitHubIntegration(HubIntegration):
    """
    GitHub Hub Integration.

    Stores tenant-scoped GitHub connection settings used by the
    ``code_repository`` skill. The ``provider`` column is currently always
    ``github`` but is reserved so the table can host other repository
    providers (Bitbucket, GitLab) in the future.

    Auth today: Personal Access Token (PAT). ``auth_method`` reserves space
    for ``app`` (GitHub App installation) when that ships.

    Mirrors the shape of :class:`JiraIntegration` exactly (polymorphic
    single-table-inheritance subclass of ``HubIntegration``).
    """
    __tablename__ = "github_integration"

    id = Column(Integer, ForeignKey("hub_integration.id", ondelete="CASCADE"), primary_key=True)
    # Reserved for future providers (bitbucket, gitlab). Always 'github' today.
    provider = Column(String(32), nullable=False, server_default="github")
    # 'pat' (shipped) | 'app' (reserved — GitHub App installation flow)
    auth_method = Column(String(20), nullable=False, server_default="pat")
    pat_token_encrypted = Column(Text, nullable=True)
    pat_token_preview = Column(String(32), nullable=True)
    # Optional default repo owner / name surfaced in the UI as a convenience
    # so callers don't have to specify both each request.
    default_owner = Column(String(100), nullable=True)
    default_repo = Column(String(100), nullable=True)
    # 'programmatic' = REST API + PAT (shipped); 'agentic' reserved for a
    # future GitHub MCP transport. Backend rejects 'agentic' until shipped.
    provider_mode = Column(String(16), nullable=False, server_default="programmatic")

    __mapper_args__ = {
        'polymorphic_identity': 'github',
    }

    __table_args__ = (
        Index("idx_github_integration_provider", "provider"),
        Index("idx_github_integration_default_owner", "default_owner"),
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
    detect_browser_ssrf = Column(Boolean, default=True, nullable=False)
    detect_vector_store_poisoning = Column(Boolean, default=True, nullable=False)
    detect_continuous_agent_action_approval = Column(Boolean, default=True, nullable=False)

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
    browser_ssrf_prompt = Column(Text, nullable=True)
    vector_store_poisoning_prompt = Column(Text, nullable=True)
    continuous_agent_action_approval_prompt = Column(Text, nullable=True)

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

    # Vector store access controls (Item 5)
    vector_store_access_enabled = Column(Boolean, nullable=True)  # NULL = inherit
    vector_store_allowed_configs = Column(JSON, nullable=True)  # List of allowed VectorStoreInstance IDs
    detect_continuous_agent_action_approval = Column(Boolean, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationship
    agent = relationship("Agent", backref="sentinel_agent_config")


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
    detection_type = Column(String(64), nullable=False)  # 'prompt_injection', 'agent_takeover', etc.

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
    detection_type = Column(String(64), nullable=False)
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
        System profile "Permissive" (is_system=True, is_default=True):
        - detection_mode='detect_only', aggressiveness_level=1
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
    okg_detection_mode = Column(String(20), default="block", nullable=False)  # V060-MEM-025: OKG-specific detection mode
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
    # passive_deletes=True on both backrefs: profile_id is CASCADE+NOT NULL
    # (deleting a SentinelProfile would fail without this) and agent_id is
    # CASCADE+nullable=True (without this the row is left as a zombie with NULL
    # agent_id instead of being deleted as the CASCADE intends).
    profile = relationship(
        "SentinelProfile",
        backref=backref("assignments", passive_deletes=True),
    )
    agent = relationship(
        "Agent",
        backref=backref("sentinel_profile_assignments", passive_deletes=True),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_id", "skill_type", name="uq_sentinel_profile_assignment_scope"),
        Index("idx_profile_assign_tenant", "tenant_id"),
        Index("idx_profile_assign_agent", "agent_id"),
        Index("idx_profile_assign_profile", "profile_id"),
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
    display_name = Column(String(100), nullable=True)  # Optional human-readable label (e.g., "Support Bot")
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

    # v0.6.0 Item 38: Circuit Breaker State
    circuit_breaker_state = Column(String(20), default="closed")  # closed, open, half_open
    circuit_breaker_opened_at = Column(DateTime, nullable=True)
    circuit_breaker_failure_count = Column(Integer, default=0)

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
    default_agent_id = Column(Integer, ForeignKey("agent.id", ondelete="SET NULL"), nullable=True, index=True)

    # Relationships
    # tenant = relationship("Tenant")  # Requires models_rbac import
    # creator = relationship("User")   # Requires models_rbac import

    __table_args__ = (
        Index("idx_mcp_instance_tenant", "tenant_id"),
        Index("idx_mcp_instance_status", "status"),
        Index("idx_mcp_instance_port", "mcp_port"),
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

    # v0.6.0 Item 38: Circuit Breaker State
    circuit_breaker_state = Column(String(20), default="closed")  # closed, open, half_open
    circuit_breaker_opened_at = Column(DateTime, nullable=True)
    circuit_breaker_failure_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

    # Webhook configuration (optional, polling is default)
    use_webhook = Column(Boolean, default=False)
    webhook_url = Column(String(500), nullable=True)
    webhook_secret_encrypted = Column(Text, nullable=True)  # MED-002 Security Fix: Fernet encrypted

    # Polling state
    last_update_id = Column(Integer, default=0)  # For getUpdates offset

    # Metadata
    created_by = Column(Integer, ForeignKey('user.id'), nullable=False)
    default_agent_id = Column(Integer, ForeignKey("agent.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_telegram_instance_tenant", "tenant_id"),
        Index("idx_telegram_instance_status", "status"),
        Index("idx_telegram_instance_username", "bot_username"),
    )


# ============================================================================
# v0.6.0 Item 33: Slack Integration
# ============================================================================

class SlackIntegration(Base):
    """
    v0.6.0 Item 33: Slack Workspace Integration

    Manages Slack workspace connections per tenant via Socket Mode or HTTP Events API.
    Tokens are encrypted with Fernet (per-workspace key derivation).

    Example:
        Tenant "acme-corp" → Slack workspace "Acme HQ" (team_id: T0123ABC)
    """
    __tablename__ = "slack_integration"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(100), nullable=False, index=True)
    workspace_id = Column(String(50), nullable=False)       # Slack team_id
    app_id = Column(String(50), nullable=True, index=True)  # Slack App ID (A0xxxxx) — BUG-312 fix
    workspace_name = Column(String(200))
    bot_token_encrypted = Column(Text, nullable=False)       # xoxb-... (Fernet)
    app_token_encrypted = Column(Text)                       # xapp-... (Socket Mode)
    signing_secret_encrypted = Column(Text)                  # HTTP mode
    mode = Column(String(20), default="socket")              # "socket" or "http"
    bot_user_id = Column(String(50))                         # Bot's Slack user ID
    is_active = Column(Boolean, default=True)
    status = Column(String(20), default="inactive")          # inactive/connected/error
    health_status = Column(String(20), default="unknown")    # v0.6.0 Item 38: unknown/healthy/unhealthy
    last_health_check = Column(DateTime, nullable=True)      # v0.6.0 Item 38
    dm_policy = Column(String(20), default="allowlist")      # open/allowlist/disabled
    allowed_channels = Column(JSON, default=[])              # List of allowed channel_ids
    default_agent_id = Column(Integer, ForeignKey("agent.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # v0.6.0 Item 38: Circuit Breaker State
    circuit_breaker_state = Column(String(20), default="closed")  # closed, open, half_open
    circuit_breaker_opened_at = Column(DateTime, nullable=True)
    circuit_breaker_failure_count = Column(Integer, default=0)

    __table_args__ = (
        Index("idx_slack_integration_tenant", "tenant_id"),
        Index("idx_slack_integration_status", "status"),
    )


class DiscordIntegration(Base):
    """
    v0.6.0 Item 34: Discord Bot Integration

    Manages Discord bot connections per tenant via REST API (outbound) and
    Gateway events (inbound). Bot token is encrypted with Fernet.

    Example:
        Tenant "acme-corp" → Discord Bot "Acme Bot" (application_id: 123456789)
    """
    __tablename__ = "discord_integration"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(100), nullable=False, index=True)
    bot_token_encrypted = Column(Text, nullable=False)          # Bot token (Fernet)
    application_id = Column(String(50), nullable=False)         # Discord Application ID
    public_key = Column(String(128), nullable=True)             # Ed25519 public key for interaction verification (BUG-311/313 fix)
    bot_user_id = Column(String(50))                            # Bot's Discord user ID
    is_active = Column(Boolean, default=True)
    status = Column(String(20), default="inactive")             # inactive/connected/error
    health_status = Column(String(20), default="unknown")       # v0.6.0 Item 38: unknown/healthy/unhealthy
    last_health_check = Column(DateTime, nullable=True)         # v0.6.0 Item 38
    dm_policy = Column(String(20), default="allowlist")         # open/allowlist/disabled
    allowed_guilds = Column(JSON, default=[])                   # List of allowed guild (server) IDs
    guild_channel_config = Column(JSON, default={})             # Per-guild channel configuration
    default_agent_id = Column(Integer, ForeignKey("agent.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # v0.6.0 Item 38: Circuit Breaker State
    circuit_breaker_state = Column(String(20), default="closed")  # closed, open, half_open
    circuit_breaker_opened_at = Column(DateTime, nullable=True)
    circuit_breaker_failure_count = Column(Integer, default=0)

    __table_args__ = (
        Index("idx_discord_integration_tenant", "tenant_id"),
        Index("idx_discord_integration_status", "status"),
    )


# ============================================================================
# v0.6.0: Webhook-as-a-Channel Integration
# ============================================================================

class WebhookIntegration(Base):
    """
    v0.6.0: Webhook Channel Integration

    Bidirectional HTTP webhook channel. External systems POST HMAC-signed
    events to /api/webhooks/{id}/inbound; responses are optionally POSTed
    back to customer-provided callback URL (also HMAC-signed).

    Inbound auth: HMAC-SHA256 signature mandatory (X-Tsushin-Signature header)
    + timestamp replay protection (X-Tsushin-Timestamp, ±5 min window).
    Optional per-webhook IP allowlist + rate limit as defense-in-depth.

    No container is spawned — webhooks are stateless HTTP in/out. Handlers
    are FastAPI routes + shared QueueWorker (matches Telegram/Slack pattern).
    """
    __tablename__ = "webhook_integration"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey('tenant.id'), nullable=False, index=True)
    integration_name = Column(String(100), nullable=False)

    # v0.7.1: human-readable slug used in inbound path. Globally unique.
    # Auto mode: wh-{6-hex}. Custom mode: user-supplied, validated.
    slug = Column(String(64), nullable=False, unique=True, index=True)

    # Inbound identity (HMAC key, encrypted with Fernet)
    api_secret_encrypted = Column(Text, nullable=False)
    api_secret_preview = Column(String(16), nullable=False)  # first 8 chars + "…" for UI

    # Outbound callback (optional bidirectional mode)
    callback_url = Column(String(500), nullable=True)
    callback_enabled = Column(Boolean, default=False)

    # Optional inbound defense layers
    ip_allowlist_json = Column(Text, nullable=True)  # JSON list of CIDRs
    rate_limit_rpm = Column(Integer, default=30)
    max_payload_bytes = Column(Integer, default=1048576)  # 1 MB

    # Status
    is_active = Column(Boolean, default=True)
    status = Column(String(20), default="active")  # active/paused/error
    health_status = Column(String(20), default="unknown")  # unknown/healthy/unhealthy
    last_health_check = Column(DateTime, nullable=True)
    last_activity_at = Column(DateTime, nullable=True)

    # v0.6.0 Item 38: Circuit Breaker State (for outbound callback failures)
    circuit_breaker_state = Column(String(20), default="closed")  # closed/open/half_open
    circuit_breaker_opened_at = Column(DateTime, nullable=True)
    circuit_breaker_failure_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

    # Retry config
    max_retry_attempts = Column(Integer, default=3)
    retry_timeout_seconds = Column(Integer, default=300)
    default_agent_id = Column(Integer, ForeignKey("agent.id", ondelete="SET NULL"), nullable=True, index=True)
    trigger_criteria = Column(JSON, nullable=True)

    # Audit
    created_by = Column(Integer, ForeignKey('user.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_webhook_integration_tenant", "tenant_id"),
        Index("idx_webhook_integration_status", "status"),
    )


# ============================================================================
# v0.7.0: Triggers↔Flows Unification — flow_trigger_binding + webhook payload capture
# ============================================================================


class FlowTriggerBinding(Base):
    """
    v0.7.0: Edge between a trigger (channel instance) and a Flow.

    One Flow can listen to N triggers (fan-in across kinds). One trigger
    can wake N Flows (fan-out). Combined with the new ``source`` step
    type, this is what lets ``trigger_dispatch_service`` enqueue
    FlowRuns alongside the legacy ContinuousRuns.

    ``trigger_instance_id`` is a *semantic* FK into one of the per-kind
    channel-instance tables (jira_trigger / email_trigger /
    github_trigger / schedule_trigger / webhook_integration). It is NOT
    declared as a SQL FK because there is no single target table —
    binding cleanup on trigger DELETE is handled application-side by
    ``flow_binding_service.delete_bindings_for_trigger``.

    Phase A auto-generation (Wave 4) creates a binding row for every
    new trigger with ``is_system_managed=True`` so the auto-flow can be
    distinguished from user-authored bindings.

    Whole feature is gated by ``TSN_FLOWS_TRIGGER_BINDING_ENABLED``
    (default false in 0.7.0).
    """
    __tablename__ = "flow_trigger_binding"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        String(50),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
    )
    flow_definition_id = Column(
        Integer,
        ForeignKey("flow_definition.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 'jira' | 'email' | 'github' | 'schedule' | 'webhook'
    trigger_kind = Column(String(32), nullable=False)
    trigger_instance_id = Column(Integer, nullable=False)
    # Pointer to the FlowNode of type 'source' inside the bound flow.
    # SET NULL on flow_node delete so a Source-step deletion doesn't
    # orphan the binding row; FlowEngine recreates it lazily.
    source_node_id = Column(
        Integer,
        ForeignKey("flow_node.id", ondelete="SET NULL"),
        nullable=True,
    )
    # When True: dispatch skips the legacy ContinuousRun for this
    # (kind, instance_id), letting the bound Flow take over fully.
    # Default False on backfilled rows for parallel-run safety; new
    # user-authored bindings default True (clean ownership).
    suppress_default_agent = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    # Marks the auto-generated 1-flow-per-trigger row created by Phase A.
    is_system_managed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    flow = relationship("FlowDefinition", back_populates="bindings")
    source_node = relationship("FlowNode")

    __table_args__ = (
        UniqueConstraint(
            "flow_definition_id",
            "trigger_kind",
            "trigger_instance_id",
            name="uq_flow_trigger_binding_unique",
        ),
        Index(
            "ix_flow_trigger_binding_lookup",
            "tenant_id", "trigger_kind", "trigger_instance_id", "is_active",
        ),
        Index("ix_flow_trigger_binding_flow", "flow_definition_id"),
    )


class WebhookPayloadCapture(Base):
    """
    v0.7.0: Last-N (default 5) inbound payloads per webhook integration.

    Used by Wave 5's frontend autocomplete to infer
    ``{{source.payload.*}}`` paths in the Flow editor. The ringbuffer
    is enforced application-side in ``routes_webhook_inbound.py`` after
    a successful dispatch — older rows are deleted to keep at most the
    5 most recent for each ``(tenant_id, webhook_id)``.

    Payload is stored as text (truncated to ~64KB at write time).
    Headers are minimally redacted (auth/cookie stripped). Both fields
    are JSON.parse'd at read time.
    """
    __tablename__ = "webhook_payload_capture"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        String(50),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
    )
    webhook_id = Column(
        Integer,
        ForeignKey("webhook_integration.id", ondelete="CASCADE"),
        nullable=False,
    )
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    payload_json = Column(Text, nullable=False)
    headers_json = Column(Text, nullable=True)
    dedupe_key = Column(String(512), nullable=True)

    __table_args__ = (
        Index(
            "ix_webhook_payload_capture_recent",
            "tenant_id", "webhook_id", "captured_at",
        ),
    )


# ============================================================================
# v0.7.0: Email Trigger Instances
# ============================================================================

class EmailChannelInstance(Base):
    """
    v0.7.0: Persisted email trigger configuration.

    Phase 1 stores the control-plane row only: which Gmail integration to
    watch, which agent should receive wakeups by default, and the basic
    query/poll metadata the later EmailTrigger adapter will consume.
    """
    __tablename__ = "email_channel_instance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    integration_name = Column(String(100), nullable=False)
    provider = Column(String(32), default="gmail", nullable=False)
    gmail_integration_id = Column(Integer, ForeignKey("gmail_integration.id", ondelete="CASCADE"), nullable=True, index=True)
    search_query = Column(String(500), nullable=True)
    trigger_criteria = Column(JSON, nullable=True)
    poll_interval_seconds = Column(Integer, default=60, nullable=False)
    default_agent_id = Column(Integer, ForeignKey("agent.id", ondelete="SET NULL"), nullable=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    status = Column(String(20), default="active", nullable=False)  # active | paused | error
    health_status = Column(String(20), default="unknown", nullable=False)  # unknown | healthy | unhealthy
    health_status_reason = Column(String(500), nullable=True)
    last_health_check = Column(DateTime, nullable=True)
    last_activity_at = Column(DateTime, nullable=True)
    last_cursor = Column(String(255), nullable=True)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_email_channel_instance_tenant", "tenant_id"),
        Index("idx_email_channel_instance_status", "status"),
    )


# ============================================================================
# v0.7.0: Jira, Schedule, and GitHub Trigger Instances
# ============================================================================

class JiraChannelInstance(Base):
    """Persisted Jira trigger configuration for JQL-polled wake events."""

    __tablename__ = "jira_channel_instance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    integration_name = Column(String(100), nullable=False)
    site_url = Column(String(500), nullable=False)
    project_key = Column(String(64), nullable=True)
    jql = Column(Text, nullable=False)
    jira_integration_id = Column(Integer, ForeignKey("jira_integration.id", ondelete="SET NULL"), nullable=True, index=True)
    auth_email = Column(String(255), nullable=True)
    api_token_encrypted = Column(Text, nullable=True)
    api_token_preview = Column(String(32), nullable=True)
    trigger_criteria = Column(JSON, nullable=True)
    poll_interval_seconds = Column(Integer, default=300, nullable=False)
    default_agent_id = Column(Integer, ForeignKey("agent.id", ondelete="SET NULL"), nullable=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    status = Column(String(20), default="active", nullable=False)
    health_status = Column(String(20), default="unknown", nullable=False)
    health_status_reason = Column(String(500), nullable=True)
    last_health_check = Column(DateTime, nullable=True)
    last_activity_at = Column(DateTime, nullable=True)
    last_cursor = Column(String(255), nullable=True)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    jira_integration = relationship("JiraIntegration")

    __table_args__ = (
        Index("idx_jira_channel_instance_tenant", "tenant_id"),
        Index("idx_jira_channel_instance_status", "status"),
        Index("idx_jira_channel_instance_default_agent_id", "default_agent_id"),
        Index("idx_jira_channel_instance_jira_integration_id", "jira_integration_id"),
    )


class GitHubChannelInstance(Base):
    """Persisted GitHub trigger configuration for signed webhook deliveries."""

    __tablename__ = "github_channel_instance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    integration_name = Column(String(100), nullable=False)
    # v0.7.0-fix Phase 3: GitHub triggers MUST link to a Hub GitHubIntegration
    # row. Per-trigger PATs were removed; the trigger reads its credentials
    # from the linked integration at call time.
    github_integration_id = Column(
        Integer,
        ForeignKey("github_integration.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    repo_owner = Column(String(100), nullable=False)
    repo_name = Column(String(100), nullable=False)
    webhook_secret_encrypted = Column(Text, nullable=True)
    webhook_secret_preview = Column(String(32), nullable=True)
    events = Column(JSON, nullable=True)
    branch_filter = Column(String(255), nullable=True)
    path_filters = Column(JSON, nullable=True)
    author_filter = Column(String(255), nullable=True)
    trigger_criteria = Column(JSON, nullable=True)
    default_agent_id = Column(Integer, ForeignKey("agent.id", ondelete="SET NULL"), nullable=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    status = Column(String(20), default="active", nullable=False)
    health_status = Column(String(20), default="unknown", nullable=False)
    health_status_reason = Column(String(500), nullable=True)
    last_health_check = Column(DateTime, nullable=True)
    last_activity_at = Column(DateTime, nullable=True)
    last_cursor = Column(String(255), nullable=True)
    last_delivery_id = Column(String(128), nullable=True)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_github_channel_instance_tenant", "tenant_id"),
        Index("idx_github_channel_instance_status", "status"),
        Index("idx_github_channel_instance_repo", "tenant_id", "repo_owner", "repo_name"),
        Index("idx_github_channel_instance_default_agent_id", "default_agent_id"),
    )


# ============================================================================
# v0.7.0 Phase 2: Continuous-Agent Control Plane
# ============================================================================

class DeliveryPolicy(Base):
    """
    Tenant-owned policy controlling wake-event batching, dedupe, and delivery
    timing for continuous agents.
    """
    __tablename__ = "delivery_policy"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    batch_window_seconds = Column(Integer, default=0, nullable=False)
    dedupe_window_seconds = Column(Integer, default=300, nullable=False)
    quiet_hours = Column(JSON, nullable=True)
    importance_threshold = Column(String(16), default="normal", nullable=False)
    cooldown_seconds = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_delivery_policy_tenant_name"),
        Index("ix_delivery_policy_tenant_active", "tenant_id", "is_active"),
    )


class BudgetPolicy(Base):
    """
    Tenant-owned budget/rate policy for continuous-agent execution.
    on_exhaustion: pause | degrade_to_hybrid | notify_only.
    """
    __tablename__ = "budget_policy"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    max_runs_per_day = Column(Integer, nullable=True)
    max_agentic_runs_per_day = Column(Integer, nullable=True)
    max_tokens_per_day = Column(BigInteger, nullable=True)
    max_tool_invocations_per_day = Column(Integer, nullable=True)
    on_exhaustion = Column(String(32), default="pause", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_budget_policy_tenant_name"),
        Index("ix_budget_policy_tenant_active", "tenant_id", "is_active"),
    )


class ContinuousAgent(Base):
    """Always-on wrapper around an Agent. CRUD exposed via routes_continuous."""
    __tablename__ = "continuous_agent"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(Integer, ForeignKey("agent.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=True)
    # v0.7.0-fix Phase 6: every continuous agent must declare its purpose so
    # operators understand what it does without reading the wrapped Agent's
    # system prompt.
    purpose = Column(Text, nullable=True)
    # action_kind codifies the four shapes a continuous agent can take:
    # tool_run | send_message | conditional_branch | react_only.
    action_kind = Column(String(32), nullable=True)
    execution_mode = Column(String(16), default="hybrid", nullable=False)  # autonomous | hybrid | notify_only
    delivery_policy_id = Column(Integer, ForeignKey("delivery_policy.id", ondelete="SET NULL"), nullable=True)
    budget_policy_id = Column(Integer, ForeignKey("budget_policy.id", ondelete="SET NULL"), nullable=True)
    approval_policy_id = Column(Integer, ForeignKey("sentinel_profile.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(16), default="active", nullable=False)  # active | paused | disabled | error
    is_system_owned = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agent = relationship("Agent", foreign_keys=[agent_id])
    delivery_policy = relationship("DeliveryPolicy")
    budget_policy = relationship("BudgetPolicy")
    subscriptions = relationship(
        "ContinuousSubscription",
        primaryjoin="ContinuousAgent.id == ContinuousSubscription.continuous_agent_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_continuous_agent_tenant_status", "tenant_id", "status"),
        Index("ix_continuous_agent_agent", "agent_id"),
    )


class ContinuousSubscription(Base):
    """
    Links a continuous agent to a trigger/channel instance that can emit wakes.
    channel_instance_id is validated by service/API code because the instance
    table varies by channel_type.
    """
    __tablename__ = "continuous_subscription"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    continuous_agent_id = Column(Integer, ForeignKey("continuous_agent.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_type = Column(String(32), nullable=False)
    channel_instance_id = Column(Integer, nullable=False)
    event_type = Column(String(64), nullable=True)
    delivery_policy_id = Column(Integer, ForeignKey("delivery_policy.id", ondelete="SET NULL"), nullable=True)
    action_config = Column(JSON, nullable=True)
    status = Column(String(16), default="active", nullable=False)  # active | paused | disabled | error
    is_system_owned = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    continuous_agent = relationship("ContinuousAgent", overlaps="subscriptions")
    delivery_policy = relationship("DeliveryPolicy")

    __table_args__ = (
        Index("ix_continuous_subscription_tenant_status", "tenant_id", "status"),
        Index("ix_continuous_subscription_instance", "tenant_id", "channel_type", "channel_instance_id"),
    )


class WakeEvent(Base):
    """
    Audit-style event emitted by a trigger and consumed by a continuous run.
    Payload content is not stored inline in v0.7.0 A2; payload_ref points to an
    opaque local file path or future blob key after upstream redaction.
    """
    __tablename__ = "wake_event"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False, index=True)
    continuous_agent_id = Column(Integer, ForeignKey("continuous_agent.id", ondelete="SET NULL"), nullable=True, index=True)
    continuous_subscription_id = Column(Integer, ForeignKey("continuous_subscription.id", ondelete="SET NULL"), nullable=True, index=True)
    channel_type = Column(String(32), nullable=False)
    channel_instance_id = Column(Integer, nullable=False)
    event_type = Column(String(64), nullable=False)
    occurred_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    dedupe_key = Column(String(512), nullable=False)
    importance = Column(String(16), default="normal", nullable=False)  # low | normal | high
    payload_ref = Column(String(512), nullable=True)
    status = Column(String(16), default="pending", nullable=False)  # pending | claimed | processed | filtered | failed
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    continuous_agent = relationship("ContinuousAgent")
    continuous_subscription = relationship("ContinuousSubscription")

    __table_args__ = (
        UniqueConstraint("tenant_id", "channel_type", "channel_instance_id", "dedupe_key", name="uq_wake_event_dedupe"),
        Index("ix_wake_event_tenant_occurred", "tenant_id", "occurred_at"),
        Index("ix_wake_event_continuous_agent", "continuous_agent_id", "occurred_at"),
        Index("ix_wake_event_subscription", "continuous_subscription_id", "occurred_at"),
    )


class ContinuousRun(Base):
    """
    Execution history for a continuous-agent wake. It is retained with
    RESTRICT tenant semantics for audit/incident review.
    """
    __tablename__ = "continuous_run"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False, index=True)
    continuous_agent_id = Column(Integer, ForeignKey("continuous_agent.id", ondelete="CASCADE"), nullable=False, index=True)
    wake_event_ids = Column(JSON, nullable=True)
    execution_mode = Column(String(16), nullable=True)
    status = Column(String(16), default="queued", nullable=False)  # queued | running | succeeded | failed | cancelled | skipped
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    watcher_run_ref = Column(String(128), nullable=True)
    memory_refs = Column(JSON, nullable=True)
    run_threat_signals = Column(JSON, nullable=True)
    outcome_state = Column(JSON, nullable=True)
    agentic_scratchpad = Column(JSON, nullable=True)
    run_type = Column(String(32), default="continuous", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    continuous_agent = relationship("ContinuousAgent")

    __table_args__ = (
        Index("ix_continuous_run_tenant_status", "tenant_id", "status", "started_at"),
        Index("ix_continuous_run_agent_started", "continuous_agent_id", "started_at"),
    )


class ChannelEventRule(Base):
    """
    Per-channel routing rule evaluated before default-agent fallback. Trigger
    details remain per-type APIs in A2; this table is the generic channel rule
    contract for later UI/adapter work.
    """
    __tablename__ = "channel_event_rule"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_type = Column(String(32), nullable=False)
    channel_instance_id = Column(Integer, nullable=False)
    event_type = Column(String(64), nullable=True)
    criteria = Column(JSON, nullable=False, default=dict)
    priority = Column(Integer, default=100, nullable=False)
    agent_id = Column(Integer, ForeignKey("agent.id", ondelete="CASCADE"), nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agent = relationship("Agent")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "channel_type",
            "channel_instance_id",
            "priority",
            name="uq_channel_event_rule_priority",
        ),
        Index("ix_channel_event_rule_instance", "tenant_id", "channel_type", "channel_instance_id", "is_active"),
        Index("ix_channel_event_rule_agent", "agent_id"),
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


class BrowserAutomationIntegration(HubIntegration):
    """
    Browser Automation Integration.

    Phase 14.5: Browser Automation Skill
    Phase 35:   Session persistence, rich actions, multi-tab, error recovery

    Stores Playwright browser automation configuration per tenant.

    Features:
        - Headless Chromium/Firefox/WebKit in Docker container
        - Configurable viewport, timeout, user agent, proxy
        - Session persistence with idle timeout (Phase 35a)
        - Multi-tenant support
    """
    __tablename__ = "browser_automation_integration"

    id = Column(Integer, ForeignKey("hub_integration.id"), primary_key=True)

    # Provider settings
    provider_type = Column(String(50), default="playwright")
    mode = Column(String(20), default="container")

    # Browser configuration
    browser_type = Column(String(20), default="chromium")  # "chromium", "firefox", "webkit"
    headless = Column(Boolean, default=True)
    timeout_seconds = Column(Integer, default=30)
    viewport_width = Column(Integer, default=1280)
    viewport_height = Column(Integer, default=720)
    max_concurrent_sessions = Column(Integer, default=3)
    user_agent = Column(Text, nullable=True)
    proxy_url = Column(Text, nullable=True)

    # Domain blocklist (JSON array)
    blocked_domains_json = Column(Text, nullable=True)

    # Domain allowlist (JSON array) — if non-empty, ONLY these domains are permitted
    allowed_domains_json = Column(Text, nullable=True)

    # Session persistence (Phase 35a)
    session_persistence = Column(Boolean, default=False)
    session_ttl_seconds = Column(Integer, default=300)  # 5-minute idle timeout

    # CDP mode
    cdp_url = Column(String(255), nullable=True, default="http://host.docker.internal:9222")

    # Polymorphic configuration
    __mapper_args__ = {
        'polymorphic_identity': 'browser_automation',
    }


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
    # passive_deletes=True: thread_id is CASCADE+NOT NULL, so let Postgres delete
    # the tag rather than letting SQLAlchemy NULL the FK first (which would fail).
    thread = relationship(
        "ConversationThread",
        backref=backref("tags", passive_deletes=True),
    )

    __table_args__ = (
        Index("idx_conversation_tag_tenant_user", "tenant_id", "user_id"),
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
    # passive_deletes=True: thread_id is CASCADE+NOT NULL — same rationale as
    # ConversationTag above.
    thread = relationship(
        "ConversationThread",
        backref=backref("insights", passive_deletes=True),
    )

    __table_args__ = (
        Index("idx_conversation_insight_tenant_user", "tenant_id", "user_id"),
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
    # passive_deletes=True: both *_thread_id columns are CASCADE+NOT NULL, so
    # let Postgres delete the link row when either thread is removed.
    source_thread = relationship(
        "ConversationThread",
        foreign_keys=[source_thread_id],
        backref=backref("outgoing_links", passive_deletes=True),
    )
    target_thread = relationship(
        "ConversationThread",
        foreign_keys=[target_thread_id],
        backref=backref("incoming_links", passive_deletes=True),
    )

    __table_args__ = (
        Index("idx_conversation_link_tenant_user", "tenant_id", "user_id"),
    )




# ============================================================================
# Message Queue System
# Async message processing with priority, retry, and dead-letter support.
# ============================================================================

class MessageQueue(Base):
    """
    Message Queue for asynchronous message processing.
    Supports playground, WhatsApp, Telegram, and API channels.
    Uses SELECT FOR UPDATE SKIP LOCKED for concurrent-safe claim.
    """
    __tablename__ = "message_queue"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    channel = Column(String(20), nullable=False, index=True)  # "playground"|"whatsapp"|"telegram"|"api"
    message_type = Column(String(32), nullable=False, default="inbound_message", index=True)
    status = Column(String(20), nullable=False, default="pending", index=True)
    # "pending" | "processing" | "completed" | "failed" | "dead_letter"

    agent_id = Column(Integer, ForeignKey("agent.id"), nullable=False, index=True)
    sender_key = Column(String(255), nullable=False)

    payload = Column(JSON, nullable=False)
    # Playground: {"user_id": int, "message": str, "thread_id": int|null, "media_type": str|null}
    # WhatsApp:  {"message": dict}
    # Telegram:  {"update": dict, "instance_id": int}
    # API:       {"user_id": int, "message": str, "thread_id": int|null, "api_client_id": str}
    # On completion, "result" key is added to payload for poll retrieval

    priority = Column(Integer, default=0)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    error_message = Column(Text, nullable=True)

    queued_at = Column(DateTime, default=datetime.utcnow, index=True)
    processing_started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_mq_tenant_agent_status", "tenant_id", "agent_id", "status"),
        Index("ix_mq_pending_priority", "status", "priority", "queued_at"),
    )


class ChannelEventDedupe(Base):
    """
    v0.7.0 Phase 0: durable dedupe/outcome ledger for trigger events.
    Instance ownership is validated in service code because trigger instance
    tables vary by channel type.
    """
    __tablename__ = "channel_event_dedupe"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        String(50),
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    channel_type = Column(String(32), nullable=False)
    instance_id = Column(Integer, nullable=False)
    dedupe_key = Column(String(512), nullable=False)
    outcome = Column(String(32), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "channel_type",
            "instance_id",
            "dedupe_key",
            name="uq_channel_event_dedupe",
        ),
        Index("ix_channel_event_dedupe_tenant_created", "tenant_id", "created_at"),
        Index("ix_channel_event_dedupe_instance", "tenant_id", "instance_id", "created_at"),
    )


# ============================================================================
# v0.6.0 Item 38: Channel Health Monitor with Circuit Breakers
# ============================================================================

class ChannelHealthEvent(Base):
    """
    v0.6.0 Item 38: Records circuit breaker state transitions for audit trail.
    Each row represents a single CLOSED→OPEN, OPEN→HALF_OPEN, or HALF_OPEN→CLOSED transition.
    """
    __tablename__ = "channel_health_event"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    channel_type = Column(String(20), nullable=False)           # whatsapp, telegram, slack, discord
    instance_id = Column(Integer, nullable=False, index=True)   # FK conceptual to respective instance table
    event_type = Column(String(50), nullable=True)              # e.g. "closed_to_open"
    old_state = Column(String(20), nullable=False)              # closed, open, half_open
    new_state = Column(String(20), nullable=False)
    reason = Column(Text, nullable=True)                        # Human-readable transition reason
    health_status = Column(String(20), nullable=True)           # healthy, unhealthy, degraded
    latency_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_health_event_tenant_channel", "tenant_id", "channel_type"),
        Index("ix_health_event_instance_created", "instance_id", "created_at"),
    )


class ChannelAlertConfig(Base):
    """
    v0.6.0 Item 38: Per-tenant alert configuration for channel health notifications.
    Supports webhook and email alert channels with configurable cooldown.
    """
    __tablename__ = "channel_alert_config"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, unique=True, index=True)
    webhook_url = Column(String(500), nullable=True)            # Slack/Discord/generic webhook URL
    email_recipients = Column(JSON, default=list)               # List of email addresses
    alert_on_open = Column(Boolean, default=True)               # Alert when CB opens
    alert_on_recovery = Column(Boolean, default=True)           # Alert when CB closes (recovered)
    cooldown_seconds = Column(Integer, default=300)             # Min time between alerts for same instance
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================================================
# Agent-to-Agent Communication (v0.6.0 Item 15)
# Enables agents within the same tenant to message each other,
# delegate tasks, and discover capabilities.
# ============================================================================

class AgentCommunicationPermission(Base):
    """
    Controls which agents are allowed to communicate with which other agents.
    Both agents must share the same tenant_id.
    """
    __tablename__ = "agent_communication_permission"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False)
    source_agent_id = Column(Integer, ForeignKey("agent.id", ondelete="CASCADE"), nullable=False)
    target_agent_id = Column(Integer, ForeignKey("agent.id", ondelete="CASCADE"), nullable=False)
    is_enabled = Column(Boolean, default=True)
    max_depth = Column(Integer, default=3)  # Max delegation depth for this pair
    rate_limit_rpm = Column(Integer, default=30)  # Rate limit for this pair
    # When true, the target agent may invoke its own skills (gmail, sandboxed_tools, etc.)
    # during an A2A call. Default false preserves the original LLM-knowledge-only behavior
    # and keeps the capability amplification surface opt-in per source→target pair.
    allow_target_skills = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    # passive_deletes=True: the FK is ondelete="CASCADE" + NOT NULL, so we let
    # Postgres delete the row when the parent agent is removed instead of letting
    # SQLAlchemy try to UPDATE ... SET <agent_id>=NULL first (which violates the
    # NOT NULL constraint and surfaces as a 409 in the agent delete endpoint).
    source_agent = relationship(
        "Agent",
        foreign_keys=[source_agent_id],
        backref=backref("outgoing_comm_permissions", passive_deletes=True),
    )
    target_agent = relationship(
        "Agent",
        foreign_keys=[target_agent_id],
        backref=backref("incoming_comm_permissions", passive_deletes=True),
    )

    __table_args__ = (
        UniqueConstraint("source_agent_id", "target_agent_id", name="uq_agent_comm_perm_pair"),
        Index("ix_agent_comm_perm_tenant", "tenant_id"),
        Index("ix_agent_comm_perm_source", "source_agent_id"),
        Index("ix_agent_comm_perm_target", "target_agent_id"),
    )


class AgentCommunicationSession(Base):
    """
    Tracks a complete inter-agent communication exchange.
    Supports nested delegation via parent_session_id chain.
    """
    __tablename__ = "agent_communication_session"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False)
    initiator_agent_id = Column(Integer, ForeignKey("agent.id", ondelete="CASCADE"), nullable=False)
    target_agent_id = Column(Integer, ForeignKey("agent.id", ondelete="CASCADE"), nullable=False)
    original_sender_key = Column(String(255), nullable=True)  # End-user who triggered this
    original_message_preview = Column(String(200), nullable=True)  # First 200 chars of user message
    session_type = Column(String(20), default="sync")  # sync / async / delegation
    status = Column(String(20), default="pending")  # pending / in_progress / completed / failed / timeout / blocked
    depth = Column(Integer, default=0)  # Current delegation depth (0 = first call)
    max_depth = Column(Integer, default=3)
    timeout_seconds = Column(Integer, default=30)
    total_messages = Column(Integer, default=0)
    error_text = Column(Text, nullable=True)
    parent_session_id = Column(Integer, ForeignKey("agent_communication_session.id", ondelete="SET NULL"), nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    initiator_agent = relationship("Agent", foreign_keys=[initiator_agent_id])
    target_agent_rel = relationship("Agent", foreign_keys=[target_agent_id])
    parent_session = relationship("AgentCommunicationSession", remote_side=[id], backref="child_sessions")
    messages = relationship("AgentCommunicationMessage", back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_agent_comm_session_tenant", "tenant_id"),
        Index("ix_agent_comm_session_tenant_status", "tenant_id", "status"),
        Index("ix_agent_comm_session_initiator", "initiator_agent_id", "started_at"),
        Index("ix_agent_comm_session_target", "target_agent_id"),
    )


class AgentCommunicationMessage(Base):
    """
    Individual messages within an inter-agent communication session.
    """
    __tablename__ = "agent_communication_message"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("agent_communication_session.id", ondelete="CASCADE"), nullable=False)
    from_agent_id = Column(Integer, ForeignKey("agent.id", ondelete="CASCADE"), nullable=False)
    to_agent_id = Column(Integer, ForeignKey("agent.id", ondelete="CASCADE"), nullable=False)
    direction = Column(String(10), nullable=False)  # request / response
    message_content = Column(Text, nullable=False)
    message_preview = Column(String(500), nullable=True)  # First 500 chars for listings
    context_transferred = Column(JSON, nullable=True)  # Metadata passed along
    model_used = Column(String(100), nullable=True)
    token_usage_json = Column(JSON, nullable=True)
    execution_time_ms = Column(Integer, nullable=True)
    sentinel_analyzed = Column(Boolean, default=False)
    sentinel_result = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    session = relationship("AgentCommunicationSession", back_populates="messages")
    from_agent = relationship("Agent", foreign_keys=[from_agent_id])
    to_agent = relationship("Agent", foreign_keys=[to_agent_id])

    __table_args__ = (
        Index("ix_agent_comm_msg_session", "session_id", "created_at"),
    )


# ============================================================================
# v0.6.0: Vector Store Instance (External Vector Database Connections)
# ============================================================================

class VectorStoreInstance(Base):
    """
    v0.6.0 Item 1: Pluggable vector store backend configuration.

    Each tenant can configure external vector databases (MongoDB Atlas, Pinecone, Qdrant)
    alongside the built-in ChromaDB default. Agents reference a specific instance via
    vector_store_instance_id FK (NULL = ChromaDB default).

    Vendors: chromadb, mongodb, pinecone, qdrant
    """
    __tablename__ = "vector_store_instance"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)

    # Provider identity
    vendor = Column(String(20), nullable=False)  # chromadb|mongodb|pinecone|qdrant
    instance_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Connection
    base_url = Column(String(500), nullable=True)  # Required for mongodb/qdrant, unused for pinecone
    credentials_encrypted = Column(Text, nullable=True)  # Fernet-encrypted JSON blob
    extra_config = Column(JSON, default=dict)  # Vendor-specific: index_name, collection_name, namespace, embedding_dims

    # Health monitoring
    health_status = Column(String(20), default="unknown")  # unknown|healthy|degraded|unavailable
    health_status_reason = Column(String(500), nullable=True)
    last_health_check = Column(DateTime, nullable=True)

    # Flags
    is_default = Column(Boolean, default=False)  # Legacy — use Config.default_vector_store_instance_id
    is_active = Column(Boolean, default=True)

    # Auto-provisioning (Docker-managed containers)
    is_auto_provisioned = Column(Boolean, default=False, nullable=False)
    container_name = Column(String(200), nullable=True)
    container_id = Column(String(80), nullable=True)
    container_port = Column(Integer, nullable=True)
    container_status = Column(String(20), default="none", nullable=False)  # none|creating|running|stopped|error
    container_image = Column(String(200), nullable=True)
    volume_name = Column(String(150), nullable=True)
    mem_limit = Column(String(20), nullable=True)
    cpu_quota = Column(Integer, nullable=True)

    # Security config (Item 4: MemGuard + rate limiting per-store)
    security_config = Column(JSON, default=dict, nullable=False)  # thresholds, rate limits, batch limits

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "instance_name", name="uq_vector_store_instance_tenant_name"),
        Index("idx_vsi_tenant_vendor", "tenant_id", "vendor"),
    )


class CaseMemory(Base):
    """
    v0.7.0 Trigger Case Memory MVP — compact post-execution case record.

    Each row is one terminal trigger-driven execution. Up to three vectors
    (problem/action/outcome) are stored in the configured vector store with
    deterministic IDs ``case_{origin_kind}_{run_id}_{kind}`` and metadata
    that joins back to this row via ``case_id``. The embedding contract
    (provider/model/dims/metric/task) used at write time is stamped here so
    a tenant that later switches their default ``VectorStoreInstance`` to a
    different model does not retroactively invalidate older cases.

    Per-tenant gate via ``Tenant.case_memory_enabled`` (DB column, settable
    from the tenant settings UI; defaults TRUE so every tenant gets the
    feature out of the box). Opting out is a tenant-level decision.
    """

    __tablename__ = "case_memory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        String(50),
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    agent_id = Column(
        Integer,
        ForeignKey("agent.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    wake_event_id = Column(
        Integer,
        ForeignKey("wake_event.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    continuous_run_id = Column(
        Integer,
        ForeignKey("continuous_run.id", ondelete="SET NULL"),
        nullable=True,
    )
    flow_run_id = Column(
        Integer,
        ForeignKey("flow_run.id", ondelete="SET NULL"),
        nullable=True,
    )
    origin_kind = Column(String(24), nullable=False)  # continuous_run | flow_run
    trigger_kind = Column(String(32), nullable=True)  # email | webhook | jira | github
    subject_digest = Column(String(128), nullable=True)
    problem_summary = Column(Text, nullable=True)
    action_summary = Column(Text, nullable=True)
    outcome_summary = Column(Text, nullable=True)
    outcome_label = Column(String(24), nullable=False, default="unknown")
    # ^ resolved | failed | skipped | escalated | unknown
    vector_store_instance_id = Column(
        Integer,
        ForeignKey("vector_store_instance.id", ondelete="SET NULL"),
        nullable=True,
    )
    embedding_provider = Column(String(32), nullable=True)
    embedding_model = Column(String(128), nullable=True)
    embedding_dims = Column(Integer, nullable=True)
    embedding_metric = Column(String(24), nullable=True)
    embedding_task = Column(String(64), nullable=True)
    vector_refs_json = Column(JSON, nullable=True)
    index_status = Column(String(16), nullable=False, default="pending")
    # ^ pending | indexed | partial | failed | skipped
    summary_status = Column(String(16), nullable=False, default="generated")
    # ^ generated | fallback | unavailable
    occurred_at = Column(DateTime, nullable=True)
    indexed_at = Column(DateTime, nullable=True)
    last_recalled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_case_memory_tenant_agent_occurred", "tenant_id", "agent_id", "occurred_at"),
    )


class TriggerRecapConfig(Base):
    """
    v0.7.x Trigger Memory Recap — per-trigger configuration row.

    One row per ``(tenant_id, trigger_kind, trigger_instance_id)``. When
    ``enabled=True`` and the parent tenant has ``case_memory_recap_enabled``
    set TRUE, the trigger dispatcher expands ``query_template`` (Jinja2
    sandboxed) against the redacted wake event payload, calls
    ``case_memory_service.search_similar_cases`` with the configured
    scope/k/min_similarity/vector_kind, renders ``format_template``, and
    attaches the rendered text to the queue payload under
    ``memory_recap``. The queue worker injects the recap into the
    agent's first-turn user message (or as a system addendum, depending
    on ``inject_position``) so the LLM cannot ignore relevant past
    cases by cherry-picking the wrong tool result.

    ``trigger_instance_id`` is a *semantic* FK into the per-kind channel
    tables (email_channel_instance / jira_channel_instance /
    github_channel_instance / webhook_integration). Cleanup on trigger
    DELETE is the caller's responsibility.

    Master tenant gate: ``Tenant.case_memory_recap_enabled`` (DB column,
    settable from the tenant settings UI). Per-trigger ``enabled`` field
    defaults FALSE so existing triggers don't get recap retroactively;
    operators opt in by toggling on the trigger detail page or wizard.
    """

    __tablename__ = "trigger_recap_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        String(50),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 'email' | 'jira' | 'github' | 'webhook' (semantic FK).
    trigger_kind = Column(String(32), nullable=False)
    trigger_instance_id = Column(Integer, nullable=False)
    enabled = Column(Boolean, nullable=False, default=False)
    # Jinja2 template expanded against the redacted payload.
    query_template = Column(Text, nullable=False, default="")
    # 'agent' | 'trigger_kind' | 'trigger_instance'
    scope = Column(String(24), nullable=False, default="trigger_instance")
    k = Column(Integer, nullable=False, default=3)
    min_similarity = Column(Float, nullable=False, default=0.35)
    vector_kind = Column(String(16), nullable=False, default="problem")
    include_failed = Column(Boolean, nullable=False, default=True)
    format_template = Column(Text, nullable=False, default="")
    # 'prepend_user_msg' | 'system_addendum'
    inject_position = Column(String(24), nullable=False, default="prepend_user_msg")
    max_recap_chars = Column(Integer, nullable=False, default=1500)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "trigger_kind",
            "trigger_instance_id",
            name="uq_trigger_recap_config_unique",
        ),
        Index(
            "ix_trigger_recap_config_lookup",
            "tenant_id", "trigger_kind", "trigger_instance_id",
        ),
    )


class OKGMemoryAuditLog(Base):
    """
    v0.6.0 Item 3: Audit trail for OKG Term Memory operations.

    Tracks all store, recall, forget, and auto-capture operations
    for compliance, debugging, and MemGuard visibility.
    """
    __tablename__ = "okg_memory_audit_log"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    agent_id = Column(Integer, nullable=False)
    user_id = Column(String(200), nullable=False)
    action = Column(String(20), nullable=False)  # store|recall|forget|auto_capture
    doc_id = Column(String(32), nullable=True, index=True)  # sha256[:32] dedup hash
    memory_type = Column(String(20), nullable=True)  # fact|episodic|semantic|procedural|belief
    subject_entity = Column(String(200), nullable=True)
    relation = Column(String(100), nullable=True)
    confidence = Column(Float, nullable=True)
    memguard_blocked = Column(Boolean, default=False, nullable=False)
    memguard_reason = Column(String(500), nullable=True)
    source = Column(String(20), nullable=True)  # tool_call|auto_capture|import
    result_count = Column(Integer, nullable=True)  # For recall operations
    latency_ms = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_okg_audit_tenant_agent", "tenant_id", "agent_id"),
        Index("idx_okg_audit_created", "created_at"),
    )



# BUG-311/312/313: public_key and app_id fields added to existing
# DiscordIntegration and SlackIntegration models above.


# ============================================================================
# Remote Access (Cloudflare Tunnel) — v0.6.0
# ============================================================================
class RemoteAccessConfig(Base):
    """System-wide Cloudflare Tunnel config (single row, id=1).

    Stores the global admin's tunnel configuration. Per-tenant entitlement
    lives on Tenant.remote_access_enabled. The tunnel_token field is
    encrypted at rest using the remote_access_encryption_key from Config.
    """
    __tablename__ = "remote_access_config"

    id = Column(Integer, primary_key=True, default=1)
    enabled = Column(Boolean, default=False, nullable=False)
    mode = Column(String(20), default="quick", nullable=False)        # quick | named
    autostart = Column(Boolean, default=False, nullable=False)
    protocol = Column(String(10), default="auto", nullable=False)     # auto | http2 | quic

    # Named-tunnel config
    tunnel_token_encrypted = Column(Text, nullable=True)              # Fernet via TokenEncryption
    tunnel_hostname = Column(String(255), nullable=True)              # e.g. tsushin.archsec.io
    tunnel_dns_target = Column(String(255), nullable=True)            # *.cfargotunnel.com (informational)

    # Target for the tunnel — defaults to the stack-scoped Caddy proxy
    target_url = Column(String(255), nullable=False, default=get_remote_access_proxy_target_url)

    # Cross-restart persistence (service may crash; admin needs visibility)
    last_started_at = Column(DateTime, nullable=True)
    last_stopped_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)

    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================================================
# v0.6.0-patch.5: TTS Instance (Auto-Provisioned Speech Synthesis Containers)
# Pulled forward from v0.7.0 roadmap K1 so tenants can manage per-tenant Kokoro
# TTS containers the same way they manage Qdrant / MongoDB vector stores.
# ============================================================================

class TTSInstance(Base):
    """Per-tenant TTS provider instance with optional auto-provisioned Docker container.

    Mirrors VectorStoreInstance shape. Vendor=`kokoro` is the only supported
    vendor in v0.6.0-patch.5; `speaches`/Whisper lands in v0.7.0.

    When is_auto_provisioned=True, tsushin manages the container lifecycle via
    KokoroContainerManager. The TTS provider resolves base_url from the selected
    instance at synthesis time via the chain:
        AgentSkill.config.tts_instance_id → Config.default_tts_instance_id
        → error response.
    (v0.7.0 removed the legacy KOKORO_SERVICE_URL env fallback and the stack-
    level kokoro-tts compose service — per-tenant instances are now the only
    way to run Kokoro.)
    """
    __tablename__ = "tts_instance"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)

    vendor = Column(String(20), nullable=False)  # kokoro (others in v0.7.x)
    instance_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Connection — base_url populated post-provision with DNS alias URL
    base_url = Column(String(500), nullable=True)

    # Health monitoring
    health_status = Column(String(20), default="unknown", nullable=False)
    health_status_reason = Column(String(500), nullable=True)
    last_health_check = Column(DateTime, nullable=True)

    # Flags
    is_default = Column(Boolean, default=False, nullable=False)  # Legacy — use Config.default_tts_instance_id
    is_active = Column(Boolean, default=True, nullable=False)

    # Auto-provisioning (Docker-managed containers)
    is_auto_provisioned = Column(Boolean, default=False, nullable=False)
    container_name = Column(String(200), nullable=True)
    container_id = Column(String(80), nullable=True)
    container_port = Column(Integer, nullable=True)
    container_status = Column(String(20), default="none", nullable=False)  # none|creating|running|stopped|error
    container_image = Column(String(200), nullable=True)
    volume_name = Column(String(150), nullable=True)
    mem_limit = Column(String(20), nullable=True)
    cpu_quota = Column(Integer, nullable=True)

    # Per-instance synthesis defaults (override agent-level skill config)
    default_voice = Column(String(50), default="pf_dora", nullable=True)
    default_speed = Column(Float, default=1.0, nullable=True)
    default_language = Column(String(10), default="pt", nullable=True)
    default_format = Column(String(10), default="opus", nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "instance_name", name="uq_tts_instance_tenant_name"),
        Index("idx_tsi_tenant_vendor", "tenant_id", "vendor"),
    )


# ============================================================================
# v0.7.0 Track D: ASR Instance (Auto-Provisioned Whisper/Speaches Containers)
# Per-tenant speech-to-text container lifecycle — mirrors the Kokoro/SearXNG pattern.
# ============================================================================

class ASRInstance(Base):
    """Per-tenant ASR provider instance with optional auto-provisioned container.

    Track D starts with vendor='speaches', an OpenAI-compatible Whisper/faster-
    whisper server that Tsushin provisions per tenant. The row stores the
    runtime URL plus the encrypted per-instance API token used by the backend
    provider and warm-up path.
    """
    __tablename__ = "asr_instance"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)

    vendor = Column(String(20), nullable=False, default="speaches")
    instance_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Connection — base_url populated post-provision with DNS alias URL, or
    # set directly for externally hosted OpenAI-compatible Whisper endpoints.
    base_url = Column(String(500), nullable=True)

    # Per-instance auth. The token is encrypted at rest using the same
    # tenant-scoped TokenEncryption conventions as provider API keys.
    auth_username = Column(String(50), nullable=True, default="tsushin")
    api_token_encrypted = Column(Text, nullable=True)

    # Default model used for warm-up and as the provider fallback when the
    # skill config doesn't specify a concrete model id.
    default_model = Column(
        String(200),
        nullable=True,
        default="Systran/faster-distil-whisper-small.en",
    )

    # Health monitoring
    health_status = Column(String(20), default="unknown", nullable=False)
    health_status_reason = Column(String(500), nullable=True)
    last_health_check = Column(DateTime, nullable=True)

    # Flags
    is_active = Column(Boolean, default=True, nullable=False)
    is_auto_provisioned = Column(Boolean, default=False, nullable=False)

    # Auto-provisioning (Docker-managed containers)
    container_name = Column(String(200), nullable=True)
    container_id = Column(String(80), nullable=True)
    container_port = Column(Integer, nullable=True)
    container_status = Column(String(20), default="none", nullable=False)
    container_image = Column(String(200), nullable=True)
    volume_name = Column(String(150), nullable=True)
    mem_limit = Column(String(20), nullable=True)
    cpu_quota = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "instance_name", name="uq_asr_instance_tenant_name"),
        Index("idx_asri_tenant_vendor", "tenant_id", "vendor"),
    )


# ============================================================================
# v0.6.0-patch.6: SearXNG Instance (Auto-Provisioned Self-Hosted Metasearch)
# Per-tenant SearXNG container lifecycle — mirrors the Kokoro/Ollama pattern.
# Replaces the shipped-by-default compose service introduced in PR #24.
# ============================================================================

class SearxngInstance(Base):
    """Per-tenant SearXNG provider instance with optional auto-provisioned Docker container.

    Mirrors TTSInstance/VectorStoreInstance shape. Vendor='searxng' only.

    When is_auto_provisioned=True, tsushin manages the container lifecycle via
    SearxngContainerManager. The SearXNG web-search provider resolves base_url
    from the active SearxngInstance row per tenant.

    extra_config stores:
      - secret_key: generated at provision time (token_urlsafe), injected into
        the container's /etc/searxng/settings.yml via put_archive (never on disk)
      - instance_name: cosmetic SearXNG label
    """
    __tablename__ = "searxng_instance"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)

    vendor = Column(String(20), nullable=False, default="searxng")
    instance_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Connection — base_url populated post-provision with DNS alias URL, or
    # left as user-provided external URL when is_auto_provisioned=False.
    base_url = Column(String(500), nullable=True)

    # Per-instance runtime config (secret_key, tuning flags)
    extra_config = Column(JSON, default=dict)

    # Health monitoring
    health_status = Column(String(20), default="unknown", nullable=False)
    health_status_reason = Column(String(500), nullable=True)
    last_health_check = Column(DateTime, nullable=True)

    # Flags
    is_active = Column(Boolean, default=True, nullable=False)

    # Auto-provisioning (Docker-managed containers)
    is_auto_provisioned = Column(Boolean, default=False, nullable=False)
    container_name = Column(String(200), nullable=True)
    container_id = Column(String(80), nullable=True)
    container_port = Column(Integer, nullable=True)
    container_status = Column(String(20), default="none", nullable=False)  # none|creating|running|stopped|error
    container_image = Column(String(200), nullable=True)
    volume_name = Column(String(150), nullable=True)
    mem_limit = Column(String(20), nullable=True)
    cpu_quota = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "instance_name", name="uq_searxng_instance_tenant_name"),
        Index("idx_sxi_tenant_vendor", "tenant_id", "vendor"),
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
