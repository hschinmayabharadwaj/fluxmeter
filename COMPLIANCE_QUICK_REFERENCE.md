# Compliance Quick Reference Guide

## EEOC Compliance

### Recording Screening Decisions
```python
import requests

# Every AI screening decision must include explainability
response = requests.post("http://localhost:8086/v1/screening-decision", json={
    "tenant_id": "your-tenant-id",
    "correlation_id": "corr_123",  # Link to billing
    "candidate_id": "candidate@email.com",
    "job_id": "job-456",
    "decision": "selected",  # or "rejected", "waitlist"
    "confidence_score": 0.85,
    "decision_factors": {
        "skills_match": 0.90,
        "experience": 0.82,
        "cultural_fit": 0.83
    },
    "top_reasons": [
        "Strong Python and ML skills match job requirements",
        "5+ years relevant experience",
        "Leadership experience aligns with senior role"
    ],
    "model": "gpt-4",
    "provider": "openai"
})
```

### Running Bias Tests
```python
# Automatically analyze a job's screening decisions
response = requests.post("http://localhost:8086/v1/automated-bias-test", json={
    "tenant_id": "your-tenant-id",
    "job_id": "job-456",
    "model": "gpt-4",
    "protected_groups": ["gender", "age_range", "ethnicity"]
})

# Check for violations
for test in response.json()["results"]:
    if not test["passes_compliance"]:
        print(f"⚠️ BIAS VIOLATION: {test['protected_group']}")
        print(f"   Adverse Impact Ratio: {test['adverse_impact_ratio']}")
```

---

## GDPR Compliance

### Consent Verification (Before Processing)
```python
# ALWAYS verify consent before processing candidate data
response = requests.post("http://localhost:8085/v1/consent/verify", json={
    "tenant_id": "your-tenant-id",
    "candidate_email": "candidate@email.com",
    "consent_types": ["data_processing", "ai_screening"]
})

if response.json()["all_valid"]:
    # Proceed with processing
    process_candidate_data()
else:
    # Request consent first
    prompt_for_consent()
```

### Handling Consent Withdrawal
```python
response = requests.post("http://localhost:8085/v1/consent/withdraw", json={
    "tenant_id": "your-tenant-id",
    "candidate_email": "candidate@email.com",
    "consent_type": "ai_screening",
    "withdrawal_reason": "Candidate requested via email"
})

# MUST stop all processing immediately after withdrawal
```

### Data Export Request
```python
# Article 15 - Right of Access
response = requests.post("http://localhost:8085/v1/data-export", json={
    "tenant_id": "your-tenant-id",
    "candidate_email": "candidate@email.com",
    "format": "json"  # or "csv"
})

# Returns all candidate data (consents, decisions, requests)
candidate_data = response.json()
```

### Data Deletion Request
```python
# Step 1: Create deletion request
response = requests.post("http://localhost:8085/v1/deletion-request", json={
    "tenant_id": "your-tenant-id",
    "candidate_email": "candidate@email.com",
    "request_type": "erasure",
    "reason": "GDPR Article 17 request via email"
})
request_id = response.json()["request_id"]

# Step 2: Execute deletion (can be automated via background job)
response = requests.post(f"http://localhost:8085/v1/deletion-request/{request_id}/execute")
print(f"Anonymized {response.json()['records_affected']} records")
```

---

## CRISPE Prompt Engineering

### Creating Templates
```python
response = requests.post("http://localhost:8087/v1/crispe/template", json={
    "tenant_id": "your-tenant-id",
    "template_name": "resume_screening",
    "crispe": {
        "capacity": "You will screen resumes for technical positions, evaluating candidates based on skills, experience, and role fit. Consider the job description, required qualifications, and company culture.",
        
        "role": "You are an expert technical recruiter with 15 years of experience at FAANG companies, specializing in software engineering and ML/AI roles.",
        
        "insight": "The best candidates demonstrate not just technical skills but also problem-solving ability, continuous learning, and collaborative mindset. Past performance in similar roles is the strongest predictor of future success.",
        
        "statement": "Analyze the candidate's resume and provide a structured evaluation including: 1) Technical skills match (0-100), 2) Experience relevance (0-100), 3) Cultural fit indicators, 4) Top 3 strengths, 5) Top 3 concerns, 6) Overall recommendation (Strong Yes / Yes / Maybe / No).",
        
        "personality": "Be objective, data-driven, and constructive. Highlight both strengths and areas for growth. Use specific examples from the resume.",
        
        "experiment": "Consider unconventional backgrounds that might bring unique perspectives."
    },
    "created_by": "recruiter@company.com"
})

validation_score = response.json()["validation_score"]
if validation_score < 0.7:
    print(f"⚠️ Quality issues: {response.json()['issues']}")
```

### Using Templates
```python
response = requests.post("http://localhost:8087/v1/crispe/apply", json={
    "tenant_id": "your-tenant-id",
    "template_name": "resume_screening",
    # version: null = use latest active version
    "variables": {
        "position": "Senior ML Engineer",
        "company": "TechStartup Inc"
    }
})

enhanced_prompt = response.json()["enhanced_prompt"]

# Use this prompt in your AI request
ai_response = openai_client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": enhanced_prompt},
        {"role": "user", "content": candidate_resume}
    ]
)
```

