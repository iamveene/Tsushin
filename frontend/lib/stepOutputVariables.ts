/**
 * Step Output Variable Definitions
 *
 * Defines available output variables for each flow step type that can be
 * referenced in subsequent steps via template syntax (e.g., {{step_1.raw_output}}).
 *
 * These definitions must match the actual step output structures from:
 * - backend/flows/flow_engine.py (step handlers)
 * - backend/flows/template_parser.py (variable resolution)
 */

export interface StepVariable {
  field: string
  label: string
  description: string
  type: 'string' | 'number' | 'boolean' | 'object' | 'array'
}

export interface HelperFunction {
  name: string
  syntax: string
  description: string
}

export interface FlowContextVar {
  variable: string
  description: string
}

// ============================================================
// Step Type → Output Fields Mapping
// ============================================================

const STEP_OUTPUT_FIELDS: Record<string, StepVariable[]> = {
  tool: [
    { field: 'raw_output', label: 'Raw Output', description: 'Raw tool execution output text', type: 'string' },
    { field: 'summary', label: 'AI Summary', description: 'AI-generated summary of tool results', type: 'string' },
    { field: 'tool_used', label: 'Tool Used', description: 'Name/ID of the tool that was executed', type: 'string' },
    { field: 'tool_type', label: 'Tool Type', description: 'Type of tool (built_in or custom)', type: 'string' },
    { field: 'status', label: 'Status', description: 'Execution status (completed or failed)', type: 'string' },
    { field: 'execution_time_ms', label: 'Execution Time', description: 'Duration in milliseconds', type: 'number' },
    { field: 'exit_code', label: 'Exit Code', description: 'Process exit code (0 = success)', type: 'number' },
    { field: 'error', label: 'Error', description: 'Error message if step failed', type: 'string' },
  ],
  notification: [
    { field: 'recipient', label: 'Recipient', description: 'Configured recipient identifier', type: 'string' },
    { field: 'resolved_recipient', label: 'Resolved Recipient', description: 'Resolved phone number', type: 'string' },
    { field: 'message_sent', label: 'Message Sent', description: 'The actual message that was delivered', type: 'string' },
    { field: 'success', label: 'Success', description: 'Whether delivery succeeded', type: 'boolean' },
    { field: 'status', label: 'Status', description: 'Delivery status', type: 'string' },
    { field: 'timestamp', label: 'Timestamp', description: 'When the notification was sent', type: 'string' },
  ],
  message: [
    { field: 'recipient', label: 'Recipient', description: 'Configured recipient identifier', type: 'string' },
    { field: 'resolved_recipient', label: 'Resolved Recipient', description: 'Resolved phone number', type: 'string' },
    { field: 'message_sent', label: 'Message Sent', description: 'The actual message that was delivered', type: 'string' },
    { field: 'sent_count', label: 'Sent Count', description: 'Number of messages sent', type: 'number' },
    { field: 'total_recipients', label: 'Total Recipients', description: 'Total recipient count', type: 'number' },
    { field: 'success', label: 'Success', description: 'Whether delivery succeeded', type: 'boolean' },
    { field: 'status', label: 'Status', description: 'Delivery status', type: 'string' },
  ],
  conversation: [
    { field: 'thread_id', label: 'Thread ID', description: 'Conversation thread identifier', type: 'number' },
    { field: 'conversation_status', label: 'Conversation Status', description: 'Outcome (active, completed, goal_achieved, timeout)', type: 'string' },
    { field: 'turns_completed', label: 'Turns Completed', description: 'Number of conversation turns', type: 'number' },
    { field: 'goal_summary', label: 'Goal Summary', description: 'AI summary of conversation outcome', type: 'string' },
    { field: 'status', label: 'Status', description: 'Step execution status', type: 'string' },
    { field: 'duration_seconds', label: 'Duration', description: 'Total conversation duration in seconds', type: 'number' },
  ],
  skill: [
    { field: 'output', label: 'Output', description: 'Structured skill execution output', type: 'string' },
    { field: 'summary', label: 'Summary', description: 'Summary of skill result', type: 'string' },
    { field: 'tool_used', label: 'Tool Used', description: 'Underlying tool used by the skill', type: 'string' },
    { field: 'status', label: 'Status', description: 'Execution status', type: 'string' },
    { field: 'error', label: 'Error', description: 'Error message if skill failed', type: 'string' },
  ],
  slash_command: [
    { field: 'command', label: 'Command', description: 'The command that was executed', type: 'string' },
    { field: 'action', label: 'Action', description: 'Parsed action from the command', type: 'string' },
    { field: 'message', label: 'Message', description: 'Human-readable result message', type: 'string' },
    { field: 'output', label: 'Output', description: 'Raw command output', type: 'string' },
    { field: 'status', label: 'Status', description: 'Execution status', type: 'string' },
    { field: 'raw_result', label: 'Raw Result', description: 'Full result object', type: 'object' },
  ],
  summarization: [
    { field: 'summary', label: 'Summary', description: 'AI-generated summary text', type: 'string' },
    { field: 'status', label: 'Status', description: 'Execution status', type: 'string' },
    { field: 'thread_id', label: 'Thread ID', description: 'Source conversation thread ID', type: 'number' },
    { field: 'conversation_status', label: 'Conversation Status', description: 'Source conversation status', type: 'string' },
    { field: 'output_format', label: 'Output Format', description: 'Format used (brief, detailed, structured, minimal)', type: 'string' },
  ],
  gate: [
    { field: 'gate_result', label: 'Gate Result', description: 'Gate outcome: "pass" or "fail"', type: 'string' },
    { field: 'gate_mode', label: 'Gate Mode', description: 'Evaluation mode used (programmatic or agentic)', type: 'string' },
    { field: 'conditions_evaluated', label: 'Conditions Evaluated', description: 'Array of evaluated conditions with pass/fail per condition', type: 'array' },
    { field: 'reasoning', label: 'Reasoning', description: 'Explanation of why the gate passed or blocked', type: 'string' },
    { field: 'status', label: 'Status', description: 'Execution status (completed or failed)', type: 'string' },
    { field: 'fail_action_taken', label: 'Fail Action Taken', description: 'Action taken on gate failure (skip or notify)', type: 'string' },
  ],
  // v0.7.0 Wave 4: Source step exposes the wake event payload + trigger metadata.
  // Reference downstream as `{{source.payload.your_field}}`, `{{source.trigger_kind}}`, etc.
  // The base list below applies to all kinds; ``getSourceStepVariables(kind)``
  // appends the per-kind deep paths a downstream step actually wants to use
  // (e.g. {{step_1.payload.issue.key}} for Jira, {{step_1.payload.subject}} for Email).
  source: [
    { field: 'payload', label: 'Payload', description: 'Raw event payload object (use deep paths below or your own)', type: 'object' },
    { field: 'trigger_kind', label: 'Trigger Kind', description: 'jira|email|github|schedule|webhook', type: 'string' },
    { field: 'instance_id', label: 'Instance ID', description: 'Which trigger fired (DB id)', type: 'number' },
    { field: 'event_type', label: 'Event Type', description: 'Underlying event type', type: 'string' },
    { field: 'dedupe_key', label: 'Dedupe Key', description: 'Source-provided idempotency key', type: 'string' },
    { field: 'occurred_at', label: 'Occurred At', description: 'ISO timestamp when event was emitted', type: 'string' },
    { field: 'wake_event_id', label: 'Wake Event ID', description: 'Backend correlation ID', type: 'number' },
  ],
}


