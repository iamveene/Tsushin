"""
Phase 13.1: Step Output Injection - Template Parser Tests

Tests for the TemplateParser service that handles variable resolution,
JSON paths, helper functions, and conditional expressions.
"""

import pytest
import json
from flows.template_parser import TemplateParser, build_step_context, TemplateParseError


class TestTemplateParserBasics:
    """Test basic variable resolution."""

    def test_simple_variable_replacement(self):
        """Test simple {{variable}} replacement."""
        parser = TemplateParser({"name": "John", "status": "active"})
        result = parser.render("Hello {{name}}, your status is {{status}}")
        assert result == "Hello John, your status is active"

    def test_undefined_variable_returns_empty(self):
        """Test that undefined variables render as empty strings."""
        parser = TemplateParser({"name": "John"})
        result = parser.render("Hello {{name}}, status: {{undefined_var}}")
        assert result == "Hello John, status: "

    def test_empty_template_returns_empty(self):
        """Test empty template handling."""
        parser = TemplateParser()
        assert parser.render("") == ""
        assert parser.render(None) is None

    def test_no_variables_returns_original(self):
        """Test template with no variables."""
        parser = TemplateParser({"name": "John"})
        result = parser.render("Hello World!")
        assert result == "Hello World!"


class TestStepReferences:
    """Test step index and name references."""

    def test_step_index_reference(self):
        """Test {{step_N.field}} syntax."""
        context = {
            "step_1": {
                "status": "completed",
                "raw_output": "Port 22 open",
                "execution_time_ms": 150
            }
        }
        parser = TemplateParser(context)

        result = parser.render("Status: {{step_1.status}}")
        assert result == "Status: completed"

        result = parser.render("Output: {{step_1.raw_output}}")
        assert result == "Output: Port 22 open"

    def test_step_name_reference(self):
        """Test {{step_name.field}} syntax."""
        context = {
            "network_scan": {
                "status": "completed",
                "raw_output": "192.168.1.1: reachable",
                "summary": "Scan completed successfully"
            }
        }
        parser = TemplateParser(context)

        result = parser.render("Scan result: {{network_scan.summary}}")
        assert result == "Scan result: Scan completed successfully"

    def test_previous_step_reference(self):
        """Test {{previous_step.field}} syntax."""
        context = {
            "previous_step": {
                "status": "completed",
                "message_sent": "Hello there!"
            }
        }
        parser = TemplateParser(context)

        result = parser.render("Last step status: {{previous_step.status}}")
        assert result == "Last step status: completed"

    def test_flow_context_reference(self):
        """Test {{flow.field}} syntax."""
        context = {
            "flow": {
                "id": 42,
                "trigger_context": {
                    "target": "192.168.1.0/24"
                }
            }
        }
        parser = TemplateParser(context)

        result = parser.render("Flow #{{flow.id}}")
        assert result == "Flow #42"


class TestJsonPaths:
    """Test JSON path navigation."""

    def test_nested_object_path(self):
        """Test nested object access."""
        context = {
            "step_1": {
                "result": {
                    "data": {
                        "name": "test",
                        "value": 123
                    }
                }
            }
        }
        parser = TemplateParser(context)

        result = parser.render("Name: {{step_1.result.data.name}}")
        assert result == "Name: test"

    def test_array_index_access(self):
        """Test array index access with [N] syntax."""
        context = {
            "step_1": {
                "ports": [22, 80, 443],
                "items": [
                    {"name": "first"},
                    {"name": "second"}
                ]
            }
        }
        parser = TemplateParser(context)

        result = parser.render("First port: {{step_1.ports[0]}}")
        assert result == "First port: 22"

        result = parser.render("Item name: {{step_1.items[1].name}}")
        assert result == "Item name: second"

    def test_array_dot_notation(self):
        """Test array access with .N syntax."""
        context = {
            "step_1": {
                "ports": [22, 80, 443]
            }
        }
        parser = TemplateParser(context)

        result = parser.render("First port: {{step_1.ports.0}}")
        assert result == "First port: 22"

    def test_invalid_path_returns_empty(self):
        """Test that invalid paths return empty string."""
        context = {"step_1": {"data": "value"}}
        parser = TemplateParser(context)

        result = parser.render("Missing: {{step_1.nonexistent.path}}")
        assert result == "Missing: "


