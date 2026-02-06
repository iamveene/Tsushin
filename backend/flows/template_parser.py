"""
Phase 13.1: Step Output Injection - Template Parser Service

Provides template parsing and variable resolution for multi-step workflows.
Enables message and notification steps to access outputs from previous steps.

Syntax supported:
- Step by index: {{step_1.status}}, {{step_2.raw_output}}
- Step by name: {{network_scan.result}}, {{notify_user.recipient}}
- Previous step: {{previous_step.output}}, {{previous_step.summary}}
- Flow context: {{flow.trigger_context.param}}, {{flow.id}}
- JSON paths: {{step_1.raw_output.ports[0]}}, {{step_1.output.items.0.name}}
- Helpers: {{truncate step_1.raw_output 100}}, {{upper step_1.status}}
- Conditionals: {{#if step_1.success}}OK{{else}}FAIL{{/if}}
- Defaults: {{default step_1.error "No error"}}
"""

import re
import json
import logging
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class TemplateParseError(Exception):
    """Raised when template parsing fails."""
    pass


class TemplateParser:
    """
    Template parser for step output injection in multi-step workflows.

    Resolves template variables with support for:
    - Step index references: {{step_1.status}}
    - Step name references: {{network_scan.result}}
    - Special references: {{previous_step}}, {{flow}}
    - JSON path navigation: {{step_1.raw_output.ports[0]}}
    - Helper functions: truncate, upper, lower, default, json
    - Conditionals: {{#if}}...{{else}}...{{/if}}
    """

    # Pattern for matching template variables: {{...}}
    VARIABLE_PATTERN = re.compile(r'\{\{([^}]+)\}\}')

    # Pattern for conditional blocks: {{#if condition}}...{{else}}...{{/if}}
    CONDITIONAL_PATTERN = re.compile(
        r'\{\{#if\s+([^}]+)\}\}(.*?)(?:\{\{else\}\}(.*?))?\{\{/if\}\}',
        re.DOTALL
    )

    # Pattern for helper functions: {{helper_name arg1 arg2}}
    HELPER_PATTERN = re.compile(r'^(\w+)\s+(.+)$')

    # Pattern for JSON path with array access: field.subfield[0].name or field.subfield.0.name
    PATH_PATTERN = re.compile(r'([^.\[\]]+)|\[(\d+)\]')

    def __init__(self, context: Optional[Dict[str, Any]] = None):
        """
        Initialize the template parser.

        Args:
            context: Initial context dictionary for variable resolution
        """
        self.context = context or {}

        # Register built-in helper functions
        self.helpers = {
            'truncate': self._helper_truncate,
            'upper': self._helper_upper,
            'lower': self._helper_lower,
            'default': self._helper_default,
            'json': self._helper_json,
            'length': self._helper_length,
            'first': self._helper_first,
            'last': self._helper_last,
            'join': self._helper_join,
            'replace': self._helper_replace,
            'trim': self._helper_trim,
        }

    def render(self, template: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Render a template string by resolving all variables and helpers.

        Args:
            template: Template string with {{variable}} placeholders
            context: Optional context to merge with instance context

        Returns:
            Rendered string with all variables resolved
        """
        if not template:
            return template

        # Merge context
        merged_context = {**self.context, **(context or {})}

        try:
            # First, process conditional blocks
            result = self._process_conditionals(template, merged_context)

            # Then, resolve remaining variables
            result = self._resolve_variables(result, merged_context)

            return result

        except Exception as e:
            logger.error(f"Template parsing error: {e}", exc_info=True)
            # Return template with unresolved variables marked
            return template

    def _process_conditionals(self, template: str, context: Dict[str, Any]) -> str:
        """Process {{#if condition}}...{{else}}...{{/if}} blocks."""

        def replace_conditional(match: re.Match) -> str:
            condition_expr = match.group(1).strip()
            true_block = match.group(2) or ""
            false_block = match.group(3) or ""

            # Evaluate the condition
            condition_value = self._evaluate_condition(condition_expr, context)

            if condition_value:
                return true_block
            else:
                return false_block

        # Process all conditional blocks (may be nested, so repeat until no more matches)
        max_iterations = 10  # Prevent infinite loops
        for _ in range(max_iterations):
            new_template = self.CONDITIONAL_PATTERN.sub(replace_conditional, template)
            if new_template == template:
                break
            template = new_template

        return template

    def _evaluate_condition(self, expr: str, context: Dict[str, Any]) -> bool:
        """
        Evaluate a condition expression.

        Supports:
        - Simple variable truthiness: step_1.success
        - Equality: step_1.status == "completed"
        - Inequality: step_1.exit_code != 0
        - Boolean operators: step_1.success and step_2.success
        """
        expr = expr.strip()

        # Handle equality/inequality operators
        if ' == ' in expr:
            left, right = expr.split(' == ', 1)
            left_val = self._resolve_path(left.strip(), context)
            right_val = self._parse_literal(right.strip())
            return left_val == right_val

        if ' != ' in expr:
            left, right = expr.split(' != ', 1)
            left_val = self._resolve_path(left.strip(), context)
            right_val = self._parse_literal(right.strip())
            return left_val != right_val

        if ' > ' in expr:
            left, right = expr.split(' > ', 1)
            left_val = self._resolve_path(left.strip(), context)
            right_val = self._parse_literal(right.strip())
            try:
                return float(left_val) > float(right_val)
            except (ValueError, TypeError):
                return False

        if ' < ' in expr:
            left, right = expr.split(' < ', 1)
            left_val = self._resolve_path(left.strip(), context)
            right_val = self._parse_literal(right.strip())
            try:
                return float(left_val) < float(right_val)
            except (ValueError, TypeError):
                return False

        # Handle 'and' operator
        if ' and ' in expr:
            parts = expr.split(' and ')
            return all(self._evaluate_condition(p.strip(), context) for p in parts)

        # Handle 'or' operator
        if ' or ' in expr:
            parts = expr.split(' or ')
            return any(self._evaluate_condition(p.strip(), context) for p in parts)

        # Handle 'not' operator
        if expr.startswith('not '):
            return not self._evaluate_condition(expr[4:].strip(), context)

        # Simple truthiness check
        value = self._resolve_path(expr, context)
        return self._is_truthy(value)

    def _parse_literal(self, value: str) -> Any:
        """Parse a literal value from a condition expression."""
        # Handle quoted strings
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            return value[1:-1]

        # Handle numbers
        try:
            if '.' in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        # Handle booleans
        if value.lower() == 'true':
            return True
        if value.lower() == 'false':
            return False
        if value.lower() == 'null' or value.lower() == 'none':
            return None

        return value

    def _is_truthy(self, value: Any) -> bool:
        """Check if a value is truthy."""
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return len(value) > 0 and value.lower() not in ('false', 'null', 'none', '0')
        if isinstance(value, (list, dict)):
            return len(value) > 0
        return bool(value)

    def _resolve_variables(self, template: str, context: Dict[str, Any]) -> str:
        """Resolve all {{variable}} placeholders in the template."""

        def replace_variable(match: re.Match) -> str:
            expr = match.group(1).strip()

            # Check if this is a helper function call
            helper_match = self.HELPER_PATTERN.match(expr)
            if helper_match:
                helper_name = helper_match.group(1)
                if helper_name in self.helpers:
                    args_str = helper_match.group(2)
                    return self._call_helper(helper_name, args_str, context)

            # Otherwise, resolve as a path
            value = self._resolve_path(expr, context)
            return self._format_value(value)

        return self.VARIABLE_PATTERN.sub(replace_variable, template)

    def _resolve_path(self, path: str, context: Dict[str, Any]) -> Any:
        """
        Resolve a dot-notation path to a value in the context.

        Supports:
        - Simple paths: step_1.status
        - Array access: step_1.ports[0] or step_1.ports.0
        - Nested paths: step_1.raw_output.data.items[0].name
        """
        if not path:
            return None

        path = path.strip()

        # Handle direct context keys first (e.g., step_1, previous_step, flow)
        parts = path.split('.', 1)
        root_key = parts[0]

        # Check for array access in root key (e.g., items[0])
        if '[' in root_key:
            root_key = root_key.split('[')[0]

        if root_key not in context:
            logger.debug(f"Path '{path}' not found in context (root key: {root_key})")
            return None

        current = context[root_key]

        # If no more path parts, return current value
        if len(parts) == 1 and '[' not in parts[0]:
            return current

        # Process remaining path
        remaining_path = path[len(root_key):]
        if remaining_path.startswith('.'):
            remaining_path = remaining_path[1:]

        # Parse the path using regex to handle both dot notation and array access
        for token in self._tokenize_path(remaining_path):
            if current is None:
                return None

            if isinstance(token, int):
                # Array index access
                if isinstance(current, (list, tuple)):
                    if 0 <= token < len(current):
                        current = current[token]
                    else:
                        return None
                else:
                    return None
            else:
                # Object property access
                if isinstance(current, dict):
                    current = current.get(token)
                elif hasattr(current, token):
                    current = getattr(current, token)
                else:
                    return None

        return current

    def _tokenize_path(self, path: str) -> List[Union[str, int]]:
        """Tokenize a path string into property names and array indices."""
        tokens = []

        if not path:
            return tokens

        # Split by dots and brackets
        parts = re.split(r'\.|\[|\]', path)

        for part in parts:
            if not part:
                continue
            # Try to parse as integer (array index)
            try:
                tokens.append(int(part))
            except ValueError:
                tokens.append(part)

        return tokens

    def _call_helper(self, helper_name: str, args_str: str, context: Dict[str, Any]) -> str:
        """Call a helper function with the given arguments."""
        helper = self.helpers.get(helper_name)
        if not helper:
            logger.warning(f"Unknown helper function: {helper_name}")
            return f"{{{{unknown helper: {helper_name}}}}}"

        try:
            # Parse arguments
            args = self._parse_helper_args(args_str, context)
            result = helper(*args)
            return self._format_value(result)
        except Exception as e:
            logger.error(f"Helper '{helper_name}' failed: {e}")
            return f"{{{{error in {helper_name}: {e}}}}}"

    def _parse_helper_args(self, args_str: str, context: Dict[str, Any]) -> List[Any]:
        """Parse helper function arguments."""
        args = []
        current_arg = ""
        in_quotes = False
        quote_char = None

        for char in args_str:
            if char in ('"', "'") and not in_quotes:
                in_quotes = True
                quote_char = char
            elif char == quote_char and in_quotes:
                in_quotes = False
                quote_char = None
            elif char == ' ' and not in_quotes:
                if current_arg:
                    args.append(self._resolve_arg(current_arg.strip(), context))
                    current_arg = ""
                continue
            current_arg += char

        if current_arg:
            args.append(self._resolve_arg(current_arg.strip(), context))

        return args

    def _resolve_arg(self, arg: str, context: Dict[str, Any]) -> Any:
        """Resolve a single helper argument."""
        # Handle quoted strings
        if (arg.startswith('"') and arg.endswith('"')) or \
           (arg.startswith("'") and arg.endswith("'")):
            return arg[1:-1]

        # Handle numbers
        try:
            if '.' in arg:
                return float(arg)
            return int(arg)
        except ValueError:
            pass

        # Resolve as path
        return self._resolve_path(arg, context)

    def _format_value(self, value: Any) -> str:
        """Format a value for template output."""
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        return str(value)

    # ========== Helper Functions ==========

    def _helper_truncate(self, value: Any, length: int = 100, suffix: str = "...") -> str:
        """Truncate a string to a maximum length."""
        text = self._format_value(value)
        if len(text) <= length:
            return text
        return text[:length - len(suffix)] + suffix

    def _helper_upper(self, value: Any) -> str:
        """Convert to uppercase."""
        return self._format_value(value).upper()

    def _helper_lower(self, value: Any) -> str:
        """Convert to lowercase."""
        return self._format_value(value).lower()

    def _helper_default(self, value: Any, default_value: Any = "") -> Any:
        """Return default value if value is empty/None."""
        if value is None or value == "" or (isinstance(value, (list, dict)) and len(value) == 0):
            return default_value
        return value

    def _helper_json(self, value: Any, indent: int = 2) -> str:
        """Format value as JSON."""
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
        return json.dumps(value, ensure_ascii=False, indent=indent)

    def _helper_length(self, value: Any) -> int:
        """Get length of a value."""
        if value is None:
            return 0
        if isinstance(value, (str, list, dict)):
            return len(value)
        return len(str(value))

    def _helper_first(self, value: Any) -> Any:
        """Get first element of a list."""
        if isinstance(value, (list, tuple)) and len(value) > 0:
            return value[0]
        return None

    def _helper_last(self, value: Any) -> Any:
        """Get last element of a list."""
        if isinstance(value, (list, tuple)) and len(value) > 0:
            return value[-1]
        return None

    def _helper_join(self, value: Any, separator: str = ", ") -> str:
        """Join list elements with a separator."""
        if isinstance(value, (list, tuple)):
            return separator.join(self._format_value(v) for v in value)
        return self._format_value(value)

    def _helper_replace(self, value: Any, old: str, new: str) -> str:
        """Replace occurrences in a string."""
        return self._format_value(value).replace(old, new)

    def _helper_trim(self, value: Any) -> str:
        """Trim whitespace from a string."""
        return self._format_value(value).strip()

    # ========== Validation ==========

    def validate_template(self, template: str) -> List[str]:
        """
        Validate a template for syntax errors.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not template:
            return errors

        # Check for unmatched braces
        open_count = template.count('{{')
        close_count = template.count('}}')
        if open_count != close_count:
            errors.append(f"Unmatched braces: {open_count} opening vs {close_count} closing")

        # Check for unclosed conditionals
        if_count = len(re.findall(r'\{\{#if\s+', template))
        endif_count = len(re.findall(r'\{\{/if\}\}', template))
        if if_count != endif_count:
            errors.append(f"Unclosed conditionals: {if_count} #if vs {endif_count} /if")

        # Check for empty expressions
        empty_matches = re.findall(r'\{\{\s*\}\}', template)
        if empty_matches:
            errors.append(f"Empty expression found: {len(empty_matches)} occurrence(s)")

        return errors

    def extract_variables(self, template: str) -> List[str]:
        """
        Extract all variable references from a template.

        Returns:
            List of unique variable paths used in the template
        """
        variables = set()

        # Extract from regular variables
        for match in self.VARIABLE_PATTERN.finditer(template):
            expr = match.group(1).strip()

            # Skip helper function calls for now
            helper_match = self.HELPER_PATTERN.match(expr)
            if helper_match:
                # Extract the path argument from helper
                args_str = helper_match.group(2)
                # Get the first argument (usually the path)
                first_arg = args_str.split()[0] if args_str else ""
                if first_arg and not first_arg.startswith('"') and not first_arg.startswith("'"):
                    variables.add(first_arg)
            else:
                variables.add(expr)

        # Extract from conditionals
        for match in self.CONDITIONAL_PATTERN.finditer(template):
            condition = match.group(1).strip()
            # Extract variable from condition
            for part in re.split(r'\s+(?:and|or|==|!=|>|<)\s+', condition):
                part = part.strip()
                if part and not part.startswith('"') and not part.startswith("'"):
                    if part.startswith('not '):
                        part = part[4:].strip()
                    try:
                        float(part)
                    except ValueError:
                        if part.lower() not in ('true', 'false', 'null', 'none'):
                            variables.add(part)

        return sorted(list(variables))


def build_step_context(
    flow_run_id: int,
    trigger_context: Optional[Dict[str, Any]],
    step_runs: List[Dict[str, Any]],
    steps: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Build comprehensive step context for template resolution.

    Args:
        flow_run_id: ID of the current flow run
        trigger_context: Initial trigger context/parameters
        step_runs: List of completed step run data
        steps: List of step definitions (with id, name, type, position)

    Returns:
        Context dictionary with step outputs accessible by:
        - step_N: Step by position (1-based)
        - step_name: Step by name (if named)
        - previous_step: Most recent completed step
        - flow: Flow-level context
    """
    context = {
        "flow": {
            "id": flow_run_id,
            "trigger_context": trigger_context or {}
        },
        "previous_step": None,
        "steps": {}
    }

    # Build a map of step_id -> step definition
    step_by_id = {s.get("id"): s for s in steps}

    for step_run in step_runs:
        step_id = step_run.get("flow_node_id")
        step_def = step_by_id.get(step_id, {})

        position = step_def.get("position", 0)
        name = step_def.get("name")
        step_type = step_def.get("type")

        # Parse output JSON if it's a string
        output = step_run.get("output", {})
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                output = {"raw": output}

        # Build step data
        step_data = {
            "position": position,
            "name": name,
            "type": step_type,
            "status": step_run.get("status", "unknown"),
            "error": step_run.get("error_text"),
            "execution_time_ms": step_run.get("execution_time_ms"),
            **output  # Merge all output fields (raw_output, summary, tool_used, etc.)
        }

        # Add by position (1-based)
        if position > 0:
            context[f"step_{position}"] = step_data
            context["steps"][position] = step_data

        # Add by name if available
        if name:
            context[name] = step_data

        # Update previous_step
        context["previous_step"] = step_data

    return context
