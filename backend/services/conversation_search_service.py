"""
Phase 14.5: Conversation Search Service
Provides full-text and semantic search across playground conversations.
"""

import logging
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


class ConversationSearchService:
    """
    Service for searching playground conversations.

    Supports:
    - Full-text search (SQLite FTS5)
    - Semantic search (ChromaDB)
    - Combined/hybrid search
    - Advanced filters (agent, thread, date range)
    """

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)
        self._fts5_available = None

    def _check_fts5_available(self) -> bool:
        """Check if FTS5 is available in SQLite."""
        if self._fts5_available is None:
            try:
                result = self.db.execute(text("PRAGMA compile_options;")).fetchall()
                self._fts5_available = any('FTS5' in str(row[0]) for row in result)
            except:
                self._fts5_available = False
        return self._fts5_available

    def search_full_text(
        self,
        query: str,
        tenant_id: str,
        user_id: int,
        agent_id: Optional[int] = None,
        thread_id: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        role: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        include_tool_results: bool = True
    ) -> Dict[str, Any]:
        """
        Full-text search using SQLite FTS5.

        Args:
            query: Search query
            tenant_id: Tenant ID for filtering
            user_id: User ID for filtering
            agent_id: Optional agent filter
            thread_id: Optional thread filter
            date_from: Optional start date (ISO format)
            date_to: Optional end date (ISO format)
            role: Optional role filter ('user' or 'assistant')
            limit: Max results
            offset: Pagination offset
            include_tool_results: Whether to include tool execution results

        Returns:
            Dict with results, total count, and metadata
        """
        try:
            result = None

            # Try FTS5 first if available
            if self._check_fts5_available():
                result = self._search_fts5(
                    query, tenant_id, user_id, agent_id, thread_id,
                    date_from, date_to, role, limit, offset
                )

                # Fall back to LIKE search if FTS5 returns no results
                # This handles cases where FTS5 table exists but isn't populated
                if result.get("total", 0) == 0:
                    self.logger.debug("FTS5 returned no results, falling back to LIKE search")
                    result = self._search_like(
                        query, tenant_id, user_id, agent_id, thread_id,
                        date_from, date_to, role, limit, offset
                    )
                    if result.get("total", 0) > 0:
                        result["search_mode"] = "like_fallback"
            else:
                result = self._search_like(
                    query, tenant_id, user_id, agent_id, thread_id,
                    date_from, date_to, role, limit, offset
                )

            # Include tool execution results if requested
            if include_tool_results and result.get("status") == "success":
                tool_results = self.search_tool_executions(
                    query, tenant_id, user_id, agent_id, limit=5
                )
                if tool_results:
                    # Merge tool results with message results
                    result["results"] = result.get("results", []) + tool_results
                    result["total"] = result.get("total", 0) + len(tool_results)
                    result["tool_results_count"] = len(tool_results)

            return result
        except Exception as e:
            self.logger.error(f"Full-text search failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "results": [],
                "total": 0
            }

    # MED-003 Security Fix: Whitelist of allowed FTS5 filter columns
    # Only these columns can be used in WHERE clause construction
    _FTS5_ALLOWED_FILTERS = frozenset({
        "tenant_id", "user_id", "agent_id", "thread_id",
        "timestamp", "role"
    })

    def _build_fts5_filter(
        self,
        filter_name: str,
        operator: str,
        param_name: str
    ) -> Optional[str]:
        """
        Build a single FTS5 filter clause safely.

        MED-003 Security Fix: Uses whitelist validation to prevent SQL injection
        through dynamic WHERE clause construction.

        Args:
            filter_name: Column name (must be in _FTS5_ALLOWED_FILTERS)
            operator: SQL operator (validated against whitelist)
            param_name: Parameter placeholder name

        Returns:
            SQL clause string or None if validation fails
        """
        # Validate column name against whitelist
        if filter_name not in self._FTS5_ALLOWED_FILTERS:
            self.logger.warning(f"Rejected invalid FTS5 filter column: {filter_name}")
            return None

        # Validate operator against whitelist
        allowed_operators = frozenset({"=", ">=", "<=", ">", "<", "LIKE"})
        if operator not in allowed_operators:
            self.logger.warning(f"Rejected invalid FTS5 operator: {operator}")
            return None

        # Validate param_name (alphanumeric and underscore only)
        import re
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', param_name):
            self.logger.warning(f"Rejected invalid FTS5 param name: {param_name}")
            return None

        return f"{filter_name} {operator} :{param_name}"

    def _search_fts5(
        self,
        query: str,
        tenant_id: str,
        user_id: int,
        agent_id: Optional[int],
        thread_id: Optional[int],
        date_from: Optional[str],
        date_to: Optional[str],
        role: Optional[str],
        limit: int,
        offset: int
    ) -> Dict[str, Any]:
        """Search using FTS5 virtual table."""

        # Build FTS5 query
        fts_query = query.replace('"', '""')  # Escape quotes

        # MED-003 Security Fix: Build WHERE clause using validated filter builder
        # This prevents SQL injection through dynamic WHERE clause construction
        where_parts = []
        params = {"query": fts_query}

        # Required filters (always included)
        tenant_filter = self._build_fts5_filter("tenant_id", "=", "tenant_id")
        user_filter = self._build_fts5_filter("user_id", "=", "user_id")
        if tenant_filter and user_filter:
            where_parts.extend([tenant_filter, user_filter])
            params["tenant_id"] = tenant_id
            params["user_id"] = user_id

        # Optional filters
        if agent_id:
            filter_clause = self._build_fts5_filter("agent_id", "=", "agent_id")
            if filter_clause:
                where_parts.append(filter_clause)
                params["agent_id"] = agent_id

        if thread_id:
            filter_clause = self._build_fts5_filter("thread_id", "=", "thread_id")
            if filter_clause:
                where_parts.append(filter_clause)
                params["thread_id"] = thread_id

        if date_from:
            filter_clause = self._build_fts5_filter("timestamp", ">=", "date_from")
            if filter_clause:
                where_parts.append(filter_clause)
                params["date_from"] = date_from

        if date_to:
            filter_clause = self._build_fts5_filter("timestamp", "<=", "date_to")
            if filter_clause:
                where_parts.append(filter_clause)
                params["date_to"] = date_to

        if role:
            filter_clause = self._build_fts5_filter("role", "=", "role")
            if filter_clause:
                where_parts.append(filter_clause)
                params["role"] = role

        where_clause = " AND ".join(where_parts)

        # Count total results
        # Note: SQL structure is static, only parameterized values vary
        count_sql = text(f"""
            SELECT COUNT(*)
            FROM conversation_search_fts
            WHERE content MATCH :query AND {where_clause}
        """)

        total = self.db.execute(count_sql, params).scalar() or 0

        # Get results with highlighting
        # Note: SQL structure is static, only parameterized values vary
        search_sql = text(f"""
            SELECT
                thread_id,
                message_id,
                role,
                content,
                timestamp,
                agent_id,
                snippet(conversation_search_fts, 3, '<mark>', '</mark>', '...', 64) as snippet,
                rank
            FROM conversation_search_fts
            WHERE content MATCH :query AND {where_clause}
            ORDER BY rank
            LIMIT :limit OFFSET :offset
        """)

        params["limit"] = limit
        params["offset"] = offset

        results = self.db.execute(search_sql, params).fetchall()

        # Format results
        formatted_results = []
        for row in results:
            formatted_results.append({
                "thread_id": row[0],
                "message_id": row[1],
                "role": row[2],
                "content": row[3],
                "timestamp": row[4],
                "agent_id": row[5],
                "snippet": row[6],
                "rank": row[7]
            })

        # Get thread info for results
        formatted_results = self._enrich_results_with_thread_info(formatted_results)

        return {
            "status": "success",
            "results": formatted_results,
            "total": total,
            "limit": limit,
            "offset": offset,
            "search_mode": "full_text"
        }

    def _search_like(
        self,
        query: str,
        tenant_id: str,
        user_id: int,
        agent_id: Optional[int],
        thread_id: Optional[int],
        date_from: Optional[str],
        date_to: Optional[str],
        role: Optional[str],
        limit: int,
        offset: int
    ) -> Dict[str, Any]:
        """Fallback search using LIKE queries."""

        # Search in Memory table (messages stored as JSON)
        from models import Memory, Agent, ConversationThread

        query_obj = self.db.query(Memory).filter(
            Memory.tenant_id == tenant_id,
            Memory.user_id == user_id,
            Memory.sender_key.like('playground_%')
        )

        if agent_id:
            query_obj = query_obj.filter(Memory.agent_id == agent_id)

        memory_records = query_obj.all()

        # Parse messages and search
        results = []
        for mem in memory_records:
            # Extract thread_id
            if '_t' not in mem.sender_key:
                continue

            thread_id_str = mem.sender_key.split('_t')[-1]
            try:
                mem_thread_id = int(thread_id_str)
            except:
                continue

            if thread_id and mem_thread_id != thread_id:
                continue

            # Parse messages
            try:
                messages = json.loads(mem.messages_json) if mem.messages_json else []
            except:
                messages = []

            # Search in messages
            for idx, msg in enumerate(messages):
                if not isinstance(msg, dict):
                    continue

                content = msg.get('content', '')
                msg_role = msg.get('role', 'user')
                timestamp = msg.get('timestamp', '')
                message_id = msg.get('message_id', f"msg_{mem.id}_{idx}")

                # Apply filters
                if role and msg_role != role:
                    continue

                if date_from and timestamp < date_from:
                    continue

                if date_to and timestamp > date_to:
                    continue

                # Search in content (case-insensitive)
                if query.lower() in content.lower():
                    # Create snippet with highlighting
                    snippet = self._create_snippet(content, query)

                    results.append({
                        "thread_id": mem_thread_id,
                        "message_id": message_id,
                        "role": msg_role,
                        "content": content,
                        "timestamp": timestamp,
                        "agent_id": mem.agent_id,
                        "snippet": snippet,
                        "rank": 0
                    })

        # Sort by timestamp (most recent first)
        results.sort(key=lambda x: x['timestamp'], reverse=True)

        # Pagination
        total = len(results)
        results = results[offset:offset + limit]

        # Enrich with thread info
        results = self._enrich_results_with_thread_info(results)

        return {
            "status": "success",
            "results": results,
            "total": total,
            "limit": limit,
            "offset": offset,
            "search_mode": "like"
        }

    def _create_snippet(self, content: str, query: str, context_length: int = 64) -> str:
        """Create highlighted snippet around query match."""
        query_lower = query.lower()
        content_lower = content.lower()

        idx = content_lower.find(query_lower)
        if idx == -1:
            return content[:context_length] + "..."

        # Get context around match
        start = max(0, idx - context_length // 2)
        end = min(len(content), idx + len(query) + context_length // 2)

        snippet = content[start:end]

        # Add ellipsis
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."

        # Highlight the query
        import re
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        snippet = pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", snippet)

        return snippet

    def search_semantic(
        self,
        query: str,
        tenant_id: str,
        user_id: int,
        agent_id: Optional[int] = None,
        limit: int = 10,
        min_similarity: float = 0.5
    ) -> Dict[str, Any]:
        """
        Semantic search using ChromaDB.

        Args:
            query: Search query
            tenant_id: Tenant ID for filtering
            user_id: User ID for filtering
            agent_id: Optional agent filter
            limit: Max results
            min_similarity: Minimum similarity threshold

        Returns:
            Dict with results and metadata
        """
        try:
            from agent.memory.vector_store_manager import get_vector_store
            import settings

            results = []

            # If agent_id specified, search that agent's vector store
            if agent_id:
                persist_dir = getattr(settings, 'CHROMA_PERSIST_DIR', 'data/chroma')
                chroma_path = f"{persist_dir}/agent_{agent_id}"

                try:
                    vector_store = get_vector_store(persist_directory=chroma_path)

                    # Search with sender_key filter for playground messages
                    search_results = vector_store.search_similar(
                        query_text=query,
                        sender_key=f"playground_u{user_id}_a{agent_id}",
                        limit=limit * 2  # Get more to filter
                    )

                    for result in search_results:
                        distance = result.get('distance', 1.0)
                        similarity = 1 / (1 + distance)

                        if similarity >= min_similarity:
                            results.append({
                                "message_id": result.get("message_id", ""),
                                "role": result.get("role", "user"),
                                "content": result.get("text", ""),
                                "similarity": round(similarity, 3),
                                "agent_id": agent_id,
                                "thread_id": None  # Would need to extract from metadata
                            })
                except Exception as e:
                    self.logger.warning(f"ChromaDB search failed for agent {agent_id}: {e}")

            else:
                # Search across all agents (more expensive)
                from models import Agent

                agents = self.db.query(Agent).filter(
                    Agent.tenant_id == tenant_id
                ).all()

                for agent in agents:
                    persist_dir = getattr(settings, 'CHROMA_PERSIST_DIR', 'data/chroma')
                    chroma_path = f"{persist_dir}/agent_{agent.id}"

                    try:
                        vector_store = get_vector_store(persist_directory=chroma_path)

                        search_results = vector_store.search_similar(
                            query_text=query,
                            sender_key=f"playground_u{user_id}",
                            limit=limit
                        )

                        for result in search_results:
                            distance = result.get('distance', 1.0)
                            similarity = 1 / (1 + distance)

                            if similarity >= min_similarity:
                                results.append({
                                    "message_id": result.get("message_id", ""),
                                    "role": result.get("role", "user"),
                                    "content": result.get("text", ""),
                                    "similarity": round(similarity, 3),
                                    "agent_id": agent.id,
                                    "thread_id": None
                                })
                    except:
                        continue

            # Sort by similarity
            results.sort(key=lambda x: x['similarity'], reverse=True)
            results = results[:limit]

            # Enrich with thread info
            results = self._enrich_results_with_thread_info(results)

            return {
                "status": "success",
                "results": results,
                "total": len(results),
                "search_mode": "semantic"
            }

        except Exception as e:
            self.logger.error(f"Semantic search failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "results": [],
                "total": 0
            }

    def search_combined(
        self,
        query: str,
        tenant_id: str,
        user_id: int,
        agent_id: Optional[int] = None,
        thread_id: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Combined/hybrid search (full-text + semantic).

        Merges results from both search methods and deduplicates.
        """
        try:
            # Get full-text results
            ft_results = self.search_full_text(
                query, tenant_id, user_id, agent_id, thread_id,
                date_from, date_to, None, limit, 0
            )

            # Get semantic results
            sem_results = self.search_semantic(
                query, tenant_id, user_id, agent_id, limit // 2, 0.5
            )

            # Merge and deduplicate by message_id
            seen = set()
            combined = []

            # Add full-text results first (exact matches prioritized)
            for result in ft_results.get('results', []):
                msg_id = result.get('message_id')
                if msg_id and msg_id not in seen:
                    seen.add(msg_id)
                    result['match_type'] = 'full_text'
                    combined.append(result)

            # Add semantic results
            for result in sem_results.get('results', []):
                msg_id = result.get('message_id')
                if msg_id and msg_id not in seen:
                    seen.add(msg_id)
                    result['match_type'] = 'semantic'
                    combined.append(result)

            return {
                "status": "success",
                "results": combined[:limit],
                "total": len(combined),
                "search_mode": "combined"
            }

        except Exception as e:
            self.logger.error(f"Combined search failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "results": [],
                "total": 0
            }

    def _enrich_results_with_thread_info(self, results: List[Dict]) -> List[Dict]:
        """Add thread title and agent name to search results."""
        from models import ConversationThread, Agent, Contact

        thread_ids = [r['thread_id'] for r in results if r.get('thread_id')]
        agent_ids = [r['agent_id'] for r in results if r.get('agent_id')]

        # Get thread info
        threads = {}
        if thread_ids:
            thread_records = self.db.query(ConversationThread).filter(
                ConversationThread.id.in_(thread_ids)
            ).all()
            threads = {t.id: t.title for t in thread_records}

        # Get agent info
        agents = {}
        if agent_ids:
            agent_records = self.db.query(Agent, Contact).join(
                Contact, Agent.contact_id == Contact.id
            ).filter(
                Agent.id.in_(agent_ids)
            ).all()
            agents = {a.id: c.friendly_name for a, c in agent_records}

        # Enrich results
        for result in results:
            thread_id = result.get('thread_id')
            agent_id = result.get('agent_id')

            if thread_id and thread_id in threads:
                result['thread_title'] = threads[thread_id]

            if agent_id and agent_id in agents:
                result['agent_name'] = agents[agent_id]

        return results

    def search_tool_executions(
        self,
        query: str,
        tenant_id: str,
        user_id: int,
        agent_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search tool execution outputs and commands.

        Args:
            query: Search query
            tenant_id: Tenant ID for filtering
            user_id: User ID for filtering
            agent_id: Optional agent filter
            limit: Max results

        Returns:
            List of matching tool execution results
        """
        from models import SandboxedToolExecution, SandboxedTool

        try:
            query_lower = query.lower()

            # Build query for tool executions
            base_query = self.db.query(SandboxedToolExecution, SandboxedTool).join(
                SandboxedTool, SandboxedToolExecution.tool_id == SandboxedTool.id
            ).filter(
                SandboxedTool.tenant_id == tenant_id
            )

            # Get recent executions (limit to 200 for performance)
            executions = base_query.order_by(
                SandboxedToolExecution.created_at.desc()
            ).limit(200).all()

            results = []
            for exec_record, tool in executions:
                output_match = exec_record.output and query_lower in exec_record.output.lower()
                command_match = query_lower in exec_record.rendered_command.lower()

                if output_match or command_match:
                    # Create snippet from output or command
                    if output_match and exec_record.output:
                        snippet = self._create_snippet(exec_record.output, query, context_length=150)
                    else:
                        snippet = self._create_snippet(exec_record.rendered_command, query, context_length=150)

                    results.append({
                        "type": "tool_execution",
                        "tool_name": tool.name,
                        "command": exec_record.rendered_command[:200],  # Truncate long commands
                        "snippet": snippet,
                        "status": exec_record.status,
                        "timestamp": exec_record.created_at.isoformat() if exec_record.created_at else None,
                        "execution_id": exec_record.id,
                        "execution_time_ms": exec_record.execution_time_ms
                    })

            return results[:limit]

        except Exception as e:
            self.logger.error(f"Tool execution search failed: {e}")
            return []

    def get_search_suggestions(
        self,
        query: str,
        tenant_id: str,
        user_id: int,
        limit: int = 5
    ) -> List[str]:
        """
        Get search suggestions based on partial query.

        Returns list of suggested search terms from recent searches or tags.
        """
        suggestions = []

        try:
            # Get common tags
            from models import ConversationTag

            tags = self.db.query(ConversationTag.tag).filter(
                ConversationTag.tenant_id == tenant_id,
                ConversationTag.user_id == user_id,
                ConversationTag.tag.like(f"{query}%")
            ).distinct().limit(limit).all()

            suggestions.extend([t[0] for t in tags])

        except Exception as e:
            self.logger.warning(f"Failed to get search suggestions: {e}")

        return suggestions[:limit]