class TestHelperFunctions:
    """Test helper functions."""

    def test_truncate_helper(self):
        """Test {{truncate expr N}} helper."""
        context = {"step_1": {"output": "This is a very long output string that needs truncation"}}
        parser = TemplateParser(context)

        result = parser.render("Output: {{truncate step_1.output 20}}")
        assert result == "Output: This is a very lo..."
        assert len(result) <= len("Output: ") + 20

    def test_truncate_short_string(self):
        """Test truncate on string shorter than limit."""
        context = {"text": "Short"}
        parser = TemplateParser(context)

        result = parser.render("{{truncate text 100}}")
        assert result == "Short"

    def test_upper_helper(self):
        """Test {{upper expr}} helper."""
        context = {"status": "completed"}
        parser = TemplateParser(context)

        result = parser.render("Status: {{upper status}}")
        assert result == "Status: COMPLETED"

    def test_lower_helper(self):
        """Test {{lower expr}} helper."""
        context = {"status": "PENDING"}
        parser = TemplateParser(context)

        result = parser.render("Status: {{lower status}}")
        assert result == "Status: pending"

    def test_default_helper(self):
        """Test {{default expr fallback}} helper."""
        context = {"value": None, "present": "exists"}
        parser = TemplateParser(context)

        result = parser.render("Value: {{default value 'N/A'}}")
        assert result == "Value: N/A"

        result = parser.render("Value: {{default present 'N/A'}}")
        assert result == "Value: exists"

    def test_json_helper(self):
        """Test {{json expr}} helper."""
        context = {"data": {"key": "value", "count": 42}}
        parser = TemplateParser(context)

        result = parser.render("{{json data}}")
        parsed = json.loads(result)
        assert parsed == {"key": "value", "count": 42}

    def test_length_helper(self):
        """Test {{length expr}} helper."""
        context = {"items": [1, 2, 3, 4, 5], "text": "Hello"}
        parser = TemplateParser(context)

        result = parser.render("Items: {{length items}}")
        assert result == "Items: 5"

        result = parser.render("Chars: {{length text}}")
        assert result == "Chars: 5"

    def test_first_last_helpers(self):
        """Test {{first expr}} and {{last expr}} helpers."""
        context = {"items": ["alpha", "beta", "gamma"]}
        parser = TemplateParser(context)

        result = parser.render("First: {{first items}}")
        assert result == "First: alpha"

        result = parser.render("Last: {{last items}}")
        assert result == "Last: gamma"

    def test_join_helper(self):
        """Test {{join expr separator}} helper."""
        context = {"tags": ["urgent", "important", "todo"]}
        parser = TemplateParser(context)

        result = parser.render("Tags: {{join tags ', '}}")
        assert result == "Tags: urgent, important, todo"

    def test_replace_helper(self):
        """Test {{replace expr old new}} helper."""
        context = {"text": "Hello World"}
        parser = TemplateParser(context)

        result = parser.render("{{replace text 'World' 'Universe'}}")
        assert result == "Hello Universe"

    def test_trim_helper(self):
        """Test {{trim expr}} helper."""
        context = {"text": "  spaced text  "}
        parser = TemplateParser(context)

        result = parser.render("[{{trim text}}]")
        assert result == "[spaced text]"


