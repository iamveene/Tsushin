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
    skill handlers resolve tenant-scoped typed integrations at runtime.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path
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
    type: str  # text, number, select, time, contact, agent, channel, textarea, toggle, tool, persona, password_vault_integration
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
            "required_params": [
                {
                    "name": p.key,
                    "type": p.type,
                    "label": p.label,
                    "description": p.help or p.label,
                }
                for p in self.params_schema
                if p.required
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
# Financial UI-first workflow templates
# ============================================================================

VAULT_INTEGRATION_PARAM = TemplateParamSpec(
    key="password_vault_integration_id",
    label="Password Vault connection",
    type="password_vault_integration",
    required=False,
    help="Choose a tenant Password Vault connection. You can still edit each vault reference in the Flow step picker after creation.",
)
VAULT_NAME_PARAM = TemplateParamSpec(
    key="vault",
    label="Vault",
    type="text",
    required=False,
    default="FinanApp",
)
VAULT_ITEM_PARAM = TemplateParamSpec(
    key="vault_item_ref",
    label="Vault item",
    type="text",
    required=False,
    help="1Password item title or id. You can edit this with the vault picker in the Flow step.",
)


def _load_financial_profiles() -> Dict[str, Dict[str, Any]]:
    """Load operator-private Finan flow profiles.

    The catalog of personal flow profiles (asset names, schedules, playbook bindings)
    lives outside the public repo at `.private/finan_profiles.json`. A fresh clone
    without that file boots with zero Finan templates registered.
    """
    env_path = os.environ.get("TSN_FINAN_PROFILES_PATH")
    candidates = [Path(env_path)] if env_path else [
        Path(__file__).resolve().parents[2] / ".private" / "finan_profiles.json",
        Path("/app/.private/finan_profiles.json"),
    ]
    for path in candidates:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "Failed to parse %s: %s; Finan templates will be skipped.", path, exc,
                )
                return {}
    logging.getLogger(__name__).info(
        "Finan profile catalog not found; Finan flow templates will be skipped. "
        "Set TSN_FINAN_PROFILES_PATH or place .private/finan_profiles.json on disk.",
    )
    return {}


FINANCIAL_PROFILES: Dict[str, Dict[str, Any]] = _load_financial_profiles()


def _financial_params(profile: Dict[str, Any]) -> List[TemplateParamSpec]:
    playbook = _load_finan_playbook(profile) or {}
    unit_options = [
        {
            "value": str(unit.get("id") or ""),
            "label": f"{unit.get('asset') or unit.get('id')} · {unit.get('installation') or unit.get('id')}",
        }
        for unit in playbook.get("units") or []
        if isinstance(unit, dict) and unit.get("active", True) and unit.get("id")
    ]
    first_unit = str(unit_options[0]["value"]) if unit_options else None

    unit_params: List[TemplateParamSpec]
    if unit_options:
        unit_params = [
            TemplateParamSpec(
                key="unit_preset",
                label="Provider unit",
                type="select",
                required=False,
                default=first_unit,
                options=unit_options,
                help="Pick the portal unit to build this Flow for. Create one Flow per active unit.",
            ),
            TemplateParamSpec(
                key="unit_id",
                label="Unit / subject key override",
                type="text",
                required=False,
                default="",
                help="Optional. Leave blank to use the selected provider unit.",
            ),
            TemplateParamSpec(
                key="asset",
                label="Asset label override",
                type="text",
                required=False,
                default="",
                help="Optional. Leave blank to use the selected provider unit label.",
            ),
        ]
    else:
        unit_params = [
            TemplateParamSpec(
                key="unit_id",
                label="Unit / subject key",
                type="text",
                required=False,
                default=profile["unit_id"],
            ),
            TemplateParamSpec(
                key="asset",
                label="Asset label",
                type="text",
                required=False,
                default=profile["asset"],
            ),
        ]

    return [
        NAME_PARAM, AGENT_PARAM, CHANNEL_PARAM, RECIPIENT_PARAM,
        VAULT_INTEGRATION_PARAM, VAULT_NAME_PARAM,
        TemplateParamSpec(
            key="vault_item_ref",
            label="Vault item",
            type="text",
            required=False,
            default=profile["credential_item"],
            help="1Password item title or id. You can replace it with the picker in the Flow step.",
        ),
        TemplateParamSpec(
            key="browser_session_profile_name",
            label="Browser session profile",
            type="text",
            required=False,
            default=profile.get("browser_session_profile_name", ""),
            help="Optional named browser profile from Hub > Tool APIs. Use it for portals that require an authenticated browser session.",
        ),
        *unit_params,
        TIMEZONE_PARAM,
    ]


