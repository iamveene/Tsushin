from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Dict, Any, Literal, Union
from datetime import datetime
from enum import Enum

class ConfigResponse(BaseModel):
    id: int
    messages_db_path: str
    agent_number: str
    group_filters: List[str]
    number_filters: List[str]
    model_provider: str
    model_name: str
    memory_size: int
    # enable_google_search removed - use web_search skill
    search_provider: str  # Used by SearchProviderRegistry
    system_prompt: str
    response_template: str
    contact_mappings: dict
    # Phase 3 fields
    maintenance_mode: bool
    maintenance_message: str
    context_message_count: int
    context_char_limit: int
    dm_auto_mode: bool
    agent_phone_number: str
    agent_name: str
    group_keywords: List[str]
    # enabled_tools removed - use AgentSkill table
    # Phase 4.1 fields
    enable_semantic_search: bool
    semantic_search_results: int
    semantic_similarity_threshold: float
    # Phase 5.2 fields
    ollama_base_url: str
    ollama_api_key: Optional[str]
    # Phase 18: Global WhatsApp conversation delay
    whatsapp_conversation_delay_seconds: float
    platform_min_agentic_rounds: Optional[int] = None
    platform_max_agentic_rounds: Optional[int] = None

    class Config:
        from_attributes = True


class ConfigUpdate(BaseModel):
    messages_db_path: Optional[str] = None
    agent_number: Optional[str] = None
    group_filters: Optional[List[str]] = None
    number_filters: Optional[List[str]] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    memory_size: Optional[int] = None
    # enable_google_search removed - use web_search skill
    search_provider: Optional[str] = None  # Used by SearchProviderRegistry
    system_prompt: Optional[str] = None
    response_template: Optional[str] = None
    contact_mappings: Optional[dict] = None
    # Phase 3 fields
    maintenance_mode: Optional[bool] = None
    maintenance_message: Optional[str] = None
    context_message_count: Optional[int] = None
    context_char_limit: Optional[int] = None
    dm_auto_mode: Optional[bool] = None
    agent_phone_number: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{6,14}$")
    agent_name: Optional[str] = None
    group_keywords: Optional[List[str]] = None
    # enabled_tools removed - use AgentSkill table
    # Phase 4.1 fields
    enable_semantic_search: Optional[bool] = None
    semantic_search_results: Optional[int] = None
    semantic_similarity_threshold: Optional[float] = None
    # Phase 5.2 fields
    ollama_base_url: Optional[str] = None
    ollama_api_key: Optional[str] = None
    # Phase 18: Global WhatsApp conversation delay
    whatsapp_conversation_delay_seconds: Optional[float] = None
    platform_min_agentic_rounds: Optional[int] = Field(None, ge=1, le=8)
    platform_max_agentic_rounds: Optional[int] = Field(None, ge=1, le=8)

    @field_validator('ollama_base_url')
    @classmethod
    def validate_ollama_base_url(cls, v):
        if v is None:
            return None
        from utils.ssrf_validator import validate_ollama_url
        return validate_ollama_url(v)


class MessageResponse(BaseModel):
    id: int
    source_id: str
    chat_name: Optional[str]
    sender: Optional[str] = None  # BUG-127: Raw sender identifier (phone/JID)
    sender_name: Optional[str]
    body: str
    timestamp: str  # Changed from int to str (datetime string from MCP)
    is_group: bool
    matched_filter: bool
    seen_at: datetime
    channel: Optional[str] = None  # Phase 10.1.1: Channel tracking for multi-channel analytics

    class Config:
        from_attributes = True


class AgentRunResponse(BaseModel):
    id: int
    agent_id: Optional[int]
    agent_name: Optional[str]  # Agent's friendly name
    triggered_by: str
    sender_key: str
    input_preview: str
    skill_type: Optional[str]  # Skill that processed this message
    tool_used: Optional[str]
    tool_result: Optional[str]  # Raw tool response
    model_used: Optional[str]  # Some old runs may have NULL values
    output_preview: Optional[str]  # Some old runs may have NULL values
    status: str
    error_text: Optional[str]
    execution_time_ms: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class TriggerTestRequest(BaseModel):
    text: str
    sender_key: str
    agent_id: Optional[int] = None  # If not provided, use default agent


