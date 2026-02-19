# Spec-Driven Development Architecture

## Overview

This document explains how specs flow through the system, how agents coordinate, and how we manage context window limits.

---

## 1. Spec Section Distribution to Agents

### The Problem
Giving every agent the entire 13-section spec wastes context tokens and confuses agents with irrelevant information.

### The Solution: Section Router

```
                         FULL SPEC
                            │
                            ▼
                    ┌───────────────┐
                    │ SectionRouter │
                    └───────┬───────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ CodingAgent   │   │ TestGenerator │   │ SecurityAgent │
│               │   │               │   │               │
│ Gets:         │   │ Gets:         │   │ Gets:         │
│ • overview    │   │ • test_cases  │   │ • security    │
│ • inputs      │   │ • edge_cases  │   │ • api_contract│
│ • outputs     │   │ • inputs      │   │ • inputs      │
│ • api_contract│   │ • outputs     │   │               │
│ • dependencies│   │               │   │               │
└───────────────┘   └───────────────┘   └───────────────┘
```

### Section-to-Agent Mapping

| Agent | Required Sections | Optional Sections |
|-------|-------------------|-------------------|
| `coding_agent` | overview, inputs, outputs, api_contract, dependencies | implementation, error_handling |
| `test_generator_agent` | test_cases, edge_cases, inputs, outputs | api_contract, error_handling |
| `security_agent` | security, api_contract | inputs, outputs, dependencies |
| `performance_agent` | performance, api_contract | dependencies, implementation |
| `code_review_agent` | overview, api_contract, security, error_handling | performance, implementation |
| `linter_agent` | metadata | (none) |
| `architecture_agent` | overview, dependencies, api_contract | implementation |

### Usage

```python
from src.orchestration import SectionRouter

router = SectionRouter()
routed = router.route(spec, agent_name="test_generator_agent")

# routed.sections only contains: test_cases, edge_cases, inputs, outputs
# routed.token_estimate tells you the size
# routed.to_prompt_context() gives formatted string for LLM
```

---

## 2. Agent Orchestration Flow

### The Problem
Agents depend on each other. TestGenerator needs code to exist. CodeReview needs both code and tests.

### The Solution: Flow Orchestrator with DAG

```
                    ┌─────────────────┐
                    │  FlowOrchestrator│
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
    ┌─────────┐         ┌─────────┐         ┌─────────┐
    │ Coding  │         │ Linter  │         │ Security│
    │ Agent   │────┐    │ Agent   │         │ Agent   │
    └────┬────┘    │    └────┬────┘         └────┬────┘
         │         │         │                   │
         │    ┌────┘         │                   │
         ▼    ▼              ▼                   ▼
    ┌─────────────┐    ┌─────────┐         ┌─────────┐
    │    Test     │    │Linted   │         │Security │
    │  Generator  │    │Code     │         │Report   │
    └──────┬──────┘    └─────────┘         └─────────┘
           │
           ▼
    ┌─────────────┐
    │   Code      │
    │   Review    │
    └─────────────┘
```

### Execution Strategies

1. **SEQUENTIAL**: Run one agent at a time, in order
2. **DAG**: Respect dependencies, run independent agents in parallel

### Message Passing

Agents communicate through:

```python
FlowMessage(
    from_agent="coding_agent",
    to_agent="test_generator_agent",
    message_type="artifact",      # result, artifact, error, request
    payload={"files_created": ["src/payment.py"]}
)
```

### Shared Artifacts

Agents produce artifacts that others consume:

```python
# CodingAgent produces:
state.add_artifact("code", file_contents, "coding_agent")
state.add_artifact("files_created", ["src/main.py"], "coding_agent")

# TestGenerator consumes:
code = context.parent_context["artifacts"]["code"]
```

### Usage

```python
from src.orchestration import FlowOrchestrator, FlowStrategy

orchestrator = FlowOrchestrator(spec, project_root, FlowStrategy.DAG)

orchestrator.register_agent(coding_agent, depends_on=[], provides=["code"])
orchestrator.register_agent(test_agent, depends_on=["coding_agent"], provides=["tests"])
orchestrator.register_agent(review_agent, depends_on=["coding_agent", "test_agent"])

# Add hooks for monitoring
orchestrator.add_hook("post_agent", lambda name, result: print(f"{name}: {result.status}"))

state = orchestrator.execute()
```

---

## 3. Rules Context Window Management

### The Problem
With global + scoped + local rules, you might have 100+ rules. That's too many tokens.

### The Solution: Priority-Based Packing