class TestConditionals:
    """Test conditional expressions."""

    def test_simple_if_true(self):
        """Test {{#if condition}}...{{/if}} when true."""
        context = {"success": True}
        parser = TemplateParser(context)

        result = parser.render("Result: {{#if success}}OK{{/if}}")
        assert result == "Result: OK"

    def test_simple_if_false(self):
        """Test {{#if condition}}...{{/if}} when false."""
        context = {"success": False}
        parser = TemplateParser(context)

        result = parser.render("Result: {{#if success}}OK{{/if}}")
        assert result == "Result: "

    def test_if_else(self):
        """Test {{#if condition}}...{{else}}...{{/if}}."""
        context_true = {"success": True}
        context_false = {"success": False}
        parser_true = TemplateParser(context_true)
        parser_false = TemplateParser(context_false)

        template = "Status: {{#if success}}✅ Success{{else}}❌ Failed{{/if}}"

        result = parser_true.render(template)
        assert result == "Status: ✅ Success"

        result = parser_false.render(template)
        assert result == "Status: ❌ Failed"

    def test_equality_condition(self):
        """Test equality operator in conditions."""
        context = {"status": "completed"}
        parser = TemplateParser(context)

        result = parser.render('{{#if status == "completed"}}Done{{else}}Pending{{/if}}')
        assert result == "Done"

    def test_inequality_condition(self):
        """Test inequality operator in conditions."""
        context = {"exit_code": 1}
        parser = TemplateParser(context)

        result = parser.render('{{#if exit_code != 0}}Error{{else}}Success{{/if}}')
        assert result == "Error"

    def test_comparison_operators(self):
        """Test > and < operators."""
        context = {"count": 5}
        parser = TemplateParser(context)

        result = parser.render('{{#if count > 3}}Many{{else}}Few{{/if}}')
        assert result == "Many"

        result = parser.render('{{#if count < 10}}Under limit{{else}}Over limit{{/if}}')
        assert result == "Under limit"

    def test_and_operator(self):
        """Test 'and' operator in conditions."""
        context = {"a": True, "b": True}
        parser = TemplateParser(context)

        result = parser.render("{{#if a and b}}Both true{{else}}Not both{{/if}}")
        assert result == "Both true"

        context["b"] = False
        parser = TemplateParser(context)
        result = parser.render("{{#if a and b}}Both true{{else}}Not both{{/if}}")
        assert result == "Not both"

    def test_or_operator(self):
        """Test 'or' operator in conditions."""
        context = {"a": False, "b": True}
        parser = TemplateParser(context)

        result = parser.render("{{#if a or b}}At least one{{else}}Neither{{/if}}")
        assert result == "At least one"

    def test_not_operator(self):
        """Test 'not' operator in conditions."""
        context = {"failed": False}
        parser = TemplateParser(context)

        result = parser.render("{{#if not failed}}Success{{else}}Failed{{/if}}")
        assert result == "Success"

    def test_nested_path_in_condition(self):
        """Test nested paths in conditions."""
        context = {
            "step_1": {
                "result": {
                    "success": True
                }
            }
        }
        parser = TemplateParser(context)

        result = parser.render("{{#if step_1.result.success}}OK{{else}}FAIL{{/if}}")
        assert result == "OK"


class TestValidation:
    """Test template validation."""

    def test_valid_template(self):
        """Test validation of valid template."""
        parser = TemplateParser()
        errors = parser.validate_template("Hello {{name}}, status: {{status}}")
        assert errors == []

    def test_unmatched_braces(self):
        """Test detection of unmatched braces."""
        parser = TemplateParser()
        errors = parser.validate_template("Hello {{name, status: {{status}}")
        assert len(errors) > 0
        assert any("brace" in e.lower() for e in errors)

    def test_unclosed_conditional(self):
        """Test detection of unclosed conditionals."""
        parser = TemplateParser()
        errors = parser.validate_template("{{#if condition}}content without closing")
        assert len(errors) > 0
        assert any("conditional" in e.lower() or "if" in e.lower() for e in errors)

    def test_empty_expression(self):
        """Test detection of empty expressions."""
        parser = TemplateParser()
        errors = parser.validate_template("Hello {{   }}")
        assert len(errors) > 0
        assert any("empty" in e.lower() for e in errors)


class TestVariableExtraction:
    """Test variable extraction."""

    def test_extract_simple_variables(self):
        """Test extraction of simple variables."""
        parser = TemplateParser()
        variables = parser.extract_variables("Hello {{name}}, status: {{status}}")
        assert set(variables) == {"name", "status"}

    def test_extract_step_references(self):
        """Test extraction of step references."""
        parser = TemplateParser()
        variables = parser.extract_variables("Step 1: {{step_1.status}}, Step 2: {{step_2.output}}")
        assert "step_1.status" in variables
        assert "step_2.output" in variables

    def test_extract_from_conditionals(self):
        """Test extraction from conditional expressions."""
        parser = TemplateParser()
        variables = parser.extract_variables("{{#if step_1.success}}OK{{else}}FAIL{{/if}}")
        assert "step_1.success" in variables

    def test_extract_from_helpers(self):
        """Test extraction from helper function calls."""
        parser = TemplateParser()
        variables = parser.extract_variables("{{truncate step_1.output 100}}")
        assert "step_1.output" in variables


