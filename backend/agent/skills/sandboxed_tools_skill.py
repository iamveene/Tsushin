"""
Sandboxed Tools Skill - Master toggle for sandboxed tool access.

Controls whether sandboxed tools (nmap, nuclei, dig, etc.) are available
to an agent. When enabled, the agent can use sandboxed tools that are
individually enabled via the Sandboxed Tools tab. When disabled, no
sandboxed tools are loaded for the agent.

This is a passive skill that acts as a gate — it doesn't process
messages directly but controls whether SandboxedToolWrapper is
initialized for the agent.
"""

import logging
from typing import Dict, Any
from agent.skills.base import BaseSkill, InboundMessage, SkillResult


class SandboxedToolsSkill(BaseSkill):
    """
    Sandboxed Tools Skill - Master toggle for sandboxed tool access.

    This skill doesn't process messages directly. It signals to
    agent_service.py whether to initialize SandboxedToolWrapper,
    which provides the agent with access to sandboxed tools running
    in isolated Docker containers.
    """

    skill_type = "sandboxed_tools"
    skill_name = "Sandboxed Tools"
    skill_description = (
        "Enable sandboxed tools (nmap, nuclei, dig, httpx, etc.) for this agent. "
        "Tools run in isolated Docker containers. Individual tools can be "
        "configured in the Sandboxed Tools tab."
    )
    execution_mode = "passive"  # Gate for sandboxed tool access, not a tool itself

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)

    async def can_handle(self, message: InboundMessage) -> bool:
        """Passive skill — doesn't handle messages directly."""
        return False

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """Passive skill — no direct processing."""
        return SkillResult(
            success=True,
            output="Sandboxed tools is a passive skill (controls tool access)",
            metadata={"passive": True}
        )

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        return {}

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "description": "No additional configuration needed. Individual tools are managed in the Sandboxed Tools tab."
        }