def _browser_action_step(
    position: int,
    name: str,
    action: str,
    description: str,
    *,
    url: Optional[str] = None,
    selector: Optional[str] = None,
    fallback_selector: Optional[str] = None,
    value: Optional[str] = None,
    tool_arguments: Optional[Dict[str, Any]] = None,
    on_failure: Optional[str] = None,
    timeout_seconds: int = 60,
    optional: bool = False,
    browser_session_profile_name: Optional[str] = None,
) -> FlowStepCreate:
    config_kwargs: Dict[str, Any] = {
        "mode": "container",
        "provider_type": "playwright",
        "use_tool_mode": True,
        "tool_action": action,
        "tool_arguments": tool_arguments or {},
        "session_persistence": True,
        "session_ttl_seconds": 300,
        "output_alias": name,
    }
    if browser_session_profile_name:
        config_kwargs["browser_session_profile_name"] = browser_session_profile_name
    if optional:
        config_kwargs["optional"] = True
        config_kwargs["treat_failure_as_skipped"] = True
    if url:
        config_kwargs["url"] = url
    if selector:
        selector_config = {
            "name": name,
            "action": action,
            "selector": selector,
            "value": value or "",
        }
        if fallback_selector:
            selector_config["fallback_selector"] = fallback_selector
        config_kwargs["selectors"] = [selector_config]
    return _step(
        position,
        StepType.BROWSER_AUTOMATION,
        name,
        FlowStepConfig(**config_kwargs),
        on_failure=on_failure,
        timeout_seconds=timeout_seconds,
        description=description,
    )