### Listing Templates
```python
response = requests.get("http://localhost:8087/v1/crispe/templates/your-tenant-id?active_only=true")

for template in response.json()["templates"]:
    print(f"{template['template_name']} v{template['version']}")
    print(f"  Quality: {template['validation_score']}")
    print(f"  Usage: {template['usage_count']} times")
    print(f"  Avg tokens: {template['avg_token_count']}")
```

---

## Error Handling

### EEOC Errors
```python
try:
    response = requests.post("http://localhost:8086/v1/screening-decision", json=data)
    response.raise_for_status()
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 400:
        # Missing explainability fields
        print("❌ EEOC Compliance Error: decision_factors and top_reasons required")
    elif e.response.status_code == 500:
        # Service error - log and retry
        logger.error(f"EEOC service error: {e}")
```

### GDPR Errors
```python
try:
    response = requests.post("http://localhost:8085/v1/consent/verify", json=data)
    result = response.json()
    
    if not result["all_valid"]:
        for consent_type, status in result["consents"].items():
            if not status["valid"]:
                reason = status["reason"]
                if reason == "no_consent_recorded":
                    # Need to collect consent first
                    collect_consent(consent_type)
                elif reason == "consent_withdrawn":
                    # Cannot process - consent withdrawn
                    raise ValueError(f"Consent withdrawn for {consent_type}")
                elif reason == "consent_expired":
                    # Need to renew consent
                    renew_consent(consent_type)
except Exception as e:
    logger.error(f"GDPR compliance check failed: {e}")
    # DO NOT PROCEED with data processing
```

### CRISPE Errors
```python
try:
    response = requests.post("http://localhost:8087/v1/crispe/template", json=template_data)
    response.raise_for_status()
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 400:
        # Validation failed
        details = e.response.json()["detail"]
        if "quality too low" in details:
            print(f"❌ Template quality insufficient: {details}")
            # Review and improve CRISPE components
        elif "Role should start with" in details:
            print("❌ Role validation failed - must start with 'You are', 'Act as', etc.")
```

---

## Integration Checklist

### For AI Screening Pipeline
- [ ] Record every screening decision with explainability
- [ ] Link decisions to correlation_id for billing
- [ ] Run automated bias tests after collecting decisions (n >= 30)
- [ ] Monitor bias_violations metric
- [ ] Set up alerts for adverse_impact_ratio < 0.8

### For Candidate Data Processing
- [ ] Verify consent before any processing
- [ ] Handle consent_withdrawn gracefully (stop processing)
- [ ] Implement consent renewal flow for expired consents
- [ ] Set up background job for processing pending deletions
- [ ] Monitor pending_deletions metric

### For Prompt Engineering
- [ ] Create CRISPE templates for all use cases
- [ ] Use template versioning for A/B testing
- [ ] Track template performance metrics
- [ ] Iterate on templates with low success_rate
- [ ] Document variable placeholders for each template

---

## Background Jobs (Recommended)

### Daily GDPR Cleanup
```python
# Run via cron at 2 AM daily
import requests

response = requests.post(
    "http://localhost:8085/v1/deletion-request/process-pending",
    params={"limit": 100}
)

result = response.json()
print(f"Processed: {result['processed']}, Succeeded: {result['succeeded']}, Failed: {result['failed']}")
```

### Weekly Bias Testing
```python
# Run after significant candidate volume
import requests

# Get all active jobs
jobs = get_active_jobs()

for job in jobs:
    response = requests.post("http://localhost:8086/v1/automated-bias-test", json={
        "tenant_id": "your-tenant-id",
        "job_id": job["job_id"],
        "model": job["model"],
        "protected_groups": ["gender", "age_range", "ethnicity"]
    })
    
    # Alert on violations
    for result in response.json()["results"]:
        if not result["passes_compliance"]:
            send_alert(f"Bias violation detected: {job['job_id']} / {result['protected_group']}")
```

---

## Metrics Dashboard

### Grafana Queries

**EEOC Metrics:**
```promql
# Active bias violations
sum(ledgerline_bias_violations_active) by (model, protected_group)

# Adverse impact ratio trend
ledgerline_adverse_impact_ratio

# EEOC operation errors
rate(ledgerline_eeoc_operations_total{status="error"}[5m])
```

**GDPR Metrics:**
```promql
# Pending deletions
sum(ledgerline_pending_deletion_requests) by (tenant_id)

# Active consents by type
sum(ledgerline_active_consents) by (consent_type)

# GDPR operation success rate
rate(ledgerline_gdpr_operations_total{status="success"}[5m]) / 
rate(ledgerline_gdpr_operations_total[5m])
```

**CRISPE Metrics:**
```promql
# Template validation acceptance rate
rate(ledgerline_crispe_validations_total{status="accepted"}[1h]) /
rate(ledgerline_crispe_validations_total[1h])

# Most used templates
topk(10, sum(rate(ledgerline_crispe_template_usage_total[1d])) by (template_name))

# Active templates
sum(ledgerline_active_crispe_templates) by (tenant_id)
```

---

## Support

- **EEOC Issues**: Check logs at `backend/services/python/compliance/eeoc.py`
- **GDPR Issues**: Check logs at `backend/services/python/compliance/gdpr.py`
- **CRISPE Issues**: Check logs at `backend/services/python/routing/main.py`
- **Documentation**: See `COMPLIANCE_IMPLEMENTATION.md`
- **Metrics**: Prometheus at `http://localhost:9090`