```
                    ALL RULES (100+)
                          │
                          ▼
               ┌────────────────────┐
               │ RulesContextManager│
               └──────────┬─────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   ┌─────────┐      ┌──────────┐      ┌──────────┐
   │ Filter  │      │ Prioritize│     │   Pack   │
   │ by      │ ───▶ │ by score │ ───▶ │ to fit   │
   │ section │      │          │      │ budget   │
   └─────────┘      └──────────┘      └──────────┘
                          │
                          ▼
                  ┌───────────────┐
                  │ RulesContext  │
                  │ Pack (fits in │
                  │ 4000 tokens)  │
                  └───────────────┘
```

### Priority Scoring

```python
# Severity weights (higher = more important)
ERROR:   100 points
WARNING:  50 points
INFO:     10 points

# Category weights
SECURITY:     80 points
TESTING:      60 points
API:          50 points
PERFORMANCE:  40 points
CODE_QUALITY: 30 points
DOCUMENTATION: 20 points

# Level weights (more specific = higher priority)
LOCAL:   100 points  # Applies to this exact block
SCOPED:   70 points  # Applies to this block's hierarchy
GLOBAL:   40 points  # Applies everywhere
```

### Packing Strategy

1. **Must Include**: All ERROR severity rules (reserved budget)
2. **High Priority**: All SECURITY category rules (reserved budget)
3. **Fill Remaining**: By priority score until budget exhausted
4. **Summarize Excluded**: Generate summary of what was left out

### Usage

```python
from src.rules import RulesContextManager

manager = RulesContextManager(max_tokens=4000)

# Pack rules for a specific context
pack = manager.pack_rules(
    rules=all_rules,
    target_sections=["security", "api_contract"],
    agent_name="security_agent"
)

# Get prompt-ready format
prompt_text = pack.to_prompt()

# Check what was excluded
print(pack.summary)
# "Included 15 rules: 3 errors, 8 warnings, 4 info"
# "Excluded 5 rules due to context limits"
```

### Chunking for Large Rule Sets

When rules exceed even the packed budget:

```python
chunks = manager.chunk_rules(rules, chunk_size=2000)
# Returns: [[rules 1-10], [rules 11-20], ...]

# Process in multiple LLM calls
for chunk in chunks:
    result = llm.validate_with_rules(code, chunk)
```

---

## 4. Complete Flow Example

```
┌──────────────────────────────────────────────────────────────────┐
│                        USER REQUEST                               │
│                  "Implement payment-system"                       │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                      1. PARSE HIERARCHY                          │
│                                                                   │
│   BlockParser.parse_hierarchy("specs/payment-system")             │
│   → Returns: [root, gateway, invoicing, ...]                      │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                    2. LOAD & PACK RULES                          │
│                                                                   │
│   RulesEngine.get_effective_rules(block)                         │
│   → Global + Parent Scoped + Local rules                          │
│                                                                   │
│   RulesContextManager.pack_rules(rules, sections)                 │
│   → Priority-sorted rules that fit in 4K tokens                   │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                    3. PROCESS BLOCKS                              │
│                                                                   │
│   BlockPipeline with BOTTOM_UP order:                             │
│                                                                   │
│   Level 2: gateway, invoicing    (leaves first)                   │
│   Level 1: payment-system        (root last)                      │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│               4. FOR EACH BLOCK: AGENT FLOW                       │
│                                                                   │
│   FlowOrchestrator executes:                                      │
│                                                                   │
│   ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐   │
│   │ Coding  │ ──▶ │ Linter  │ ──▶ │  Test   │ ──▶ │ Review  │   │
│   └─────────┘     └─────────┘     └─────────┘     └─────────┘   │
│                                                                   │
│   Each agent receives:                                            │
│   • Routed spec sections (only what they need)                    │
│   • Packed rules (priority-sorted, fits context)                  │
│   • Artifacts from previous agents                                │
│   • Parent block context (if bottom-up)                           │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                      5. COLLECT RESULTS                           │
│                                                                   │
│   • Files created/modified per block                              │
│   • Test results                                                  │
│   • Rule violations found                                         │
│   • Architecture updates                                          │
└──────────────────────────────────────────────────────────────────┘
```

---

## 5. Key Design Decisions

### Why Bottom-Up Processing?
- Leaf blocks are independent, can be implemented first
- Parent blocks can aggregate child context
- Reduces circular dependencies

### Why Priority-Based Rule Packing?
- Errors must never be skipped (safety)
- Security is always high priority (compliance)
- Less critical rules can be deferred

### Why Section Routing?
- Smaller context = faster responses
- Focused agents = better outputs
- Less confusion from irrelevant info