// ============================================================
// v0.7.0 Wave 5/finishing: per-kind Source-step deep payload paths
// ============================================================
//
// When the Source step is bound to a Jira / Email / GitHub / Schedule / Webhook
// trigger, the wake-event payload has a kind-specific shape. Downstream steps
// (Notification, Conversation, Gate, etc.) typically want to reference deep
// fields like `{{source.payload.issue.key}}` (Jira ticket key) or
// `{{source.payload.subject}}` (Gmail subject). The generic `payload` chip
// alone forces operators to know the schema by heart; surfacing per-kind paths
// makes the variable reference panel actually useful for the auto-generated
// notification flow.
//
// Reference shapes:
//   Jira  — Atlassian webhook envelope: { webhookEvent, issue: { key, fields: {...} } }
//   Email — Gmail dispatch payload (services/email_notification_service): subject,
//           sender_email, sender_name, snippet, body_preview, received_at, message_id, thread_id
//   GitHub — PR-Submitted criteria envelope: pull_request:{ title, body, user.login, ... }
//   Schedule — { fired_at, cron_expression, instance_name, payload_template }
//   Webhook — arbitrary JSON. Last-5-captures inference is wired in
//             SourceStepConfig (Wave 5); the static list here only carries the
//             well-known wrapper fields.

