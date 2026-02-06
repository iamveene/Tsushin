"""
Task 3: Knowledge Sharing Skill

Automatically extracts and shares factual knowledge across agents while maintaining
personality isolation. Supports both fact extraction from conversations and group
context summarization.

Key Features:
- AI-powered fact extraction from conversation turns
- Group conversation summarization for cross-agent context awareness
- Permission-based sharing via Layer 4 (SharedMemoryPool)
- Personality isolation (only facts shared, not conversational style)
- Post-response hook pattern (non-blocking)
"""

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

from agent.skills.base import BaseSkill, InboundMessage, SkillResult
from agent.memory.shared_memory_pool import SharedMemoryPool
from agent.ai_client import AIClient


class KnowledgeSharingSkill(BaseSkill):
    """
    Knowledge Sharing Skill - Extracts and shares factual knowledge across agents.

    This skill operates as a post-response hook, running after the agent generates
    a response. It extracts factual statements and group context summaries, then
    shares them to Layer 4 (SharedMemoryPool) for other agents to access.

    Workflow:
    1. Agent processes message and generates response
    2. KnowledgeSharingSkill.post_response_hook() triggered
    3. Extract facts from conversation turn
    4. If group message: Extract group context summary
    5. Share facts and summaries to Layer 4 with metadata
    6. Other agents query Layer 4 during context building
    """

    skill_type = "knowledge_sharing"
    skill_name = "Knowledge Sharing"
    skill_description = (
        "Automatically extract and share factual knowledge with other agents. "
        "Enables cross-agent learning while maintaining personality isolation. "
        "Supports fact extraction and group context summarization."
    )
    execution_mode = "passive"  # Post-response hook for fact sharing

    def __init__(self, db_session, agent_id: int):
        """
        Initialize Knowledge Sharing Skill.

        Args:
            db_session: Database session for accessing SharedMemoryPool
            agent_id: ID of the agent using this skill
        """
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.db = db_session
        self.agent_id = agent_id
        self.shared_memory_pool = SharedMemoryPool(db_session)
        self.ai_client = None  # Will be initialized with agent's AI client

    async def can_handle(self, message: InboundMessage) -> bool:
        """
        Knowledge sharing is a post-response skill, not a pre-processing skill.

        Returns:
            False - This skill doesn't pre-process messages
        """
        return False

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Not used for knowledge sharing (post-response skill).

        The actual work happens in post_response_hook() which is called after
        the agent generates a response.
        """
        return SkillResult(
            success=True,
            output="Knowledge sharing is a post-response skill",
            metadata={"passive": True}
        )

    async def post_response_hook(
        self,
        user_message: str,
        agent_response: str,
        context: Dict[str, Any],
        config: Dict[str, Any],
        ai_client: AIClient
    ) -> Dict[str, Any]:
        """
        Post-response hook - Called after agent generates response.

        Extracts facts and group context, then shares to Layer 4.

        Args:
            user_message: User's message text
            agent_response: Agent's response text
            context: Conversation context (sender, chat_id, is_group, etc.)
            config: Skill configuration
            ai_client: AI client for fact extraction

        Returns:
            Dict with extraction results and statistics
        """
        self.ai_client = ai_client

        try:
            results = {
                "facts_extracted": 0,
                "facts_shared": 0,
                "group_summaries_extracted": 0,
                "group_summaries_shared": 0,
                "errors": []
            }

            # Step 1: Extract facts from conversation turn
            if config.get("auto_extract", True):
                facts = await self._extract_facts(
                    user_message=user_message,
                    agent_response=agent_response,
                    context=context,
                    config=config
                )

                results["facts_extracted"] = len(facts)

                # Share facts to Layer 4
                if config.get("auto_share", True):
                    shared_count = await self._share_facts(facts, config)
                    results["facts_shared"] = shared_count

            # Step 2: Extract and share group context (if group message)
            if context.get("is_group") and config.get("share_group_context", True):
                summaries = await self._extract_group_context(context, config)
                results["group_summaries_extracted"] = len(summaries)

                if summaries:
                    shared_count = await self._share_group_context(summaries, context, config)
                    results["group_summaries_shared"] = shared_count

            self.logger.info(
                f"Knowledge sharing completed: {results['facts_shared']} facts, "
                f"{results['group_summaries_shared']} summaries shared"
            )

            return results

        except Exception as e:
            self.logger.error(f"Knowledge sharing failed: {e}", exc_info=True)
            return {
                "facts_extracted": 0,
                "facts_shared": 0,
                "group_summaries_extracted": 0,
                "group_summaries_shared": 0,
                "errors": [str(e)]
            }

    async def _extract_facts(
        self,
        user_message: str,
        agent_response: str,
        context: Dict[str, Any],
        config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Use AI to extract factual statements from conversation turn.

        Args:
            user_message: User's message
            agent_response: Agent's response
            context: Conversation context
            config: Skill configuration

        Returns:
            List of extracted facts with confidence scores
        """
        try:
            # Build fact extraction prompt
            prompt = self._build_fact_extraction_prompt(
                user_message=user_message,
                agent_response=agent_response,
                context=context,
                config=config
            )

            # Call AI for fact extraction
            system_prompt = "You are a fact extraction expert. Extract only factual statements, not conversational style or tone."
            response = await self.ai_client.generate(
                system_prompt=system_prompt,
                user_message=prompt
            )

            # Extract answer from response dict
            answer = response.get("answer", "")

            # Parse facts from AI response
            facts = self._parse_facts_response(answer)

            # Filter by confidence threshold
            min_confidence = config.get("min_confidence", 0.7)
            filtered_facts = [
                fact for fact in facts
                if fact.get("confidence", 0.0) >= min_confidence
            ]

            self.logger.info(f"Extracted {len(filtered_facts)} facts (from {len(facts)} total)")

            return filtered_facts

        except Exception as e:
            self.logger.error(f"Fact extraction failed: {e}")
            return []

    def _build_fact_extraction_prompt(
        self,
        user_message: str,
        agent_response: str,
        context: Dict[str, Any],
        config: Dict[str, Any]
    ) -> str:
        """
        Build AI prompt for fact extraction.

        Returns:
            Fact extraction prompt
        """
        topics = config.get("topics", [
            "user_preferences",
            "factual_information",
            "event_details",
            "personal_information"
        ])

        exclude_topics = config.get("exclude_topics", [
            "personal_secrets",
            "sensitive_information"
        ])

        prompt = f"""Analyze this conversation turn and extract ONLY factual statements.

USER MESSAGE:
{user_message}

AGENT RESPONSE:
{agent_response}

INSTRUCTIONS:
1. Extract only factual statements (preferences, events, personal info, etc.)
2. DO NOT extract conversational style, tone, greetings, or pleasantries
3. DO NOT extract opinions unless they're stated as facts about preferences
4. Each fact should be a complete, standalone statement
5. Categorize each fact by topic: {', '.join(topics)}
6. Exclude these topics: {', '.join(exclude_topics)}
7. Assign confidence score (0.0-1.0) based on how clearly stated the fact is

OUTPUT FORMAT (JSON):
[
  {{
    "content": "User likes churrascos with picanha",
    "topic": "user_preferences",
    "confidence": 0.9
  }},
  {{
    "content": "User is planning trip to Italy in March 2026",
    "topic": "event_details",
    "confidence": 0.95
  }}
]

Extract facts now (return empty array [] if no facts found):"""

        return prompt

    def _parse_facts_response(self, response: str) -> List[Dict[str, Any]]:
        """
        Parse AI response into structured facts list.

        Args:
            response: AI response text

        Returns:
            List of fact dictionaries
        """
        try:
            # Try to extract JSON from response
            response = response.strip()

            # Find JSON array in response
            start_idx = response.find('[')
            end_idx = response.rfind(']')

            if start_idx == -1 or end_idx == -1:
                self.logger.warning("No JSON array found in fact extraction response")
                return []

            json_str = response[start_idx:end_idx + 1]
            facts = json.loads(json_str)

            # Validate structure
            valid_facts = []
            for fact in facts:
                if isinstance(fact, dict) and "content" in fact:
                    # Ensure required fields
                    valid_facts.append({
                        "content": fact["content"],
                        "topic": fact.get("topic", "uncategorized"),
                        "confidence": float(fact.get("confidence", 0.8))
                    })

            return valid_facts

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse facts JSON: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error parsing facts: {e}")
            return []

    async def _share_facts(
        self,
        facts: List[Dict[str, Any]],
        config: Dict[str, Any]
    ) -> int:
        """
        Share extracted facts to Layer 4 (SharedMemoryPool).

        Args:
            facts: List of extracted facts
            config: Skill configuration

        Returns:
            Number of facts successfully shared
        """
        shared_count = 0
        access_level = config.get("access_level", "public")

        for fact in facts:
            try:
                success = self.shared_memory_pool.share_knowledge(
                    agent_id=self.agent_id,
                    content=fact["content"],
                    topic=fact["topic"],
                    access_level=access_level,
                    metadata={
                        "confidence": fact["confidence"],
                        "extracted_at": datetime.utcnow().isoformat() + "Z",
                        "extraction_method": "ai_fact_extraction"
                    }
                )

                if success:
                    shared_count += 1

            except Exception as e:
                self.logger.error(f"Failed to share fact: {e}")

        return shared_count

    async def _extract_group_context(
        self,
        context: Dict[str, Any],
        config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract summaries from group conversation for cross-agent context awareness.

        Args:
            context: Conversation context (includes chat_id, recent_messages, etc.)
            config: Skill configuration

        Returns:
            List of group context summaries
        """
        try:
            # Get recent group messages for context
            recent_messages = context.get("recent_messages", [])
            context_window = config.get("group_context_window", 20)

            # Limit to context window
            messages_to_analyze = recent_messages[-context_window:] if len(recent_messages) > context_window else recent_messages

            if len(messages_to_analyze) < 3:
                # Not enough messages for meaningful summarization
                return []

            # Format messages for AI analysis
            conversation_text = self._format_messages_for_analysis(messages_to_analyze)

            # Build summarization prompt
            prompt = self._build_group_context_prompt(conversation_text, config)

            # Call AI for summarization
            system_prompt = "You are a conversation summarization expert. Extract high-level summaries of group discussions."
            response = await self.ai_client.generate(
                system_prompt=system_prompt,
                user_message=prompt
            )

            # Extract answer from response dict
            answer = response.get("answer", "")

            # Parse summaries
            summaries = self._parse_summaries_response(answer)

            self.logger.info(f"Extracted {len(summaries)} group context summaries")

            return summaries

        except Exception as e:
            self.logger.error(f"Group context extraction failed: {e}")
            return []

    def _format_messages_for_analysis(self, messages: List[Dict]) -> str:
        """
        Format recent messages for AI analysis.

        Args:
            messages: List of recent messages

        Returns:
            Formatted conversation text
        """
        formatted = []
        for msg in messages:
            sender = msg.get("sender_name", msg.get("sender", "Unknown"))
            content = msg.get("body", msg.get("content", ""))
            formatted.append(f"{sender}: {content}")

        return "\n".join(formatted)

    def _build_group_context_prompt(self, conversation_text: str, config: Dict[str, Any]) -> str:
        """
        Build AI prompt for group context summarization.

        Returns:
            Summarization prompt
        """
        relevant_topics = config.get("group_context_topics", [
            "travel_plans",
            "event_scheduling",
            "shared_interests",
            "group_activities",
            "important_decisions"
        ])

        prompt = f"""Analyze this group conversation and extract high-level summaries of key topics.

CONVERSATION:
{conversation_text}

INSTRUCTIONS:
1. Extract ONLY factual summaries of what the group is discussing
2. Focus on these topics: {', '.join(relevant_topics)}
3. DO NOT include conversational style, greetings, or small talk
4. DO NOT include personal opinions (only facts about plans/decisions)
5. Each summary should be 1-2 sentences
6. Include participants involved in each topic

OUTPUT FORMAT (JSON):
[
  {{
    "content": "Group discussing Italy trip - Planning to visit Rome and Coliseum in March 2026",
    "topic": "travel_plans",
    "participants": ["Alice", "Agent1"]
  }},
  {{
    "content": "Group planning barbecue meetup this weekend at Alice's place",
    "topic": "group_activities",
    "participants": ["Alice", "Agent1", "Bob"]
  }}
]

Extract summaries now (return empty array [] if no relevant topics found):"""

        return prompt

    def _parse_summaries_response(self, response: str) -> List[Dict[str, Any]]:
        """
        Parse AI response into structured summaries list.

        Args:
            response: AI response text

        Returns:
            List of summary dictionaries
        """
        try:
            # Try to extract JSON from response
            response = response.strip()

            # Find JSON array in response
            start_idx = response.find('[')
            end_idx = response.rfind(']')

            if start_idx == -1 or end_idx == -1:
                self.logger.warning("No JSON array found in summarization response")
                return []

            json_str = response[start_idx:end_idx + 1]
            summaries = json.loads(json_str)

            # Validate structure
            valid_summaries = []
            for summary in summaries:
                if isinstance(summary, dict) and "content" in summary:
                    valid_summaries.append({
                        "content": summary["content"],
                        "topic": summary.get("topic", "group_context"),
                        "participants": summary.get("participants", [])
                    })

            return valid_summaries

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse summaries JSON: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error parsing summaries: {e}")
            return []

    async def _share_group_context(
        self,
        summaries: List[Dict[str, Any]],
        context: Dict[str, Any],
        config: Dict[str, Any]
    ) -> int:
        """
        Share group context summaries to Layer 4.

        Args:
            summaries: List of group context summaries
            context: Conversation context
            config: Skill configuration

        Returns:
            Number of summaries successfully shared
        """
        shared_count = 0
        access_level = config.get("access_level", "public")
        chat_id = context.get("chat_id", "unknown")

        for summary in summaries:
            try:
                success = self.shared_memory_pool.share_knowledge(
                    agent_id=self.agent_id,
                    content=summary["content"],
                    topic="group_context",
                    access_level=access_level,
                    metadata={
                        "chat_id": chat_id,
                        "participants": summary.get("participants", []),
                        "summary_topic": summary.get("topic", "general"),
                        "extracted_at": datetime.utcnow().isoformat() + "Z",
                        "extraction_method": "group_context_summarization"
                    }
                )

                if success:
                    shared_count += 1

            except Exception as e:
                self.logger.error(f"Failed to share group context: {e}")

        return shared_count

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Default configuration for knowledge sharing skill.

        Returns:
            Dict with default settings
        """
        return {
            # Fact extraction
            "auto_extract": True,
            "auto_share": True,
            "access_level": "public",  # "public" | "restricted" | "private"
            "min_confidence": 0.7,
            "topics": [
                "user_preferences",
                "factual_information",
                "event_details",
                "personal_information"
            ],
            "exclude_topics": [
                "personal_secrets",
                "sensitive_information"
            ],

            # Group context sharing
            "share_group_context": True,
            "group_context_window": 20,  # Analyze last 20 messages
            "group_context_topics": [
                "travel_plans",
                "event_scheduling",
                "shared_interests",
                "group_activities",
                "important_decisions"
            ]
        }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        JSON schema for configuration validation (for UI).

        Returns:
            Schema for UI form generation
        """
        return {
            "type": "object",
            "properties": {
                "auto_extract": {
                    "type": "boolean",
                    "default": True,
                    "description": "Automatically extract facts from conversations"
                },
                "auto_share": {
                    "type": "boolean",
                    "default": True,
                    "description": "Automatically share extracted facts with other agents"
                },
                "access_level": {
                    "type": "string",
                    "enum": ["public", "restricted", "private"],
                    "default": "public",
                    "description": "Who can access shared knowledge (public = all agents)"
                },
                "min_confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.7,
                    "description": "Minimum confidence threshold for fact extraction (0.0-1.0)"
                },
                "share_group_context": {
                    "type": "boolean",
                    "default": True,
                    "description": "Share group conversation summaries with other agents"
                },
                "group_context_window": {
                    "type": "integer",
                    "minimum": 5,
                    "maximum": 50,
                    "default": 20,
                    "description": "Number of recent messages to analyze for group context"
                }
            },
            "required": []
        }