class TriggerTestResponse(BaseModel):
    answer: Optional[str]
    tool_used: Optional[str]
    tokens: Optional[dict]
    execution_time_ms: int
    error: Optional[str]


# ============================================================================
# Phase 8.0: Unified Flow Architecture Schemas
# ============================================================================

class ExecutionMethod(str, Enum):
    IMMEDIATE = "immediate"
    SCHEDULED = "scheduled"
    RECURRING = "recurring"
    KEYWORD = "keyword"  # BUG-336: Fired when a message matches trigger_keywords
    # v0.7.0 Wave 2/4: Triggers↔Flows Unification — flow is woken by a trigger
    # event (jira/email/github/webhook) via flow_trigger_binding.
    # Wave 2 already added 'triggered' to the legacy VALID_EXECUTION_METHODS set
    # used by the BUG-342 path, but the Pydantic enum used by POST /api/flows/create
    # was missed — caught by Wave 4 deep-link prefill QA when the modal silently
    # 422'd.
    TRIGGERED = "triggered"


class FlowType(str, Enum):
    NOTIFICATION = "notification"
    CONVERSATION = "conversation"
    WORKFLOW = "workflow"
    TASK = "task"


class StepType(str, Enum):
    NOTIFICATION = "notification"
    MESSAGE = "message"
    TOOL = "tool"
    CONVERSATION = "conversation"
    SKILL = "skill"  # Phase 16: Agentic skill execution in flows
    SLASH_COMMAND = "slash_command"  # Phase 8: Slash command execution
    SUMMARIZATION = "summarization"  # Phase 17: AI-powered summarization
    GATE = "gate"  # Conditional gate node (programmatic or agentic)
    # BUG-629: enum must match runtime handler registry (flow_engine.py:2590-2613)
    # FlowNode.type is stored as a string, so adding new values is additive and
    # safe — no DB migration required.
    CUSTOM_SKILL = "custom_skill"  # Phase 22: Custom skill (alias for skill)
    BROWSER_AUTOMATION = "browser_automation"  # Phase 14.5: Browser automation
    # v0.7.x Recorder UX: pure UI marker that bundles the consecutive
    # browser_automation children compiled from one recording session.
    # Handler (BrowserGroupStepHandler) is a no-op pass-through — the
    # children run as they always have. See
    # browser_recorder.event_compiler.compile_events_into_group.
    BROWSER_GROUP = "browser_group"
    PASSWORD_VAULT = "password_vault"  # v0.7.x: provider-neutral vault references
    HTTP_REQUEST = "http_request"  # UI-authored deterministic HTTP/API step
    DATA_TRANSFORM = "data_transform"  # UI-authored extraction/normalization step
    FINANCIAL_BILL_STORE = "financial_bill_store"  # Utility-bill storage/dedupe only
    FINANCIAL_RECORD_STORE = "financial_record_store"  # Generic financial record storage/dedupe
    # v0.7.x: domain-neutral rename of financial_record_store. New flows
    # should use this; the financial_* aliases keep working for existing
    # flows. Same handler with fallback-aware field resolution
    # (record_* preferred, financial_* fallback).
    RECORD_STORE = "record_store"
    # v0.7.0 Wave 2/4: Triggers↔Flows Unification — Source step is the
    # canonical entry point for triggered flows. Wave 4 deep-link prefill
    # (Create flow from this trigger) sends a Source step with config
    # {trigger_kind, trigger_instance_id} via POST /api/flows/create. Without
    # this enum value the v2 endpoint silently 422s and the modal stays open.
    SOURCE = "source"


class FlowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class ConversationThreadStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    GOAL_ACHIEVED = "goal_achieved"


