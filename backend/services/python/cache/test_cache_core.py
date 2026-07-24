"""
Unit tests for Ledgerline Semantic Cache Service
Tests triple-tag validation
Focus: Core business logic without Qdrant/Redis dependencies
"""
import pytest
from semantic_cache import (
    validate_triple_tags,
    CacheEntry,
    HitReason
)


class TestTripleTagValidation:
    """Test triple-tag validation for policy version, region, and provider"""
    
    def test_valid_triple_tags(self):
        """Test validation passes with valid triple-tags"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="What is machine learning?",
            response="Machine learning is a subset of AI...",
            policy_version="v1.0.0",
            region="us-east-1",
            provider="openai",
            model="gpt-4",
            estimated_tokens=100
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        assert is_valid is True
        assert len(errors) == 0
    
    def test_empty_policy_version_fails(self):
        """Test validation fails with empty policy_version"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test",
            response="Response",
            policy_version="",  # Empty - INVALID
            region="us-east-1",
            provider="openai",
            model="gpt-4"
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        assert is_valid is False
        assert any("policy_version" in err.lower() and "empty" in err.lower() for err in errors)
    
    def test_empty_region_fails(self):
        """Test validation fails with empty region"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test",
            response="Response",
            policy_version="v1.0.0",
            region="",  # Empty - INVALID
            provider="openai",
            model="gpt-4"
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        assert is_valid is False
        assert any("region" in err.lower() and "empty" in err.lower() for err in errors)
    
    def test_empty_provider_fails(self):
        """Test validation fails with empty provider"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test",
            response="Response",
            policy_version="v1.0.0",
            region="us-east-1",
            provider="",  # Empty - INVALID
            model="gpt-4"
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        assert is_valid is False
        assert any("provider" in err.lower() and "empty" in err.lower() for err in errors)
    
    def test_invalid_policy_version_characters(self):
        """Test validation fails with invalid characters in policy_version"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test",
            response="Response",
            policy_version="v1@@@.0",  # Invalid @ characters
            region="us-east-1",
            provider="openai",
            model="gpt-4"
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        assert is_valid is False
        assert any("invalid characters" in err.lower() for err in errors)
    
    def test_invalid_region_characters(self):
        """Test validation fails with invalid characters in region"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test",
            response="Response",
            policy_version="v1.0.0",
            region="us@east#1",  # Invalid @# characters
            provider="openai",
            model="gpt-4"
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        assert is_valid is False
        assert any("invalid characters" in err.lower() for err in errors)
    
    def test_invalid_provider_not_in_allowed_list(self):
        """Test validation fails when provider not in allowed list"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test",
            response="Response",
            policy_version="v1.0.0",
            region="us-east-1",
            provider="invalid_provider",  # Not in [openai, anthropic, cohere, mistral]
            model="gpt-4"
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        assert is_valid is False
        assert any("not in allowed list" in err.lower() for err in errors)
    
    def test_allowed_providers_pass_validation(self):
        """Test all allowed providers pass validation"""
        allowed_providers = ["openai", "anthropic", "cohere", "mistral"]
        
        for provider in allowed_providers:
            entry = CacheEntry(
                tenant_id="tenant_001",
                prompt="Test",
                response="Response",
                policy_version="v1.0.0",
                region="us-east-1",
                provider=provider,
                model="test-model"
            )
            
            is_valid, errors = validate_triple_tags(entry)
            
            assert is_valid is True, f"Provider {provider} should be valid but got errors: {errors}"
    
    def test_policy_version_max_length(self):
        """Test validation fails when policy_version exceeds max length (255)"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test",
            response="Response",
            policy_version="v" + "1" * 260,  # 261 chars > 255 max
            region="us-east-1",
            provider="openai",
            model="gpt-4"
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        assert is_valid is False
        assert any("exceeds max length" in err.lower() for err in errors)
    
    def test_region_max_length(self):
        """Test validation fails when region exceeds max length (64)"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test",
            response="Response",
            policy_version="v1.0.0",
            region="region-" + "x" * 60,  # 67 chars > 64 max
            provider="openai",
            model="gpt-4"
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        assert is_valid is False
        assert any("exceeds max length" in err.lower() for err in errors)
    
    def test_provider_max_length(self):
        """Test validation fails when provider exceeds max length (64)"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test",
            response="Response",
            policy_version="v1.0.0",
            region="us-east-1",
            provider="p" * 70,  # 70 chars > 64 max
            model="gpt-4"
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        assert is_valid is False
        assert any("exceeds max length" in err.lower() for err in errors)
    
    def test_valid_policy_version_formats(self):
        """Test various valid policy_version formats"""
        valid_formats = [
            "v1",
            "v1.0",
            "v1.0.0",
            "v2024-07",
            "v2024.07.24",
            "v1-beta",
            "v1_final",
            "2024-07-24",
        ]
        
        for policy_version in valid_formats:
            entry = CacheEntry(
                tenant_id="tenant_001",
                prompt="Test",
                response="Response",
                policy_version=policy_version,
                region="us-east-1",
                provider="openai",
                model="gpt-4"
            )
            
            is_valid, errors = validate_triple_tags(entry)
            
            assert is_valid is True, f"Policy version '{policy_version}' should be valid but got errors: {errors}"
    
    def test_valid_region_formats(self):
        """Test various valid region formats"""
        valid_formats = [
            "us-east-1",
            "eu-west-1",
            "ap_southeast_1",
            "us_west_2",
            "region-1",
            "global",
        ]
        
        for region in valid_formats:
            entry = CacheEntry(
                tenant_id="tenant_001",
                prompt="Test",
                response="Response",
                policy_version="v1.0.0",
                region=region,
                provider="openai",
                model="gpt-4"
            )
            
            is_valid, errors = validate_triple_tags(entry)
            
            assert is_valid is True, f"Region '{region}' should be valid but got errors: {errors}"
    
    def test_case_insensitive_provider_validation(self):
        """Test provider validation is case insensitive"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test",
            response="Response",
            policy_version="v1.0.0",
            region="us-east-1",
            provider="OpenAI",  # Mixed case
            model="gpt-4"
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        # Should pass because validation converts to lowercase
        assert is_valid is True, f"Mixed case provider should be valid but got errors: {errors}"
    
    def test_multiple_validation_errors(self):
        """Test entry with multiple validation errors"""
        entry = CacheEntry(
            tenant_id="tenant_001",
            prompt="Test",
            response="Response",
            policy_version="",  # Empty - ERROR
            region="",  # Empty - ERROR
            provider="invalid_provider",  # Not in allowed list - ERROR
            model="gpt-4"
        )
        
        is_valid, errors = validate_triple_tags(entry)
        
        assert is_valid is False
        assert len(errors) >= 3, f"Expected at least 3 errors but got {len(errors)}: {errors}"


class TestHitReasons:
    """Test cache hit reason enumeration"""
    
    def test_hit_reason_enum_values(self):
        """Test that all expected hit reasons exist"""
        expected_reasons = [
            "VALID_HIT",
            "POLICY_MISMATCH",
            "CONSENT_MISSING",
            "CONSENT_WITHDRAWN",
            "RATE_LIMIT_EXCEEDED",
            "EXPIRED",
            "INVALID_TAGS"
        ]
        
        for reason_name in expected_reasons:
            assert hasattr(HitReason, reason_name), f"HitReason.{reason_name} not found"
            reason = getattr(HitReason, reason_name)
            assert reason.value is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
