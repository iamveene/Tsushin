"""
Phase 22/23: Custom Skills — Adapter

Wraps a CustomSkill DB record as a BaseSkill instance so that
tenant-created skills integrate seamlessly with the existing
SkillManager registry, tool definitions, and prompt injection pipeline.

Phase 23 adds script execution support: deploys scripts to the
tenant's toolbox container and runs them with JSON input/output.
"""
import json
import time
import logging
from typing import Dict, Optional, Any

from agent.skills.base import BaseSkill, InboundMessage, SkillResult

logger = logging.getLogger(__name__)


class CustomSkillAdapter(BaseSkill):
    """Adapter that wraps a CustomSkill DB record as a BaseSkill instance."""

    skill_type = "custom"
    skill_name = "Custom Skill"
    skill_description = "Tenant-created custom skill"
    execution_mode = "tool"

    def __init__(self, skill_record=None):
        super().__init__()
        self._record = skill_record
        if skill_record:
            self.skill_type = f"custom:{skill_record.slug}"
            self.skill_name = skill_record.name
            self.skill_description = skill_record.description or ""
            self.execution_mode = skill_record.execution_mode

    async def can_handle(self, message: InboundMessage) -> bool:
        if not self._record:
            return False
        if self._record.trigger_mode == 'always_on':
            return True
        if self._record.trigger_mode == 'keyword' and self._record.trigger_keywords:
            msg_lower = message.body.lower() if message.body else ""
            return any(kw.lower() in msg_lower for kw in self._record.trigger_keywords)
        return False  # llm_decided -- handled via tool call

    async def process(self, message: InboundMessage, config: Dict) -> SkillResult:
        return await self.execute_tool({}, message, config)

    def get_mcp_tool_definition(self) -> Optional[Dict]:
        if not self._record or self._record.execution_mode == 'passive':
            return None
        tool_def = {
            "name": f"custom_{self._record.slug}",
            "description": self._record.description or self._record.name,
        }
        if self._record.input_schema:
            tool_def["inputSchema"] = self._record.input_schema
        else:
            tool_def["inputSchema"] = {"type": "object", "properties": {}}
        return tool_def

    async def execute_tool(self, arguments: Dict, message: InboundMessage = None, config: Dict = None) -> SkillResult:
        if not self._record:
            return SkillResult(success=False, output="No skill record attached", metadata={})

        if self._record.skill_type_variant == 'instruction':
            return self._execute_instruction(arguments)
        elif self._record.skill_type_variant == 'script':
            return await self._execute_script(arguments, config)
        else:
            return SkillResult(success=False, output=f"Unknown skill type: {self._record.skill_type_variant}", metadata={})

    def _execute_instruction(self, arguments: Dict) -> SkillResult:
        output = self._record.instructions_md or ""
        if arguments:
            # Simple template substitution
            for key, value in arguments.items():
                output = output.replace(f"{{{{{key}}}}}", str(value))
        return SkillResult(
            success=True,
            output=output,
            metadata={"skill_type": "instruction", "skill_name": self._record.name},
        )

    async def _execute_script(self, arguments: Dict, config: Dict = None) -> SkillResult:
        """
        Execute script in tenant's toolbox container.

        The script receives input via the TSUSHIN_INPUT environment variable
        (JSON-encoded arguments). It should print JSON to stdout with at least
        an "output" field. Non-JSON stdout is returned as plain text.
        """
        from services.custom_skill_deploy_service import CustomSkillDeployService
        from services.toolbox_container_service import get_toolbox_service

        tenant_id = config.get('tenant_id') if config else None
        if not tenant_id:
            return SkillResult(
                success=False,
                output="No tenant context for script execution",
                metadata={"skill_type": "script", "skill_name": self._record.name},
            )

        # Ensure script is deployed (check hash, redeploy if stale)
        try:
            db = config.get('db') if config else None
            if db:
                deployed = await CustomSkillDeployService.ensure_deployed(
                    self._record, tenant_id, db
                )
                if not deployed:
                    return SkillResult(
                        success=False,
                        output="Failed to deploy skill script to container",
                        metadata={"skill_type": "script", "skill_name": self._record.name},
                    )
        except Exception as e:
            logger.warning(f"Deploy check failed for skill {self._record.name}: {e}")

        # Build the execution command
        entrypoint = self._record.script_entrypoint or "main.py"
        skill_dir = f"/workspace/skills/{self._record.id}"
        language = self._record.script_language or "python"

        if language == "python":
            cmd = f"cd {skill_dir} && python {entrypoint}"
        elif language == "bash":
            cmd = f"cd {skill_dir} && bash {entrypoint}"
        elif language == "nodejs":
            cmd = f"cd {skill_dir} && node {entrypoint}"
        else:
            cmd = f"cd {skill_dir} && python {entrypoint}"

        # Prepare input as JSON environment variable
        input_json = json.dumps(arguments or {})
        cmd = f'export TSUSHIN_INPUT={json.dumps(input_json)} && {cmd}'

        container_service = get_toolbox_service()
        timeout = self._record.timeout_seconds or 30

        start_time = time.time()
        try:
            result = await container_service.execute_command(
                tenant_id,
                cmd,
                timeout=timeout,
                workdir=skill_dir,
                db=db,
            )
        except Exception as e:
            logger.error(f"Script execution failed for skill {self._record.name}: {e}")
            return SkillResult(
                success=False,
                output=f"Script execution error: {e}",
                metadata={
                    "skill_type": "script",
                    "skill_name": self._record.name,
                    "execution_time_ms": int((time.time() - start_time) * 1000),
                },
            )

        stdout = result.get('stdout', '').strip()
        stderr = result.get('stderr', '').strip()
        exit_code = result.get('exit_code', -1)
        exec_time_ms = result.get('execution_time_ms', 0)

        metadata = {
            "skill_type": "script",
            "skill_name": self._record.name,
            "exit_code": exit_code,
            "execution_time_ms": exec_time_ms,
            "timed_out": result.get('timed_out', False),
            "oom_killed": result.get('oom_killed', False),
        }

        if exit_code != 0:
            error_msg = stderr or stdout or f"Script exited with code {exit_code}"
            if result.get('timed_out'):
                error_msg = f"Script timed out after {timeout}s"
            elif result.get('oom_killed'):
                error_msg = "Script killed (out of memory)"
            return SkillResult(success=False, output=error_msg, metadata=metadata)

        # Try to parse stdout as JSON
        try:
            parsed = json.loads(stdout)
            output_text = parsed.get('output', stdout)
            metadata.update({k: v for k, v in parsed.items() if k != 'output'})
            return SkillResult(success=True, output=str(output_text), metadata=metadata)
        except (json.JSONDecodeError, AttributeError):
            # Return raw stdout as plain text
            return SkillResult(success=True, output=stdout, metadata=metadata)

    def get_instructions_for_prompt(self) -> Optional[str]:
        if self._record and self._record.instructions_md:
            return f"\n\n## Custom Skill: {self._record.name}\n{self._record.instructions_md}"
        return None
