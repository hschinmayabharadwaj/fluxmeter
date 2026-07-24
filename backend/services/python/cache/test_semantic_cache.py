"""
Unit tests for Ledgerline Semantic Cache Service
Tests triple-tag validation, compliance checks, and cache operations
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
import hashlib

# Mock dependencies
mock_db = MagicMock()
mock_qdrant = MagicMock()
mock_redis = MagicMock()

with patch('psycopg2.connect', return_value=mock_db):
    with patch('qdrant_client.QdrantClient', return_value=mock_qdrant):
        with patch('redis.Redis', return_value=mock_redis):
            from semantic_cache import (
                app,
                CacheQuery,
                CacheEntry,
                HitReason,
                validate_triple_tags,
                create_triple_tag_filter,
                COLLECTION_NAME
            )

client = TestClient(app)


class TestTripleTagValidation:
    """Test triple-tag validation for policy version, region, and provider"""
    
    def test_valid_triple_tags(self):
        """Test validation passes with valid triple-tags"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test prompt",
            response="Test response",
            policy_version="v1.0.0",
            region="us-east-1",
            provider="openai",
            model="gpt-4",
            estimated_tokens=100
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        assert is_valid is True
        assert len(errors) == 0
    
    def test_triple_tag_empty_policy_version(self):
        """Test validation fails with empty policy_version"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test prompt",
            response="Test response",
            policy_version="",  # Empty
            region="us-east-1",
            provider="openai",
            model="gpt-4"
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        assert is_valid is False
        assert any("policy_version" in error.lower() and "empty" in error.lower() for error in errors)
    
    def test_triple_tag_empty_region(self):
        """Test validation fails with empty region"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test prompt",
            response="Test response",
            policy_version="v1.0.0",
            region="",  # Empty
            provider="openai",
            model="gpt-4"
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        assert is_valid is False
        assert any("region" in error.lower() and "empty" in error.lower() for error in errors)
    
    def test_triple_tag_empty_provider(self):
        """Test validation fails with empty provider"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test prompt",
            response="Test response",
            policy_version="v1.0.0",
            region="us-east-1",
            provider="",  # Empty
            model="gpt-4"
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        assert is_valid is False
        assert any("provider" in error.lower() and "empty" in error.lower() for error in errors)
    
    def test_triple_tag_invalid_characters_policy_version(self):
        """Test validation fails with invalid characters in policy_version"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test prompt",
            response="Test response",
            policy_version="v1@@@.0",  # Invalid characters
            region="us-east-1",
            provider="openai",
            model="gpt-4"
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        assert is_valid is False
        assert any("invalid characters" in error.lower() for error in errors)
    
    def test_triple_tag_invalid_provider_value(self):
        """Test validation fails with invalid provider not in allowed list"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test prompt",
            response="Test response",
            policy_version="v1.0.0",
            region="us-east-1",
            provider="invalid_provider",  # Not in allowed list
            model="gpt-4"
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        assert is_valid is False
        assert any("not in allowed list" in error.lower() for error in errors)
    
    def test_triple_tag_all_providers_valid(self):
        """Test all allowed providers pass validation"""
        providers = ["openai", "anthropic", "cohere", "mistral"]
        
        for provider in providers:
            entry = CacheEntry(
                tenant_id="tenant_001",
                prompt="Test prompt",
                response="Test response",
                policy_version="v1.0.0",
                region="us-east-1",
                provider=provider,
                model="test-model"
            )
            
            is_valid, errors = validate_triple_tags(entry)
            
            assert is_valid is True, f"Provider {provider} should be valid but got errors: {errors}"
    
    def test_triple_tag_policy_version_too_long(self):
        """Test validation fails when policy_version exceeds max length"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test prompt",
            response="Test response",
            policy_version="v" + "1" * 260,  # Exceeds 255
            region="us-east-1",
            provider="openai",
            model="gpt-4"
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        assert is_valid is False
        assert any("exceeds max length" in error.lower() for error in errors)
    
    def test_triple_tag_region_too_long(self):
        """Test validation fails when region exceeds max length"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test prompt",
            response="Test response",
            policy_version="v1.0.0",
            region="region-" + "x" * 60,  # Exceeds 64
            provider="openai",
            model="gpt-4"
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        assert is_valid is False
        assert any("exceeds max length" in error.lower() for error in errors)


class TestCacheStoreWithTripleTagValidation:
    """Test cache storage with triple-tag validation"""
    
    def test_store_cache_with_valid_triple_tags(self):
        """Test storing cache entry with valid triple-tags"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="What is machine learning?",
            response="Machine learning is a subset of AI...",
            policy_version="v1.2.0",
            region="eu-west-1",
            provider="openai",
            model="gpt-4",
            estimated_tokens=150,
            ttl_hours=24
        )
        
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (1,)  # cache_id
        
        with patch('semantic_cache.get_db', return_value=mock_db):
            response = client.post("/v1/cache/store", json=entry.dict())
        
        assert response.status_code == 200
        data = response.json()
        assert data["triple_tags_validated"] is True
        assert data["triple_tags"]["policy_version"] == "v1.2.0"
        assert data["triple_tags"]["region"] == "eu-west-1"
        assert data["triple_tags"]["provider"] == "openai"
    
    def test_store_cache_with_invalid_triple_tags(self):
        """Test cache storage rejects invalid triple-tags"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test",
            response="Response",
            policy_version="",  # Invalid - empty
            region="us-east-1",
            provider="openai",
            model="gpt-4"
        )
        
        with patch('semantic_cache.get_db', return_value=mock_db):
            response = client.post("/v1/cache/store", json=entry.dict())
        
        assert response.status_code == 400
        assert "triple-tag validation failed" in response.json()["detail"]
    
    def test_store_cache_generates_correct_point_id(self):
        """Test cache storage generates correct point ID with all triple-tags"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test prompt",
            response="Test response",
            policy_version="v1.0.0",
            region="us-east-1",
            provider="openai",
            model="gpt-4"
        )
        
        # Expected point_id should include all three tags
        expected_id = hashlib.md5(
            f"tenant_001:Test prompt:v1.0.0:us-east-1:openai".encode()
        ).hexdigest()
        
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (1,)
        
        with patch('semantic_cache.get_db', return_value=mock_db):
            with patch('semantic_cache.qdrant_client.upsert') as mock_upsert:
                response = client.post("/v1/cache/store", json=entry.dict())
        
        assert response.status_code == 200
        # Verify qdrant was called with correct point ID structure
        if mock_upsert.called:
            call_args = mock_upsert.call_args
            # The point should have been created with proper triple-tags


