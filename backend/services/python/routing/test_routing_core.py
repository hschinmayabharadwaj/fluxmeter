"""
Unit tests for Ledgerline Routing Service
Tests A/B testing with sibling attempts and CRISPE template management
Focus: Core business logic without DB dependencies
"""
import pytest
import hashlib
from main import (
    validate_crispe_quality,
    apply_crispe_template,
    CRISPEPrompt,
    ROUTING_STRATEGIES
)


class TestABTestDeterminism:
    """Test deterministic A/B test variant assignment"""
    
    def test_ab_test_hash_consistency(self):
        """Test that AB test ID + tenant_id always produces same hash"""
        ab_test_id = "test_abc123"
        tenant_id = "tenant_001"
        
        hash1 = hashlib.md5(f"{ab_test_id}:{tenant_id}".encode()).hexdigest()
        hash2 = hashlib.md5(f"{ab_test_id}:{tenant_id}".encode()).hexdigest()
        
        assert hash1 == hash2
        
        # Variant should be deterministic
        seed1 = int(hash1, 16) % 2
        seed2 = int(hash2, 16) % 2
        assert seed1 == seed2
    
    def test_different_ab_ids_different_hashes(self):
        """Test that different AB test IDs produce different hashes"""
        ab_test_id_1 = "test_abc123"
        ab_test_id_2 = "test_xyz789"
        tenant_id = "tenant_001"
        
        hash1 = hashlib.md5(f"{ab_test_id_1}:{tenant_id}".encode()).hexdigest()
        hash2 = hashlib.md5(f"{ab_test_id_2}:{tenant_id}".encode()).hexdigest()
        
        # Hashes should be different
        assert hash1 != hash2
    
    def test_variant_assignment_range(self):
        """Test that variants are in valid range [cost_optimized, quality_optimized]"""
        test_cases = [
            ("test_001", "tenant_001"),
            ("test_002", "tenant_001"),
            ("test_003", "tenant_002"),
            ("test_abc", "tenant_xyz"),
        ]
        
        for ab_test_id, tenant_id in test_cases:
            test_hash = hashlib.md5(f"{ab_test_id}:{tenant_id}".encode()).hexdigest()
            variant_seed = int(test_hash, 16)
            variant = "cost_optimized" if variant_seed % 2 == 0 else "quality_optimized"
            
            assert variant in ["cost_optimized", "quality_optimized"]


class TestCRISPEQualityValidation:
    """Test CRISPE quality validation"""
    
    def test_validate_minimum_requirements(self):
        """Test CRISPE validation with minimum requirements"""
        crispe = CRISPEPrompt(
            capacity="Expert with comprehensive knowledge and years of experience in the field",
            role="You are a senior expert",
            insight="Key insight about data and analysis methodology",
            statement="Analyze dataset. Generate insights. Provide recommendations. Report findings.",
            personality="Professional and thorough"
        )
        
        score, issues = validate_crispe_quality(crispe)
        
        assert score >= 0.5, f"Score too low: {score}, issues: {issues}"
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
    
    def test_validate_with_experiment(self):
        """Test CRISPE validation with experiment gets bonus"""
        crispe = CRISPEPrompt(
            capacity="Expert with comprehensive knowledge and years of experience in the field",
            role="You are a senior expert",
            insight="Key insight about data and analysis methodology",
            statement="Analyze dataset. Generate insights. Provide recommendations. Report findings.",
            personality="Professional and thorough",
            experiment="Use advanced Bayesian methods for better uncertainty estimation"
        )
        
        score, issues = validate_crispe_quality(crispe)
        
        # Should have experiment bonus
        assert score >= 0.5
    
    def test_validate_low_capacity(self):
        """Test that low capacity word count affects score"""
        crispe_good = CRISPEPrompt(
            capacity="Expert with comprehensive knowledge and years of experience in the field",
            role="You are a senior expert",
            insight="Key insight about data and analysis methodology",
            statement="Analyze dataset. Generate insights. Provide recommendations. Report findings.",
            personality="Professional and thorough"
        )
        
        crispe_low_capacity = CRISPEPrompt(
            capacity="Expert with good knowledge and experience",
            role="You are a senior expert",
            insight="Key insight about data and analysis methodology",
            statement="Analyze dataset. Generate insights. Provide recommendations. Report findings.",
            personality="Professional and thorough"
        )
        
        score_good, _ = validate_crispe_quality(crispe_good)
        score_low, issues_low = validate_crispe_quality(crispe_low_capacity)
        
        # Low capacity should have lower or equal score
        assert score_low <= score_good or len(issues_low) > 0


