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
    { field: 'gate_result', label: 'Gate Result', description: 'Whether the gate passed or blocked (pass/block)', type: 'string' },
    { field: 'gate_mode', label: 'Gate Mode', description: 'Evaluation mode used (programmatic or agentic)', type: 'string' },
    { field: 'conditions_evaluated', label: 'Conditions Evaluated', description: 'Number of conditions that were checked', type: 'number' },
    { field: 'reasoning', label: 'Reasoning', description: 'Explanation of why the gate passed or blocked', type: 'string' },
    { field: 'status', label: 'Status', description: 'Execution status (completed or failed)', type: 'string' },
    { field: 'fail_action_taken', label: 'Fail Action Taken', description: 'Action taken on gate failure (skip, notify, alternative)', type: 'string' },
  ],
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
