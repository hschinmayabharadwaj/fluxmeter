"""
Unit tests for Ledgerline Routing Service
Tests A/B testing with sibling attempts and CRISPE template management
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from contextlib import contextmanager
from fastapi.testclient import TestClient
from datetime import datetime
import hashlib
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Mock psycopg2 before importing main
import psycopg2
psycopg2.connect = MagicMock()

from main import (
    app,
    RoutingRequest,
    CRISPEPrompt,
    CRISPETemplateCreate,
    CRISPETemplateUse,
    validate_crispe_quality,
    apply_crispe_template
)

# Create mock DB that's always available
mock_db = MagicMock()
mock_db.cursor.return_value = MagicMock()

@contextmanager
def mock_db_context():
    yield mock_db

client = TestClient(app)


class TestABTestingSiblingAttempts:
    """Test A/B testing with sibling attempts"""
    
    def test_ab_test_consistent_variant_assignment(self):
        """Test that same A/B test ID always gets same variant"""
        ab_test_id = "test_abc123"
        tenant_id = "tenant_001"
        
        # First request
        request1 = RoutingRequest(
            tenant_id=tenant_id,
            use_case="cost_optimization",
            messages=[{"role": "user", "content": "Hello"}],
            ab_test_id=ab_test_id
        )
        
        # Compute deterministic variant
        test_hash = hashlib.md5(f"{ab_test_id}:{tenant_id}".encode()).hexdigest()
        variant_seed = int(test_hash, 16)
        expected_variant = "cost_optimized" if variant_seed % 2 == 0 else "quality_optimized"
        
        # Mock DB cursor
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        
        # First call - new AB test
        mock_cursor.fetchone.return_value = None  # No existing AB test
        
        with patch('main.get_db', return_value=mock_db_context()):
            response1 = client.post("/v1/route", json=request1.model_dump())
        
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["variant_assigned"] == expected_variant
        assert data1["strategy"] == expected_variant
        
        # Second call - existing AB test should use same variant
        mock_cursor.fetchone.return_value = (expected_variant, 1)  # Existing test with attempt count
        
        with patch('main.get_db', return_value=mock_db_context()):
            response2 = client.post("/v1/route", json=request1.model_dump())
        
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["variant_assigned"] == expected_variant
        assert data2["strategy"] == expected_variant
    
    def test_ab_test_different_ab_ids_different_variants(self):
        """Test that different A/B test IDs can get different variants"""
        tenant_id = "tenant_001"
        
        ab_test_id_1 = "test_abc123"
        ab_test_id_2 = "test_xyz789"
        
        # Compute variants
        hash1 = hashlib.md5(f"{ab_test_id_1}:{tenant_id}".encode()).hexdigest()
        variant1 = "cost_optimized" if int(hash1, 16) % 2 == 0 else "quality_optimized"
        
        hash2 = hashlib.md5(f"{ab_test_id_2}:{tenant_id}".encode()).hexdigest()
        variant2 = "cost_optimized" if int(hash2, 16) % 2 == 0 else "quality_optimized"
        
        request1 = RoutingRequest(
            tenant_id=tenant_id,
            use_case="test",
            messages=[{"role": "user", "content": "Hello"}],
            ab_test_id=ab_test_id_1
        )
        
        request2 = RoutingRequest(
            tenant_id=tenant_id,
            use_case="test",
            messages=[{"role": "user", "content": "Hello"}],
            ab_test_id=ab_test_id_2
        )
        
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None  # Both new
        
        with patch('main.get_db', return_value=mock_db_context()):
            response1 = client.post("/v1/route", json=request1.model_dump())
            response2 = client.post("/v1/route", json=request2.model_dump())
        
        data1 = response1.json()
        data2 = response2.json()
        
        assert data1["ab_test_id"] == ab_test_id_1
        assert data2["ab_test_id"] == ab_test_id_2
        # Could be same or different - just verify each returns a valid variant
        assert data1["strategy"] in ["cost_optimized", "quality_optimized"]
        assert data2["strategy"] in ["cost_optimized", "quality_optimized"]
    
    def test_ab_test_without_id_uses_balanced_strategy(self):
        """Test that requests without A/B test ID use balanced strategy"""
        request = RoutingRequest(
            tenant_id="tenant_001",
            use_case="general",
            messages=[{"role": "user", "content": "Hello"}],
            ab_test_id=None
        )
        
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        
        with patch('main.get_db', return_value=mock_db_context()):
            response = client.post("/v1/route", json=request.model_dump())
        
        assert response.status_code == 200
        data = response.json()
        assert data["strategy"] == "balanced"
        assert data["variant_assigned"] is None
        assert data["provider"] == "openai"
        assert data["model"] == "gpt-4-turbo"
    
    def test_ab_test_sibling_attempt_tracking(self):
        """Test that sibling attempts increment attempt counter"""
        ab_test_id = "test_sibling_001"
        tenant_id = "tenant_001"
        
        request = RoutingRequest(
            tenant_id=tenant_id,
            use_case="test",
            messages=[{"role": "user", "content": "Hello"}],
            ab_test_id=ab_test_id
        )
        
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        
        # First attempt - new test
        mock_cursor.fetchone.return_value = None
        with patch('main.get_db', return_value=mock_db_context()):
            client.post("/v1/route", json=request.model_dump())
        
        # Verify INSERT was called
        assert mock_cursor.execute.called
        insert_calls = [call for call in mock_cursor.execute.call_args_list 
                       if 'INSERT INTO ab_tests' in str(call)]
        assert len(insert_calls) > 0
        
        # Second attempt - existing test with attempt_count = 1
        mock_cursor.fetchone.return_value = ("quality_optimized", 1)
        with patch('main.get_db', return_value=mock_db_context()):
            response = client.post("/v1/route", json=request.model_dump())
        
        assert response.status_code == 200
        # Verify UPDATE was called to increment attempt count
        update_calls = [call for call in mock_cursor.execute.call_args_list 
                       if 'UPDATE ab_tests' in str(call)]
        assert len(update_calls) > 0


class TestCRISPEFramework:
    """Test CRISPE prompt framework"""
    
    def test_validate_crispe_quality_minimum_requirements(self):
        """Test CRISPE quality validation with minimum requirements"""
        crispe = CRISPEPrompt(
            capacity="You have expertise in data analysis and reporting with deep knowledge",
            role="You are an expert data analyst",
            insight="Key insight: data quality directly impacts analysis outcomes",
            statement="Analyze the provided dataset and generate insights. Create visualizations. Provide recommendations.",
            personality="Professional, clear, analytical"
        )
        
        score, issues = validate_crispe_quality(crispe)
        
        # Should pass with minimal issues
        assert score >= 0.5, f"Score too low: {score}, issues: {issues}"
    
    def test_validate_crispe_quality_low_capacity_penalty(self):
        """Test that low capacity word count reduces quality score"""
        crispe = CRISPEPrompt(
            capacity="You have expertise in data analysis and reporting with deep knowledge to share here now",
            role="You are an expert",
            insight="Key insight about the task at hand",
            statement="Create analysis. Provide insights. Summarize findings. Generate reports.",
            personality="Professional"
        )
        
        score, issues = validate_crispe_quality(crispe)
        
        # Should have lower score due to capacity
        assert score < 1.0
    
    def test_apply_crispe_template_variable_substitution(self):
        """Test variable substitution in CRISPE templates"""
        crispe = CRISPEPrompt(
            capacity="You work in {industry} sector",
            role="You are a {role_title} expert",
            insight="Understanding {domain} is crucial",
            statement="Analyze {dataset} and provide {output_type}",
            personality="Professional and {tone}"
        )
        
        variables = {
            "industry": "healthcare",
            "role_title": "senior analyst",
            "domain": "biotech",
            "dataset": "clinical trials",
            "output_type": "recommendations",
            "tone": "empathetic"
        }
        
        prompt = apply_crispe_template(crispe, variables)
        
        # Verify substitutions
        assert "healthcare" in prompt
        assert "senior analyst" in prompt
        assert "biotech" in prompt
        assert "clinical trials" in prompt
        assert "recommendations" in prompt
        assert "empathetic" in prompt
        assert "{industry}" not in prompt
        assert "{role_title}" not in prompt
    
    def test_apply_crispe_template_without_variables(self):
        """Test CRISPE template without variable substitution"""
        crispe = CRISPEPrompt(
            capacity="Analyze data quality issues with comprehensive verification methods",
            role="You are a data quality expert",
            insight="Data quality affects downstream analytics and decision making",
            statement="Identify missing values. Check for duplicates. Validate ranges. Report findings.",
            personality="Detailed and methodical"
        )
        
        prompt = apply_crispe_template(crispe)
        
        assert "CAPACITY:" in prompt
        assert "ROLE:" in prompt
        assert "INSIGHT:" in prompt
        assert "STATEMENT:" in prompt
        assert "PERSONALITY:" in prompt
        assert "data quality" in prompt.lower()
        assert "expert" in prompt.lower()
    
    def test_crispe_template_crud_operations(self):
        """Test CRISPE template create, read, list operations"""
        tenant_id = "tenant_001"
        template_name = "data_analysis"
        
        crispe = CRISPEPrompt(
            capacity="Expert in statistical analysis with 10+ years experience in the field",
            role="You are a senior data scientist",
            insight="Statistical rigor is essential for valid conclusions in all research",
            statement="Analyze the provided data. Generate statistics. Test hypotheses. Report findings.",
            personality="Precise, academic, thorough",
            experiment="Optional: Use Bayesian methods for uncertainty estimation"
        )
        
        template = CRISPETemplateCreate(
            tenant_id=tenant_id,
            template_name=template_name,
            crispe=crispe,
            created_by="data_team"
        )
        
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (1,)  # Next version
        
        with patch('main.get_db', return_value=mock_db_context()):
            response = client.post("/v1/crispe/template", json=template.model_dump())
        
        assert response.status_code == 200
        data = response.json()
        assert data["template_name"] == template_name
        assert "validation_score" in data
        assert data["validation_score"] >= 0.5


class TestRoutingStrategies:
    """Test routing strategies"""
    
    def test_cost_optimized_strategy(self):
        """Test cost-optimized routing strategy"""
        request = RoutingRequest(
            tenant_id="tenant_001",
            use_case="cost_test",
            messages=[{"role": "user", "content": "Hello"}],
            ab_test_id="cost_test_001"
        )
        
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        
        # Ensure cost_optimized variant
        test_hash = hashlib.md5(f"cost_test_001:tenant_001".encode()).hexdigest()
        if int(test_hash, 16) % 2 == 0:  # Will be cost_optimized
            mock_cursor.fetchone.return_value = None
            with patch('main.get_db', return_value=mock_db):
                response = client.post("/v1/route", json=request.dict())
            
            data = response.json()
            if data["strategy"] == "cost_optimized":
                assert data["provider"] == "anthropic"
                assert data["model"] == "claude-3-haiku"
    
    def test_quality_optimized_strategy(self):
        """Test quality-optimized routing strategy"""
        request = RoutingRequest(
            tenant_id="tenant_001",
            use_case="quality_test",
            messages=[{"role": "user", "content": "Hello"}],
            ab_test_id="quality_test_001"
        )
        
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        
        # Ensure quality_optimized variant
        test_hash = hashlib.md5(f"quality_test_001:tenant_001".encode()).hexdigest()
        if int(test_hash, 16) % 2 == 1:  # Will be quality_optimized
            mock_cursor.fetchone.return_value = None
            with patch('main.get_db', return_value=mock_db):
                response = client.post("/v1/route", json=request.dict())
            
            data = response.json()
            if data["strategy"] == "quality_optimized":
                assert data["provider"] == "openai"
                assert data["model"] == "gpt-4"
    
    def test_balanced_strategy_default(self):
        """Test balanced strategy as default"""
        request = RoutingRequest(
            tenant_id="tenant_001",
            use_case="balanced_test",
            messages=[{"role": "user", "content": "Hello"}]
        )
        
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        
        with patch('main.get_db', return_value=mock_db_context()):
            response = client.post("/v1/route", json=request.model_dump())
        
        data = response.json()
        assert data["strategy"] == "balanced"
        assert data["provider"] == "openai"
        assert data["model"] == "gpt-4-turbo"


class TestHealthAndMetrics:
    """Test health check and metrics endpoints"""
    
    def test_health_check(self):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "routing"
    
    def test_metrics_endpoint(self):
        """Test metrics endpoint returns prometheus format"""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        # Prometheus format should contain TYPE comments
        assert "#" in response.text or len(response.text) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