const SOURCE_PAYLOAD_FIELDS_BY_KIND: Record<string, StepVariable[]> = {
  jira: [
    { field: 'payload.webhookEvent', label: 'Webhook Event', description: 'Atlassian event name (e.g. jira:issue_created)', type: 'string' },
    { field: 'payload.issue.key', label: 'Issue Key', description: 'e.g. "JSM-193570"', type: 'string' },
    { field: 'payload.issue.id', label: 'Issue ID', description: 'Internal Jira issue ID', type: 'string' },
    { field: 'payload.issue.fields.summary', label: 'Summary', description: 'Issue title', type: 'string' },
    { field: 'payload.issue.fields.description', label: 'Description', description: 'Issue body (ADF rendered to plain text)', type: 'string' },
    { field: 'payload.issue.fields.status.name', label: 'Status', description: 'Current workflow status (e.g. "In Progress")', type: 'string' },
    { field: 'payload.issue.fields.priority.name', label: 'Priority', description: 'Priority label (e.g. "High")', type: 'string' },
    { field: 'payload.issue.fields.issuetype.name', label: 'Issue Type', description: 'e.g. "Bug", "Story", "Pen Test"', type: 'string' },
    { field: 'payload.issue.fields.assignee.displayName', label: 'Assignee', description: 'Assigned user display name', type: 'string' },
    { field: 'payload.issue.fields.reporter.displayName', label: 'Reporter', description: 'Reporter display name', type: 'string' },
    { field: 'payload.issue.fields.project.key', label: 'Project Key', description: 'Project identifier (e.g. "JSM")', type: 'string' },
    { field: 'payload.issue.fields.project.name', label: 'Project Name', description: 'Human-readable project name', type: 'string' },
    { field: 'payload.issue.fields.labels', label: 'Labels', description: 'Issue labels array', type: 'array' },
    { field: 'payload.issue.fields.created', label: 'Created At', description: 'Issue creation ISO timestamp', type: 'string' },
    { field: 'payload.issue.fields.updated', label: 'Updated At', description: 'Last update ISO timestamp', type: 'string' },
    { field: 'payload.issue.self', label: 'Issue API URL', description: 'Direct REST link to the issue', type: 'string' },
  ],
  email: [
    { field: 'payload.subject', label: 'Subject', description: 'Gmail message subject line', type: 'string' },
    { field: 'payload.sender_email', label: 'Sender Email', description: 'From: address', type: 'string' },
    { field: 'payload.sender_name', label: 'Sender Name', description: 'From: display name', type: 'string' },
    { field: 'payload.snippet', label: 'Snippet', description: 'Gmail-generated short preview', type: 'string' },
    { field: 'payload.body_preview', label: 'Body Preview', description: 'First ~500 chars of the message body', type: 'string' },
    { field: 'payload.body', label: 'Body', description: 'Full message body (plain text)', type: 'string' },
    { field: 'payload.message_id', label: 'Gmail Message ID', description: 'Gmail-assigned message ID', type: 'string' },
    { field: 'payload.thread_id', label: 'Thread ID', description: 'Gmail thread ID', type: 'string' },
    { field: 'payload.received_at', label: 'Received At', description: 'When Gmail received the message (ISO)', type: 'string' },
    { field: 'payload.labels', label: 'Labels', description: 'Gmail label IDs applied to the message', type: 'array' },
    { field: 'payload.has_attachments', label: 'Has Attachments', description: 'True if any attachments are present', type: 'boolean' },
  ],
  github: [
    { field: 'payload.action', label: 'Action', description: 'PR action (opened, reopened, synchronize, edited, ready_for_review, review_requested)', type: 'string' },
    { field: 'payload.pull_request.number', label: 'PR Number', description: 'GitHub pull request number', type: 'number' },
    { field: 'payload.pull_request.title', label: 'PR Title', description: 'PR title', type: 'string' },
    { field: 'payload.pull_request.body', label: 'PR Body', description: 'PR description', type: 'string' },
    { field: 'payload.pull_request.html_url', label: 'PR URL', description: 'Link to the PR on github.com', type: 'string' },
    { field: 'payload.pull_request.state', label: 'PR State', description: 'open / closed', type: 'string' },
    { field: 'payload.pull_request.draft', label: 'Is Draft', description: 'True if PR is in draft state', type: 'boolean' },
    { field: 'payload.pull_request.merged', label: 'Is Merged', description: 'True if PR has been merged', type: 'boolean' },
    { field: 'payload.pull_request.user.login', label: 'Author', description: 'GitHub username of the PR author', type: 'string' },
    { field: 'payload.pull_request.head.ref', label: 'Head Branch', description: 'Source branch (e.g. "feature/x")', type: 'string' },
    { field: 'payload.pull_request.base.ref', label: 'Base Branch', description: 'Target branch (e.g. "main")', type: 'string' },
    { field: 'payload.pull_request.changed_files', label: 'Files Changed', description: 'Total file change count', type: 'number' },
    { field: 'payload.pull_request.additions', label: 'Additions', description: 'Lines added', type: 'number' },
    { field: 'payload.pull_request.deletions', label: 'Deletions', description: 'Lines removed', type: 'number' },
    { field: 'payload.repository.full_name', label: 'Repository', description: 'e.g. "owner/repo"', type: 'string' },
    { field: 'payload.sender.login', label: 'Sender', description: 'GitHub user that triggered the event', type: 'string' },
  ],
  schedule: [
    { field: 'payload.fired_at', label: 'Fired At', description: 'When the schedule fired (ISO)', type: 'string' },
    { field: 'payload.cron_expression', label: 'Cron Expression', description: 'The schedule that fired this run', type: 'string' },
    { field: 'payload.instance_name', label: 'Schedule Name', description: 'Operator-set integration name', type: 'string' },
    { field: 'payload.timezone', label: 'Timezone', description: 'IANA timezone the cron evaluates in', type: 'string' },
    { field: 'payload.payload_template', label: 'Payload Template', description: 'Operator-defined static payload (object)', type: 'object' },
  ],
  webhook: [
    { field: 'payload.message_text', label: 'Message Text', description: 'Inbound message body (string)', type: 'string' },
    { field: 'payload.sender_id', label: 'Sender ID', description: 'External sender identifier', type: 'string' },
    { field: 'payload.sender_name', label: 'Sender Name', description: 'External sender display name', type: 'string' },
    { field: 'payload.source_id', label: 'Source ID', description: 'Source-provided event ID', type: 'string' },
    { field: 'payload.timestamp', label: 'Timestamp', description: 'Inbound event unix seconds', type: 'number' },
    { field: 'payload.raw_event', label: 'Raw Event', description: 'Full inbound JSON body (object). Use {{source.payload.raw_event.your_field}} for arbitrary fields.', type: 'object' },
    { field: 'payload.webhook_id', label: 'Webhook ID', description: 'Tsushin webhook integration id', type: 'number' },
  ],
}