# --- Recurrence Rule Schema ---
class RecurrenceRule(BaseModel):
    """Cron-like recurrence configuration"""
    frequency: Literal["hourly", "daily", "weekly", "monthly"] = "daily"
    interval: int = Field(default=1, ge=1, description="Recurrence interval")
    days_of_week: Optional[List[int]] = Field(default=None, description="Days for weekly recurrence (1=Monday, 7=Sunday)")
    timezone: Optional[str] = Field(default="America/Sao_Paulo", description="Timezone for scheduling")
    start_time: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="Local start time in HH:MM format")
    cron_expression: Optional[str] = Field(default=None, description="Raw cron expression (overrides other fields)")

    @field_validator("cron_expression")
    @classmethod
    def validate_cron_expression_field(cls, value):
        if value is None:
            return None

        expression = value.strip()
        if not expression:
            return None

        from services.cron_preview_service import validate_cron_expression

        return validate_cron_expression(expression)


# --- Flow Step Schemas ---
class FlowStepConfig(BaseModel):
    """Type-specific step configuration.

    v0.7.x Recorder UX: `extra="allow"` so recorder-emitted metadata
    (group_recording_id, group_index, recorded_driver, recorded_at,
    screenshot_b64, target_host, child_count, event_count) round-trips
    through POST /api/flows/create without being silently dropped by
    Pydantic's default `extra="ignore"`. The runtime handlers only read
    fields they recognise, so passthrough fields are harmless.
    """
    class Config:
        extra = "allow"

    # Common fields
    channel: Optional[str] = Field(default="whatsapp", description="Delivery channel: whatsapp, telegram")
    recipient: Optional[str] = None  # Phone number or @mention
    recipients: Optional[List[str]] = None  # Multiple recipients for message steps

    # Notification-specific
    message_template: Optional[str] = None
    # State-aware message templates. When present, the notification step picks
    # the template whose key matches the upstream step's notification_state
    # (e.g. {"new_boleto": "...", "pending_no_barcode": "...", "default": "..."}).
    # If no key matches, falls back to message_template.
    message_templates_by_state: Optional[Dict[str, str]] = None
    notification_templates_by_state: Optional[Dict[str, str]] = None

    # Message-specific
    content: Optional[str] = None

    # Tool-specific
    tool_type: Optional[str] = None  # "built_in" or "custom"
    tool_name: Optional[str] = None
    tool_id: Optional[str] = None  # Alias for tool_name
    tool_parameters: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None  # Alias for tool_parameters

    # Password Vault-specific
    action: Optional[str] = None  # list_items, read_item, read_totp, compose_basic_auth, test_connection
    integration_id: Optional[int] = None
    vault: Optional[str] = None
    item_ref: Optional[str] = None
    item_id: Optional[str] = None
    field_name: Optional[str] = None
    username_handle: Optional[str] = None
    password_handle: Optional[str] = None
    scheme: Optional[str] = None
    # UI preservation fields for the Password Vault reference picker. The
    # programmatic handler reads the compact fields above; these keep the
    # selected Hub integration/vault/item labels round-trippable on edit.
    password_vault_integration_id: Optional[int] = None
    password_vault_provider: Optional[str] = None
    password_vault_vault_id: Optional[str] = None
    password_vault_vault_name: Optional[str] = None
    password_vault_item_id: Optional[str] = None
    password_vault_item_title: Optional[str] = None
    password_vault_field_name: Optional[str] = None
    password_vault_reference: Optional[str] = None

    # Financial utility automation-specific. These are UI-authored so the
    # canary boleto automation is reproducible without seeds or scripts.
    financial_automation_template: Optional[str] = None
    financial_provider: Optional[str] = None
    financial_unit_id: Optional[str] = None
    financial_asset: Optional[str] = None
    financial_address: Optional[str] = None
    financial_customer_code: Optional[str] = None
    financial_delivery_location: Optional[str] = None
    financial_username_field: Optional[str] = None
    financial_password_field: Optional[str] = None
    financial_browser_timeout_ms: Optional[int] = None
    financial_notification_enabled: Optional[bool] = None
    financial_notification_recipient: Optional[str] = None
    financial_notification_agent_id: Optional[int] = None
    financial_password_vault_integration_id: Optional[int] = None
    financial_password_vault_provider: Optional[str] = None
    financial_password_vault_vault_id: Optional[str] = None
    financial_password_vault_vault_name: Optional[str] = None
    financial_password_vault_item_id: Optional[str] = None
    financial_password_vault_item_title: Optional[str] = None
    financial_password_vault_field_name: Optional[str] = None
    financial_password_vault_reference: Optional[str] = None

    # Browser automation primitive-specific. These fields keep a UI-authored
    # browser step round-trippable as explicit actions/selectors rather than a
    # natural-language-only prompt.
    url: Optional[str] = None
    mode: Optional[str] = None
    provider_type: Optional[str] = None
    timeout_seconds: Optional[int] = None
    use_tool_mode: Optional[bool] = None
    tool_action: Optional[str] = None
    tool_arguments: Optional[Dict[str, Any]] = None
    selectors: Optional[Any] = None
    browser_secret_references: Optional[Any] = None
    session_persistence: Optional[bool] = None
    session_ttl_seconds: Optional[int] = None
    browser_session_profile_name: Optional[str] = None
    browser_session_integration_id: Optional[int] = None
    optional: Optional[bool] = None
    treat_failure_as_skipped: Optional[bool] = None

    # HTTP request primitive-specific. These fields intentionally mirror the
    # UI control groups so imported financial automations can be rebuilt as
    # visible request/transform/store flows instead of opaque mega-steps.
    method: Optional[str] = None
    headers: Optional[Any] = None
    query: Optional[Any] = None
    params: Optional[Any] = None
    body: Optional[Any] = None
    form: Optional[Any] = None
    secret_references: Optional[Any] = None
    http_secret_references: Optional[Any] = None
    fail_on_http_error: Optional[bool] = None
    http_method: Optional[str] = None
    http_url: Optional[str] = None
    http_headers: Optional[Any] = None
    http_query: Optional[Any] = None
    http_body: Optional[Any] = None
    http_json: Optional[Any] = None
    http_form: Optional[Any] = None
    http_timeout_seconds: Optional[float] = None
    http_capture_raw_response: Optional[bool] = None
    http_query_params: Optional[Any] = None
    http_body_type: Optional[str] = None
    http_json_body: Optional[Any] = None
    http_form_fields: Optional[Any] = None
    http_raw_body: Optional[str] = None
    http_follow_redirects: Optional[bool] = None
    http_raw_response_handle: Optional[bool] = None

    # Data transform primitive-specific. `source_step` is shared with
    # summarization; these fields add deterministic extraction and financial
    # parser modes.
    transform_mode: Optional[str] = None
    parser_mode: Optional[str] = None
    source_steps: Optional[Dict[str, Any]] = None
    source_handle_path: Optional[str] = None
    source_path: Optional[str] = None
    raw_response_handle: Optional[str] = None
    raw_response_handles: Optional[Dict[str, str]] = None
    json_path: Optional[str] = None
    extraction_rules: Optional[Any] = None
    parser_rules: Optional[Any] = None
    record_mapping: Optional[Dict[str, Any]] = None
    issue_record_handle: Optional[bool] = None
    financial_parser_mode: Optional[str] = None
    emit_raw_bill_handle: Optional[bool] = None
    emit_financial_record_handle: Optional[bool] = None

    # Generic financial record store primitive-specific. `financial_bill_store`
    # is a utility-bill alias; broader Finan workflows can use
    # `financial_record_store` with record_kind values such as tax_obligation,
    # income_transfer, and investment_snapshot.
    record_kind: Optional[str] = None
    financial_record_kind: Optional[str] = None
    financial_automation_key: Optional[str] = None
    financial_subject_key: Optional[str] = None
    financial_record: Optional[Dict[str, Any]] = None
    financial_record_handle: Optional[str] = None
    financial_record_handle_path: Optional[str] = None
    financial_record_source_step: Optional[str] = None
    financial_record_dedupe_key: Optional[str] = None
    financial_record_key_fields: Optional[str] = None
    financial_record_payload: Optional[str] = None
    financial_source_step: Optional[str] = None
    financial_dedupe_key: Optional[str] = None
    financial_notify_on_update: Optional[bool] = None

    # Financial bill store primitive-specific. The handler only stores or
    # dedupes normalized bill data; notification remains an explicit later node.
    financial_bill_handle: Optional[str] = None
    financial_bill_source_step: Optional[str] = None
    financial_bill_source: Optional[str] = None
    financial_bill: Optional[Dict[str, Any]] = None

    # v0.7.x: domain-neutral aliases for the financial_* fields above. Used
    # by the new `record_store` step type and by the renamed UI panel.
    # `RecordStoreStepHandler` reads these first; falls back to the
    # `financial_*` names when only the legacy fields are present so old
    # flows keep working. Same idea for `data_transform`'s emit flags.
    record_provider: Optional[str] = None              # ⇆ financial_provider
    record_unit: Optional[str] = None                  # ⇆ financial_unit_id
    record_asset: Optional[str] = None                 # ⇆ financial_asset
    record_address: Optional[str] = None               # ⇆ financial_address
    record_automation_key: Optional[str] = None        # ⇆ financial_automation_key
    record_source_step: Optional[str] = None           # ⇆ financial_record_source_step / financial_source_step / source_step
    record_dedupe_key: Optional[str] = None            # ⇆ financial_dedupe_key / financial_record_dedupe_key
    emit_record_handle: Optional[bool] = None          # ⇆ emit_financial_record_handle
    emit_raw_handle: Optional[bool] = None             # ⇆ emit_raw_bill_handle
    parser_mode: Optional[str] = None                  # ⇆ financial_parser_mode

    # Conversation-specific
    objective: Optional[str] = None
    initial_prompt: Optional[str] = None
    initial_prompt_template: Optional[str] = None  # Alias for initial_prompt
    context: Optional[Dict[str, Any]] = None

    # Skill-specific
    skill_type: Optional[str] = None  # e.g. "flight_search", "scheduler"
    prompt: Optional[str] = None  # Natural language instruction for the skill

    # Summarization-specific
    source_step: Optional[str] = None  # e.g. "step_1" or step name
    summary_prompt: Optional[str] = None  # Custom summarization instructions
    output_format: Optional[str] = None  # e.g. "brief", "structured", "minimal"
    prompt_mode: Optional[str] = None  # "append" or "replace"
    model: Optional[str] = None  # AI model for summarization

    # Slash command-specific
    command: Optional[str] = None  # e.g. "/scheduler list week"
    command_id: Optional[Union[str, int]] = None  # For tool commands

    # v0.7.0 Wave 2/4: Source step config carries the trigger binding info.
    # Used both at create-time (deep-link prefill from /hub/triggers/{kind}/{id})
    # and at runtime (SourceStepHandler reads these as a fallback when
    # trigger_context['source'] is absent).
    trigger_kind: Optional[str] = Field(
        default=None,
        description="Source-step: 'jira'|'email'|'github'|'webhook'",
    )
    trigger_instance_id: Optional[int] = Field(
        default=None,
        description="Source-step: per-kind channel instance id this flow is bound to",
    )

    # Gate-specific (conditional flow control)
    gate_mode: Optional[str] = Field(default=None, description="'programmatic' (zero LLM cost) or 'agentic' (AI-driven)")
    gate_conditions: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Programmatic conditions: [{field, operator, value, type}]"
    )
    gate_logic: Optional[str] = Field(default="all", description="'all' (AND) or 'any' (OR)")
    gate_prompt: Optional[str] = Field(default=None, description="Agentic mode: natural language evaluation prompt")
    gate_source_step: Optional[str] = Field(default=None, description="Step output to evaluate (e.g. 'inbox', 'step_1')")
    gate_on_fail: Optional[str] = Field(default="skip", description="'skip' or 'notify'")
    gate_fail_notification: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Notification config on gate fail: {channel, recipient, message_template}"
    )

    # Agent settings (can override flow-level defaults)
    agent_id: Optional[int] = None
    persona_id: Optional[int] = None

    # Phase 13.1: Step Output Injection
    # Custom name for step output reference in templates
    # Example: output_alias="scan_results" allows {{scan_results.status}} in later steps
    output_alias: Optional[str] = None

    @field_validator("recipients", mode="before")
    @classmethod
    def normalize_recipients_field(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            return [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return value

    @model_validator(mode="after")
    def normalize_recipients(self):
        if isinstance(self.recipient, str):
            normalized_recipient = self.recipient.strip()
            self.recipient = normalized_recipient or None

        recipients = list(self.recipients or [])
        if self.recipient and self.recipient not in recipients:
            recipients.append(self.recipient)
        self.recipients = recipients
        return self


class FlowStepCreate(BaseModel):
    """Create a new flow step"""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    type: StepType
    position: int = Field(..., ge=1)
    config: FlowStepConfig

    # Execution settings
    timeout_seconds: int = Field(default=300, ge=1)
    retry_on_failure: bool = False
    max_retries: int = Field(default=0, ge=0)
    retry_delay_seconds: int = Field(default=1, ge=1)

    # Flow control
    condition: Optional[Dict[str, Any]] = None
    on_success: Optional[str] = None
    on_failure: Optional[str] = None

    # Conversation settings
    allow_multi_turn: bool = False
    max_turns: int = Field(default=20, ge=1)
    conversation_objective: Optional[str] = None

    # Agent override
    agent_id: Optional[int] = None
    persona_id: Optional[int] = None


class FlowStepUpdate(BaseModel):
    """Update an existing flow step"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    type: Optional[StepType] = None
    position: Optional[int] = Field(default=None, ge=1)
    config: Optional[FlowStepConfig] = None

    timeout_seconds: Optional[int] = Field(default=None, ge=1)
    retry_on_failure: Optional[bool] = None
    max_retries: Optional[int] = Field(default=None, ge=0)
    retry_delay_seconds: Optional[int] = Field(default=None, ge=1)

    condition: Optional[Dict[str, Any]] = None
    on_success: Optional[str] = None
    on_failure: Optional[str] = None

    allow_multi_turn: Optional[bool] = None
    max_turns: Optional[int] = Field(default=None, ge=1)
    conversation_objective: Optional[str] = None

    agent_id: Optional[int] = None
    persona_id: Optional[int] = None


class FlowStepResponse(BaseModel):
    """Flow step response"""
    id: int
    flow_definition_id: int
    name: Optional[str]
    step_description: Optional[str]
    type: str
    position: int
    config_json: str  # Will be parsed by frontend

    timeout_seconds: int
    retry_on_failure: bool
    max_retries: int
    retry_delay_seconds: int

    condition: Optional[Dict[str, Any]]
    on_success: Optional[str]
    on_failure: Optional[str]

    allow_multi_turn: bool
    max_turns: int
    conversation_objective: Optional[str]

    agent_id: Optional[int]
    persona_id: Optional[int]

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Flow Schemas ---
class FlowCreate(BaseModel):
    """Create a new flow with steps.

    BUG-587: `extra="forbid"` so typos or wrong field names (e.g.
    `trigger_type` instead of `execution_method`) surface as 422 rather
    than being silently dropped.
    """
    class Config:
        extra = "forbid"

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None

    # Execution configuration
    execution_method: ExecutionMethod = ExecutionMethod.IMMEDIATE
    scheduled_at: Optional[datetime] = None
    recurrence_rule: Optional[RecurrenceRule] = None

    # BUG-336: Keyword triggers (for execution_method='keyword')
    trigger_keywords: Optional[List[str]] = None

    # Flow configuration
    flow_type: FlowType = FlowType.WORKFLOW
    default_agent_id: Optional[int] = None

    # Steps (optional - can be added later)
    steps: Optional[List[FlowStepCreate]] = None


class FlowUpdate(BaseModel):
    """Update an existing flow"""
    class Config:
        extra = "forbid"

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None

    execution_method: Optional[ExecutionMethod] = None
    scheduled_at: Optional[datetime] = None
    recurrence_rule: Optional[RecurrenceRule] = None

    # BUG-336: Keyword triggers (for execution_method='keyword')
    trigger_keywords: Optional[List[str]] = None

    flow_type: Optional[FlowType] = None
    default_agent_id: Optional[int] = None
    is_active: Optional[bool] = None


class FlowResponse(BaseModel):
    """Flow response with step count"""
    id: int
    tenant_id: Optional[str]
    name: str
    description: Optional[str]

    execution_method: str
    scheduled_at: Optional[datetime]
    recurrence_rule: Optional[Dict[str, Any]]

    # BUG-336: Keyword triggers
    trigger_keywords: Optional[List[str]] = None

    flow_type: str
    default_agent_id: Optional[int]
    initiator_type: str

    is_active: bool
    version: int

    last_executed_at: Optional[datetime]
    next_execution_at: Optional[datetime]
    execution_count: int

    created_at: datetime
    updated_at: Optional[datetime]

    # Computed
    step_count: int = 0
    # BUG-630: legacy alias — `FlowDefinitionResponse` historically exposed
    # `node_count`. v2 callers should read `step_count` but the alias stays
    # populated so clients migrating from legacy don't break.
    node_count: int = 0

    # v0.7.0 release-finishing — system-managed trigger flow metadata.
    # Mirrors FlowDefinitionResponse so v2 callers see the same fields.
    is_system_owned: bool = False
    editable_by_tenant: bool = True
    deletable_by_tenant: bool = True
    system_trigger_kind: Optional[str] = None

    @model_validator(mode="after")
    def _mirror_step_node_count(self):
        # Keep step_count and node_count in sync regardless of which one
        # was supplied by the caller/constructor.
        if self.step_count and not self.node_count:
            self.node_count = self.step_count
        elif self.node_count and not self.step_count:
            self.step_count = self.node_count
        return self

    class Config:
        from_attributes = True


class FlowDetailResponse(FlowResponse):
    """Detailed flow response with steps"""
    steps: List[FlowStepResponse] = []


# --- Flow Run Schemas ---
class FlowRunCreate(BaseModel):
    """Trigger a flow execution"""
    trigger_context: Optional[Dict[str, Any]] = None
    triggered_by: Optional[str] = None


class FlowRunResponse(BaseModel):
    """Flow run response"""
    id: int
    flow_definition_id: int
    tenant_id: Optional[str]

    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    initiator: Optional[str]
    trigger_type: Optional[str]
    triggered_by: Optional[str]

    total_steps: int
    completed_steps: int
    failed_steps: int

    trigger_context_json: Optional[str]
    final_report_json: Optional[str]
    error_text: Optional[str]

    created_at: datetime

    class Config:
        from_attributes = True


class FlowStepRunResponse(BaseModel):
    """Flow step run response"""
    id: int
    flow_run_id: int
    flow_node_id: int

    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    retry_count: int

    input_json: Optional[str]
    output_json: Optional[str]
    error_text: Optional[str]

    execution_time_ms: Optional[int]
    tool_used: Optional[str]

    class Config:
        from_attributes = True


# --- Conversation Thread Schemas ---
class ConversationThreadResponse(BaseModel):
    """Conversation thread response"""
    id: int
    flow_step_run_id: int
    flow_definition_id: Optional[int] = None  # Added for UI badges
    flow_name: Optional[str] = None  # Added for display

    status: str
    current_turn: int
    max_turns: int

    recipient: str
    agent_id: int
    persona_id: Optional[int]

    objective: Optional[str]

    conversation_history: List[Dict[str, Any]]
    context_data: Dict[str, Any]

    goal_achieved: bool
    goal_summary: Optional[str]

    started_at: datetime
    last_activity_at: datetime
    completed_at: Optional[datetime]
    timeout_at: Optional[datetime]

    class Config:
        from_attributes = True


class ConversationReplyRequest(BaseModel):
    """Process a reply to an active conversation"""
    message_content: str
    sender: str  # Phone number/WhatsApp ID


class ConversationReplyResponse(BaseModel):
    """Response after processing a conversation reply"""
    should_reply: bool
    reply_content: Optional[str]
    status: str
    thread_status: str
    current_turn: int
    goal_achieved: bool
