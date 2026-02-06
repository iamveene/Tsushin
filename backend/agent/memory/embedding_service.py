"""
Embedding Service - Generate text embeddings for semantic search

Uses sentence-transformers library with all-MiniLM-L6-v2 model by default.
This model produces 384-dimensional embeddings optimized for semantic similarity.

BUG-001 Fix: Added singleton pattern and batched processing to prevent OOM crashes
on large document uploads.
"""

import logging
import gc
from typing import List, Optional
import numpy as np
from sentence_transformers import SentenceTransformer

# Singleton cache for embedding models
_model_cache: dict = {}
_model_lock = None  # Will be initialized lazily if threading is used


def get_shared_embedding_service(model_name: str = "all-MiniLM-L6-v2") -> "EmbeddingService":
    """
    Get a shared embedding service instance (singleton pattern).

    This prevents loading the model multiple times and causing memory spikes.

    Args:
        model_name: Name of the sentence-transformers model

    Returns:
        Shared EmbeddingService instance
    """
    global _model_cache

    if model_name not in _model_cache:
        _model_cache[model_name] = EmbeddingService(model_name)
        logging.getLogger(__name__).info(f"Created shared embedding service for model: {model_name}")

    return _model_cache[model_name]


class EmbeddingService:
    """
    Service for generating text embeddings using sentence-transformers.

    Attributes:
        model_name: Name of the sentence-transformers model
        model: Loaded SentenceTransformer model
        logger: Logger instance
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize the embedding service.

        Args:
            model_name: Name of the sentence-transformers model to use.
                       Default is 'all-MiniLM-L6-v2' (384 dimensions, fast, good quality)
        """
        self.model_name = model_name
        self.logger = logging.getLogger(__name__)

        self.logger.info(f"Loading embedding model: {model_name}")
        try:
            self.model = SentenceTransformer(model_name)
            self.logger.info(f"Model loaded successfully. Embedding dimension: {self.model.get_sentence_embedding_dimension()}")
        except Exception as e:
            self.logger.error(f"Failed to load embedding model: {e}")
            raise

    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector (384 dimensions for MiniLM)
        """
        try:
            # Handle empty text
            if not text:
                text = " "  # Use single space for empty text

            # Generate embedding
            embedding = self.model.encode(text, convert_to_numpy=True)

            # Convert to list of floats
            return embedding.tolist()

        except Exception as e:
            self.logger.error(f"Error generating embedding: {e}")
            raise

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts (more efficient than calling embed_text repeatedly).

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        try:
            # Handle empty list
            if not texts:
                return []

            # Handle empty strings in batch
            processed_texts = [text if text else " " for text in texts]

            # Generate embeddings in batch (more efficient)
            embeddings = self.model.encode(processed_texts, convert_to_numpy=True, show_progress_bar=False)

            # Convert to list of lists
            return [emb.tolist() for emb in embeddings]

        except Exception as e:
            self.logger.error(f"Error generating batch embeddings: {e}")
            raise

    def embed_batch_chunked(
        self,
        texts: List[str],
        batch_size: int = 50,
        force_gc: bool = True
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in smaller batches to prevent OOM.

        BUG-001 Fix: Process chunks in smaller batches to prevent memory spikes
        when embedding large documents.

        Args:
            texts: List of texts to embed
            batch_size: Number of texts to process at once (default 50)
            force_gc: Whether to force garbage collection between batches

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        all_embeddings = []
        total_texts = len(texts)

        self.logger.info(f"Embedding {total_texts} chunks in batches of {batch_size}")

        for i in range(0, total_texts, batch_size):
            batch = texts[i:i + batch_size]

            try:
                # Handle empty strings in batch
                processed_batch = [text if text else " " for text in batch]

                # Generate embeddings for this batch
                batch_embeddings = self.model.encode(
                    processed_batch,
                    convert_to_numpy=True,
                    show_progress_bar=False
                )

                # Convert to list and extend results
                all_embeddings.extend([emb.tolist() for emb in batch_embeddings])

                # Force garbage collection to free memory
                if force_gc and i + batch_size < total_texts:
                    del batch_embeddings
                    gc.collect()

            except Exception as e:
                self.logger.error(f"Error embedding batch {i//batch_size + 1}: {e}")
                # Return partial results rather than failing completely
                break

        self.logger.info(f"Successfully embedded {len(all_embeddings)}/{total_texts} chunks")
        return all_embeddings

    @staticmethod
    def cosine_similarity(embedding1: List[float], embedding2: List[float]) -> float:
        """
        Calculate cosine similarity between two embeddings.

        Cosine similarity ranges from -1 (opposite) to 1 (identical).
        Values closer to 1 indicate higher semantic similarity.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score between -1 and 1
        """
        try:
            # Convert to numpy arrays
            emb1 = np.array(embedding1)
            emb2 = np.array(embedding2)

            # Calculate cosine similarity
            dot_product = np.dot(emb1, emb2)
            norm1 = np.linalg.norm(emb1)
            norm2 = np.linalg.norm(emb2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            similarity = dot_product / (norm1 * norm2)

            # Ensure result is in valid range (due to floating point errors)
            return float(np.clip(similarity, -1.0, 1.0))

        except Exception as e:
            logging.error(f"Error calculating cosine similarity: {e}")
            raise

    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings produced by this model.

        Returns:
            Embedding dimension (384 for all-MiniLM-L6-v2)
        """
        return self.model.get_sentence_embedding_dimension()
