# SecurityScanAgent Design

## Overview

The SecurityScanAgent performs security analysis on generated code, with two execution modes to balance thoroughness with speed.

---

## 1. Execution Modes

### Lightweight Mode (PR/Fast)

```
┌─────────────────────────────────────────────────────────────────┐
│                    LIGHTWEIGHT MODE (~30s)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Triggers: Every PR, pre-commit hooks                          │
│                                                                  │
│   Checks:                                                        │
│   ├── Pattern-based vulnerability detection                     │
│   ├── Hardcoded secrets/credentials                             │
│   ├── SQL injection patterns                                    │
│   ├── XSS patterns                                              │
│   ├── Command injection patterns                                │
│   ├── Insecure crypto usage                                     │
│   └── Dependency version checks (known CVEs)                    │
│                                                                  │
│   Output: Pass/Fail with blocking issues only                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Heavyweight Mode (Nightly/Thorough)

```
┌─────────────────────────────────────────────────────────────────┐
│                    HEAVYWEIGHT MODE (~5-10min)                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Triggers: Nightly builds, release prep, on-demand             │
│                                                                  │
│   Checks (includes all lightweight +):                          │
│   ├── LLM-powered code review for security                      │
│   ├── Data flow analysis (taint tracking)                       │
│   ├── Authentication/authorization logic review                 │
│   ├── Cryptographic implementation review                       │
│   ├── API security (rate limiting, input validation)            │
│   ├── Compliance checks (OWASP Top 10)                          │
│   ├── Dependency deep scan (transitive vulnerabilities)         │
│   └── Security spec compliance verification                     │
│                                                                  │
│   Output: Full security report with recommendations             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      SecurityScanAgent                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │    Mode      │───▶│   Scanner    │───▶│   Reporter   │      │
│  │   Selector   │    │   Pipeline   │    │              │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│         │                   │                   │               │
│         ▼                   ▼                   ▼               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  Lightweight │    │   Scanners   │    │   Findings   │      │
│  │  Heavyweight │    │   Registry   │    │   Formatter  │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
       ┌───────────┐   ┌───────────┐   ┌───────────┐
       │  Pattern  │   │    LLM    │   │   Spec    │
       │  Scanner  │   │  Scanner  │   │ Compliance│
       └───────────┘   └───────────┘   └───────────┘
```

---

## 3. Scanner Types

### Pattern Scanner (Lightweight)

Fast regex-based detection for common vulnerabilities:

```python
VULNERABILITY_PATTERNS = {
    "hardcoded_secret": [
        r"password\s*=\s*['\"][^'\"]+['\"]",
        r"api_key\s*=\s*['\"][^'\"]+['\"]",
        r"secret\s*=\s*['\"][^'\"]+['\"]",
        r"AWS_SECRET_ACCESS_KEY\s*=\s*['\"][^'\"]+['\"]",
    ],
    "sql_injection": [
        r"execute\s*\(\s*['\"].*%s",
        r"f['\"]SELECT.*\{",
        r"\.format\s*\(.*SELECT",
    ],
    "command_injection": [
        r"os\.system\s*\(",
        r"subprocess\.call\s*\([^,]+shell\s*=\s*True",
        r"eval\s*\(",
        r"exec\s*\(",
    ],
    "xss": [
        r"innerHTML\s*=",
        r"document\.write\s*\(",
        r"\{\{\s*.*\s*\|\s*safe\s*\}\}",
    ],
    "insecure_crypto": [
        r"hashlib\.md5\s*\(",
        r"hashlib\.sha1\s*\(",
        r"DES\s*\(",
        r"random\.random\s*\(",  # Not cryptographically secure
    ],
}
```

### LLM Scanner (Heavyweight)

Deep analysis using Claude for:
- Logic flaws in auth/authz
- Business logic vulnerabilities
- Data exposure risks
- Race conditions
- Insecure defaults

### Spec Compliance Scanner

Verifies code matches security spec:
- Required authentication implemented
- Rate limiting in place
- Input validation present
- Encryption for sensitive data

---

## 4. Finding Severity Levels

```python
class Severity(Enum):
    CRITICAL = "critical"   # Block deployment, immediate fix required
    HIGH = "high"           # Block PR, fix before merge
    MEDIUM = "medium"       # Warning, should fix soon
    LOW = "low"             # Informational, best practice
    INFO = "info"           # Suggestion for improvement