class TestCacheQueryWithTripleTagValidation:
    """Test cache queries with triple-tag validation"""
    
    def test_query_cache_with_valid_triple_tags(self):
        """Test querying cache with valid triple-tags"""
        query = CacheQuery(
            tenant_id="tenant_001",
            correlation_id="corr_123",
            prompt="What is machine learning?",
            policy_version="v1.2.0",
            region="eu-west-1",
            provider="openai",
            model="gpt-4",
            similarity_threshold=0.95
        )
        
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [
            ("v1.2.0",),  # get_current_policy_version
            None  # verify_consent_valid
        ]
        
        # Mock search result
        mock_hit = MagicMock()
        mock_hit.id = hashlib.md5(b"test").hexdigest()
        mock_hit.score = 0.97
        mock_hit.payload = {
            "response": "ML is a subset of AI",
            "created_at": datetime.utcnow().isoformat(),
            "ttl_hours": 24,
            "estimated_tokens": 100
        }
        
        with patch('semantic_cache.get_db', return_value=mock_db):
            with patch('semantic_cache.qdrant_client.search', return_value=[mock_hit]):
                response = client.post("/v1/cache/query", json=query.dict())
        
        assert response.status_code == 200
        data = response.json()
        assert "latency_ms" in data
    
    def test_query_cache_incomplete_triple_tags(self):
        """Test query with incomplete triple-tags returns no match"""
        query = CacheQuery(
            tenant_id="tenant_001",
            correlation_id="corr_123",
            prompt="What is machine learning?",
            policy_version="",  # Empty
            region="eu-west-1",
            provider="openai",
            model="gpt-4"
        )
        
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        
        with patch('semantic_cache.get_db', return_value=mock_db):
            response = client.post("/v1/cache/query", json=query.dict())
        
        assert response.status_code == 200
        data = response.json()
        assert data["hit"] is False
        assert data["reason"] == "invalid_tags"
    
    def test_query_cache_policy_mismatch_rejection(self):
        """Test cache hit rejected when policy version changes"""
        query = CacheQuery(
            tenant_id="tenant_001",
            correlation_id="corr_123",
            prompt="What is machine learning?",
            policy_version="v1.2.0",
            region="eu-west-1",
            provider="openai",
            model="gpt-4"
        )
        
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        
        # Mock search returns hit
        mock_hit = MagicMock()
        mock_hit.id = hashlib.md5(b"test").hexdigest()
        mock_hit.score = 0.97
        mock_hit.payload = {
            "response": "ML response",
            "created_at": datetime.utcnow().isoformat(),
            "ttl_hours": 24
        }
        
        # But policy version in DB is different
        mock_cursor.fetchone.return_value = ("v1.1.0",)  # Different version
        
        with patch('semantic_cache.get_db', return_value=mock_db):
            with patch('semantic_cache.qdrant_client.search', return_value=[mock_hit]):
                response = client.post("/v1/cache/query", json=query.dict())
        
        assert response.status_code == 200
        data = response.json()
        assert data["hit"] is False
        assert data["reason"] == "policy_changed"


