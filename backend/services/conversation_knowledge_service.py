"""
Phase 14.6: Conversation Knowledge Extraction Service
AI-powered extraction of tags, insights, and related conversations.
"""

import logging
import json
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


class ConversationKnowledgeService:
    """
    Service for extracting and managing conversation knowledge.

    Features:
    - AI-powered tag generation
    - Insight extraction (facts, conclusions, decisions, action items)
    - Related conversation discovery
    - Knowledge export
    """

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)

    async def extract_knowledge(
        self,
        thread_id: int,
        tenant_id: str,
        user_id: int,
        agent_id: int
    ) -> Dict[str, Any]:
        """
        Main orchestrator for knowledge extraction.

        Extracts tags, insights, and finds related threads.

        Args:
            thread_id: Thread ID to extract knowledge from
            tenant_id: Tenant ID
            user_id: User ID
            agent_id: Agent ID (used for LLM config)

        Returns:
            Dict with extracted tags, insights, and related threads
        """
        try:
            self.logger.info(f"[Phase 14.6] Extracting knowledge for thread {thread_id}")

            # Get thread messages
            messages = await self._get_thread_messages(thread_id, tenant_id, user_id)
            self.logger.info(f"[Phase 14.6] Retrieved {len(messages)} messages for thread {thread_id}")

            if len(messages) < 2:
                self.logger.warning(f"[Phase 14.6] Thread {thread_id} has insufficient messages ({len(messages)} < 2)")
                return {
                    "status": "error",
                    "error": "Thread must have at least 2 messages for knowledge extraction",
                    "tags": [],
                    "insights": [],
                    "related_threads": []
                }

            # Get agent configuration
            from models import Agent
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                self.logger.warning(f"[Phase 14.6] Agent {agent_id} not found")
                return {
                    "status": "error",
                    "error": "Agent not found",
                    "tags": [],
                    "insights": [],
                    "related_threads": []
                }

            # Extract tags
            tags = await self._extract_tags(messages, agent, thread_id, tenant_id, user_id)

            # Extract insights
            insights = await self._extract_insights(messages, agent, thread_id, tenant_id, user_id)

            # Find related threads
            related_threads = await self._find_related_threads(thread_id, tenant_id, user_id, agent_id)

            self.logger.info(f"[Phase 14.6] Extracted {len(tags)} tags, {len(insights)} insights, {len(related_threads)} related threads")

            return {
                "status": "success",
                "tags": tags,
                "insights": insights,
                "related_threads": related_threads,
                "extracted_at": datetime.utcnow().isoformat() + "Z"
            }

        except Exception as e:
            self.logger.error(f"Knowledge extraction failed: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "tags": [],
                "insights": [],
                "related_threads": []
            }

    async def _get_thread_messages(
        self,
        thread_id: int,
        tenant_id: str,
        user_id: int
    ) -> List[Dict[str, str]]:
        """Get all messages from a thread."""
        from models import Memory

        # Find memory record for this thread
        # sender_key pattern for playground threads: sender_playground_u{user_id}_a{agent_id}_t{thread_id}
        sender_key_pattern = f"%_t{thread_id}"

        self.logger.info(f"[Phase 14.6] Querying Memory with pattern: {sender_key_pattern}")

        memory_records = self.db.query(Memory).filter(
            Memory.sender_key.like(sender_key_pattern)
        ).all()

        self.logger.info(f"[Phase 14.6] Found {len(memory_records)} memory records for thread {thread_id}")
        for mem in memory_records:
            self.logger.info(f"[Phase 14.6] Memory record: sender_key={mem.sender_key}, messages_json_length={len(mem.messages_json) if mem.messages_json else 0}")

        messages = []
        for mem in memory_records:
            try:
                # messages_json is already deserialized by SQLAlchemy (JSON type)
                msgs = mem.messages_json if mem.messages_json else []
                if isinstance(msgs, str):
                    # If it's still a string, parse it
                    msgs = json.loads(msgs)
                messages.extend(msgs)
            except Exception as e:
                self.logger.warning(f"[Phase 14.6] Failed to parse messages_json: {e}")
                continue

        return messages

    async def _extract_tags(
        self,
        messages: List[Dict],
        agent: Any,
        thread_id: int,
        tenant_id: str,
        user_id: int
    ) -> List[Dict[str, Any]]:
        """
        Extract tags using LLM.

        Uses the agent's configured LLM to generate topical tags.
        """
        try:
            # Build conversation text
            conversation_text = self._format_messages_for_llm(messages, max_messages=30)

            # Build prompt
            prompt = f"""Analyze the following conversation and generate 3-5 concise tags that capture the main topics discussed.

Conversation:
{conversation_text}

Return ONLY a JSON array of tags (lowercase, hyphen-separated, no spaces):
["tag-1", "tag-2", "tag-3"]

Do not include any explanation, only the JSON array."""

            # Call LLM
            llm_response = await self._call_agent_llm(agent, prompt)
            self.logger.info(f"[Phase 14.6] LLM response for tags (full): {llm_response}")

            # Parse response
            tags_list = self._parse_json_response(llm_response)
            self.logger.info(f"[Phase 14.6] Parsed tags list: {tags_list}")

            if not isinstance(tags_list, list):
                self.logger.warning("LLM returned non-list for tags")
                tags_list = []

            # Store tags in database
            from models import ConversationTag

            # Delete existing AI-generated tags
            self.db.query(ConversationTag).filter(
                ConversationTag.thread_id == thread_id,
                ConversationTag.source == 'ai'
            ).delete()

            # Color palette for tags
            colors = ["blue", "green", "purple", "orange", "pink", "cyan", "yellow", "red"]

            stored_tags = []
            for idx, tag in enumerate(tags_list[:5]):  # Limit to 5 tags
                if isinstance(tag, str) and tag:
                    tag_obj = ConversationTag(
                        thread_id=thread_id,
                        tag=tag.lower(),
                        source='ai',
                        color=colors[idx % len(colors)],
                        tenant_id=tenant_id,
                        user_id=user_id
                    )
                    self.db.add(tag_obj)
                    self.db.flush()

                    stored_tags.append({
                        "id": tag_obj.id,
                        "tag": tag_obj.tag,
                        "color": tag_obj.color,
                        "source": tag_obj.source
                    })

            self.db.commit()
            return stored_tags

        except Exception as e:
            self.logger.error(f"Tag extraction failed: {e}")
            self.db.rollback()
            return []

    async def _extract_insights(
        self,
        messages: List[Dict],
        agent: Any,
        thread_id: int,
        tenant_id: str,
        user_id: int
    ) -> List[Dict[str, Any]]:
        """
        Extract insights using LLM.

        Identifies facts, conclusions, decisions, and action items.
        """
        try:
            # Build conversation text
            conversation_text = self._format_messages_for_llm(messages, max_messages=50)

            # Build prompt
            prompt = f"""Analyze this conversation and extract key insights.

For each insight, provide:
- insight_text: The actual insight (1-2 sentences)
- insight_type: One of [fact, conclusion, decision, action_item, question]
- confidence: Your confidence (0.0-1.0)

Conversation:
{conversation_text}

Return ONLY a JSON array (3-7 insights):
[{{"insight_text": "...", "insight_type": "fact", "confidence": 0.9}}]

Do not include any explanation, only the JSON array."""

            # Call LLM
            llm_response = await self._call_agent_llm(agent, prompt)
            self.logger.info(f"[Phase 14.6] LLM response for insights (full): {llm_response}")

            # Parse response
            insights_list = self._parse_json_response(llm_response)
            self.logger.info(f"[Phase 14.6] Parsed insights list (count={len(insights_list) if isinstance(insights_list, list) else 0})")

            if not isinstance(insights_list, list):
                self.logger.warning("LLM returned non-list for insights")
                insights_list = []

            # Store insights in database
            from models import ConversationInsight

            # Delete existing insights
            self.db.query(ConversationInsight).filter(
                ConversationInsight.thread_id == thread_id
            ).delete()

            stored_insights = []
            for insight_data in insights_list[:7]:  # Limit to 7 insights
                if not isinstance(insight_data, dict):
                    continue

                insight_text = insight_data.get('insight_text', '')
                insight_type = insight_data.get('insight_type', 'fact')
                confidence = insight_data.get('confidence', 0.5)

                if insight_text and insight_type in ['fact', 'conclusion', 'decision', 'action_item', 'question']:
                    insight_obj = ConversationInsight(
                        thread_id=thread_id,
                        insight_text=insight_text,
                        insight_type=insight_type,
                        confidence=float(confidence),
                        tenant_id=tenant_id,
                        user_id=user_id
                    )
                    self.db.add(insight_obj)
                    self.db.flush()

                    stored_insights.append({
                        "id": insight_obj.id,
                        "insight_text": insight_obj.insight_text,
                        "insight_type": insight_obj.insight_type,
                        "confidence": insight_obj.confidence
                    })

            self.db.commit()
            return stored_insights

        except Exception as e:
            self.logger.error(f"Insight extraction failed: {e}")
            self.db.rollback()
            return []

    async def _find_related_threads(
        self,
        thread_id: int,
        tenant_id: str,
        user_id: int,
        agent_id: int,
        limit: int = 5,
        min_similarity: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Find related conversation threads using semantic similarity.

        Uses ChromaDB to find threads with similar content.
        """
        try:
            from models import ConversationThread, ConversationLink

            # Get current thread's messages
            messages = await self._get_thread_messages(thread_id, tenant_id, user_id)

            if not messages:
                return []

            # Create query from recent messages
            recent_messages = messages[-10:] if len(messages) > 10 else messages
            query_text = " ".join([msg.get('content', '') for msg in recent_messages])

            # Search using semantic search service
            from services.conversation_search_service import ConversationSearchService
            search_service = ConversationSearchService(self.db)

            semantic_results = search_service.search_semantic(
                query=query_text,
                tenant_id=tenant_id,
                user_id=user_id,
                agent_id=agent_id,
                limit=limit + 1,  # +1 because we'll filter out current thread
                min_similarity=min_similarity
            )

            # Filter out current thread and format results
            related = []
            for result in semantic_results.get('results', []):
                result_thread_id = result.get('thread_id')
                if result_thread_id and result_thread_id != thread_id:
                    # Get thread info
                    thread = self.db.query(ConversationThread).filter(
                        ConversationThread.id == result_thread_id
                    ).first()

                    if thread:
                        related.append({
                            "thread_id": result_thread_id,
                            "thread_title": thread.title,
                            "confidence": result.get('similarity', 0.0),
                            "relationship_type": "related"
                        })

            # Store links in database
            # Delete existing links
            self.db.query(ConversationLink).filter(
                ConversationLink.source_thread_id == thread_id
            ).delete()

            for rel in related[:limit]:
                link_obj = ConversationLink(
                    source_thread_id=thread_id,
                    target_thread_id=rel['thread_id'],
                    relationship_type='related',
                    confidence=rel['confidence'],
                    tenant_id=tenant_id,
                    user_id=user_id
                )
                self.db.add(link_obj)

            self.db.commit()

            return related[:limit]

        except Exception as e:
            self.logger.error(f"Failed to find related threads: {e}")
            self.db.rollback()
            return []

    def _format_messages_for_llm(self, messages: List[Dict], max_messages: int = 50) -> str:
        """Format messages as readable text for LLM."""
        # Take most recent messages
        recent = messages[-max_messages:] if len(messages) > max_messages else messages

        lines = []
        for msg in recent:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            lines.append(f"{role.capitalize()}: {content}")

        return "\n".join(lines)

    async def _call_agent_llm(self, agent: Any, prompt: str) -> str:
        """
        Call the agent's configured LLM.

        Uses the agent's model provider and settings.
        """
        try:
            from agent.ai_client import AIClient

            client = AIClient(
                provider=agent.model_provider,
                model_name=agent.model_name
            )

            # Call LLM with simple prompt
            response = await client.generate(
                system_prompt="You are an expert at extracting structured knowledge from conversations.",
                user_message=prompt,
                operation_type="knowledge_extraction"
            )

            # AIClient returns a dict with 'answer' key
            return response.get('answer', '[]')

        except Exception as e:
            self.logger.error(f"LLM call failed: {e}", exc_info=True)
            return "[]"  # Return empty JSON array as fallback

    def _parse_json_response(self, response: str) -> Any:
        """Parse JSON from LLM response, handling markdown code blocks."""
        # Remove markdown code blocks if present
        response = response.strip()

        # Try to find JSON array or object
        json_match = re.search(r'[\[\{].*[\]\}]', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        # Try parsing the whole response
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            self.logger.warning(f"Failed to parse JSON from LLM response: {response[:200]}")
            return []

    def get_thread_knowledge(
        self,
        thread_id: int,
        tenant_id: str,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Get all extracted knowledge for a thread.

        Returns tags, insights, and related threads.
        """
        try:
            from models import ConversationTag, ConversationInsight, ConversationLink, ConversationThread

            # Get tags
            tags = self.db.query(ConversationTag).filter(
                ConversationTag.thread_id == thread_id,
                ConversationTag.tenant_id == tenant_id,
                ConversationTag.user_id == user_id
            ).all()

            # Get insights
            insights = self.db.query(ConversationInsight).filter(
                ConversationInsight.thread_id == thread_id,
                ConversationInsight.tenant_id == tenant_id,
                ConversationInsight.user_id == user_id
            ).all()

            # Get related threads
            links = self.db.query(ConversationLink, ConversationThread).join(
                ConversationThread,
                ConversationLink.target_thread_id == ConversationThread.id
            ).filter(
                ConversationLink.source_thread_id == thread_id,
                ConversationLink.tenant_id == tenant_id
            ).all()

            return {
                "status": "success",
                "tags": [{
                    "id": t.id,
                    "tag": t.tag,
                    "color": t.color,
                    "source": t.source
                } for t in tags],
                "insights": [{
                    "id": i.id,
                    "insight_text": i.insight_text,
                    "insight_type": i.insight_type,
                    "confidence": i.confidence
                } for i in insights],
                "related_threads": [{
                    "link_id": link.id,
                    "thread_id": link.target_thread_id,
                    "thread_title": thread.title,
                    "confidence": link.confidence,
                    "relationship_type": link.relationship_type
                } for link, thread in links]
            }

        except Exception as e:
            self.logger.error(f"Failed to get thread knowledge: {e}")
            return {
                "status": "error",
                "error": str(e),
                "tags": [],
                "insights": [],
                "related_threads": []
            }

    def update_tag(
        self,
        tag_id: int,
        tenant_id: str,
        user_id: int,
        new_tag: Optional[str] = None,
        new_color: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update a tag."""
        try:
            from models import ConversationTag

            tag = self.db.query(ConversationTag).filter(
                ConversationTag.id == tag_id,
                ConversationTag.tenant_id == tenant_id,
                ConversationTag.user_id == user_id
            ).first()

            if not tag:
                return {"status": "error", "error": "Tag not found"}

            if new_tag:
                tag.tag = new_tag.lower()
                tag.source = 'user'  # Mark as user-edited

            if new_color:
                tag.color = new_color

            self.db.commit()

            return {
                "status": "success",
                "tag": {
                    "id": tag.id,
                    "tag": tag.tag,
                    "color": tag.color,
                    "source": tag.source
                }
            }

        except Exception as e:
            self.logger.error(f"Failed to update tag: {e}")
            self.db.rollback()
            return {"status": "error", "error": str(e)}

    def delete_tag(
        self,
        tag_id: int,
        tenant_id: str,
        user_id: int
    ) -> Dict[str, Any]:
        """Delete a tag."""
        try:
            from models import ConversationTag

            result = self.db.query(ConversationTag).filter(
                ConversationTag.id == tag_id,
                ConversationTag.tenant_id == tenant_id,
                ConversationTag.user_id == user_id
            ).delete()

            self.db.commit()

            if result > 0:
                return {"status": "success"}
            else:
                return {"status": "error", "error": "Tag not found"}

        except Exception as e:
            self.logger.error(f"Failed to delete tag: {e}")
            self.db.rollback()
            return {"status": "error", "error": str(e)}

    def update_insight(
        self,
        insight_id: int,
        tenant_id: str,
        user_id: int,
        new_text: Optional[str] = None,
        new_type: Optional[str] = None,
        new_confidence: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Update an insight.

        Args:
            insight_id: Insight ID to update
            tenant_id: Tenant ID
            user_id: User ID
            new_text: New insight text (optional)
            new_type: New insight type (optional)
            new_confidence: New confidence score (optional)

        Returns:
            Dict with updated insight or error
        """
        try:
            from models import ConversationInsight

            # Valid insight types
            valid_types = ['fact', 'conclusion', 'decision', 'action_item', 'question']

            # Query insight with tenant/user verification
            insight = self.db.query(ConversationInsight).filter(
                ConversationInsight.id == insight_id,
                ConversationInsight.tenant_id == tenant_id,
                ConversationInsight.user_id == user_id
            ).first()

            if not insight:
                return {"status": "error", "error": "Insight not found"}

            # Update fields
            if new_text is not None:
                insight.insight_text = new_text

            if new_type is not None:
                if new_type not in valid_types:
                    return {"status": "error", "error": f"Invalid insight type. Must be one of: {', '.join(valid_types)}"}
                insight.insight_type = new_type

            if new_confidence is not None:
                # Validate confidence range
                if not 0.0 <= new_confidence <= 1.0:
                    return {"status": "error", "error": "Confidence must be between 0.0 and 1.0"}
                insight.confidence = float(new_confidence)

            self.db.commit()

            return {
                "status": "success",
                "insight": {
                    "id": insight.id,
                    "insight_text": insight.insight_text,
                    "insight_type": insight.insight_type,
                    "confidence": insight.confidence
                }
            }

        except Exception as e:
            self.logger.error(f"Failed to update insight: {e}")
            self.db.rollback()
            return {"status": "error", "error": str(e)}

    def delete_insight(
        self,
        insight_id: int,
        tenant_id: str,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Delete an insight.

        Args:
            insight_id: Insight ID to delete
            tenant_id: Tenant ID
            user_id: User ID

        Returns:
            Dict with success or error status
        """
        try:
            from models import ConversationInsight

            # Delete with tenant/user verification
            result = self.db.query(ConversationInsight).filter(
                ConversationInsight.id == insight_id,
                ConversationInsight.tenant_id == tenant_id,
                ConversationInsight.user_id == user_id
            ).delete()

            self.db.commit()

            if result > 0:
                return {"status": "success"}
            else:
                return {"status": "error", "error": "Insight not found"}

        except Exception as e:
            self.logger.error(f"Failed to delete insight: {e}")
            self.db.rollback()
            return {"status": "error", "error": str(e)}

    def delete_conversation_link(
        self,
        link_id: int,
        tenant_id: str,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Remove a conversation thread relationship.

        Args:
            link_id: Link ID to delete
            tenant_id: Tenant ID
            user_id: User ID

        Returns:
            Dict with success or error status
        """
        try:
            from models import ConversationLink

            # Delete with tenant/user verification
            result = self.db.query(ConversationLink).filter(
                ConversationLink.id == link_id,
                ConversationLink.tenant_id == tenant_id,
                ConversationLink.user_id == user_id
            ).delete()

            self.db.commit()

            if result > 0:
                return {"status": "success"}
            else:
                return {"status": "error", "error": "Link not found"}

        except Exception as e:
            self.logger.error(f"Failed to delete conversation link: {e}")
            self.db.rollback()
            return {"status": "error", "error": str(e)}

    def export_knowledge(
        self,
        thread_id: int,
        tenant_id: str,
        user_id: int,
        format: str = "json"
    ) -> Dict[str, Any]:
        """
        Export thread knowledge as JSON or Markdown.

        Args:
            thread_id: Thread ID
            tenant_id: Tenant ID
            user_id: User ID
            format: Export format ('json' or 'markdown')

        Returns:
            Dict with export data
        """
        try:
            knowledge = self.get_thread_knowledge(thread_id, tenant_id, user_id)

            if format == "markdown":
                # Format as markdown
                md = f"# Thread Knowledge Export\n\n"
                md += f"**Thread ID:** {thread_id}\n"
                md += f"**Exported:** {datetime.utcnow().isoformat() + 'Z'}\n\n"

                md += "## Tags\n\n"
                for tag in knowledge['tags']:
                    md += f"- `{tag['tag']}` ({tag['source']})\n"

                md += "\n## Insights\n\n"
                for insight in knowledge['insights']:
                    icon = {
                        'fact': '💡',
                        'conclusion': '📊',
                        'decision': '✅',
                        'action_item': '📌',
                        'question': '❓'
                    }.get(insight['insight_type'], '•')
                    md += f"{icon} **{insight['insight_type'].title()}** (confidence: {insight['confidence']:.2f})\n"
                    md += f"  {insight['insight_text']}\n\n"

                md += "## Related Threads\n\n"
                for rel in knowledge['related_threads']:
                    md += f"- [{rel['thread_title']}] (similarity: {rel['confidence']:.2f})\n"

                return {
                    "status": "success",
                    "format": "markdown",
                    "content": md
                }

            else:
                # Return as JSON
                return {
                    "status": "success",
                    "format": "json",
                    "content": knowledge
                }

        except Exception as e:
            self.logger.error(f"Failed to export knowledge: {e}")
            return {"status": "error", "error": str(e)}