/**
 * Returns the variable list to surface for a Source step bound to ``triggerKind``.
 * Combines the generic source fields (payload / trigger_kind / event_type / etc.)
 * with the per-kind deep payload paths so a downstream Notification step can
 * directly insert ``{{step_1.payload.issue.key}}`` (Jira) or
 * ``{{step_1.payload.subject}}`` (Email) without knowing the wake-event schema.
 *
 * Used by StepVariablePanel when iterating previous steps — if step.type ===
 * 'source', the panel calls this with step.config.trigger_kind.
 */
export function getSourceStepVariables(triggerKind: string | null | undefined): StepVariable[] {
  const base = STEP_OUTPUT_FIELDS.source || []
  if (!triggerKind) return base
  const perKind = SOURCE_PAYLOAD_FIELDS_BY_KIND[triggerKind] || []
  return [...base, ...perKind]
}

// ============================================================
// Helper Functions Reference
// ============================================================

export const HELPER_FUNCTIONS: HelperFunction[] = [
  { name: 'truncate', syntax: '{{truncate step_N.FIELD 100}}', description: 'Truncate text to N characters' },
  { name: 'upper', syntax: '{{upper step_N.FIELD}}', description: 'Convert to UPPERCASE' },
  { name: 'lower', syntax: '{{lower step_N.FIELD}}', description: 'Convert to lowercase' },
  { name: 'trim', syntax: '{{trim step_N.FIELD}}', description: 'Remove leading/trailing whitespace' },
  { name: 'default', syntax: '{{default step_N.FIELD "fallback"}}', description: 'Use fallback value if empty' },
  { name: 'json', syntax: '{{json step_N.FIELD}}', description: 'Format as pretty JSON' },
  { name: 'length', syntax: '{{length step_N.FIELD}}', description: 'Get length of string or list' },
  { name: 'first', syntax: '{{first step_N.FIELD}}', description: 'Get first element of a list' },
  { name: 'last', syntax: '{{last step_N.FIELD}}', description: 'Get last element of a list' },
  { name: 'join', syntax: '{{join step_N.FIELD ", "}}', description: 'Join list elements with separator' },
  { name: 'replace', syntax: '{{replace step_N.FIELD "old" "new"}}', description: 'Replace substring in text' },
]

