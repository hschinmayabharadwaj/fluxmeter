-- Ledgerline PostgreSQL Schema
-- Designed for zero-silent-loss guarantees and comprehensive audit trails

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- For fast text search

-- Tenants table with RBAC and configuration
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'deleted')),
    
    -- Rate limits
    tpm_limit INTEGER DEFAULT 10000, -- Tokens per minute
    rpm_limit INTEGER DEFAULT 100,   -- Requests per minute
    
    -- Billing configuration
    billing_enabled BOOLEAN DEFAULT true,
    cost_multiplier DECIMAL(5,2) DEFAULT 1.0,
    
    -- Data retention
    retention_days INTEGER DEFAULT 90,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Tenant API keys (stored encrypted in Vault, only references here)
CREATE TABLE IF NOT EXISTS tenant_api_keys (
    key_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    key_name VARCHAR(255) NOT NULL,
    key_hash VARCHAR(255) NOT NULL UNIQUE,
    vault_path VARCHAR(500) NOT NULL, -- Path to encrypted key in HashiCorp Vault
    
    provider VARCHAR(50) NOT NULL CHECK (provider IN ('openai', 'anthropic', 'cohere')),
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
    
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    
    UNIQUE(tenant_id, key_name, provider)
);

-- Main ledger table - the source of truth for all billing
CREATE TABLE IF NOT EXISTS ledger (
    id BIGSERIAL PRIMARY KEY,
    correlation_id VARCHAR(255) NOT NULL,
    attempt_id VARCHAR(255) NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    
    -- Request details
    provider VARCHAR(50) NOT NULL,
    model VARCHAR(100) NOT NULL,
    request_type VARCHAR(50) DEFAULT 'completion',
    
    -- Token accounting
    token_count INTEGER NOT NULL DEFAULT 0,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    
    -- Cost calculation
    estimated_cost DECIMAL(12,6) DEFAULT 0.0,
    actual_cost DECIMAL(12,6),
    currency VARCHAR(10) DEFAULT 'USD',
    
    -- Status tracking
    status VARCHAR(50) NOT NULL CHECK (status IN (
        'PROCESSING', 'RECONCILED', 'PARTIAL', 'ORPHANED', 'FAILED', 'REFUNDED'
    )),
    
    -- Cost allocation and tagging
    cost_allocation_tags JSONB DEFAULT '{}'::jsonb,
    
    -- A/B testing support
    ab_test_id VARCHAR(255),
    variant_id VARCHAR(255),
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reconciled_at TIMESTAMP,
    
    -- Metadata for debugging and audit
    metadata JSONB DEFAULT '{}'::jsonb,
    
    -- Composite unique constraint for idempotency
    UNIQUE(correlation_id, attempt_id)
);

-- Indexes for fast querying
CREATE INDEX idx_ledger_tenant_created ON ledger(tenant_id, created_at DESC);
CREATE INDEX idx_ledger_status ON ledger(status);
CREATE INDEX idx_ledger_correlation ON ledger(correlation_id);
CREATE INDEX idx_ledger_ab_test ON ledger(ab_test_id, variant_id) WHERE ab_test_id IS NOT NULL;
CREATE INDEX idx_ledger_cost_tags ON ledger USING gin(cost_allocation_tags);

-- Audit log for all state transitions
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    correlation_id VARCHAR(255) NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    
    event_type VARCHAR(100) NOT NULL,
    event_source VARCHAR(100) NOT NULL, -- service that generated the event
    
    old_status VARCHAR(50),
    new_status VARCHAR(50),
    
    actor VARCHAR(255), -- User or service that triggered the change
    reason TEXT,
    
    changes JSONB DEFAULT '{}'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_correlation ON audit_log(correlation_id);
CREATE INDEX idx_audit_tenant_created ON audit_log(tenant_id, created_at DESC);
CREATE INDEX idx_audit_event_type ON audit_log(event_type);