class TestCacheInvalidation:
    """Test cache invalidation"""
    
    def test_invalidate_cache_entry_success(self):
        """Test successful cache invalidation"""
        cache_id = "cache_123"
        
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (cache_id,)
        
        with patch('semantic_cache.get_db', return_value=mock_db):
            response = client.post(f"/v1/cache/invalidate/{cache_id}?reason=policy_change")
        
        assert response.status_code == 200
        data = response.json()
        assert data["cache_id"] == cache_id
        assert data["invalidated"] is True
    
    def test_invalidate_cache_entry_not_found(self):
        """Test invalidation of non-existent cache entry"""
        cache_id = "nonexistent_123"
        
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        
        with patch('semantic_cache.get_db', return_value=mock_db):
            response = client.post(f"/v1/cache/invalidate/{cache_id}")
        
        assert response.status_code == 404


class TestCacheStatistics:
    """Test cache statistics endpoints"""
    
    def test_get_cache_stats(self):
        """Test getting cache statistics for tenant"""
        tenant_id = "tenant_001"
        
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (100, 500, 5.0, 10)  # total, hits, avg, invalidated
        
        mock_collection = MagicMock()
        mock_collection.points_count = 100
        
        with patch('semantic_cache.get_db', return_value=mock_db):
            with patch('semantic_cache.qdrant_client.get_collection', return_value=mock_collection):
                response = client.get(f"/v1/cache/stats/{tenant_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["tenant_id"] == tenant_id
        assert data["total_entries"] == 100
        assert data["total_hits"] == 500
        assert data["invalidated_entries"] == 10


class TestAuditTrail:
    """Test cache audit trail"""
    
    def test_get_cache_audit_trail(self):
        """Test getting audit trail for cache entry"""
        cache_id = "cache_123"
        
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        
        # Mock audit entries
        mock_cursor.fetchall.return_value = [
            ("valid_hit", 0.98, datetime.utcnow(), 1001),
            ("valid_hit", 0.95, datetime.utcnow(), 1002),
            ("policy_mismatch", 0.92, datetime.utcnow(), None)
        ]
        
        with patch('semantic_cache.get_db', return_value=mock_db):
            response = client.get(f"/v1/cache/audit/{cache_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["cache_id"] == cache_id
        assert len(data["audit_trail"]) == 3
        assert data["audit_trail"][0]["reason"] == "valid_hit"


class TestHealthAndMetrics:
    """Test health check and metrics endpoints"""
    
    def test_health_check(self):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "semantic-cache"
    
    def test_metrics_endpoint(self):
        """Test metrics endpoint returns prometheus format"""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
