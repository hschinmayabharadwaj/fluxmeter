"""
Ledgerline AI Guardrails Service
Handles PII masking, jailbreak detection, and content safety
"""
import logging
import os
import re
from typing import List, Dict, Optional
from enum import Enum

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from prometheus_client import Counter, generate_latest
from starlette.responses import Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GUARDRAIL_CHECKS = Counter(
    'ledgerline_guardrail_checks_total',
    'Total guardrail checks',
    ['check_type', 'result']
)

class GuardrailType(str, Enum):
    PII_DETECTION = "pii_detection"
    JAILBREAK_DETECTION = "jailbreak_detection"
    TOXICITY_DETECTION = "toxicity_detection"
    PROMPT_INJECTION = "prompt_injection"

class GuardrailRequest(BaseModel):
    text: str
    checks: List[GuardrailType]
    tenant_id: Optional[str] = None

class PIIMaskRequest(BaseModel):
    text: str
    mask_char: str = "*"

app = FastAPI(
    title="Ledgerline AI Guardrails",
    description="PII masking, jailbreak detection, and content safety",
    version="1.0.0"
)

# PII patterns
PII_PATTERNS = {
    "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    "phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
    "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
    "credit_card": r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
    "ip_address": r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'
}

# Jailbreak patterns
JAILBREAK_PATTERNS = [
    r"ignore previous instructions",
    r"disregard all prior",
    r"forget everything",
    r"you are now",
    r"new instructions",
    r"system prompt",
    r"reveal your prompt",
    r"show me your instructions"
]

# Prompt injection patterns
INJECTION_PATTERNS = [
    r"</s>",
    r"<\|endoftext\|>",
    r"\[INST\]",
    r"<|im_start|>",
    r"###\s*Human:",
    r"###\s*Assistant:"
]

def detect_pii(text: str) -> Dict:
    """Detect PII in text"""
    findings = {}
    
    for pii_type, pattern in PII_PATTERNS.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            findings[pii_type] = {
                "count": len(matches),
                "examples": matches[:3]  # First 3 examples
            }
    
    has_pii = len(findings) > 0
    GUARDRAIL_CHECKS.labels(check_type='pii', result='detected' if has_pii else 'clean').inc()
    
    return {
        "has_pii": has_pii,
        "findings": findings
    }

def mask_pii(text: str, mask_char: str = "*") -> str:
    """Mask PII in text"""
    masked_text = text
    
    for pii_type, pattern in PII_PATTERNS.items():
        def mask_match(match):
            matched = match.group(0)
            if pii_type == "email":
                # Keep domain visible
                parts = matched.split("@")
                if len(parts) == 2:
                    return f"{mask_char * 5}@{parts[1]}"
            elif pii_type in ["phone", "ssn", "credit_card"]:
                # Keep last 4 digits
                if len(matched) > 4:
                    return mask_char * (len(matched) - 4) + matched[-4:]
            return mask_char * len(matched)
        
        masked_text = re.sub(pattern, mask_match, masked_text, flags=re.IGNORECASE)
    
    return masked_text

def detect_jailbreak(text: str) -> Dict:
    """Detect jailbreak attempts"""
    text_lower = text.lower()
    detected_patterns = []
    
    for pattern in JAILBREAK_PATTERNS:
        if re.search(pattern, text_lower):
            detected_patterns.append(pattern)
    
    is_jailbreak = len(detected_patterns) > 0
    GUARDRAIL_CHECKS.labels(check_type='jailbreak', result='detected' if is_jailbreak else 'clean').inc()
    
    if is_jailbreak:
        logger.warning(f"Jailbreak attempt detected: {detected_patterns}")
    
    return {
        "is_jailbreak": is_jailbreak,
        "patterns_detected": detected_patterns,
        "confidence": min(len(detected_patterns) * 0.3, 1.0)
    }

def detect_prompt_injection(text: str) -> Dict:
    """Detect prompt injection attempts"""
    detected_patterns = []
    
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            detected_patterns.append(pattern)
    
    is_injection = len(detected_patterns) > 0
    GUARDRAIL_CHECKS.labels(check_type='injection', result='detected' if is_injection else 'clean').inc()
    
    return {
        "is_injection": is_injection,
        "patterns_detected": detected_patterns
    }

def detect_toxicity(text: str) -> Dict:
    """
    Detect toxic content
    In production, integrate with Perspective API or similar
    """
    # Simple keyword-based check (in production, use ML model)
    toxic_keywords = ["hate", "violent", "explicit", "offensive"]
    text_lower = text.lower()
    
    found_keywords = [kw for kw in toxic_keywords if kw in text_lower]
    is_toxic = len(found_keywords) > 0
    
    GUARDRAIL_CHECKS.labels(check_type='toxicity', result='detected' if is_toxic else='clean').inc()
    
    return {
        "is_toxic": is_toxic,
        "keywords_found": found_keywords,
        "confidence": 0.5 if is_toxic else 0.0  # Mock confidence
    }

@app.post("/v1/guardrails/check")
def check_guardrails(request: GuardrailRequest):
    """
    Run multiple guardrail checks on text
    """
    try:
        results = {
            "text_length": len(request.text),
            "checks_performed": []
        }
        
        violations = []
        
        for check in request.checks:
            if check == GuardrailType.PII_DETECTION:
                pii_result = detect_pii(request.text)
                results["pii"] = pii_result
                results["checks_performed"].append("pii_detection")
                if pii_result["has_pii"]:
                    violations.append("pii_detected")
            
            elif check == GuardrailType.JAILBREAK_DETECTION:
                jailbreak_result = detect_jailbreak(request.text)
                results["jailbreak"] = jailbreak_result
                results["checks_performed"].append("jailbreak_detection")
                if jailbreak_result["is_jailbreak"]:
                    violations.append("jailbreak_attempt")
            
            elif check == GuardrailType.PROMPT_INJECTION:
                injection_result = detect_prompt_injection(request.text)
                results["injection"] = injection_result
                results["checks_performed"].append("prompt_injection")
                if injection_result["is_injection"]:
                    violations.append("prompt_injection")
            
            elif check == GuardrailType.TOXICITY_DETECTION:
                toxicity_result = detect_toxicity(request.text)
                results["toxicity"] = toxicity_result
                results["checks_performed"].append("toxicity_detection")
                if toxicity_result["is_toxic"]:
                    violations.append("toxic_content")
        
        results["safe"] = len(violations) == 0
        results["violations"] = violations
        
        return results
        
    except Exception as e:
        logger.error(f"Guardrail check failed: {e}")
        raise HTTPException(status_code=500, detail="Guardrail check failed")

@app.post("/v1/guardrails/mask-pii")
def mask_pii_endpoint(request: PIIMaskRequest):
    """Mask PII in text"""
    try:
        # First detect PII
        pii_result = detect_pii(request.text)
        
        # Then mask it
        masked_text = mask_pii(request.text, request.mask_char)
        
        return {
            "original_length": len(request.text),
            "masked_length": len(masked_text),
            "masked_text": masked_text,
            "pii_detected": pii_result["findings"],
            "mask_count": sum(v["count"] for v in pii_result["findings"].values())
        }
        
    except Exception as e:
        logger.error(f"PII masking failed: {e}")
        raise HTTPException(status_code=500, detail="PII masking failed")

@app.get("/v1/guardrails/patterns")
def get_patterns():
    """Get configured detection patterns"""
    return {
        "pii_types": list(PII_PATTERNS.keys()),
        "jailbreak_patterns_count": len(JAILBREAK_PATTERNS),
        "injection_patterns_count": len(INJECTION_PATTERNS)
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "ai-guardrails"}

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8089"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