// ============================================================
// Flow Context Variables
// ============================================================

export const FLOW_CONTEXT_VARS: FlowContextVar[] = [
  { variable: 'flow.id', description: 'Current flow run ID' },
  { variable: 'flow.status', description: 'Current flow execution status' },
  { variable: 'flow.trigger_context', description: 'Trigger parameters object' },
  { variable: 'previous_step.status', description: 'Most recent step status' },
  { variable: 'previous_step.summary', description: 'Most recent step summary' },
]

// ============================================================
// Conditional Syntax Reference
// ============================================================

export const CONDITIONAL_EXAMPLES = [
  { syntax: '{{#if step_N.success}}...{{/if}}', description: 'Basic if block' },
  { syntax: '{{#if step_N.status == "completed"}}...{{else}}...{{/if}}', description: 'If/else with comparison' },
  { syntax: '{{#if step_1.success and step_2.success}}...{{/if}}', description: 'AND condition' },
  { syntax: '{{#if step_1.failed or step_2.failed}}...{{/if}}', description: 'OR condition' },
]

// ============================================================
// Utility Functions
// ============================================================

export function getOutputFieldsForStepType(stepType: string): StepVariable[] {
  return STEP_OUTPUT_FIELDS[stepType] || []
}

export function generateVariableTemplate(
  stepPosition: number,
  field: string,
): string {
  return `{{step_${stepPosition}.${field}}}`
}

export function generateNamedVariableTemplate(
  stepName: string,
  field: string,
): string {
  const normalized = stepName.toLowerCase().replace(/[\s-]/g, '_')
  return `{{${normalized}.${field}}}`
}

export function generateAliasVariableTemplate(
  alias: string,
  field: string,
): string {
  return `{{${alias}.${field}}}`
}