def _resolve_finan_playbook_dir() -> Path:
    """Resolve the finan playbook directory.

    Priority: TSN_FINAN_PLAYBOOK_DIR env var, then host repo `.private/finan_playbooks`,
    then container `/app/.private/finan_playbooks`. The first existing path wins; if none
    exist we still return the most likely default so seeding can log a helpful warning.
    """
    env = os.environ.get("TSN_FINAN_PLAYBOOK_DIR")
    if env:
        return Path(env)
    candidates = [
        Path(__file__).resolve().parents[2] / ".private" / "finan_playbooks",
        Path("/app/.private/finan_playbooks"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


FINAN_PLAYBOOK_DIR = _resolve_finan_playbook_dir()
_FINAN_DIR_MISSING_LOGGED = False


def _safe_flow_step_name(prefix: str, value: str, max_len: int = 72) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    if not slug:
        slug = "step"
    name = f"{prefix}_{slug}" if prefix else slug
    return name[:max_len].strip("_") or "step"


def _load_finan_playbook(profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    global _FINAN_DIR_MISSING_LOGGED
    filename = profile.get("playbook_file")
    if not filename:
        return None
    if not FINAN_PLAYBOOK_DIR.exists():
        if not _FINAN_DIR_MISSING_LOGGED:
            logging.getLogger(__name__).info(
                "Finan playbook directory not found at %s; Finan flow templates will be skipped. "
                "Set TSN_FINAN_PLAYBOOK_DIR or place playbooks at .private/finan_playbooks/.",
                FINAN_PLAYBOOK_DIR,
            )
            _FINAN_DIR_MISSING_LOGGED = True
        return None
    path = FINAN_PLAYBOOK_DIR / str(filename)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _selected_playbook_unit(profile: Dict[str, Any], unit_id: str, asset: str) -> Dict[str, Any]:
    playbook = _load_finan_playbook(profile) or {}
    units = [unit for unit in playbook.get("units") or [] if isinstance(unit, dict)]
    for unit in units:
        if str(unit.get("id") or "") == str(unit_id):
            return {**unit, "id": unit_id, "asset": asset or unit.get("asset") or profile.get("asset")}
    for unit in units:
        if unit.get("active", True):
            return {**unit, "id": unit.get("id") or unit_id, "asset": asset or unit.get("asset") or profile.get("asset")}
    return {"id": unit_id, "asset": asset or profile.get("asset")}


def _playbook_context_script(profile: Dict[str, Any], unit: Dict[str, Any]) -> str:
    credentials: Dict[str, str] = {
        "username": "{{vault_username.secret_handle}}",
        "email": "{{vault_username.secret_handle}}",
        "cpf": "{{vault_username.secret_handle}}",
        "inscricao": "{{vault_username.secret_handle}}",
        "password": "{{vault_password.secret_handle}}",
        "senha": "{{vault_password.secret_handle}}",
        "codigo_cliente": "{{vault_password.secret_handle}}",
        "codigo_client": "{{vault_password.secret_handle}}",
    }
    if profile.get("username_field"):
        credentials[str(profile["username_field"])] = "{{vault_username.secret_handle}}"
    if profile.get("password_field"):
        credentials[str(profile["password_field"])] = "{{vault_password.secret_handle}}"
    if profile.get("totp"):
        credentials["totp"] = "{{vault_totp.secret_handle}}"
        credentials["otp"] = "{{vault_totp.secret_handle}}"
    for extra_field in profile.get("extra_secret_fields", []):
        if isinstance(extra_field, dict) and extra_field.get("field_name"):
            alias = str(extra_field.get("alias") or _safe_flow_step_name("vault", str(extra_field["field_name"])))
            credentials[str(extra_field["field_name"])] = "{{" + f"{alias}.secret_handle" + "}}"

    context = {
        "credentials": credentials,
        "unit": unit,
        "profile": {
            "provider": profile.get("provider"),
            "automation_id": profile.get("automation_id"),
        },
    }
    context_json = json.dumps(context, ensure_ascii=False)
    return f"(() => {{ window.__codexTemplateContext = {context_json}; return 'context_ready'; }})()"


def _replace_playbook_templates(value: Any, profile: Dict[str, Any], field_aliases: Dict[str, Dict[str, str]], unit: Dict[str, Any]) -> Any:
    if isinstance(value, list):
        return [_replace_playbook_templates(item, profile, field_aliases, unit) for item in value]
    if isinstance(value, dict):
        return {key: _replace_playbook_templates(item, profile, field_aliases, unit) for key, item in value.items()}
    if not isinstance(value, str):
        return value

    username_fields = {str(profile.get("username_field") or ""), "email", "username", "cpf", "inscricao"}
    password_fields = {str(profile.get("password_field") or ""), "password", "senha", "codigo_cliente", "codigo_client", "cpf"}
    extra_secret_fields = {
        str(field.get("field_name") or ""): str(field.get("alias") or _safe_flow_step_name("vault", str(field.get("field_name") or "")))
        for field in profile.get("extra_secret_fields", [])
        if isinstance(field, dict) and field.get("field_name")
    }
    rendered = value
    for field in username_fields:
        if field:
            rendered = rendered.replace(f"{{{{credentials.{field}}}}}", "{{vault_username.secret_handle}}")
    for field in password_fields:
        if field:
            rendered = rendered.replace(f"{{{{credentials.{field}}}}}", "{{vault_password.secret_handle}}")
    for field, alias in extra_secret_fields.items():
        rendered = rendered.replace(f"{{{{credentials.{field}}}}}", "{{" + f"{alias}.secret_handle" + "}}")
    rendered = rendered.replace("{{unit.id}}", str(unit.get("id") or ""))
    rendered = rendered.replace("{{unit.installation}}", str(unit.get("installation") or unit.get("id") or ""))
    rendered = rendered.replace("{{unit.asset}}", str(unit.get("asset") or profile.get("asset") or ""))
    rendered = rendered.replace("{{unit.address}}", str(unit.get("address") or ""))
    metadata = unit.get("metadata") if isinstance(unit.get("metadata"), dict) else {}
    for key, val in metadata.items():
        rendered = rendered.replace("{{" + f"unit.metadata.{key}" + "}}", str(val))
    rendered = rendered.replace("{{plate}}", str(metadata.get("plate") or unit.get("id") or ""))
    rendered = rendered.replace("{{asset_name}}", str(unit.get("asset") or profile.get("asset") or ""))
    rendered = rendered.replace("{{renavam}}", str(metadata.get("renavam") or ""))

    def replace_extract(match: re.Match[str]) -> str:
        field = match.group(1)
        alias = field_aliases.get(field)
        if not alias:
            return match.group(0)
        return "{{" + f"{alias['alias']}.metadata_preview.{alias['path'].split('.', 1)[-1]}" + "}}"

    return re.sub(r"\{\{extract\.([a-zA-Z0-9_]+)\}\}", replace_extract, rendered)


def _record_targets_for_field(field_name: str) -> List[str]:
    targets = [field_name]
    if field_name in {"month", "reference", "referencia"}:
        targets.append("reference_month")
    if field_name == "barcode_cota_unica":
        targets.append("barcode")
    if field_name == "total_amount":
        targets.append("amount")
    if field_name in {"all_transfers", "all_positions", "all_transactions", "installments_json"}:
        targets.append("details")
    return list(dict.fromkeys(targets))


def _append_finan_playbook_browser_steps(
    steps: List[FlowStepCreate],
    position: int,
    profile: Dict[str, Any],
    agent_id: int,
    unit: Dict[str, Any],
    browser_session_profile_name: Optional[str] = None,
) -> tuple[int, List[Dict[str, Any]]]:
    playbook = _load_finan_playbook(profile)
    if not playbook:
        return _append_browser_financial_steps(steps, position, profile, agent_id), []

    extraction_rules: List[Dict[str, Any]] = [
        {"target": "record_kind", "value": profile["record_kind"]},
        {"target": "automation_key", "value": profile["automation_id"]},
        {"target": "provider", "value": profile["provider"]},
        {"target": "unit_id", "value": unit.get("id") or profile["unit_id"]},
        {"target": "asset", "value": unit.get("asset") or profile["asset"]},
        {"target": "period_key", "value": "latest"},
    ]
    field_aliases: Dict[str, Dict[str, str]] = {}

    for raw_step in playbook.get("steps") or []:
        if not isinstance(raw_step, dict):
            continue
        original_action = str(raw_step.get("action") or "").strip()
        original_id = raw_step.get("id") or position
        description = str(raw_step.get("description") or raw_step.get("name") or original_action)
        timeout_seconds = max(5, int(raw_step.get("timeout") or 30000) // 1000)
        effective_optional = bool(raw_step.get("optional") or original_action == "dismiss_modal")
        on_failure = "continue" if effective_optional else None

        if original_action == "extract" and isinstance(raw_step.get("fields"), dict):
            for field_name, field in raw_step["fields"].items():
                if not isinstance(field, dict):
                    continue
                extract_kind = field.get("extract") or "text"
                alias = _safe_flow_step_name(f"extract_{original_id}", str(field_name))
                selector = _replace_playbook_templates(field.get("selector") or raw_step.get("selector") or "body", profile, field_aliases, unit)
                if extract_kind == "javascript":
                    script = _replace_playbook_templates(field.get("script") or "", profile, field_aliases, unit)
                    if "__codexTemplateContext" in script:
                        context_step = _browser_action_step(
                            position,
                            _safe_flow_step_name(f"context_{original_id}", "set_playbook_context"),
                            "execute_script",
                            "Set the visible playbook context used by the following extraction script.",
                            tool_arguments={"script": _playbook_context_script(profile, unit)},
                            timeout_seconds=10,
                            browser_session_profile_name=browser_session_profile_name,
                        )
                        context_step.agent_id = agent_id
                        steps.append(context_step)
                        position += 1
                    browser_action = "execute_script"
                    tool_arguments = {"script": script}
                    source_path = "metadata.result"
                elif extract_kind == "attribute":
                    browser_action = "get_attribute"
                    tool_arguments = {"attribute": _replace_playbook_templates(field.get("attribute") or "", profile, field_aliases, unit)}
                    source_path = "metadata.value"
                else:
                    browser_action = "extract"
                    tool_arguments = {}
                    source_path = "metadata.text"
                browser_step = _browser_action_step(
                    position,
                    alias,
                    browser_action,
                    description,
                    selector=selector if browser_action != "execute_script" else None,
                    tool_arguments=tool_arguments,
                    on_failure=on_failure,
                    timeout_seconds=timeout_seconds,
                    optional=effective_optional,
                    browser_session_profile_name=browser_session_profile_name,
                )
                browser_step.agent_id = agent_id
                steps.append(browser_step)
                field_aliases[str(field_name)] = {"alias": alias, "path": source_path}
                if not str(field_name).startswith("_"):
                    for target in _record_targets_for_field(str(field_name)):
                        extraction_rules.append({"target": target, "source_step": alias, "path": source_path})
                position += 1
            continue

        action = original_action
        selector = _replace_playbook_templates(raw_step.get("selector"), profile, field_aliases, unit)
        fallback_selector = _replace_playbook_templates(raw_step.get("fallback_selector"), profile, field_aliases, unit)
        value = _replace_playbook_templates(raw_step.get("value"), profile, field_aliases, unit)
        url = _replace_playbook_templates(raw_step.get("url"), profile, field_aliases, unit)
        tool_arguments: Dict[str, Any] = {}
        if fallback_selector:
            tool_arguments["fallback_selector"] = fallback_selector
        if raw_step.get("fallback"):
            tool_arguments["fallback_script"] = _replace_playbook_templates(raw_step.get("fallback"), profile, field_aliases, unit)
        if original_action == "execute_script":
            tool_arguments["script"] = _replace_playbook_templates(raw_step.get("script") or "(() => null)()", profile, field_aliases, unit)
        if raw_step.get("timeout"):
            tool_arguments["timeout_ms"] = raw_step.get("timeout")
        if raw_step.get("wait_until"):
            tool_arguments["wait_until"] = raw_step.get("wait_until")
        for key in (
            "input_selector",
            "submit_selector",
            "solver_provider",
            "captcha_solver_provider",
            "ollama_model",
            "ollama_base_url",
            "max_attempts",
            "post_submit_wait_ms",
            "error_text_regex",
            "success_selector",
            "captcha_length",
            "prompt",
            "solver_timeout_seconds",
            "temperature",
        ):
            if raw_step.get(key) is not None:
                tool_arguments[key] = _replace_playbook_templates(raw_step.get(key), profile, field_aliases, unit)
        if original_action == "wait_selector":
            action = "wait_for"
            tool_arguments["state"] = "visible"
        elif original_action == "wait_navigation":
            action = "wait_for_url"
            tool_arguments["url_contains"] = raw_step.get("url_contains") or ""
        elif original_action == "fill_totp":
            action = "fill"
            value = "{{vault_totp.secret_handle}}"
        elif original_action == "solve_captcha":
            action = "solve_captcha"
        elif original_action not in {"navigate", "click", "fill", "extract", "screenshot", "execute_script", "dismiss_modal"}:
            action = "execute_script"
            tool_arguments["script"] = _replace_playbook_templates(raw_step.get("script") or "(() => null)()", profile, field_aliases, unit)

        name = _safe_flow_step_name(f"browser_{original_id}", description)
        browser_step = _browser_action_step(
            position,
            name,
            action,
            description,
            url=url,
            selector=selector,
            fallback_selector=fallback_selector,
            value=value,
            tool_arguments=tool_arguments,
            on_failure=on_failure,
            timeout_seconds=timeout_seconds,
            optional=effective_optional,
            browser_session_profile_name=browser_session_profile_name,
        )
        browser_step.agent_id = agent_id
        steps.append(browser_step)
        position += 1

    if any(rule.get("target") == "reference_month" for rule in extraction_rules):
        extraction_rules.append({"target": "period_key", "source_step": next(rule["source_step"] for rule in extraction_rules if rule.get("target") == "reference_month"), "path": next(rule["path"] for rule in extraction_rules if rule.get("target") == "reference_month")})
    elif any(rule.get("target") == "year" for rule in extraction_rules):
        extraction_rules.append({"target": "period_key", "source_step": next(rule["source_step"] for rule in extraction_rules if rule.get("target") == "year"), "path": next(rule["path"] for rule in extraction_rules if rule.get("target") == "year")})

    return position, extraction_rules


def _append_browser_financial_steps(
    steps: List[FlowStepCreate],
    position: int,
    profile: Dict[str, Any],
    agent_id: int,
) -> int:
    provider = profile["provider"].replace("_", "-")
    login_url = profile.get("login_url") or f"https://{provider}.example/login"
    records_url = profile.get("records_url") or f"https://{provider}.example/financeiro"
    username_selector = profile.get("username_selector") or "input[name='username'], input[type='email']"
    password_selector = profile.get("password_selector") or "input[type='password']"
    totp_selector = profile.get("totp_selector") or "input[name='totp'], input[name='otp']"
    submit_selector = profile.get("submit_selector") or "button[type='submit']"
    extract_selector = profile.get("extract_selector") or "body"

    browser_steps = [
        _browser_action_step(
            position,
            "open_portal_login",
            "navigate",
            "Open the provider login page. Edit the URL in the Flow UI.",
            url=login_url,
        ),
        _browser_action_step(
            position + 1,
            "fill_login_identifier",
            "fill",
            "Fill the login/user field using the Password Vault username handle.",
            selector=username_selector,
            value="{{vault_username.secret_handle}}",
        ),
        _browser_action_step(
            position + 2,
            "fill_login_secret",
            "fill",
            "Fill the password/second credential using the Password Vault password handle.",
            selector=password_selector,
            value="{{vault_password.secret_handle}}",
        ),
    ]
    position += 3

    if profile.get("totp"):
        browser_steps.append(_browser_action_step(
            position,
            "fill_totp",
            "fill",
            "Fill TOTP using the Password Vault TOTP handle.",
            selector=totp_selector,
            value="{{vault_totp.secret_handle}}",
        ))
        position += 1

    browser_steps.extend([
        _browser_action_step(
            position,
            "submit_login",
            "click",
            "Submit the login form. Edit the selector in the Flow UI.",
            selector=submit_selector,
        ),
        _browser_action_step(
            position + 1,
            "open_financial_records",
            "navigate",
            "Open the financial records / invoices page. Edit the URL in the Flow UI.",
            url=records_url,
        ),
        _browser_action_step(
            position + 2,
            "extract_financial_records",
            "extract",
            "Extract the visible financial records from the page. Edit the selector in the Flow UI.",
            selector=extract_selector,
            timeout_seconds=90,
        ),
    ])
    steps.extend(browser_steps)
    for browser_step in browser_steps:
        browser_step.agent_id = agent_id
    return position + 3


def build_financial_ui_first_workflow(params: Dict[str, Any], tenant_id: str, profile_key: str) -> FlowCreate:
    profile = FINANCIAL_PROFILES[profile_key]
    agent_id = int(params["agent_id"])
    channel = params.get("channel", "whatsapp")
    recipient = params["recipient"]
    timezone = params.get("timezone", "America/Sao_Paulo")
    integration_id = params.get("password_vault_integration_id")
    vault = params.get("vault") or "FinanApp"
    item_ref = params.get("vault_item_ref") or profile["credential_item"]
    browser_session_profile_name = str(params.get("browser_session_profile_name") or profile.get("browser_session_profile_name") or "").strip()
    unit_preset = params.get("unit_preset")
    unit_id = params.get("unit_id") or unit_preset or profile["unit_id"]
    asset = params.get("asset") or ""
    playbook_unit = _selected_playbook_unit(profile, unit_id, asset)
    unit_id = str(playbook_unit.get("id") or unit_id)
    asset = str(playbook_unit.get("asset") or asset or profile["asset"])

    steps: List[FlowStepCreate] = [
        _step(1, StepType.PASSWORD_VAULT, "vault_username", FlowStepConfig(
            action="read_item",
            integration_id=integration_id,
            vault=vault,
            item_ref=item_ref,
            field_name=profile["username_field"],
            output_alias="vault_username",
        ), timeout_seconds=30, description="Resolve login/user identifier from Password Vault."),
        _step(2, StepType.PASSWORD_VAULT, "vault_password", FlowStepConfig(
            action="read_item",
            integration_id=integration_id,
            vault=vault,
            item_ref=item_ref,
            field_name=profile["password_field"],
            output_alias="vault_password",
        ), timeout_seconds=30, description="Resolve password or second credential from Password Vault."),
    ]

    position = 3
    if profile.get("totp"):
        steps.append(_step(position, StepType.PASSWORD_VAULT, "vault_totp", FlowStepConfig(
            action="read_totp",
            integration_id=integration_id,
            vault=vault,
            item_ref=item_ref,
            output_alias="vault_totp",
        ), timeout_seconds=30, description="Resolve TOTP only for providers that require it."))
        position += 1

    for extra_field in profile.get("extra_secret_fields", []):
        if not isinstance(extra_field, dict) or not extra_field.get("field_name"):
            continue
        alias = str(extra_field.get("alias") or _safe_flow_step_name("vault", str(extra_field["field_name"])))
        action = str(extra_field.get("action") or "read_item")
        if action == "compose_basic_auth":
            config = FlowStepConfig(
                action="compose_basic_auth",
                username_handle=str(extra_field.get("username_handle") or "{{vault_username.secret_handle}}"),
                password_handle=str(extra_field.get("password_handle") or "{{vault_password.secret_handle}}"),
                scheme=str(extra_field.get("scheme") or "Basic"),
                output_alias=alias,
            )
        else:
            config = FlowStepConfig(
                action="read_item",
                integration_id=integration_id,
                vault=vault,
                item_ref=item_ref,
                field_name=str(extra_field["field_name"]),
                output_alias=alias,
            )
        steps.append(_step(position, StepType.PASSWORD_VAULT, alias, config, timeout_seconds=30, description=str(extra_field.get("description") or f"Resolve {extra_field['field_name']} from Password Vault.")))
        position += 1

    extraction_rules: List[Dict[str, Any]] = []
    if profile["steps"] == "http_dual":
        steps.extend([
            _step(position, StepType.HTTP_REQUEST, "fetch_boletos", FlowStepConfig(
                http_method="GET",
                http_url="https://provider.example/{{vault_username.value_preview}}/boletos",
                http_headers={"Authorization": "Bearer {{vault_password.secret_handle}}"},
                http_capture_raw_response=True,
                output_alias="boletos",
            ), timeout_seconds=60, description="Provider API call for boleto rows. Edit URL, params, and headers in the Flow UI."),
            _step(position + 1, StepType.HTTP_REQUEST, "fetch_notas", FlowStepConfig(
                http_method="GET",
                http_url="https://provider.example/{{vault_username.value_preview}}/notas",
                http_headers={"Authorization": "Bearer {{vault_password.secret_handle}}"},
                http_capture_raw_response=True,
                output_alias="notas",
            ), timeout_seconds=60, description="Provider API call for fiscal note/details rows. Edit URL, params, and headers in the Flow UI."),
        ])
        position += 2
        source_steps = {"boleto": "boletos", "nota": "notas"}
    elif profile.get("playbook_file"):
        position, extraction_rules = _append_finan_playbook_browser_steps(
            steps,
            position,
            profile,
            agent_id,
            playbook_unit,
            browser_session_profile_name,
        )
        source_steps = {}
    else:
        position = _append_browser_financial_steps(steps, position, profile, agent_id)
        source_steps = {"source": "extract_financial_records"}

    transform_config = FlowStepConfig(
        transform_mode="extract_fields" if extraction_rules else ("financial_parser" if profile["parser"].endswith("_utility_bill") else "record_mapping"),
        financial_parser_mode=None if extraction_rules else (profile["parser"] if profile["parser"].endswith("_utility_bill") else None),
        source_steps=source_steps,
        extraction_rules=extraction_rules or None,
        record_kind=profile["record_kind"],
        financial_provider=profile["provider"],
        financial_automation_key=profile["automation_id"],
        financial_unit_id=unit_id,
        financial_asset=asset,
        record_mapping={
            "record_kind": profile["record_kind"],
            "automation_id": profile["automation_id"],
            "provider": profile["provider"],
            "subject_key": unit_id,
            "period_key": "{{flow.id}}",
            "title": asset,
            "status": "pending_extraction_mapping",
        },
        emit_raw_bill_handle=profile["record_kind"] == "utility_bill",
        emit_financial_record_handle=True,
        output_alias="normalized_financial_record",
    )
    steps.append(_step(position, StepType.DATA_TRANSFORM, "normalize_record", transform_config, timeout_seconds=30, description="Normalize provider output into a redacted financial record shape."))
    position += 1

    store_type = StepType.FINANCIAL_BILL_STORE if profile["record_kind"] == "utility_bill" else StepType.FINANCIAL_RECORD_STORE
    steps.append(_step(position, store_type, "store_and_dedupe", FlowStepConfig(
        record_kind=profile["record_kind"],
        financial_record_kind=profile["record_kind"],
        financial_record_source_step="normalized_financial_record",
        financial_provider=profile["provider"],
        financial_automation_key=profile["automation_id"],
        financial_unit_id=unit_id,
        financial_asset=asset,
        output_alias="financial_store",
    ), timeout_seconds=30, description="Persist local state and dedupe. No hidden browser/API/notification work happens here."))
    position += 1

    notify_states = profile.get("notify_states") or [
        "new_boleto",
        "barcode_changed",
        "pending_no_barcode",
    ]
    gate_conditions = [
        {
            "field": "conditions.notification_state",
            "operator": "in",
            "value": list(notify_states),
        }
    ]

    steps.append(_step(position, StepType.GATE, "new_record_gate", FlowStepConfig(
        gate_mode="programmatic",
        gate_source_step="financial_store",
        gate_conditions=gate_conditions,
        gate_logic="all",
        gate_on_fail="skip",
    ), on_failure="skip", timeout_seconds=10, description=(
        "Pass only when storage detects a notifiable state. Default states: new_boleto, "
        "barcode_changed, pending_no_barcode. Edit the value list to opt into "
        "no_pending_bills, paid, unchanged, or error if you want."
    )))
    position += 1

    profile_name = profile["name"]
    templates_by_state = profile.get("message_templates_by_state") or {
        "new_boleto": (
            f"Novo boleto detectado em {profile_name}: "
            "{{financial_store.title}}{{financial_store.asset}} "
            "{{financial_store.reference_month}}{{financial_store.period_key}} "
            "vence {{financial_store.due_date}} no valor {{financial_store.amount_display}}. "
            "Linha digitável: {{financial_store.linha_digitavel}}"
        ),
        "barcode_changed": (
            f"Atualização de boleto em {profile_name}: "
            "{{financial_store.title}}{{financial_store.asset}} "
            "{{financial_store.reference_month}}{{financial_store.period_key}}. "
            "Nova linha digitável: {{financial_store.linha_digitavel}} "
            "(valor {{financial_store.amount_display}}, vence {{financial_store.due_date}})"
        ),
        "pending_no_barcode": (
            f"Conta em aberto em {profile_name}: "
            "{{financial_store.title}}{{financial_store.asset}} "
            "{{financial_store.reference_month}}{{financial_store.period_key}} "
            "ainda sem linha digitável disponível no portal. Acesse manualmente para regularizar."
        ),
        "no_pending_bills": (
            f"Sem boleto pendente em {profile_name}: "
            "{{financial_store.title}}{{financial_store.asset}} "
            "{{financial_store.reference_month}}{{financial_store.period_key}}"
        ),
        "default": (
            f"Atualização financeira em {profile_name}: "
            "{{financial_store.notification_state}} - {{financial_store.title}}{{financial_store.asset}} "
            "{{financial_store.reference_month}}{{financial_store.period_key}}"
        ),
    }
    fallback_template = templates_by_state.get("new_boleto") or templates_by_state.get("default") or ""

    steps.append(_step(position, StepType.NOTIFICATION, "notify_financial_event", FlowStepConfig(
        channel=channel,
        recipient=recipient,
        message_template=fallback_template,
        message_templates_by_state=templates_by_state,
    ), timeout_seconds=30, description=(
        "State-aware notification. The message_templates_by_state dict maps the "
        "upstream notification_state (new_boleto, barcode_changed, pending_no_barcode, "
        "no_pending_bills, paid, unchanged, error) to a template. message_template is "
        "the fallback when no state-keyed template matches."
    )))

    return FlowCreate(
        name=params.get("name") or profile["name"],
        description=profile["description"] + " UI-first: vault -> request/browser -> transform -> store/dedupe -> gate -> notification.",
        execution_method=ExecutionMethod.RECURRING,
        scheduled_at=_first_scheduled_at("08:00", timezone),
        recurrence_rule=RecurrenceRule(
            frequency="daily",
            interval=1,
            timezone=timezone,
            cron_expression=profile["schedule"],
        ),
        flow_type=FlowType.WORKFLOW,
        default_agent_id=agent_id,
        steps=steps,
    )


def _make_financial_builder(profile_key: str) -> FlowBuilder:
    return lambda params, tenant_id: build_financial_ui_first_workflow(params, tenant_id, profile_key)


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
    *[
        FlowTemplate(
            id=f"financial_{profile_key}",
            name=profile["name"],
            description=profile["description"],
            category="monitoring",
            icon="vault" if profile.get("steps") == "http_dual" else "browser",
            required_credentials=["password_vault"],
            highlights=[
                "UI-first visible steps, no opaque automation node",
                "Password Vault -> HTTP/browser -> transform -> store/dedupe -> gate -> notification",
                "Acceptance still requires manual run, local state update, second-run dedupe, and conditional notification",
            ],
            params_schema=_financial_params(profile),
            build=_make_financial_builder(profile_key),
        )
        for profile_key, profile in FINANCIAL_PROFILES.items()
        if profile.get("template_enabled", True)
    ],
]


def list_templates() -> List[FlowTemplate]:
    return list(FLOW_TEMPLATES)


def get_template(template_id: str) -> Optional[FlowTemplate]:
    for t in FLOW_TEMPLATES:
        if t.id == template_id:
            return t
    return None
