from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
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
    agent_phone_number: Optional[str] = None
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


class MessageResponse(BaseModel):
    id: int
    source_id: str
    chat_name: Optional[str]
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
    frequency: Literal["daily", "weekly", "monthly"] = "daily"
    interval: int = Field(default=1, ge=1, description="Recurrence interval")
    days_of_week: Optional[List[int]] = Field(default=None, description="Days for weekly recurrence (1=Monday, 7=Sunday)")
    timezone: Optional[str] = Field(default="America/Sao_Paulo", description="Timezone for scheduling")
    cron_expression: Optional[str] = Field(default=None, description="Raw cron expression (overrides other fields)")


# --- Flow Step Schemas ---
class FlowStepConfig(BaseModel):
    """Type-specific step configuration"""
    # Common fields
    channel: Optional[str] = Field(default="whatsapp", description="Delivery channel: whatsapp, telegram")
    recipient: Optional[str] = None  # Phone number or @mention
    recipients: Optional[List[str]] = None  # Multiple recipients for message steps

    # Notification-specific
    message_template: Optional[str] = None

    # Message-specific
    content: Optional[str] = None

    # Tool-specific
    tool_type: Optional[str] = None  # "built_in" or "custom"
    tool_name: Optional[str] = None
    tool_id: Optional[str] = None  # Alias for tool_name
    tool_parameters: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None  # Alias for tool_parameters

    # Conversation-specific
    objective: Optional[str] = None
    initial_prompt: Optional[str] = None
    initial_prompt_template: Optional[str] = None  # Alias for initial_prompt
    context: Optional[Dict[str, Any]] = None

    # Agent settings (can override flow-level defaults)
    agent_id: Optional[int] = None
    persona_id: Optional[int] = None

    # Phase 13.1: Step Output Injection
    # Custom name for step output reference in templates
    # Example: output_alias="scan_results" allows {{scan_results.status}} in later steps
    output_alias: Optional[str] = None


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
    """Create a new flow with steps"""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None

    # Execution configuration
    execution_method: ExecutionMethod = ExecutionMethod.IMMEDIATE
    scheduled_at: Optional[datetime] = None
    recurrence_rule: Optional[RecurrenceRule] = None

    # Flow configuration
    flow_type: FlowType = FlowType.WORKFLOW
    default_agent_id: Optional[int] = None

    # Steps (optional - can be added later)
    steps: Optional[List[FlowStepCreate]] = None


class FlowUpdate(BaseModel):
    """Update an existing flow"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None

    execution_method: Optional[ExecutionMethod] = None
    scheduled_at: Optional[datetime] = None
    recurrence_rule: Optional[RecurrenceRule] = None

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
