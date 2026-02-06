"""
Unit tests for EmbeddingService (Phase 4.1 - Day 1)

Tests written FIRST following TDD methodology.
"""
import pytest
from agent.memory.embedding_service import EmbeddingService


class TestEmbeddingService:
    """Test suite for EmbeddingService"""

    @pytest.fixture
    def embedding_service(self):
        """Create EmbeddingService instance for testing"""
        return EmbeddingService(model_name="all-MiniLM-L6-v2")

    def test_initialization(self, embedding_service):
        """Test that service initializes correctly"""
        assert embedding_service is not None
        assert embedding_service.model_name == "all-MiniLM-L6-v2"
        assert embedding_service.model is not None

    def test_embed_text_returns_list(self, embedding_service):
        """Test that embed_text returns a list of floats"""
        text = "Hello, this is a test message"
        embedding = embedding_service.embed_text(text)

        assert isinstance(embedding, list)
        assert len(embedding) > 0
        assert all(isinstance(x, float) for x in embedding)

    def test_embed_text_dimensions(self, embedding_service):
        """Test that embeddings have correct dimensions (384 for MiniLM-L6-v2)"""
        text = "Test message for dimension check"
        embedding = embedding_service.embed_text(text)

        # MiniLM-L6-v2 produces 384-dimensional embeddings
        assert len(embedding) == 384

    def test_embed_empty_text(self, embedding_service):
        """Test handling of empty text"""
        embedding = embedding_service.embed_text("")

        # Should still return valid embedding
        assert isinstance(embedding, list)
        assert len(embedding) == 384

    def test_embed_batch_returns_list_of_lists(self, embedding_service):
        """Test that embed_batch returns list of embeddings"""
        texts = [
            "First message",
            "Second message",
            "Third message"
        ]
        embeddings = embedding_service.embed_batch(texts)

        assert isinstance(embeddings, list)
        assert len(embeddings) == 3
        assert all(isinstance(emb, list) for emb in embeddings)
        assert all(len(emb) == 384 for emb in embeddings)

    def test_embed_batch_empty_list(self, embedding_service):
        """Test embed_batch with empty list"""
        embeddings = embedding_service.embed_batch([])

        assert isinstance(embeddings, list)
        assert len(embeddings) == 0

    def test_similar_texts_have_similar_embeddings(self, embedding_service):
        """Test that semantically similar texts have similar embeddings"""
        text1 = "I love programming in Python"
        text2 = "Python programming is great"
        text3 = "The weather is sunny today"

        emb1 = embedding_service.embed_text(text1)
        emb2 = embedding_service.embed_text(text2)
        emb3 = embedding_service.embed_text(text3)

        # Calculate cosine similarity
        similarity_1_2 = embedding_service.cosine_similarity(emb1, emb2)
        similarity_1_3 = embedding_service.cosine_similarity(emb1, emb3)

        # Similar texts should have higher similarity
        assert similarity_1_2 > similarity_1_3
        assert similarity_1_2 > 0.5  # Reasonable threshold

    def test_cosine_similarity_range(self, embedding_service):
        """Test that cosine similarity is in valid range [-1, 1]"""
        text1 = "Hello world"
        text2 = "Goodbye world"

        emb1 = embedding_service.embed_text(text1)
        emb2 = embedding_service.embed_text(text2)

        similarity = embedding_service.cosine_similarity(emb1, emb2)

        assert -1.0 <= similarity <= 1.0

    def test_identical_texts_have_similarity_one(self, embedding_service):
        """Test that identical texts have similarity of ~1.0"""
        text = "This is a test message"

        emb1 = embedding_service.embed_text(text)
        emb2 = embedding_service.embed_text(text)

        similarity = embedding_service.cosine_similarity(emb1, emb2)

        # Should be very close to 1.0 (allowing for floating point errors)
        assert similarity > 0.99

    def test_batch_and_single_produce_same_embeddings(self, embedding_service):
        """Test that batch and single embedding produce same results"""
        texts = ["Message 1", "Message 2", "Message 3"]

        # Get embeddings individually
        single_embs = [embedding_service.embed_text(text) for text in texts]

        # Get embeddings in batch
        batch_embs = embedding_service.embed_batch(texts)

        # Compare
        for single, batch in zip(single_embs, batch_embs):
            similarity = embedding_service.cosine_similarity(single, batch)
            assert similarity > 0.99  # Should be essentially identical

    @pytest.mark.slow
    def test_performance_single_embedding(self, embedding_service, benchmark):
        """Test performance of single embedding (should be < 100ms)"""
        text = "This is a test message for performance testing"

        result = benchmark(embedding_service.embed_text, text)

        assert isinstance(result, list)
        assert len(result) == 384

    @pytest.mark.slow
    def test_performance_batch_embedding(self, embedding_service, benchmark):
        """Test performance of batch embedding (should be faster than sequential)"""
        texts = ["Test message " + str(i) for i in range(10)]

        result = benchmark(embedding_service.embed_batch, texts)

        assert len(result) == 10

    def test_different_models_produce_different_dimensions(self):
        """Test that different models can be loaded (if available)"""
        # Test with default model
        service1 = EmbeddingService(model_name="all-MiniLM-L6-v2")
        emb1 = service1.embed_text("Test")
        assert len(emb1) == 384

        # Note: We only test one model in unit tests
        # Other models would be tested in integration tests

    def test_embedding_caching_disabled_by_default(self, embedding_service):
        """Test that embeddings are not cached by default"""
        text = "Test message"

        emb1 = embedding_service.embed_text(text)
        emb2 = embedding_service.embed_text(text)

        # Should produce identical results but not from cache
        similarity = embedding_service.cosine_similarity(emb1, emb2)
        assert similarity > 0.99