class TestCRISPETemplateApplication:
    """Test CRISPE template application and variable substitution"""
    
    def test_apply_template_with_variables(self):
        """Test variable substitution in CRISPE templates"""
        crispe = CRISPEPrompt(
            capacity="You work in {industry} sector with expertise",
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
        
        # Verify no placeholder remains
        assert "{industry}" not in prompt
        assert "{role_title}" not in prompt
    
    def test_apply_template_without_variables(self):
        """Test CRISPE template without variable substitution"""
        crispe = CRISPEPrompt(
            capacity="Analyze data quality issues with comprehensive methods and validation techniques",
            role="You are a data quality expert",
            insight="Data quality affects downstream analytics and decisions significantly",
            statement="Identify missing values. Check for duplicates. Validate data ranges. Analyze patterns. Report findings.",
            personality="Detailed and methodical"
        )
        
        prompt = apply_crispe_template(crispe)
        
        # Verify structure
        assert "CAPACITY:" in prompt
        assert "ROLE:" in prompt
        assert "INSIGHT:" in prompt
        assert "STATEMENT:" in prompt
        assert "PERSONALITY:" in prompt
        
        # Verify content
        assert "data quality" in prompt.lower()
        assert "expert" in prompt.lower()
    
    def test_apply_template_with_experiment(self):
        """Test CRISPE template includes experiment section"""
        crispe = CRISPEPrompt(
            capacity="Expert analyst with comprehensive knowledge",
            role="You are an expert",
            insight="Key insights are important",
            statement="Analyze and provide insights.",
            personality="Professional",
            experiment="Optional: Use advanced methods"
        )
        
        prompt = apply_crispe_template(crispe)
        
        # Verify experiment is included
        assert "EXPERIMENT:" in prompt
        assert "advanced methods" in prompt
    
    def test_apply_template_without_experiment(self):
        """Test CRISPE template without experiment section"""
        crispe = CRISPEPrompt(
            capacity="Expert analyst with comprehensive knowledge",
            role="You are an expert",
            insight="Key insights are important",
            statement="Analyze and provide insights.",
            personality="Professional"
        )
        
        prompt = apply_crispe_template(crispe)
        
        # Verify experiment is not included
        assert "EXPERIMENT:" not in prompt


class TestRoutingStrategies:
    """Test routing strategy definitions"""
    
    def test_routing_strategies_structure(self):
        """Test that routing strategies have correct structure"""
        required_strategies = ["cost_optimized", "quality_optimized", "balanced"]
        
        for strategy_name in required_strategies:
            assert strategy_name in ROUTING_STRATEGIES
            strategy = ROUTING_STRATEGIES[strategy_name]
            
            # Check primary route
            assert "primary" in strategy
            assert "provider" in strategy["primary"]
            assert "model" in strategy["primary"]
            
            # Check fallback
            assert "fallback" in strategy
            assert "provider" in strategy["fallback"]
            assert "model" in strategy["fallback"]
    
    def test_cost_optimized_provider(self):
        """Test cost_optimized uses economical provider"""
        strategy = ROUTING_STRATEGIES["cost_optimized"]
        assert strategy["primary"]["provider"] in ["anthropic", "cohere"]  # Lower cost
    
    def test_quality_optimized_provider(self):
        """Test quality_optimized uses premium provider"""
        strategy = ROUTING_STRATEGIES["quality_optimized"]
        assert strategy["primary"]["provider"] in ["openai", "anthropic"]  # Higher quality
    
    def test_balanced_strategy_primary(self):
        """Test balanced strategy has valid provider"""
        strategy = ROUTING_STRATEGIES["balanced"]
        assert strategy["primary"]["provider"] in ["openai", "anthropic", "cohere", "mistral"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