```

### Severity Mapping

| Vulnerability | Severity | Blocks PR | Blocks Deploy |
|--------------|----------|-----------|---------------|
| Hardcoded secrets | CRITICAL | Yes | Yes |
| SQL injection | CRITICAL | Yes | Yes |
| Command injection | CRITICAL | Yes | Yes |
| XSS | HIGH | Yes | Yes |
| Insecure crypto | HIGH | Yes | No |
| Missing auth | HIGH | Yes | Yes |
| Missing rate limit | MEDIUM | No | No |
| Missing input validation | MEDIUM | No | No |
| Weak password policy | LOW | No | No |

---

## 5. Integration with FlowOrchestrator

```python
# SecurityScanAgent runs after CodingAgent
orchestrator.register_agent(
    agent=SecurityScanAgent(mode="lightweight"),
    depends_on=["coding_agent"],
    provides=["security_report"],
    priority=80,
)
```

### Flow Position

```
CodingAgent ──▶ SecurityScanAgent ──▶ TestGeneratorAgent
                      │
                      ▼
               [If CRITICAL/HIGH]
                      │
                      ▼
                 Block Flow
```

---

## 6. Security Spec Section Usage

From routed spec sections:

```yaml
# Section 11: Security Requirements
security:
  authentication:
    method: JWT
    required: true
  authorization:
    model: RBAC
    roles: [admin, user, viewer]
  encryption:
    at_rest: AES-256
    in_transit: TLS 1.3
  rate_limiting:
    enabled: true
    requests_per_minute: 100
```

Agent verifies:
1. Auth method matches spec (JWT implemented correctly)
2. RBAC roles enforced in code
3. Encryption used for sensitive fields
4. Rate limiting middleware present

---

## 7. Report Format

### Lightweight Report (PR)

```
Security Scan: FAILED (2 blocking issues)

CRITICAL:
  src/auth/login.py:42 - Hardcoded API key detected
  src/db/queries.py:15 - SQL injection vulnerability

Run `spec-dev security scan --mode heavyweight` for full analysis.
```

### Heavyweight Report (Full)

```markdown
# Security Scan Report

## Summary
- Files scanned: 45
- Issues found: 8 (2 critical, 3 high, 2 medium, 1 low)
- Spec compliance: 85%

## Critical Issues

### 1. Hardcoded API Key
**File:** src/auth/login.py:42
**Pattern:** `api_key = "sk-1234..."`
**Recommendation:** Use environment variables or secret manager

### 2. SQL Injection
**File:** src/db/queries.py:15
**Code:** `cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")`
**Recommendation:** Use parameterized queries

## High Issues
...

## Spec Compliance

| Requirement | Status | Notes |
|------------|--------|-------|
| JWT Authentication | ✅ Pass | Implemented in auth/jwt.py |
| RBAC Authorization | ⚠️ Partial | Missing viewer role checks |
| Rate Limiting | ❌ Fail | No rate limiting middleware found |

## Recommendations
1. Add rate limiting middleware (see security spec section 11.4)
2. Complete RBAC implementation for viewer role
3. Consider adding CSRF protection
```

---

## 8. Usage

```python
# Lightweight (fast, PR mode)
agent = SecurityScanAgent(mode="lightweight")
result = agent.execute(context)

# Heavyweight (thorough, nightly mode)
agent = SecurityScanAgent(mode="heavyweight", llm_client=claude)
result = agent.execute(context)

# Check if blocking
if result.data.get("has_blocking_issues"):
    raise SecurityException(result.data["blocking_issues"])
```

### CLI

```bash
# Quick scan (default for PRs)
spec-dev security scan

# Full scan
spec-dev security scan --mode heavyweight

# Scan specific files
spec-dev security scan src/auth/

# Output formats
spec-dev security scan --format json
spec-dev security scan --format sarif  # For GitHub Security tab
```
