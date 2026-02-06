"""
Phase 16: Combined Knowledge Service

Handles retrieval of knowledge from both agent and project knowledge bases,
merging results intelligently without overriding either source.
"""

import os
import logging
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class CombinedKnowledgeService:
    """
    Service for combining agent and project knowledge bases.

    When an agent is operating within a project context, both knowledge bases
    are searched and results are intelligently merged:
    - Results from both sources are combined
    - Duplicate/similar content is deduplicated
    - Source attribution is maintained
    - Project KB takes precedence for project-specific queries
    """

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)
        self._chroma_client = None
        self._embedding_model = None

    def _get_chroma_client(self):
        """Lazy-load ChromaDB client."""
        if self._chroma_client is None:
            try:
                import chromadb
                from chromadb.config import Settings

                chroma_dir = os.environ.get("TSN_CHROMA_DIR", "/app/data/chroma")
                self._chroma_client = chromadb.PersistentClient(
                    path=chroma_dir,
                    settings=Settings(anonymized_telemetry=False)
                )
            except Exception as e:
                self.logger.error(f"Failed to initialize ChromaDB: {e}")
                raise
        return self._chroma_client

    def _get_embedding_model(self, model_name: str = "all-MiniLM-L6-v2"):
        """Get embedding model for semantic search."""
        if self._embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedding_model = SentenceTransformer(model_name)
            except Exception as e:
                self.logger.error(f"Failed to load embedding model: {e}")
                raise
        return self._embedding_model

    async def search_combined_knowledge(
        self,
        query: str,
        agent_id: Optional[int] = None,
        project_id: Optional[int] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[int] = None,
        max_results: int = 5,
        similarity_threshold: float = 0.3,
        include_source_attribution: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search both agent and project knowledge bases and merge results.

        Args:
            query: Search query
            agent_id: Agent ID for agent KB search
            project_id: Project ID for project KB search
            tenant_id: Tenant ID (for agent KB collection name)
            user_id: User ID (for agent KB collection name)
            max_results: Maximum total results to return
            similarity_threshold: Minimum similarity score
            include_source_attribution: Include source info in results

        Returns:
            List of knowledge chunks with source attribution
        """
        self.logger.info(f"[KB BADGE] search_combined_knowledge CALLED: query={query[:50]}, agent_id={agent_id}, project_id={project_id}")
        all_results = []

        # Search agent knowledge base
        if agent_id and tenant_id and user_id:
            self.logger.info(f"[KB BADGE] Starting agent KB search: agent_id={agent_id}, tenant_id={tenant_id}, user_id={user_id}")
            agent_results = await self._search_agent_kb(
                tenant_id=tenant_id,
                user_id=user_id,
                agent_id=agent_id,
                query=query,
                max_results=max_results
            )
            self.logger.info(f"[KB BADGE] Agent KB search returned {len(agent_results)} results")
            for i, result in enumerate(agent_results):
                self.logger.info(f"[KB BADGE]   Agent result {i+1}: {result.get('document_name')} similarity={result.get('similarity'):.3f}")
                result["source_type"] = "agent"
                result["agent_id"] = agent_id
            all_results.extend(agent_results)

        # Search project knowledge base
        if project_id:
            self.logger.info(f"[KB BADGE] Starting project KB search: project_id={project_id}")
            project_results = await self._search_project_kb(
                project_id=project_id,
                query=query,
                max_results=max_results
            )
            self.logger.info(f"[KB BADGE] Project KB search returned {len(project_results)} results")
            for i, result in enumerate(project_results):
                self.logger.info(f"[KB BADGE]   Project result {i+1}: {result.get('document_name')} similarity={result.get('similarity'):.3f} chunk_index={result.get('chunk_index')}")
                result["source_type"] = "project"
                result["project_id"] = project_id
            all_results.extend(project_results)

        self.logger.info(f"[KB BADGE] Total combined results before filtering: {len(all_results)}")

        if not all_results:
            self.logger.warning(f"[KB BADGE] No results found in combined KB search!")
            return []

        # Filter by similarity threshold
        filtered_results = [
            r for r in all_results
            if r.get("similarity", 0) >= similarity_threshold
        ]
        self.logger.info(f"[KB BADGE] After similarity filter ({similarity_threshold}): {len(filtered_results)} results")

        # Sort by similarity (highest first)
        filtered_results.sort(key=lambda x: x.get("similarity", 0), reverse=True)

        # Deduplicate similar content
        deduplicated = self._deduplicate_results(filtered_results)
        self.logger.info(f"[KB BADGE] After deduplication: {len(deduplicated)} results")

        # Take top results
        final_results = deduplicated[:max_results]
        self.logger.info(f"[KB BADGE] Returning {len(final_results)} final results with source attribution")

        # Optionally strip source attribution
        if not include_source_attribution:
            for result in final_results:
                result.pop("source_type", None)
                result.pop("agent_id", None)
                result.pop("project_id", None)

        return final_results

    async def _search_agent_kb(
        self,
        tenant_id: str,
        user_id: int,
        agent_id: int,
        query: str,
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Search agent's knowledge base."""
        try:
            # Agent KB is stored in the knowledge subfolder (from knowledge_service.py)
            import chromadb
            from chromadb.config import Settings
            import os

            chroma_dir = os.environ.get("TSN_CHROMA_DIR", "/app/data/chroma")
            knowledge_dir = os.path.join(chroma_dir, "knowledge")

            self.logger.info(f"[KB BADGE] Agent KB path: {knowledge_dir}")

            knowledge_client = chromadb.PersistentClient(
                path=knowledge_dir,
                settings=Settings(anonymized_telemetry=False)
            )

            # Agent KB uses knowledge_agent_{agent_id} format (from knowledge_service.py)
            collection_name = f"knowledge_agent_{agent_id}"

            self.logger.info(f"[KB BADGE] Looking for agent KB collection: {collection_name}")
            try:
                collection = knowledge_client.get_collection(name=collection_name)
                self.logger.info(f"[KB BADGE] Found agent collection: {collection_name} with {collection.count()} items")
            except Exception as e:
                self.logger.warning(f"[KB BADGE] Agent KB collection '{collection_name}' not found in {knowledge_dir}: {e}")
                return []  # Collection doesn't exist

            model = self._get_embedding_model()
            query_embedding = model.encode(query).tolist()

            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=max_results
            )

            if not results or not results.get('documents') or not results['documents'][0]:
                return []

            documents = results.get('documents', [[]])[0]
            metadatas = results.get('metadatas', [[]])[0]
            distances = results.get('distances', [[]])[0]

            return [
                {
                    "content": doc,
                    "metadata": meta,
                    "similarity": 1 / (1 + dist),  # Convert distance to similarity
                    "document_name": meta.get("filename", meta.get("document_name", "Agent KB"))
                }
                for doc, meta, dist in zip(documents, metadatas, distances)
            ]
        except Exception as e:
            self.logger.error(f"Failed to search agent KB: {e}")
            return []

    async def _search_project_kb(
        self,
        project_id: int,
        query: str,
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Search project's knowledge base."""
        from models import Project

        try:
            self.logger.info(f"[KB BADGE] _search_project_kb called: project_id={project_id}, query='{query[:100]}'")
            project = self.db.query(Project).filter(Project.id == project_id).first()
            if not project:
                self.logger.error(f"[KB BADGE] Project {project_id} not found in database!")
                return []

            self.logger.info(f"[KB BADGE] Project found: {project.name}, embedding_model={project.kb_embedding_model}")

            client = self._get_chroma_client()
            # BUGFIX: Collection name is project_{id}, not project_{id}_kb
            collection_name = f"project_{project_id}"

            try:
                collection = client.get_collection(name=collection_name)
                self.logger.info(f"[KB BADGE] Found project collection: {collection_name} with {collection.count()} items")
            except Exception as e1:
                # Try alternate patterns
                self.logger.warning(f"[KB BADGE] Collection '{collection_name}' not found: {e1}")
                collection_name = f"project_{project_id}_kb"
                try:
                    collection = client.get_collection(name=collection_name)
                    self.logger.info(f"[KB BADGE] Found project collection with _kb suffix: {collection_name}")
                except Exception as e2:
                    collection_name = f"project_{project.tenant_id}_{project_id}"
                    try:
                        collection = client.get_collection(name=collection_name)
                        self.logger.info(f"[KB BADGE] Found project collection with tenant_id: {collection_name}")
                    except Exception as e3:
                        self.logger.error(f"[KB BADGE] No project collection found for project {project_id}")
                        return []  # Collection doesn't exist

            # Use project-specific embedding model
            model_name = project.kb_embedding_model or "all-MiniLM-L6-v2"
            self.logger.info(f"[KB BADGE] Loading embedding model: {model_name}")
            model = self._get_embedding_model(model_name)
            query_embedding = model.encode(query).tolist()
            self.logger.info(f"[KB BADGE] Query embedding generated, dimension: {len(query_embedding)}")

            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=max_results
            )

            self.logger.info(f"[KB BADGE] ChromaDB query returned: docs={len(results.get('documents', [[]])[0])}, metas={len(results.get('metadatas', [[]])[0])}")

            if not results or not results.get('documents') or not results['documents'][0]:
                self.logger.warning(f"[KB BADGE] No documents returned from ChromaDB query!")
                return []

            documents = results.get('documents', [[]])[0]
            metadatas = results.get('metadatas', [[]])[0]
            distances = results.get('distances', [[]])[0]

            formatted_results = []
            for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
                similarity = 1 / (1 + dist)
                self.logger.info(f"[KB BADGE]   Raw result {i+1}: doc={meta.get('document_name')}, dist={dist:.4f}, similarity={similarity:.4f}")
                formatted_results.append({
                    "content": doc,
                    "metadata": meta,
                    "similarity": similarity,
                    "document_name": meta.get("document_name", meta.get("filename", "Project KB")),
                    "chunk_index": meta.get("chunk_index", 0),
                    "project_name": project.name
                })

            return formatted_results
        except Exception as e:
            self.logger.error(f"Failed to search project KB: {e}")
            return []

    def _deduplicate_results(
        self,
        results: List[Dict[str, Any]],
        similarity_threshold: float = 0.9
    ) -> List[Dict[str, Any]]:
        """
        Remove near-duplicate results based on content similarity.
        Keeps the result with higher similarity score.
        """
        if len(results) <= 1:
            return results

        try:
            from difflib import SequenceMatcher

            deduplicated = []
            seen_contents = []

            for result in results:
                content = result.get("content", "")
                is_duplicate = False

                for seen in seen_contents:
                    # Quick length check
                    if abs(len(content) - len(seen)) < len(content) * 0.3:
                        ratio = SequenceMatcher(None, content, seen).ratio()
                        if ratio >= similarity_threshold:
                            is_duplicate = True
                            break

                if not is_duplicate:
                    deduplicated.append(result)
                    seen_contents.append(content)

            return deduplicated
        except Exception as e:
            self.logger.warning(f"Deduplication failed: {e}")
            return results

    def format_combined_context(
        self,
        results: List[Dict[str, Any]],
        include_sources: bool = True
    ) -> str:
        """
        Format combined knowledge results into a context string for the AI.

        Args:
            results: List of search results
            include_sources: Include source attribution in output

        Returns:
            Formatted context string
        """
        if not results:
            return ""

        parts = ["[RELEVANT KNOWLEDGE]"]

        for i, result in enumerate(results, 1):
            content = result.get("content", "")

            if include_sources:
                source_type = result.get("source_type", "unknown")
                doc_name = result.get("document_name", "Unknown")
                project_name = result.get("project_name", "")

                if source_type == "project" and project_name:
                    source = f"Project '{project_name}' - {doc_name}"
                elif source_type == "agent":
                    source = f"Agent KB - {doc_name}"
                else:
                    source = doc_name

                parts.append(f"[{i}. From {source}]:\n{content}")
            else:
                parts.append(f"[{i}]:\n{content}")

        return "\n\n".join(parts)

    async def get_context_for_message(
        self,
        query: str,
        agent_id: int,
        project_id: Optional[int] = None,
        tenant_id: str = None,
        user_id: int = None,
        max_results: int = 5
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Get formatted knowledge context for a message.

        This is the main method to call when building AI context.
        Returns both formatted string and raw results for logging/debugging.

        Args:
            query: User's message/query
            agent_id: Current agent ID
            project_id: Optional project ID if in project context
            tenant_id: Tenant ID
            user_id: User ID
            max_results: Max results to return

        Returns:
            Tuple of (formatted_context_string, raw_results_list)
        """
        results = await self.search_combined_knowledge(
            query=query,
            agent_id=agent_id,
            project_id=project_id,
            tenant_id=tenant_id,
            user_id=user_id,
            max_results=max_results,
            include_source_attribution=True
        )

        formatted = self.format_combined_context(results, include_sources=True)

        return formatted, results