-- Manual review queue for PARTIAL states
CREATE TABLE IF NOT EXISTS manual_review_queue (
    id BIGSERIAL PRIMARY KEY,
    correlation_id VARCHAR(255) NOT NULL UNIQUE,
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    
    review_status VARCHAR(50) DEFAULT 'pending' CHECK (review_status IN (
        'pending', 'in_review', 'approved', 'rejected', 'requires_info'
    )),
    
    checkpoint_tokens INTEGER DEFAULT 0,
    recommended_action VARCHAR(100),
    
    assigned_to VARCHAR(255),
    assigned_at TIMESTAMP,
    
    resolved_at TIMESTAMP,
    resolution_notes TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_review_status ON manual_review_queue(review_status, created_at);
CREATE INDEX idx_review_tenant ON manual_review_queue(tenant_id);

-- GDPR compliance: consent management
CREATE TABLE IF NOT EXISTS candidate_consent (
    consent_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    
    candidate_email VARCHAR(255) NOT NULL,
    candidate_id VARCHAR(255),
    
    consent_given BOOLEAN NOT NULL,
    consent_type VARCHAR(100) NOT NULL, -- 'data_processing', 'ai_screening', etc.
    
    consent_method VARCHAR(100), -- 'web_form', 'email', 'api'
    ip_address INET,
    user_agent TEXT,
    
    expires_at TIMESTAMP,
    revoked_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb,
    
    UNIQUE(tenant_id, candidate_email, consent_type)
);

CREATE INDEX idx_consent_tenant_email ON candidate_consent(tenant_id, candidate_email);

-- GDPR compliance: data deletion requests
CREATE TABLE IF NOT EXISTS data_deletion_requests (
    request_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    
    candidate_email VARCHAR(255) NOT NULL,
    request_type VARCHAR(50) CHECK (request_type IN ('erasure', 'export', 'rectification')),
    
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN (
        'pending', 'processing', 'completed', 'failed'
    )),
    
    records_affected INTEGER DEFAULT 0,
    completed_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_deletion_status ON data_deletion_requests(status, created_at);

-- EEOC compliance: AI screening decisions with explainability
CREATE TABLE IF NOT EXISTS ai_screening_decisions (
    decision_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    correlation_id VARCHAR(255), -- Link to ledger entry
    
    candidate_id VARCHAR(255) NOT NULL,
    job_id VARCHAR(255) NOT NULL,
    
    decision VARCHAR(50) CHECK (decision IN ('selected', 'rejected', 'waitlist')),
    confidence_score DECIMAL(5,4),
    
    -- Explainability metadata
    decision_factors JSONB NOT NULL, -- e.g., {"skills_match": 0.85, "experience": 0.72, "cultural_fit": 0.68}
    top_reasons TEXT[], -- Human-readable reasons
    
    model VARCHAR(100) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    
    -- Protected attributes (for bias testing only, never used in decisions)
    protected_attributes JSONB, -- e.g., {"age_range": "30-40", "gender": "F"}
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_screening_tenant_created ON ai_screening_decisions(tenant_id, created_at DESC);
CREATE INDEX idx_screening_candidate ON ai_screening_decisions(candidate_id);
CREATE INDEX idx_screening_job ON ai_screening_decisions(job_id);
CREATE INDEX idx_screening_decision ON ai_screening_decisions(decision);

-- EEOC compliance: bias monitoring
CREATE TABLE IF NOT EXISTS bias_monitoring (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    
    test_date DATE NOT NULL,
    model VARCHAR(100) NOT NULL,
    job_id VARCHAR(255),
    
    -- Protected attributes
    protected_group VARCHAR(100) NOT NULL,
    
    -- Adverse impact ratio (4/5ths rule)
    selection_rate_protected DECIMAL(5,4),
    selection_rate_comparison DECIMAL(5,4),
    adverse_impact_ratio DECIMAL(5,4),
    
    passes_compliance BOOLEAN,
    
    sample_size INTEGER,
    flagged_for_review BOOLEAN DEFAULT false,
    
    -- Detailed results
    protected_selected INTEGER,
    protected_total INTEGER,
    comparison_selected INTEGER,
    comparison_total INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_bias_tenant_date ON bias_monitoring(tenant_id, test_date DESC);
CREATE INDEX idx_bias_flagged ON bias_monitoring(flagged_for_review) WHERE flagged_for_review = true;
CREATE INDEX idx_bias_job ON bias_monitoring(job_id);

-- A/B Testing experiments
CREATE TABLE IF NOT EXISTS ab_tests (
    test_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    
    test_name VARCHAR(255) NOT NULL,
    description TEXT,
    
    status VARCHAR(50) DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'paused', 'completed')),
    
    variants JSONB NOT NULL, -- Array of variant configurations
    traffic_split JSONB DEFAULT '{}'::jsonb, -- Percentage split per variant
    
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- CRISPE prompt templates with versioning
CREATE TABLE IF NOT EXISTS crispe_prompts (
    prompt_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    
    template_name VARCHAR(255) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    
    -- CRISPE components
    capacity TEXT NOT NULL,  -- Task capacity/context
    role TEXT NOT NULL,      -- AI role definition
    insight TEXT NOT NULL,   -- Key insight or background
    statement TEXT NOT NULL, -- Core instruction
    personality TEXT NOT NULL, -- Tone and style
    experiment TEXT,         -- Optional experimental instructions
    
    -- Validation and quality
    is_active BOOLEAN DEFAULT true,
    validation_score DECIMAL(3,2), -- Quality score 0-1
    
    -- Performance tracking
    usage_count INTEGER DEFAULT 0,
    avg_response_time_ms INTEGER,
    avg_token_count INTEGER,
    success_rate DECIMAL(5,4),
    
    created_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    metadata JSONB DEFAULT '{}'::jsonb,
    
    UNIQUE(tenant_id, template_name, version)
);

CREATE INDEX idx_crispe_tenant_active ON crispe_prompts(tenant_id, is_active);
CREATE INDEX idx_crispe_template_name ON crispe_prompts(template_name, version DESC);

-- Semantic cache metadata (actual vectors stored in Qdrant)
CREATE TABLE IF NOT EXISTS semantic_cache_metadata (
    cache_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    
    qdrant_point_id VARCHAR(255) UNIQUE NOT NULL,
    
    -- Triple-tag validation
    policy_version VARCHAR(50) NOT NULL,
    region VARCHAR(50) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    
    prompt_hash VARCHAR(255) NOT NULL,
    response_preview TEXT,
    
    -- Compliance metadata
    candidate_email VARCHAR(255),  -- For GDPR consent checks
    job_id VARCHAR(255),           -- For audit trail
    model VARCHAR(100),
    
    -- Hit tracking
    hit_count INTEGER DEFAULT 0,
    last_hit_at TIMESTAMP,
    
    -- Token accounting (for billing even on cache hits)
    estimated_tokens INTEGER DEFAULT 0,
    
    -- TTL and expiration
    ttl_seconds INTEGER DEFAULT 3600,
    expires_at TIMESTAMP,
    
    -- Audit trail
    created_by VARCHAR(255),  -- Service or user that cached this
    invalidation_reason VARCHAR(255),  -- Why cache entry was invalidated
    invalidated_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(tenant_id, policy_version, region, provider, prompt_hash)
);

CREATE INDEX idx_cache_triple_tag ON semantic_cache_metadata(policy_version, region, provider);
CREATE INDEX idx_cache_expires ON semantic_cache_metadata(expires_at);
CREATE INDEX idx_cache_candidate ON semantic_cache_metadata(tenant_id, candidate_email);
CREATE INDEX idx_cache_job ON semantic_cache_metadata(job_id);

-- Cache hit audit log (for compliance and debugging)
CREATE TABLE IF NOT EXISTS cache_hit_log (
    id BIGSERIAL PRIMARY KEY,
    cache_id UUID NOT NULL REFERENCES semantic_cache_metadata(cache_id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    
    correlation_id VARCHAR(255),
    ledger_id BIGINT REFERENCES ledger(id),  -- Link to billing record
    
    hit_reason VARCHAR(100),  -- "valid_hit", "policy_mismatch", "consent_missing", "rate_limited"
    similarity_score DECIMAL(5,4),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_hit_log_cache ON cache_hit_log(cache_id);
CREATE INDEX idx_hit_log_ledger ON cache_hit_log(ledger_id);

-- Function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for auto-updating timestamps
CREATE TRIGGER update_tenants_updated_at BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_ledger_updated_at BEFORE UPDATE ON ledger
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Sample tenant for development
INSERT INTO tenants (name, email, tpm_limit, rpm_limit)
VALUES ('Development Tenant', 'dev@ledgerline.ai', 100000, 1000)
ON CONFLICT (email) DO NOTHING;

-- Views for reporting
CREATE OR REPLACE VIEW tenant_usage_summary AS
SELECT 
    t.tenant_id,
    t.name,
    COUNT(l.id) as total_requests,
    SUM(l.token_count) as total_tokens,
    SUM(l.estimated_cost) as total_cost,
    AVG(l.token_count) as avg_tokens_per_request,
    COUNT(CASE WHEN l.status = 'RECONCILED' THEN 1 END) as reconciled_count,
    COUNT(CASE WHEN l.status = 'PARTIAL' THEN 1 END) as partial_count,
    COUNT(CASE WHEN l.status = 'FAILED' THEN 1 END) as failed_count
FROM tenants t
LEFT JOIN ledger l ON t.tenant_id = l.tenant_id
    AND l.created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY t.tenant_id, t.name;

CREATE OR REPLACE VIEW manual_review_summary AS
SELECT 
    t.name as tenant_name,
    mrq.correlation_id,
    mrq.review_status,
    mrq.checkpoint_tokens,
    mrq.recommended_action,
    mrq.assigned_to,
    mrq.created_at,
    l.provider,
    l.model,
    l.metadata
FROM manual_review_queue mrq
JOIN tenants t ON mrq.tenant_id = t.tenant_id
LEFT JOIN ledger l ON mrq.correlation_id = l.correlation_id
WHERE mrq.review_status IN ('pending', 'in_review')
ORDER BY mrq.created_at DESC;
