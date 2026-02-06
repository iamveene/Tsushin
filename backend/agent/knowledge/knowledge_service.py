"""
Phase 5.0: Knowledge Base - Knowledge Service
Manages agent knowledge base including document upload, processing, and retrieval.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from models import AgentKnowledge, KnowledgeChunk
from agent.knowledge.document_processor import DocumentProcessor
from agent.memory.embedding_service import EmbeddingService
import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)


class KnowledgeService:
    """Service for managing agent knowledge base."""

    def __init__(self, db: Session):
        """
        Initialize knowledge service.

        Args:
            db: Database session
        """
        self.db = db
        self.processor = DocumentProcessor()
        self.embedding_service = EmbeddingService()

        # Initialize ChromaDB client for knowledge base
        vector_dir = Path("./data/chroma/knowledge")
        vector_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(
            path=str(vector_dir),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

        # Storage directory for uploaded files
        self.storage_dir = Path("./data/knowledge")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def upload_document(
        self,
        agent_id: int,
        file_path: str,
        document_name: str,
        document_type: str
    ) -> AgentKnowledge:
        """
        Upload a document to the knowledge base.

        Args:
            agent_id: ID of the agent
            file_path: Path to the uploaded file
            document_name: Name of the document
            document_type: Type of document (txt, csv, json, pdf, docx)

        Returns:
            AgentKnowledge record
        """
        try:
            # Get file size
            file_size = os.path.getsize(file_path)

            # Copy file to storage directory
            agent_dir = self.storage_dir / f"agent_{agent_id}"
            agent_dir.mkdir(exist_ok=True)

            # Generate unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_ext = Path(file_path).suffix
            stored_filename = f"{timestamp}_{document_name}"
            if not stored_filename.endswith(file_ext):
                stored_filename += file_ext

            stored_path = agent_dir / stored_filename
            shutil.copy2(file_path, stored_path)

            # Create database record
            knowledge = AgentKnowledge(
                agent_id=agent_id,
                document_name=document_name,
                document_type=document_type,
                file_path=str(stored_path),
                file_size_bytes=file_size,
                status="pending"
            )

            self.db.add(knowledge)
            self.db.commit()
            self.db.refresh(knowledge)

            logger.info(f"Document uploaded: {document_name} (ID: {knowledge.id})")
            return knowledge

        except Exception as e:
            logger.error(f"Error uploading document: {e}")
            self.db.rollback()
            raise

    def process_document(self, knowledge_id: int) -> bool:
        """
        Process a document: extract text, create chunks, generate embeddings.

        Args:
            knowledge_id: ID of the AgentKnowledge record

        Returns:
            True if successful, False otherwise
        """
        knowledge = self.db.query(AgentKnowledge).get(knowledge_id)
        if not knowledge:
            logger.error(f"Knowledge record not found: {knowledge_id}")
            return False

        try:
            # Update status
            knowledge.status = "processing"
            self.db.commit()

            # Process document and create chunks
            chunks = self.processor.process_document(
                knowledge.file_path,
                knowledge.document_type
            )

            if not chunks:
                raise ValueError("No chunks created from document")

            # Store chunks in database and generate embeddings
            for chunk_data in chunks:
                # Create chunk record
                chunk = KnowledgeChunk(
                    knowledge_id=knowledge.id,
                    chunk_index=chunk_data["chunk_index"],
                    content=chunk_data["content"],
                    char_count=chunk_data["char_count"],
                    metadata_json={
                        "start_pos": chunk_data["start_pos"],
                        "end_pos": chunk_data["end_pos"]
                    }
                )
                self.db.add(chunk)
                self.db.flush()  # Get chunk ID

                # Generate embedding and store in vector store
                try:
                    embedding = self.embedding_service.embed_text(chunk_data["content"])

                    # Get or create collection for this agent
                    collection_name = f"knowledge_agent_{knowledge.agent_id}"
                    collection = self.chroma_client.get_or_create_collection(
                        name=collection_name,
                        metadata={"description": f"Knowledge base for agent {knowledge.agent_id}"}
                    )

                    # Store in ChromaDB
                    document_id = f"knowledge_{knowledge.id}_chunk_{chunk.id}"
                    collection.upsert(
                        ids=[document_id],
                        embeddings=[embedding],
                        metadatas=[{
                            "knowledge_id": knowledge.id,
                            "chunk_id": chunk.id,
                            "chunk_index": chunk_data["chunk_index"],
                            "document_name": knowledge.document_name,
                            "content": chunk_data["content"][:200]  # Store preview
                        }],
                        documents=[chunk_data["content"]]
                    )
                except Exception as e:
                    logger.error(f"Error generating embedding for chunk {chunk.id}: {e}")
                    # Continue processing other chunks

            # Update knowledge record
            knowledge.num_chunks = len(chunks)
            knowledge.status = "completed"
            knowledge.processed_date = datetime.utcnow()
            self.db.commit()

            logger.info(f"Document processed successfully: {knowledge.document_name} ({len(chunks)} chunks)")
            return True

        except Exception as e:
            logger.error(f"Error processing document {knowledge_id}: {e}")
            knowledge.status = "failed"
            knowledge.error_message = str(e)
            self.db.commit()
            return False

    def search_knowledge(
        self,
        agent_id: int,
        query: str,
        max_results: int = 5,
        similarity_threshold: float = 0.3
    ) -> List[Dict]:
        """
        Search agent's knowledge base using semantic similarity.

        Args:
            agent_id: ID of the agent
            query: Search query
            max_results: Maximum number of results to return
            similarity_threshold: Minimum similarity score (0.0-1.0)

        Returns:
            List of relevant chunks with metadata
        """
        try:
            # Get collection for this agent
            collection_name = f"knowledge_agent_{agent_id}"
            try:
                collection = self.chroma_client.get_collection(name=collection_name)
            except:
                # Collection doesn't exist yet
                return []

            # Check if collection has any documents
            if collection.count() == 0:
                return []

            # Generate query embedding
            query_embedding = self.embedding_service.embed_text(query)

            # Search ChromaDB
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=max_results
            )

            # Filter by similarity threshold and format results
            formatted_results = []
            if results['ids'] and len(results['ids'][0]) > 0:
                for i in range(len(results['ids'][0])):
                    # Convert distance to similarity (ChromaDB returns L2 distance)
                    # Lower distance = higher similarity
                    distance = results['distances'][0][i]
                    similarity = 1.0 / (1.0 + distance)  # Convert distance to similarity score

                    if similarity >= similarity_threshold:
                        metadata = results['metadatas'][0][i]
                        chunk_id = metadata.get("chunk_id")
                        if chunk_id:
                            chunk = self.db.query(KnowledgeChunk).get(chunk_id)
                            if chunk:
                                knowledge = self.db.query(AgentKnowledge).get(chunk.knowledge_id)
                                formatted_results.append({
                                    "chunk_id": chunk.id,
                                    "knowledge_id": knowledge.id,
                                    "document_name": knowledge.document_name,
                                    "content": chunk.content,
                                    "similarity": similarity,
                                    "chunk_index": chunk.chunk_index
                                })

            logger.info(f"Knowledge search for agent {agent_id}: {len(formatted_results)} results")
            return formatted_results

        except Exception as e:
            logger.error(f"Error searching knowledge base: {e}")
            return []

    def get_agent_knowledge(self, agent_id: int) -> List[AgentKnowledge]:
        """
        Get all knowledge documents for an agent.

        Args:
            agent_id: ID of the agent

        Returns:
            List of AgentKnowledge records
        """
        return self.db.query(AgentKnowledge).filter(
            AgentKnowledge.agent_id == agent_id
        ).order_by(AgentKnowledge.upload_date.desc()).all()

    def get_knowledge_by_id(self, knowledge_id: int) -> Optional[AgentKnowledge]:
        """
        Get a specific knowledge document.

        Args:
            knowledge_id: ID of the knowledge document

        Returns:
            AgentKnowledge record or None
        """
        return self.db.query(AgentKnowledge).get(knowledge_id)

    def get_knowledge_chunks(self, knowledge_id: int) -> List[KnowledgeChunk]:
        """
        Get all chunks for a knowledge document.

        Args:
            knowledge_id: ID of the knowledge document

        Returns:
            List of KnowledgeChunk records
        """
        return self.db.query(KnowledgeChunk).filter(
            KnowledgeChunk.knowledge_id == knowledge_id
        ).order_by(KnowledgeChunk.chunk_index).all()

    def delete_knowledge(self, knowledge_id: int) -> bool:
        """
        Delete a knowledge document and all its chunks.

        Args:
            knowledge_id: ID of the knowledge document

        Returns:
            True if successful, False otherwise
        """
        try:
            knowledge = self.db.query(AgentKnowledge).get(knowledge_id)
            if not knowledge:
                logger.error(f"Knowledge record not found: {knowledge_id}")
                return False

            # Delete chunks from vector store
            chunks = self.get_knowledge_chunks(knowledge_id)
            collection_name = f"knowledge_agent_{knowledge.agent_id}"

            try:
                collection = self.chroma_client.get_collection(name=collection_name)
                for chunk in chunks:
                    try:
                        document_id = f"knowledge_{knowledge.id}_chunk_{chunk.id}"
                        collection.delete(ids=[document_id])
                    except Exception as e:
                        logger.warning(f"Error deleting embedding for chunk {chunk.id}: {e}")
            except Exception as e:
                logger.warning(f"Error getting collection for deletion: {e}")

            # Delete database records (chunks will cascade)
            self.db.delete(knowledge)
            self.db.commit()

            # Delete file
            try:
                file_path = Path(knowledge.file_path)
                if file_path.exists():
                    file_path.unlink()
            except Exception as e:
                logger.warning(f"Error deleting file {knowledge.file_path}: {e}")

            logger.info(f"Knowledge deleted: {knowledge.document_name} (ID: {knowledge_id})")
            return True

        except Exception as e:
            logger.error(f"Error deleting knowledge {knowledge_id}: {e}")
            self.db.rollback()
            return False

    def get_knowledge_stats(self, agent_id: int) -> Dict:
        """
        Get statistics about agent's knowledge base.

        Args:
            agent_id: ID of the agent

        Returns:
            Dictionary with statistics
        """
        knowledge_list = self.get_agent_knowledge(agent_id)

        total_documents = len(knowledge_list)
        total_chunks = sum(k.num_chunks for k in knowledge_list)
        total_size_bytes = sum(k.file_size_bytes for k in knowledge_list)

        completed = sum(1 for k in knowledge_list if k.status == "completed")
        processing = sum(1 for k in knowledge_list if k.status == "processing")
        failed = sum(1 for k in knowledge_list if k.status == "failed")

        return {
            "total_documents": total_documents,
            "total_chunks": total_chunks,
            "total_size_bytes": total_size_bytes,
            "total_size_mb": round(total_size_bytes / (1024 * 1024), 2),
            "completed": completed,
            "processing": processing,
            "failed": failed
        }
