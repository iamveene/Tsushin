"""
Flow Template Seeding Service

Code-defined catalog of pre-built "hybrid" flows (programmatic + agentic)
exposed via GET /api/flows/templates. Each template has a pure `build(params,
tenant_id)` function that produces a `FlowCreate` ready to hand off to the
flow-creation path.

Design notes:
  * Templates reuse existing FlowNode step types only — no new primitives.
  * The "conditional gate" that skips LLM spend on empty data is implemented
    via `on_failure: "skip"` on the summarization step. When the upstream
    fetch step produces empty `raw_output`, SummarizationStepHandler returns
    `status="failed"` (without calling the LLM), and the engine honours
    `on_failure=skip` by breaking the execution loop — the downstream
    notification step never fires. See architect blueprint for details.
  * Credentials (Gmail, Calendar, etc.) are NEVER embedded in config_json —
    skill handlers resolve them at runtime via api_key_service using
    tenant_id context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any, Callable, Dict, List, Optional

from schemas import (
    ExecutionMethod,
    FlowCreate,
    FlowStepConfig,
    FlowStepCreate,
    FlowType,
    RecurrenceRule,
    StepType,
)


FlowBuilder = Callable[[Dict[str, Any], str], FlowCreate]


@dataclass
class TemplateParamSpec:
    """Declarative description of a template parameter for UI rendering."""

    key: str
    label: str
    type: str  # text, number, select, time, contact, agent, channel, textarea, toggle, tool, persona
    required: bool = True
    default: Any = None
    options: Optional[List[Dict[str, Any]]] = None  # for select
    help: Optional[str] = None
    min: Optional[int] = None
    max: Optional[int] = None


@dataclass
class FlowTemplate:
    id: str
    name: str
    description: str
    category: str  # productivity | monitoring | welcome | on_demand
    icon: str  # icon key resolved by the frontend
    params_schema: List[TemplateParamSpec]
    build: FlowBuilder
    required_credentials: List[str] = field(default_factory=list)
    highlights: List[str] = field(default_factory=list)  # bullet points for UI

    def to_summary(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "icon": self.icon,
            "highlights": self.highlights,
            "required_credentials": self.required_credentials,
            "params_schema": [
                {
                    "key": p.key,
                    "label": p.label,
                    "type": p.type,
                    "required": p.required,
                    "default": p.default,
                    "options": p.options,
                    "help": p.help,
                    "min": p.min,
                    "max": p.max,
                }
                for p in self.params_schema
            ],
        }


# ============================================================================
# Parameter-spec helpers (shared across templates)
# ============================================================================

NAME_PARAM = TemplateParamSpec(
    key="name", label="Flow name", type="text", required=True,
    help="Shown in the Flows list. You can rename it later.",
)
AGENT_PARAM = TemplateParamSpec(
    key="agent_id", label="Agent", type="agent", required=True,
    help="Which agent runs the summarization / reasoning step.",
)
CHANNEL_PARAM = TemplateParamSpec(
    key="channel", label="Delivery channel", type="channel", required=True,
    default="whatsapp",
    options=[
        {"value": "whatsapp", "label": "WhatsApp"},
        {"value": "telegram", "label": "Telegram"},
        {"value": "playground", "label": "Playground"},
    ],
)
RECIPIENT_PARAM = TemplateParamSpec(
    key="recipient", label="Recipient", type="contact", required=True,
    help="Phone number (WhatsApp/Telegram) or user handle.",
)
TIMEZONE_PARAM = TemplateParamSpec(
    key="timezone", label="Timezone", type="text", required=False,
    default="America/Sao_Paulo",
)
TIME_OF_DAY_PARAM = TemplateParamSpec(
    key="time_of_day", label="Time of day", type="time", required=True,
    default="08:00", help="24h format. Example: 08:00",
)
PERSONA_PARAM = TemplateParamSpec(
    key="persona_id", label="Persona (optional)", type="persona", required=False,
    help="Override the summarization voice with a saved persona.",
)


# ============================================================================
# Helpers
# ============================================================================

def _parse_time_of_day(value: str, default: str = "08:00") -> time:
    value = (value or default).strip()
    try:
        hh, mm = value.split(":")
        return time(int(hh), int(mm))
    except Exception:
        return time(8, 0)


def _first_scheduled_at(time_of_day: str, timezone_name: str = "America/Sao_Paulo") -> datetime:
    """Compute today's scheduled_at in UTC for the given HH:MM in the given
    timezone. Returned datetime is UTC-naive (project convention).
    Scheduler tolerates past times — it will compute next occurrence from
    recurrence rule.
    """
    import pytz
    tod = _parse_time_of_day(time_of_day)
    try:
        tz = pytz.timezone(timezone_name)
    except Exception:
        tz = pytz.timezone("America/Sao_Paulo")
    now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
    now_local = now_utc.astimezone(tz)
    scheduled_local = now_local.replace(hour=tod.hour, minute=tod.minute, second=0, microsecond=0)
    scheduled_utc = scheduled_local.astimezone(pytz.UTC).replace(tzinfo=None)
    return scheduled_utc


def _step(
    position: int,
    step_type: StepType,
    name: str,
    config: FlowStepConfig,
    on_failure: Optional[str] = None,
    agent_id: Optional[int] = None,
    persona_id: Optional[int] = None,
    timeout_seconds: int = 300,
    description: Optional[str] = None,
) -> FlowStepCreate:
    return FlowStepCreate(
        name=name,
        description=description,
        type=step_type,
        position=position,
        config=config,
        timeout_seconds=timeout_seconds,
        on_failure=on_failure,
        agent_id=agent_id,
        persona_id=persona_id,
    )


# ============================================================================
# Template 1 — Daily Email Digest
# ============================================================================

def build_daily_email_digest(params: Dict[str, Any], tenant_id: str) -> FlowCreate:
    agent_id = int(params["agent_id"])
    channel = params.get("channel", "whatsapp")
    recipient = params["recipient"]
    time_of_day = params.get("time_of_day", "08:00")
    timezone = params.get("timezone", "America/Sao_Paulo")
    max_emails = int(params.get("max_emails", 20))
    persona_id = params.get("persona_id")

    steps: List[FlowStepCreate] = [
        _step(1, StepType.SKILL, "fetch_emails", FlowStepConfig(
            skill_type="gmail",
            prompt=f"List the most recent {max_emails} emails from my inbox.",
            output_alias="inbox",
        ), on_failure="skip", agent_id=agent_id, timeout_seconds=90,
           description="Programmatic Gmail poll."),
        _step(2, StepType.SUMMARIZATION, "digest_summary", FlowStepConfig(
            source_step="inbox",
            output_format="structured",
            summary_prompt="Create a daily email digest. Group by sender. Highlight action items, deadlines, and urgent threads. Keep it scannable.",
            prompt_mode="append",
        ), on_failure="skip", agent_id=agent_id, persona_id=persona_id, timeout_seconds=180,
           description="Agentic summarization (only runs when inbox has data)."),
        _step(3, StepType.NOTIFICATION, "send_digest", FlowStepConfig(
            channel=channel, recipient=recipient,
            message_template="📬 *Daily Email Digest*\n\n{{step_2.summary}}",
        ), timeout_seconds=30,
           description="Deliver the digest to your channel of choice."),
    ]

    return FlowCreate(
        name=params.get("name") or "Daily Email Digest",
        description="Hybrid: programmatic Gmail poll gated into agentic summarization, delivered daily.",
        execution_method=ExecutionMethod.RECURRING,
        scheduled_at=_first_scheduled_at(time_of_day, timezone),
        recurrence_rule=RecurrenceRule(frequency="daily", interval=1, timezone=timezone),
        flow_type=FlowType.WORKFLOW,
        default_agent_id=agent_id,
        steps=steps,
    )


# ============================================================================
# Template 2 — Weekly Calendar Summary
# ============================================================================

def build_weekly_calendar_summary(params: Dict[str, Any], tenant_id: str) -> FlowCreate:
    agent_id = int(params["agent_id"])
    channel = params.get("channel", "whatsapp")
    recipient = params["recipient"]
    day_of_week = int(params.get("day_of_week", 1))  # 1=Monday
    time_of_day = params.get("time_of_day", "08:00")
    timezone = params.get("timezone", "America/Sao_Paulo")
    persona_id = params.get("persona_id")

    steps: List[FlowStepCreate] = [
        _step(1, StepType.SKILL, "fetch_week_events", FlowStepConfig(
            skill_type="scheduler",
            prompt="List every calendar event for the next 7 days. Include title, date, time, and attendees.",
            output_alias="week_events",
        ), on_failure="skip", agent_id=agent_id, timeout_seconds=60,
           description="Programmatic calendar read (7-day window)."),
        _step(2, StepType.SUMMARIZATION, "week_briefing", FlowStepConfig(
            source_step="week_events",
            output_format="structured",
            summary_prompt="Produce a week-ahead briefing. Day-by-day highlights, prep notes per meeting, flag schedule conflicts and long days. Be concise.",
            prompt_mode="append",
        ), on_failure="skip", agent_id=agent_id, persona_id=persona_id, timeout_seconds=180,
           description="Agentic week-ahead briefing."),
        _step(3, StepType.NOTIFICATION, "send_briefing", FlowStepConfig(
            channel=channel, recipient=recipient,
            message_template="🗓️ *Your Week Ahead*\n\n{{step_2.summary}}",
        ), timeout_seconds=30,
           description="Deliver the week-ahead briefing."),
    ]

    return FlowCreate(
        name=params.get("name") or "Weekly Calendar Summary",
        description="Hybrid: programmatic calendar read → agentic week briefing, delivered weekly.",
        execution_method=ExecutionMethod.RECURRING,
        scheduled_at=_first_scheduled_at(time_of_day, timezone),
        recurrence_rule=RecurrenceRule(
            frequency="weekly", interval=1,
            days_of_week=[day_of_week], timezone=timezone,
        ),
        flow_type=FlowType.WORKFLOW,
        default_agent_id=agent_id,
        steps=steps,
    )


# ============================================================================
# Template 3 — Summarize-on-Demand (immediate / API-triggered)
# ============================================================================

def build_summarize_on_demand(params: Dict[str, Any], tenant_id: str) -> FlowCreate:
    agent_id = int(params["agent_id"])
    channel = params.get("channel", "whatsapp")
    recipient = params.get("recipient", "{{trigger.sender}}")
    source = params.get("source", "gmail")  # gmail | scheduler
    fetch_prompt = params.get("fetch_prompt") or (
        "List my most recent 20 emails with sender, subject, and preview."
        if source == "gmail"
        else "List my calendar events for the next 7 days."
    )
    summary_prompt = params.get("summary_prompt") or (
        "Produce a concise brief of the data above. Group related items. Flag urgent items."
    )
    output_format = params.get("output_format", "brief")
    persona_id = params.get("persona_id")

    steps: List[FlowStepCreate] = [
        _step(1, StepType.SKILL, "fetch_data", FlowStepConfig(
            skill_type=source,
            prompt=fetch_prompt,
            output_alias="fetched",
        ), on_failure="skip", agent_id=agent_id, timeout_seconds=60),
        _step(2, StepType.SUMMARIZATION, "summarize", FlowStepConfig(
            source_step="fetched",
            output_format=output_format,
            summary_prompt=summary_prompt,
            prompt_mode="append",
        ), on_failure="skip", agent_id=agent_id, persona_id=persona_id, timeout_seconds=180),
        _step(3, StepType.NOTIFICATION, "reply", FlowStepConfig(
            channel=channel, recipient=recipient,
            message_template="{{step_2.summary}}",
        ), timeout_seconds=30),
    ]

    return FlowCreate(
        name=params.get("name") or "Summarize on Demand",
        description="Trigger this flow manually (or from an external call) to fetch + summarize.",
        execution_method=ExecutionMethod.IMMEDIATE,
        flow_type=FlowType.TASK,
        default_agent_id=agent_id,
        steps=steps,
    )


# ============================================================================
# Template 4 — Proactive Watcher (scheduled + conditional)
# ============================================================================

def build_proactive_watcher(params: Dict[str, Any], tenant_id: str) -> FlowCreate:
    import json as _json

    agent_id = int(params["agent_id"])
    channel = params.get("channel", "whatsapp")
    recipient = params["recipient"]
    tool_name = params.get("tool_name")  # sandboxed tool name
    raw_tool_params = params.get("tool_params") or {}
    # UI exposes tool_params as a JSON textarea — parse string safely.
    if isinstance(raw_tool_params, str):
        s = raw_tool_params.strip()
        if not s:
            tool_params = {}
        else:
            try:
                tool_params = _json.loads(s)
            except (ValueError, TypeError) as e:
                raise ValueError(f"tool_params must be valid JSON: {e}")
            if not isinstance(tool_params, dict):
                raise ValueError("tool_params JSON must decode to an object")
    elif isinstance(raw_tool_params, dict):
        tool_params = raw_tool_params
    else:
        raise ValueError("tool_params must be a JSON object or string")
    frequency = params.get("frequency", "daily")  # daily|weekly
    time_of_day = params.get("time_of_day", "08:00")
    timezone = params.get("timezone", "America/Sao_Paulo")
    persona_id = params.get("persona_id")

    if not tool_name:
        raise ValueError("tool_name is required for Proactive Watcher")

    steps: List[FlowStepCreate] = [
        _step(1, StepType.TOOL, "probe", FlowStepConfig(
            tool_type="custom",
            tool_name=tool_name,
            parameters=tool_params,
            output_alias="probe",
        ), on_failure="skip", timeout_seconds=120,
           description="Programmatic probe/check (returns empty when no anomaly)."),
        _step(2, StepType.SUMMARIZATION, "triage", FlowStepConfig(
            source_step="probe",
            output_format="brief",
            summary_prompt="Triage the anomaly below. Give a root-cause hypothesis and a recommended action in 2-3 sentences.",
            prompt_mode="append",
        ), on_failure="skip", agent_id=agent_id, persona_id=persona_id, timeout_seconds=180,
           description="Agentic triage (only runs when probe found something)."),
        _step(3, StepType.NOTIFICATION, "alert", FlowStepConfig(
            channel=channel, recipient=recipient,
            message_template="🚨 *Anomaly Detected*\n\n{{step_2.summary}}",
        ), timeout_seconds=30),
    ]

    return FlowCreate(
        name=params.get("name") or "Proactive Watcher",
        description="Hybrid: programmatic check → agentic triage only on anomaly.",
        execution_method=ExecutionMethod.RECURRING,
        scheduled_at=_first_scheduled_at(time_of_day, timezone),
        recurrence_rule=RecurrenceRule(
            frequency=frequency if frequency in ("daily", "weekly") else "daily",
            interval=1, timezone=timezone,
        ),
        flow_type=FlowType.WORKFLOW,
        default_agent_id=agent_id,
        steps=steps,
    )


# ============================================================================
# Template 5 — New-Contact Welcome (manual/API-triggered)
# ============================================================================

def build_new_contact_welcome(params: Dict[str, Any], tenant_id: str) -> FlowCreate:
    agent_id = int(params["agent_id"])
    channel = params.get("channel", "whatsapp")
    persona_id = params.get("persona_id")
    welcome_brief = params.get("welcome_brief") or (
        "Write a warm, 2-sentence welcome message for a new contact. Introduce yourself and invite them to reply."
    )

    steps: List[FlowStepCreate] = [
        _step(1, StepType.SUMMARIZATION, "compose_greeting", FlowStepConfig(
            source_step="trigger",  # trigger_context provides contact fields
            output_format="minimal",
            summary_prompt=welcome_brief,
            prompt_mode="replace",
        ), agent_id=agent_id, persona_id=persona_id, timeout_seconds=120,
           description="Agentic greeting composition using trigger context."),
        _step(2, StepType.NOTIFICATION, "send_welcome", FlowStepConfig(
            channel=channel,
            recipient="{{trigger.contact_phone}}",
            message_template="{{step_1.summary}}",
        ), timeout_seconds=30),
    ]

    return FlowCreate(
        name=params.get("name") or "New-Contact Welcome",
        description="Trigger via API with {contact_name, contact_phone} to send an agentic welcome.",
        execution_method=ExecutionMethod.IMMEDIATE,
        flow_type=FlowType.NOTIFICATION,
        default_agent_id=agent_id,
        steps=steps,
    )


# ============================================================================
# Template 6 — Zero-Cost Email Inbox Monitor (fully programmatic, no LLM)
# ============================================================================

def build_zero_cost_inbox_monitor(params: Dict[str, Any], tenant_id: str) -> FlowCreate:
    """Fully programmatic email monitoring — zero LLM tokens.

    1. Gmail skill fetches unread emails (programmatic)
    2. Gate node checks if unread count meets threshold (programmatic)
    3. Notification delivers email list via WhatsApp/Telegram (programmatic)

    Total AI cost: $0.00
    """
    agent_id = int(params["agent_id"])
    channel = params.get("channel", "whatsapp")
    recipient = params["recipient"]
    time_of_day = params.get("time_of_day", "08:00")
    timezone = params.get("timezone", "America/Sao_Paulo")
    min_emails = int(params.get("min_emails", 1))
    max_emails = int(params.get("max_emails", 20))
    keyword_filter = params.get("keyword_filter", "")
    persona_id = params.get("persona_id")

    steps: List[FlowStepCreate] = [
        _step(1, StepType.SKILL, "fetch_emails", FlowStepConfig(
            skill_type="gmail",
            prompt=f"List the {max_emails} most recent unread emails. Include sender, subject, date, and a short preview of each.",
            output_alias="inbox",
        ), on_failure="skip", agent_id=agent_id, timeout_seconds=90,
           description="Programmatic Gmail poll — fetches unread emails."),
    ]

    # Build gate conditions
    gate_conditions = [
        {"field": "count", "operator": ">=", "value": min_emails, "type": "number"},
    ]
    # Optional keyword filter
    if keyword_filter and keyword_filter.strip():
        gate_conditions.append(
            {"field": "raw_output", "operator": "matches", "value": keyword_filter.strip(), "type": "regex"}
        )

    steps.append(
        _step(2, StepType.GATE, "inbox_gate", FlowStepConfig(
            gate_mode="programmatic",
            gate_source_step="inbox",
            gate_conditions=gate_conditions,
            gate_logic="all",
            gate_on_fail="skip",
        ), on_failure="skip", timeout_seconds=10,
           description="Programmatic gate — passes only when inbox meets threshold."),
    )

    steps.append(
        _step(3, StepType.NOTIFICATION, "send_inbox", FlowStepConfig(
            channel=channel, recipient=recipient,
            message_template=(
                "📬 *Inbox Alert* — {{inbox.count}} unread email(s)\n\n"
                "{{inbox.raw_output}}"
            ),
        ), timeout_seconds=30,
           description="Deliver email list to your channel — no AI summarization."),
    )

    return FlowCreate(
        name=params.get("name") or "Zero-Cost Inbox Monitor",
        description="Fully programmatic: Gmail poll → gate (unread threshold) → WhatsApp delivery. Zero AI token cost.",
        execution_method=ExecutionMethod.RECURRING,
        scheduled_at=_first_scheduled_at(time_of_day, timezone),
        recurrence_rule=RecurrenceRule(frequency="daily", interval=1, timezone=timezone),
        flow_type=FlowType.WORKFLOW,
        default_agent_id=agent_id,
        steps=steps,
    )


# ============================================================================
# Template 7 — Agentic Email Gate (AI-driven condition)
# ============================================================================

def build_agentic_email_gate(params: Dict[str, Any], tenant_id: str) -> FlowCreate:
    """Email monitoring with AI-driven gate — agent decides if emails are relevant.

    1. Gmail skill fetches recent emails (programmatic)
    2. Gate node: agentic — agent evaluates if emails match criteria (e.g. financial)
    3. Summarization: agent generates digest of matching emails
    4. Notification: deliver digest

    Use case: "Only notify me if financial-related emails arrive"
    """
    agent_id = int(params["agent_id"])
    channel = params.get("channel", "whatsapp")
    recipient = params["recipient"]
    time_of_day = params.get("time_of_day", "08:00")
    timezone = params.get("timezone", "America/Sao_Paulo")
    max_emails = int(params.get("max_emails", 20))
    gate_criteria = params.get("gate_criteria") or "Emails contain financial, billing, invoice, or payment-related content"
    persona_id = params.get("persona_id")

    steps: List[FlowStepCreate] = [
        _step(1, StepType.SKILL, "fetch_emails", FlowStepConfig(
            skill_type="gmail",
            prompt=f"List the {max_emails} most recent emails with sender, subject, and preview.",
            output_alias="inbox",
        ), on_failure="skip", agent_id=agent_id, timeout_seconds=90,
           description="Programmatic Gmail poll."),
        _step(2, StepType.GATE, "relevance_gate", FlowStepConfig(
            gate_mode="agentic",
            gate_source_step="inbox",
            gate_prompt=gate_criteria,
            gate_on_fail="skip",
        ), on_failure="skip", agent_id=agent_id, timeout_seconds=60,
           description="Agentic gate — AI evaluates if emails match your criteria."),
        _step(3, StepType.SUMMARIZATION, "digest", FlowStepConfig(
            source_step="inbox",
            output_format="structured",
            summary_prompt="Summarize only the emails that match the gate criteria. Group by sender, highlight action items.",
            prompt_mode="append",
        ), on_failure="skip", agent_id=agent_id, persona_id=persona_id, timeout_seconds=180,
           description="Agentic summarization of relevant emails."),
        _step(4, StepType.NOTIFICATION, "send_digest", FlowStepConfig(
            channel=channel, recipient=recipient,
            message_template="🎯 *Filtered Email Digest*\n\n{{step_3.summary}}",
        ), timeout_seconds=30,
           description="Deliver filtered digest."),
    ]

    return FlowCreate(
        name=params.get("name") or "Smart Email Filter",
        description="Hybrid: Gmail poll → AI gate (relevance check) → summarization → delivery.",
        execution_method=ExecutionMethod.RECURRING,
        scheduled_at=_first_scheduled_at(time_of_day, timezone),
        recurrence_rule=RecurrenceRule(frequency="daily", interval=1, timezone=timezone),
        flow_type=FlowType.WORKFLOW,
        default_agent_id=agent_id,
        steps=steps,
    )


# ============================================================================
# Registry
# ============================================================================

FLOW_TEMPLATES: List[FlowTemplate] = [
    FlowTemplate(
        id="daily_email_digest",
        name="Daily Email Digest",
        description="Every morning, pull your latest emails and deliver an AI-summarized digest to your channel of choice.",
        category="productivity",
        icon="mail",
        required_credentials=["gmail"],
        highlights=[
            "Programmatic Gmail poll (no LLM cost)",
            "Agentic summary only when there are new emails",
            "Delivered via WhatsApp/Telegram",
        ],
        params_schema=[
            NAME_PARAM, AGENT_PARAM, CHANNEL_PARAM, RECIPIENT_PARAM,
            TIME_OF_DAY_PARAM, TIMEZONE_PARAM,
            TemplateParamSpec(
                key="max_emails", label="Max emails to scan", type="number",
                required=False, default=20, min=1, max=100,
            ),
            PERSONA_PARAM,
        ],
        build=build_daily_email_digest,
    ),
    FlowTemplate(
        id="weekly_calendar_summary",
        name="Weekly Calendar Summary",
        description="Each week, pull the next 7 days of calendar events and deliver an agentic briefing with prep notes.",
        category="productivity",
        icon="calendar",
        required_credentials=["google_calendar"],
        highlights=[
            "Programmatic 7-day calendar read",
            "Agentic day-by-day briefing",
            "Flags schedule conflicts",
        ],
        params_schema=[
            NAME_PARAM, AGENT_PARAM, CHANNEL_PARAM, RECIPIENT_PARAM,
            TemplateParamSpec(
                key="day_of_week", label="Day of week", type="select",
                required=False, default=1,
                options=[
                    {"value": 1, "label": "Monday"}, {"value": 2, "label": "Tuesday"},
                    {"value": 3, "label": "Wednesday"}, {"value": 4, "label": "Thursday"},
                    {"value": 5, "label": "Friday"}, {"value": 6, "label": "Saturday"},
                    {"value": 7, "label": "Sunday"},
                ],
            ),
            TIME_OF_DAY_PARAM, TIMEZONE_PARAM, PERSONA_PARAM,
        ],
        build=build_weekly_calendar_summary,
    ),
    FlowTemplate(
        id="summarize_on_demand",
        name="Summarize on Demand",
        description="Trigger manually to fetch emails or calendar events, summarize, and send the result to a channel.",
        category="on_demand",
        icon="wand",
        required_credentials=[],
        highlights=[
            "Triggered manually (Run button) or via API",
            "Pick Gmail or Calendar as the data source",
            "Custom summarization prompt",
        ],
        params_schema=[
            NAME_PARAM, AGENT_PARAM,
            TemplateParamSpec(
                key="source", label="Data source", type="select", required=True, default="gmail",
                options=[
                    {"value": "gmail", "label": "Gmail (recent emails)"},
                    {"value": "scheduler", "label": "Calendar (next 7 days)"},
                ],
            ),
            TemplateParamSpec(
                key="output_format", label="Summary format", type="select", required=False,
                default="brief",
                options=[
                    {"value": "brief", "label": "Brief"},
                    {"value": "detailed", "label": "Detailed"},
                    {"value": "structured", "label": "Structured"},
                    {"value": "minimal", "label": "Minimal"},
                ],
            ),
            TemplateParamSpec(
                key="summary_prompt", label="Custom summarization prompt (optional)", type="textarea",
                required=False,
            ),
            CHANNEL_PARAM, RECIPIENT_PARAM, PERSONA_PARAM,
        ],
        build=build_summarize_on_demand,
    ),
    FlowTemplate(
        id="proactive_watcher",
        name="Proactive Watcher",
        description="Scheduled probe runs a tool; when it finds something, an agent triages and alerts you.",
        category="monitoring",
        icon="eye",
        required_credentials=[],
        highlights=[
            "Runs a custom/sandboxed tool on a schedule",
            "Agent triages ONLY when anomaly detected",
            "Alert with root-cause hypothesis",
        ],
        params_schema=[
            NAME_PARAM, AGENT_PARAM,
            TemplateParamSpec(
                key="tool_name", label="Sandboxed tool", type="tool", required=True,
                help="Tool that returns empty output when there is no anomaly.",
            ),
            TemplateParamSpec(
                key="tool_params", label="Tool parameters (JSON)", type="textarea",
                required=False, default="{}", help="Passed to the tool verbatim.",
            ),
            CHANNEL_PARAM, RECIPIENT_PARAM,
            TemplateParamSpec(
                key="frequency", label="Frequency", type="select", required=False, default="daily",
                options=[
                    {"value": "daily", "label": "Daily"},
                    {"value": "weekly", "label": "Weekly"},
                ],
            ),
            TIME_OF_DAY_PARAM, TIMEZONE_PARAM, PERSONA_PARAM,
        ],
        build=build_proactive_watcher,
    ),
    FlowTemplate(
        id="new_contact_welcome",
        name="New-Contact Welcome",
        description="Trigger via API when a contact is created — agent composes a personalized greeting and sends it.",
        category="welcome",
        icon="sparkles",
        required_credentials=[],
        highlights=[
            "Triggered by external API with contact payload",
            "Agentic greeting composition",
            "Hand off to your channel",
        ],
        params_schema=[
            NAME_PARAM, AGENT_PARAM, CHANNEL_PARAM,
            TemplateParamSpec(
                key="welcome_brief", label="Greeting instructions", type="textarea",
                required=False,
                default="Write a warm, 2-sentence welcome message for a new contact. Introduce yourself and invite them to reply.",
            ),
            PERSONA_PARAM,
        ],
        build=build_new_contact_welcome,
    ),
    FlowTemplate(
        id="zero_cost_inbox_monitor",
        name="Zero-Cost Inbox Monitor",
        description="Fully programmatic email monitoring — no AI tokens used. Get notified when your inbox meets conditions.",
        category="monitoring",
        icon="gate",
        required_credentials=["gmail"],
        highlights=[
            "Zero AI cost — no LLM tokens consumed",
            "Programmatic gate: triggers when unread >= N",
            "Optional keyword/regex filter",
            "Direct email list delivery to WhatsApp/Telegram",
        ],
        params_schema=[
            NAME_PARAM, AGENT_PARAM, CHANNEL_PARAM, RECIPIENT_PARAM,
            TIME_OF_DAY_PARAM, TIMEZONE_PARAM,
            TemplateParamSpec(
                key="min_emails", label="Minimum unread emails", type="number",
                required=False, default=1, min=1, max=100,
                help="Gate passes when unread count is >= this value.",
            ),
            TemplateParamSpec(
                key="max_emails", label="Max emails to fetch", type="number",
                required=False, default=20, min=1, max=100,
            ),
            TemplateParamSpec(
                key="keyword_filter", label="Keyword filter (optional regex)", type="text",
                required=False, default="",
                help="Only pass gate if emails match this pattern. E.g. 'urgent|critical' or 'invoice'.",
            ),
        ],
        build=build_zero_cost_inbox_monitor,
    ),
    FlowTemplate(
        id="agentic_email_gate",
        name="Smart Email Filter",
        description="AI-powered email filtering — agent decides which emails are relevant before summarizing and delivering.",
        category="productivity",
        icon="brain",
        required_credentials=["gmail"],
        highlights=[
            "AI gate: agent evaluates email relevance",
            "Only summarizes matching emails",
            "Custom criteria (financial, project-specific, etc.)",
            "Delivered via WhatsApp/Telegram",
        ],
        params_schema=[
            NAME_PARAM, AGENT_PARAM, CHANNEL_PARAM, RECIPIENT_PARAM,
            TIME_OF_DAY_PARAM, TIMEZONE_PARAM,
            TemplateParamSpec(
                key="max_emails", label="Max emails to scan", type="number",
                required=False, default=20, min=1, max=100,
            ),
            TemplateParamSpec(
                key="gate_criteria", label="Gate criteria", type="textarea",
                required=True,
                default="Emails contain financial, billing, invoice, or payment-related content",
                help="Describe when the gate should PASS. The AI evaluates this against the emails.",
            ),
            PERSONA_PARAM,
        ],
        build=build_agentic_email_gate,
    ),
]


def list_templates() -> List[FlowTemplate]:
    return list(FLOW_TEMPLATES)


def get_template(template_id: str) -> Optional[FlowTemplate]:
    for t in FLOW_TEMPLATES:
        if t.id == template_id:
            return t
    return None