class TestBuildStepContext:
    """Test build_step_context function."""

    def test_basic_context_building(self):
        """Test basic context building."""
        step_runs = [
            {
                "flow_node_id": 1,
                "status": "completed",
                "output": {"raw_output": "Result 1", "summary": "Step 1 done"}
            }
        ]
        steps = [
            {"id": 1, "position": 1, "name": "first_step", "type": "tool"}
        ]

        context = build_step_context(
            flow_run_id=42,
            trigger_context={"target": "test"},
            step_runs=step_runs,
            steps=steps
        )

        assert context["flow"]["id"] == 42
        assert context["flow"]["trigger_context"]["target"] == "test"
        assert "step_1" in context
        assert context["step_1"]["status"] == "completed"
        assert context["step_1"]["raw_output"] == "Result 1"
        assert "first_step" in context  # By name

    def test_multiple_steps(self):
        """Test context with multiple steps."""
        step_runs = [
            {"flow_node_id": 1, "status": "completed", "output": {"result": "A"}},
            {"flow_node_id": 2, "status": "completed", "output": {"result": "B"}}
        ]
        steps = [
            {"id": 1, "position": 1, "name": "step_a", "type": "tool"},
            {"id": 2, "position": 2, "name": "step_b", "type": "tool"}
        ]

        context = build_step_context(42, None, step_runs, steps)

        assert context["step_1"]["result"] == "A"
        assert context["step_2"]["result"] == "B"
        assert context["step_a"]["result"] == "A"
        assert context["step_b"]["result"] == "B"
        assert context["previous_step"]["result"] == "B"

    def test_output_as_json_string(self):
        """Test handling of output as JSON string."""
        step_runs = [
            {
                "flow_node_id": 1,
                "status": "completed",
                "output": '{"data": "value", "count": 5}'  # JSON string
            }
        ]
        steps = [{"id": 1, "position": 1, "name": "test", "type": "tool"}]

        context = build_step_context(42, None, step_runs, steps)

        assert context["step_1"]["data"] == "value"
        assert context["step_1"]["count"] == 5


class TestComplexScenarios:
    """Test complex real-world scenarios."""

    def test_network_scan_notification(self):
        """Test network scan result notification template."""
        context = {
            "step_1": {
                "name": "network_scan",
                "status": "completed",
                "success": True,
                "raw_output": "Host: 192.168.1.1\nPorts: 22, 80, 443 open\nServices: SSH, HTTP, HTTPS",
                "parameters": {
                    "target": "192.168.1.0/24"
                }
            }
        }

        template = """Scan complete!

Target: {{step_1.parameters.target}}
Status: {{#if step_1.success}}✅ Success{{else}}❌ Failed{{/if}}

Results:
{{truncate step_1.raw_output 100}}"""

        parser = TemplateParser(context)
        result = parser.render(template)

        assert "192.168.1.0/24" in result
        assert "✅ Success" in result
        assert "Host: 192.168.1.1" in result

    def test_multi_step_flow_summary(self):
        """Test multi-step flow summary template."""
        context = {
            "step_1": {"name": "analyze", "status": "completed", "findings": 3},
            "step_2": {"name": "fix", "status": "completed", "fixed": 2},
            "step_3": {"name": "verify", "status": "completed", "verified": True},
            "previous_step": {"name": "verify", "status": "completed", "verified": True}
        }

        template = """Flow Summary:
1. Analysis: Found {{step_1.findings}} issues
2. Fix: Resolved {{step_2.fixed}} issues
3. Verification: {{#if step_3.verified}}All verified{{else}}Needs review{{/if}}

Final Status: {{upper previous_step.status}}"""

        parser = TemplateParser(context)
        result = parser.render(template)

        assert "Found 3 issues" in result
        assert "Resolved 2 issues" in result
        assert "All verified" in result
        assert "COMPLETED" in result

    def test_error_handling_template(self):
        """Test error handling in notification template."""
        context = {
            "step_1": {
                "status": "failed",
                "success": False,
                "error": "Connection timeout after 30s",
                "raw_output": None
            }
        }

        template = """Task Status: {{#if step_1.success}}✅{{else}}❌{{/if}}

{{#if step_1.error}}Error: {{step_1.error}}{{else}}No error{{/if}}

Output: {{default step_1.raw_output "No output available"}}"""

        parser = TemplateParser(context)
        result = parser.render(template)

        assert "❌" in result
        assert "Connection timeout after 30s" in result
        assert "No output available" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
