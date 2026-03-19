"""STRIDE threat model template injected into SecurityAgent's prompts."""

THREAT_MODEL_TEMPLATE = """
## STRIDE Threat Model

For each category, identify specific threats, mitigations, and risk score (1-10).

| STRIDE | Threat | Component | Mitigation | Risk (1-10) |
|--------|--------|-----------|------------|-------------|
| Spoofing | | | | |
| Tampering | | | | |
| Repudiation | | | | |
| Info Disclosure | | | | |
| Denial of Service | | | | |
| Elevation of Privilege | | | | |

### Trust Boundaries
List each trust boundary (e.g. internet → API, API → DB, API → third-party).

### Data Flow
Describe what sensitive data flows where and how it's protected at each hop.

### Attack Surface
List all external entry points: endpoints, webhooks, file uploads, OAuth callbacks, admin panels.
"""

STRIDE_CATEGORIES = {
    "Spoofing": {
        "description": "Pretending to be someone or something else",
        "controls": ["MFA", "Strong authentication", "Certificate pinning", "API key rotation"],
        "examples": ["JWT token theft and replay", "Phishing for credentials", "DNS spoofing"],
    },
    "Tampering": {
        "description": "Modifying data or code",
        "controls": ["Input validation", "Signed tokens", "Database integrity constraints", "Audit logs"],
        "examples": ["SQL injection", "Request parameter manipulation", "Man-in-the-middle"],
    },
    "Repudiation": {
        "description": "Denying an action was performed",
        "controls": ["Audit logging", "Non-repudiation tokens", "Signed audit trails"],
        "examples": ["User denies placing order", "Admin denies deleting record"],
    },
    "Information Disclosure": {
        "description": "Exposing information to unauthorised parties",
        "controls": ["Encryption at rest/transit", "Access control", "Data minimisation", "Error handling"],
        "examples": ["Stack traces in error responses", "Verbose logging", "IDOR"],
    },
    "Denial of Service": {
        "description": "Making a service unavailable",
        "controls": ["Rate limiting", "Circuit breakers", "Input size limits", "WAF", "CDN"],
        "examples": ["Flooding login endpoint", "Large file uploads", "ReDoS"],
    },
    "Elevation of Privilege": {
        "description": "Gaining capabilities beyond what's authorised",
        "controls": ["Least privilege", "RBAC", "Row-level security", "Principle of separation"],
        "examples": ["Horizontal privilege escalation (IDOR)", "Vertical (regular → admin)", "JWT role manipulation"],
    },
}