---

## 6. CodingAgent Design

The CodingAgent is the primary code generation agent, designed with a "skeleton-first" approach.

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scope | Skeleton-first | Generate interfaces, then fill implementations |
| Context | Full relevant files | Give agent complete context of related code |
| Ambiguity | Hybrid | Ask critical questions, assume minor ones |
| Languages | Single agent + plugins | Language-agnostic with plugin support |

### Generation Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    PHASE 1: SKELETON                             │
│  Generate interfaces, types, signatures (no implementations)     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   PHASE 2: AMBIGUITY CHECK                       │
│  Critical → ASK user  |  Minor → ASSUME with documentation      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  PHASE 3: CONTEXT BUILD                          │
│  Gather full content of dependencies, siblings, type files      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  PHASE 4: IMPLEMENTATION                         │
│  Fill in method bodies, handle errors, add logging              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  PHASE 5: VALIDATION                             │
│  Syntax check, write files if valid                              │
└─────────────────────────────────────────────────────────────────┘
```

### Language Plugins

```
CodingAgent
    │
    ▼
PluginRegistry
    ├── PythonPlugin    (pytest, snake_case, Google docstrings)
    ├── TypeScriptPlugin (jest, camelCase, JSDoc)
    └── (extensible)
```

### Ambiguity Categories

**Critical (ALWAYS ASK):**
- Security, authentication, authorization
- Data persistence, external APIs
- Breaking changes, payment, compliance

**Minor (ASSUME with docs):**
- Variable naming, error messages
- Log levels, docstring style
- Import ordering, code formatting

---

## 7. SecurityScanAgent Design

The SecurityScanAgent performs security analysis with dual execution modes.

### Execution Modes

| Mode | Triggers | Duration | Checks |
|------|----------|----------|--------|
| **Lightweight** | Every PR, pre-commit | ~30s | Pattern-based (secrets, injection, XSS, crypto) |
| **Heavyweight** | Nightly, on-demand | ~5-10min | Pattern + LLM analysis + spec compliance |

### Scanner Pipeline

```
SecurityScanAgent
    │
    ▼
ScannerRegistry
    ├── PatternScanner     (fast, regex-based, always runs)
    ├── LLMScanner         (heavyweight only, deep analysis)
    └── SpecComplianceScanner (heavyweight only, verifies spec requirements)
```

### Severity Levels

| Severity | Blocks PR | Blocks Deploy | Examples |
|----------|-----------|---------------|----------|
| CRITICAL | Yes | Yes | Hardcoded secrets, SQL injection |
| HIGH | Yes | No | XSS, weak crypto, missing auth |
| MEDIUM | No | No | Missing rate limiting, input validation |
| LOW | No | No | Best practice suggestions |

### Built-in Pattern Detection

- **Secrets:** Hardcoded passwords, API keys, private keys
- **Injection:** SQL, command, code (eval/exec)
- **XSS:** innerHTML, document.write, unsafe templates
- **Crypto:** MD5, SHA1, insecure random
- **Config:** Debug mode, binding to 0.0.0.0

---

## 8. File Structure

```
src/
├── orchestration/
│   ├── section_router.py      # Routes spec sections to agents
│   ├── flow_orchestrator.py   # Manages agent execution DAG
│   ├── block_pipeline.py      # Processes block hierarchy
│   └── pipeline.py            # Basic sequential pipeline
│
├── rules/
│   ├── context_manager.py     # Packs rules to fit context
│   ├── engine.py              # Loads and validates rules
│   └── validators.py          # Built-in validation functions
│
├── llm/
│   ├── client.py              # LLM client interface
│   └── mock_client.py         # Mock client for testing
│
└── agents/
    ├── base.py                # AgentContext with block/rules support
    ├── coding/
    │   ├── agent.py           # CodingAgent implementation
    │   ├── context_builder.py # Builds code context for LLM
    │   ├── ambiguity.py       # Ambiguity detection and resolution
    │   └── plugins/
    │       ├── base.py        # Plugin interface
    │       ├── registry.py    # Plugin registry
    │       ├── python_plugin.py
    │       └── typescript_plugin.py
    │
    └── security/
        ├── agent.py           # SecurityScanAgent implementation
        ├── findings.py        # Finding, SecurityReport classes
        └── scanners/
            ├── base.py        # Scanner interface
            ├── registry.py    # Scanner registry
            ├── pattern_scanner.py   # Fast regex-based detection
            ├── llm_scanner.py       # LLM-powered deep analysis
            └── spec_compliance.py   # Spec requirement verification
```
