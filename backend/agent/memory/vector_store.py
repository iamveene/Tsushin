"""
Vector Store - ChromaDB integration for semantic search

Stores message embeddings and provides similarity search functionality.
Uses ChromaDB for persistent vector storage.
"""

import logging
from typing import List, Dict, Optional
import chromadb
from chromadb.config import Settings


class VectorStore:
    """
    Vector database for storing and searching message embeddings.

    Uses ChromaDB for persistent storage and fast similarity search.

    Attributes:
        persist_directory: Path to ChromaDB storage directory
        embedding_service: EmbeddingService instance for generating embeddings
        client: ChromaDB client
        collection: ChromaDB collection for messages
    """

    def __init__(self, persist_directory: str, embedding_service):
        """
        Initialize the vector store.

        Args:
            persist_directory: Directory path for ChromaDB persistence
            embedding_service: EmbeddingService instance for embeddings
        """
        self.persist_directory = persist_directory
        self.embedding_service = embedding_service
        self.logger = logging.getLogger(__name__)

        # Initialize ChromaDB client with persistence
        self.logger.info(f"Initializing ChromaDB at {persist_directory}")
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

        # Get or create collection for messages
        self.collection = self.client.get_or_create_collection(
            name="whatsapp_messages",
            metadata={"description": "WhatsApp message embeddings"}
        )

        self.logger.info(f"VectorStore initialized. Collection size: {self.collection.count()}")

    async def add_message(
        self,
        message_id: str,
        sender_key: str,
        text: str,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Add a message to the vector store.

        Args:
            message_id: Unique identifier for the message
            sender_key: Sender identifier (phone/group ID)
            text: Message text content
            metadata: Optional additional metadata
        """
        try:
            # Generate embedding
            embedding = await self.embedding_service.embed_text_async(text)

            # Prepare metadata
            msg_metadata = {
                "sender_key": sender_key,
                "text": text
            }
            if metadata:
                msg_metadata.update(metadata)

            # Add to collection (upsert to handle duplicates)
            self.collection.upsert(
                ids=[message_id],
                embeddings=[embedding],
                metadatas=[msg_metadata],
                documents=[text]
            )

            self.logger.debug(f"Added message {message_id} to vector store")

        except Exception as e:
            self.logger.error(f"Error adding message to vector store: {e}")
            raise

    async def search_similar(
        self,
        query_text: str,
        limit: int = 5,
        sender_key: Optional[str] = None
    ) -> List[Dict]:
        """
        Search for messages similar to the query text.

        Args:
            query_text: Text to search for
            limit: Maximum number of results to return
            sender_key: Optional filter by sender

        Returns:
            List of dictionaries containing:
                - message_id: Message identifier
                - sender_key: Sender identifier
                - text: Message text
                - distance: Similarity distance (lower = more similar)
                - metadata: Additional metadata
        """
        try:
            # Handle empty collection
            if self.collection.count() == 0:
                return []

            # Generate query embedding
            query_embedding = await self.embedding_service.embed_text_async(query_text)

            # Prepare query filters
            where_filter = None
            if sender_key:
                where_filter = {"sender_key": sender_key}

            # Search in ChromaDB
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                where=where_filter
            )

            # Format results
            formatted_results = []
            if results['ids'] and len(results['ids'][0]) > 0:
                for i in range(len(results['ids'][0])):
                    result = {
                        'message_id': results['ids'][0][i],
                        'text': results['documents'][0][i],
                        'distance': results['distances'][0][i],
                        'sender_key': results['metadatas'][0][i].get('sender_key'),
                    }
                    # Add any additional metadata
                    for key, value in results['metadatas'][0][i].items():
                        if key not in ['sender_key', 'text']:
                            result[key] = value

                    formatted_results.append(result)

            self.logger.debug(f"Found {len(formatted_results)} similar messages")
            return formatted_results

        except Exception as e:
            self.logger.error(f"Error searching vector store: {e}")
            raise

    def delete_message(self, message_id: str) -> None:
        """
        Delete a message from the vector store.

        Args:
            message_id: ID of message to delete
        """
        try:
            self.collection.delete(ids=[message_id])
            self.logger.debug(f"Deleted message {message_id} from vector store")
        except Exception as e:
            self.logger.error(f"Error deleting message: {e}")
            raise

    def delete_by_sender(self, sender_key: str) -> None:
        """
        Delete all messages from a specific sender.

        Args:
            sender_key: Sender identifier to delete messages for
        """
        try:
            self.collection.delete(
                where={"sender_key": sender_key}
            )
            self.logger.info(f"Deleted all messages from sender {sender_key}")
        except Exception as e:
            self.logger.error(f"Error deleting messages by sender: {e}")
            raise

    def clear_all(self) -> None:
        """Clear all messages from the vector store."""
        try:
            # Delete and recreate collection
            self.client.delete_collection(name="whatsapp_messages")
            self.collection = self.client.create_collection(
                name="whatsapp_messages",
                metadata={"description": "WhatsApp message embeddings"}
            )
            self.logger.info("Cleared all messages from vector store")
        except Exception as e:
            self.logger.error(f"Error clearing vector store: {e}")
            raise

    def update_access_time(self, message_ids: List[str]) -> None:
        """
        Update the last_accessed_at metadata field for the given message IDs.

        Args:
            message_ids: List of message IDs to update
        """
        if not message_ids:
            return

        try:
            from datetime import datetime
            now_iso = datetime.utcnow().isoformat() + "Z"

            # Fetch existing metadata for these IDs
            existing = self.collection.get(ids=message_ids, include=["metadatas"])

            if not existing or not existing['ids']:
                return

            updated_metadatas = []
            for metadata in existing['metadatas']:
                meta = dict(metadata) if metadata else {}
                meta['last_accessed_at'] = now_iso
                updated_metadatas.append(meta)

            self.collection.update(
                ids=existing['ids'],
                metadatas=updated_metadatas
            )

            self.logger.debug(f"Updated access time for {len(message_ids)} messages")

        except Exception as e:
            self.logger.error(f"Error updating access time: {e}")

    async def search_similar_with_embeddings(
        self,
        query_text: str,
        limit: int = 5,
        sender_key: Optional[str] = None
    ) -> tuple:
        """
        Search for similar messages and also return query embedding and result embeddings.

        Used by temporal decay MMR reranking.

        Args:
            query_text: Text to search for
            limit: Maximum number of results
            sender_key: Optional filter by sender

        Returns:
            Tuple of (formatted_results, query_embedding, result_embeddings)
            where result_embeddings is a list of embedding vectors aligned with results
        """
        try:
            if self.collection.count() == 0:
                return [], [], []

            query_embedding = await self.embedding_service.embed_text_async(query_text)

            where_filter = None
            if sender_key:
                where_filter = {"sender_key": sender_key}

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                where=where_filter,
                include=["documents", "metadatas", "distances", "embeddings"]
            )

            formatted_results = []
            result_embeddings = []

            if results['ids'] and len(results['ids'][0]) > 0:
                for i in range(len(results['ids'][0])):
                    result = {
                        'message_id': results['ids'][0][i],
                        'text': results['documents'][0][i],
                        'distance': results['distances'][0][i],
                        'sender_key': results['metadatas'][0][i].get('sender_key'),
                    }
                    for key, value in results['metadatas'][0][i].items():
                        if key not in ['sender_key', 'text']:
                            result[key] = value

                    formatted_results.append(result)

                    # Collect embeddings
                    if results.get('embeddings') and results['embeddings'][0]:
                        result_embeddings.append(results['embeddings'][0][i])
                    else:
                        result_embeddings.append([])

            return formatted_results, query_embedding, result_embeddings

        except Exception as e:
            self.logger.error(f"Error in search_similar_with_embeddings: {e}")
            raise

    def get_stats(self) -> Dict:
        """
        Get statistics about the vector store.

        Returns:
            Dictionary with collection statistics
        """
        return {
            "total_messages": self.collection.count(),
            "collection_name": self.collection.name,
            "persist_directory": self.persist_directory
        }
