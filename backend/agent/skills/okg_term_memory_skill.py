"""
v0.6.0 Item 3: OKG Term Memory Skill

Ontological Knowledge Graph long-term memory with 3 LLM-callable tools:
- okg_store: Store a memory with typed metadata
- okg_recall: Search memories by query + metadata filters
- okg_forget: Delete a memory by doc_id

Also provides passive hooks:
- post_response_hook: Auto-capture facts from conversations
- Context injection via OKGContextInjector (Layer 5)
"""

import logging
from typing import Any, Dict, List, Optional

from agent.skills.base import BaseSkill, InboundMessage, SkillResult

logger = logging.getLogger(__name__)

# All 3 MCP tool definitions
OKG_TOOL_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "okg_store": {
        "name": "okg_store",
        "title": "OKG Store Memory",
        "description": (
            "Store a long-term memory with ontological metadata. Use when you learn "
            "a durable fact, preference, or relationship about a user or topic that "
            "should be remembered across conversations."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The memory content to store"
                },
                "memory_type": {
                    "type": "string",
                    "enum": ["fact", "episodic", "semantic", "procedural", "belief"],
                    "description": "Type of memory (default: fact)",
                    "default": "fact"
                },
                "subject_entity": {
                    "type": "string",
                    "description": "Who/what this memory is about (e.g., 'user:+5527...', 'topic:python')"
                },
                "relation": {
                    "type": "string",
                    "description": "Relationship label (e.g., 'prefers', 'knows', 'experienced', 'believes')"
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score 0.0-1.0 (default: 0.85)",
                    "default": 0.85,
                    "minimum": 0.0,
                    "maximum": 1.0
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Free-form labels for filtering"
                },
            },
            "required": ["text", "subject_entity", "relation"]
        },
        "annotations": {
            "destructive": False,
            "idempotent": True,
            "audience": ["assistant"]
        }
    },
    "okg_recall": {
        "name": "okg_recall",
        "title": "OKG Recall Memories",
        "description": (
            "Search long-term memories by semantic similarity and metadata filters. "
            "Use when you need to recall what you know about a user, topic, or relationship."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for semantic similarity"
                },
                "memory_type": {
                    "type": "string",
                    "enum": ["fact", "episodic", "semantic", "procedural", "belief"],
                    "description": "Filter by memory type"
                },
                "subject_entity": {
                    "type": "string",
                    "description": "Filter by subject entity"
                },
                "relation": {
                    "type": "string",
                    "description": "Filter by relation type"
                },
                "min_confidence": {
                    "type": "number",
                    "description": "Minimum confidence threshold (default: 0.3)",
                    "default": 0.3,
                    "minimum": 0.0,
                    "maximum": 1.0
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (1-20, default: 5)",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20
                },
            },
            "required": ["query"]
        },
        "annotations": {
            "destructive": False,
            "idempotent": True,
            "audience": ["assistant"]
        }
    },
    "okg_forget": {
        "name": "okg_forget",
        "title": "OKG Forget Memory",
        "description": (
            "Delete a specific memory by its document ID. Use when a user asks "
            "to forget something or when a stored fact is no longer valid."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {
                    "type": "string",
                    "description": "The document ID of the memory to delete (from recall results)"
                },
            },
            "required": ["doc_id"]
        },
        "annotations": {
            "destructive": True,
            "idempotent": True,
            "audience": ["assistant"]
        }
    },
}


class OKGTermMemorySkill(BaseSkill):
    """
    Ontological Knowledge Graph Term Memory — structured long-term memory
    with typed metadata (subject/relation/type/confidence).

    First multi-tool skill in Tsushin: exposes 3 separate MCP tools
    under a single skill_type registration.
    """

    skill_type = "okg_term_memory"
    skill_name = "OKG Term Memory"
    skill_description = (
        "Structured long-term memory with ontological metadata. "
        "Stores, recalls, and manages durable facts and relationships."
    )
    execution_mode = "hybrid"  # tool calls + passive post-response hook

    def __init__(self, db=None, agent_id=None):
        super().__init__()
        self._db = db
        self._agent_id = agent_id
        self._okg_service = None
        self._current_tool_name = None  # Set by SkillManager before execute_tool

    # --- Multi-tool MCP definitions ---

    @classmethod
    def get_mcp_tool_definition(cls) -> Optional[Dict[str, Any]]:
        """Return the primary tool for backward compatibility."""
        return OKG_TOOL_DEFINITIONS["okg_store"]

    @classmethod
    def get_all_mcp_tool_definitions(cls) -> List[Dict[str, Any]]:
        """Return all 3 MCP tool definitions."""
        return list(OKG_TOOL_DEFINITIONS.values())

    @classmethod
    def to_openai_tools(cls) -> List[Dict[str, Any]]:
        """Convert all MCP definitions to OpenAI format."""
        tools = []
        for mcp in cls.get_all_mcp_tool_definitions():
            tools.append({
                "type": "function",
                "function": {
                    "name": mcp["name"],
                    "description": mcp["description"],
                    "parameters": mcp["inputSchema"]
                }
            })
        return tools

    @classmethod
    def to_anthropic_tools(cls) -> List[Dict[str, Any]]:
        """Convert all MCP definitions to Anthropic format."""
        tools = []
        for mcp in cls.get_all_mcp_tool_definitions():
            tools.append({
                "name": mcp["name"],
                "description": mcp["description"],
                "input_schema": mcp["inputSchema"]
            })
        return tools

    @classmethod
    def get_sentinel_context(cls) -> Dict[str, Any]:
        return {
            "expected_intents": [
                "Store facts and preferences about users",
                "Recall stored memories and knowledge",
                "Delete outdated or incorrect memories"
            ],
            "risk_notes": (
                "Block instruction injection, identity override, credential storage, "
                "behavioral triggers. Memory operations are NEVER exempt from detection."
            )
        }

    @classmethod
    def get_sentinel_exemptions(cls) -> List[str]:
        """Memory operations are never exempt from Sentinel detection."""
        return []

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "auto_capture_enabled": {
                    "type": "boolean",
                    "title": "Auto-Capture Facts",
                    "description": "Automatically extract and store durable facts from conversations",
                    "default": False,  # Opt-in for data minimization
                },
                "auto_recall_enabled": {
                    "type": "boolean",
                    "title": "Auto-Recall Memories",
                    "description": "Automatically inject relevant memories as context on every message",
                    "default": True,
                },
                "auto_recall_limit": {
                    "type": "integer",
                    "title": "Auto-Recall Limit",
                    "description": "Max memories to inject per message",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
                "auto_recall_min_confidence": {
                    "type": "number",
                    "title": "Auto-Recall Min Confidence",
                    "description": "Minimum confidence to include in auto-recall",
                    "default": 0.3,
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "capture_min_confidence": {
                    "type": "number",
                    "title": "Capture Min Confidence",
                    "description": "Minimum fact confidence for auto-capture",
                    "default": 0.75,
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "default_merge_mode": {
                    "type": "string",
                    "title": "Default Merge Mode",
                    "description": "How to handle duplicate memories",
                    "enum": ["replace", "prepend", "merge"],
                    "default": "merge",
                },
            },
            "required": [],
        }

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        return {
            "auto_capture_enabled": False,  # Opt-in
            "auto_recall_enabled": True,
            "auto_recall_limit": 5,
            "auto_recall_min_confidence": 0.3,
            "capture_min_confidence": 0.75,
            "default_merge_mode": "merge",
        }

    def is_tool_enabled(self, config: Dict[str, Any]) -> bool:
        return True

    # --- Tool execution ---

    async def execute_tool(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any]
    ) -> SkillResult:
        """Dispatch to the correct sub-tool based on _current_tool_name."""
        tool_name = self._current_tool_name or "okg_store"

        try:
            service = self._get_service(config)

            if tool_name == "okg_store":
                return await self._execute_store(service, arguments, message, config)
            elif tool_name == "okg_recall":
                return await self._execute_recall(service, arguments, message, config)
            elif tool_name == "okg_forget":
                return await self._execute_forget(service, arguments, message, config)
            else:
                return SkillResult(
                    success=False,
                    output=f"Unknown OKG tool: {tool_name}",
                    metadata={"tool": tool_name}
                )
        except Exception as e:
            logger.error(f"OKG execute_tool error ({tool_name}): {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"OKG {tool_name} failed: {str(e)}",
                metadata={"tool": tool_name, "error": str(e)}
            )

    async def _execute_store(self, service, arguments, message, config):
        result = await service.store(
            text=arguments.get("text", ""),
            memory_type=arguments.get("memory_type", "fact"),
            subject_entity=arguments.get("subject_entity", ""),
            relation=arguments.get("relation", ""),
            confidence=float(arguments.get("confidence", 0.85)),
            tags=arguments.get("tags", []),
            user_id=message.sender_key,
            source="tool_call",
            merge_mode=arguments.get("merge_mode", "merge"),
            config=self._get_sentinel_config(config),
        )

        if result.get("blocked"):
            return SkillResult(
                success=False,
                output=f"Memory blocked by MemGuard: {result.get('reason', 'security policy')}",
                metadata=result
            )

        return SkillResult(
            success=result.get("success", False),
            output=f"Stored memory: {arguments.get('subject_entity')}/{arguments.get('relation')} "
                   f"(doc_id: {result.get('doc_id', 'unknown')}, confidence: {arguments.get('confidence', 0.85)})",
            metadata=result
        )

    async def _execute_recall(self, service, arguments, message, config):
        results = await service.recall(
            query=arguments.get("query", ""),
            memory_type=arguments.get("memory_type"),
            subject_entity=arguments.get("subject_entity"),
            relation=arguments.get("relation"),
            min_confidence=float(arguments.get("min_confidence", 0.3)),
            limit=int(arguments.get("limit", 5)),
            user_id=message.sender_key,
        )

        if not results:
            return SkillResult(
                success=True,
                output="No relevant memories found.",
                metadata={"results": [], "count": 0}
            )

        # Format as XML for LLM context
        xml_block = service.format_as_xml(results)
        return SkillResult(
            success=True,
            output=xml_block,
            metadata={"results": results, "count": len(results)}
        )

    async def _execute_forget(self, service, arguments, message, config):
        result = await service.forget(
            doc_id=arguments.get("doc_id", ""),
            user_id=message.sender_key,
        )
        return SkillResult(
            success=result.get("success", False),
            output=f"Memory {arguments.get('doc_id', '')} {'forgotten' if result.get('success') else 'not found'}.",
            metadata=result
        )

    # --- Passive hooks ---

    async def post_response_hook(
        self,
        user_message: str,
        agent_response: str,
        context: dict,
        config: dict,
        ai_client=None,
    ) -> Dict[str, Any]:
        """
        Auto-capture: extract durable facts from conversation and store as OKG memories.

        Uses existing FactExtractor infrastructure to identify facts,
        then stores each as an OKG memory with source="auto_capture".
        """
        if not config.get("auto_capture_enabled", False):
            return {"captured": 0}

        try:
            service = self._get_service(config)
            if not service:
                return {"captured": 0}

            # Use FactExtractor to find durable facts
            from agent.memory.fact_extractor import FactExtractor

            # Get provider + model_name from agent config
            provider_name = None
            model_name = None
            try:
                from models import Agent as AgentModel
                agent = self._db.query(AgentModel).filter(AgentModel.id == self._agent_id).first() if self._db else None
                if agent:
                    provider_name = agent.model_provider
                    model_name = agent.model_name
            except Exception as e:
                logger.warning(f"OKG auto-capture: failed to load agent model config: {e}")

            extractor = FactExtractor(
                ai_client=ai_client,
                provider=provider_name,
                model_name=model_name,
                db=self._db,
            )

            conversation = [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": agent_response},
            ]
            facts = await extractor.extract_facts(
                conversation=conversation,
                user_id=context.get("sender_key", ""),
                agent_id=self._agent_id,
            )

            if not facts:
                return {"captured": 0}

            min_confidence = config.get("capture_min_confidence", 0.75)
            captured = 0

            for fact in facts:
                confidence = float(fact.get("confidence", 0.5))
                if confidence < min_confidence:
                    continue

                # Map fact to OKG metadata
                await service.store(
                    text=f"{fact.get('key', '')}: {fact.get('value', '')}",
                    memory_type="fact",
                    subject_entity=f"topic:{fact.get('topic', 'general')}",
                    relation=fact.get("key", "knows"),
                    confidence=confidence,
                    user_id=context.get("sender_key", ""),
                    source="auto_capture",
                    config=self._get_sentinel_config(config),
                )
                captured += 1

            return {"captured": captured}

        except Exception as e:
            logger.warning(f"OKG auto-capture failed: {e}")
            return {"captured": 0, "error": str(e)}

    # --- Helpers ---

    def _get_service(self, config: dict):
        """Lazy-init OKG service with current config."""
        current_tenant_id = config.get("tenant_id")

        # v0.6.0 fix (Task 19): Validate cached service matches current request context
        if self._okg_service:
            if (self._okg_service.tenant_id == current_tenant_id and
                self._okg_service.agent_id == self._agent_id):
                return self._okg_service
            # Tenant/agent mismatch — invalidate cache
            self._okg_service = None

        if not self._db or not self._agent_id:
            logger.warning("OKG skill: no db or agent_id available")
            return None

        try:
            from models import Agent as AgentModel
            agent = self._db.query(AgentModel).filter(AgentModel.id == self._agent_id).first()
            tenant_id = current_tenant_id or (agent.tenant_id if agent else "")

            # Resolve vector store provider
            provider = None
            try:
                from agent.memory.providers.registry import VectorStoreRegistry
                from agent.memory.providers.resolver import VectorStoreResolver
                from agent.memory.providers.bridge import ProviderBridgeStore
                from agent.memory.embedding_service import get_shared_embedding_service

                instance_id = agent.vector_store_instance_id if agent else None
                if instance_id:
                    registry = VectorStoreRegistry()
                    resolver = VectorStoreResolver(registry)
                    resolved = resolver.resolve(
                        agent_id=self._agent_id,
                        db=self._db,
                        persist_directory=agent.chroma_db_path or "./data/chroma",
                        vector_store_instance_id=instance_id,
                        vector_store_mode=agent.vector_store_mode or "override",
                        tenant_id=tenant_id,
                    )
                    if resolved:
                        embedding_service = get_shared_embedding_service()
                        security_context = {
                            "db": self._db,
                            "tenant_id": tenant_id,
                            "agent_id": self._agent_id,
                            "instance_id": instance_id,
                        }
                        provider = ProviderBridgeStore(
                            resolved,
                            embedding_service,
                            security_context=security_context,
                        )
            except Exception as e:
                logger.warning(f"OKG: failed to resolve vector store (using None): {e}")

            from agent.memory.okg.okg_memory_service import OKGMemoryService

            self._okg_service = OKGMemoryService(
                agent_id=self._agent_id,
                db_session=self._db,
                tenant_id=tenant_id,
                vector_store_provider=provider,
            )
            return self._okg_service

        except Exception as e:
            logger.error(f"OKG service init failed: {e}", exc_info=True)
            return None

    def _get_sentinel_config(self, config: dict):
        """Get Sentinel effective config for MemGuard checks."""
        try:
            from services.sentinel_service import SentinelService
            sentinel = SentinelService(
                self._db,
                tenant_id=config.get("tenant_id"),
            )
            return sentinel.get_effective_config(agent_id=self._agent_id)
        except Exception:
            return None

    # --- BaseSkill interface ---

    async def can_handle(self, message: InboundMessage) -> bool:
        """OKG is tool-only, no keyword detection."""
        return False

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """Placeholder — OKG uses execute_tool exclusively."""
        return SkillResult(
            success=True,
            output="OKG Term Memory is available via tool calls (okg_store, okg_recall, okg_forget).",
            metadata={}
        )
