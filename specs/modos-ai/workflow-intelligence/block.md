# Block Specification: Workflow Intelligence

## 0. Block Configuration

### 0.1: Hierarchy

- block_type: component
- parent: modos-ai

### 0.2: Sub-Blocks

| Name | Type | Description |
|------|------|-------------|
| signals | module | Event-driven signal detection from entity changes |
| cases | module | Case management for grouping related signals |
| workflow-mining | module | Process discovery from historical execution data |

### 0.3: Scoped Rules

| ID | Name | Category | Severity | Sections | Validator | Description |
|----|------|----------|----------|----------|-----------|-------------|
| WFI-001 | Signal Idempotency | code_quality | error | implementation | check_idempotency | Signal handlers must be idempotent |
| WFI-002 | Case State Machine | code_quality | error | implementation | check_state_machine | Case transitions must follow defined states |

### 0.4: Same-As References

| Target | Source | Source Section | Mode |
|--------|--------|----------------|------|
| security | ../security | security | extend |

## 1. Metadata

- spec_id: workflow-intelligence
- version: 1.0.0
- status: draft
- tech_stack: Python, Temporal, Redis, PostgreSQL
- author: Modos AI Team
- created: 2024-01-15
- updated: 2024-02-19

## 2. Overview

### Summary

Workflow Intelligence detects actionable signals from entity changes, groups related signals into cases for human review or automated action, and mines historical data to discover workflow patterns. It serves as the "brain" that identifies what work needs to be done.

### Goals

- Detect workflow signals from entity change events in real-time
- Group related signals into actionable cases
- Prioritize cases based on urgency and business impact
- Discover workflow patterns from historical execution data
- Enable custom signal rules via configuration

### Non-Goals

- Execute workflows (that's safe-execution-runtime)
- Store raw entity data (that's connected-data-spine)
- Provide a visual workflow designer (API-first in v1)

### Background

Knowledge workers spend hours identifying what needs attention across systems. Workflow Intelligence automates this by monitoring entity changes and detecting patterns that indicate action is needed. For example, detecting when a deal is stalled, a customer is at risk of churning, or an approval is overdue.

## 3. Inputs

### User Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| signal_rules | list[SignalRule] | no | default | Custom signal detection rules |
| case_config | CaseConfig | no | default | Case grouping and prioritization settings |
| alert_channels | list[AlertChannel] | no | [] | Where to send urgent alerts |

### System Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| entity_events | Stream[EntityEvent] | yes | - | Entity change event stream |
| tenant_id | UUID | yes | - | Tenant context |
| historical_executions | list[ExecutionTrace] | no | [] | Past workflow executions for mining |

### Environment Variables

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| SIGNAL_DETECTION_WINDOW | int | no | 3600 | Time window for pattern detection (seconds) |
| CASE_STALENESS_THRESHOLD | int | no | 86400 | Seconds before case marked stale |
| MAX_SIGNALS_PER_CASE | int | no | 100 | Maximum signals grouped in one case |

## 4. Outputs

### Return Values

| Name | Type | Description |
|------|------|-------------|
| signals | list[Signal] | Detected workflow signals |
| cases | list[Case] | Grouped and prioritized cases |
| discovered_patterns | list[WorkflowPattern] | Mined workflow patterns |
| recommendations | list[ActionRecommendation] | Suggested actions for cases |

### Side Effects

- Signals persisted to database
- Cases created/updated
- Alerts sent for urgent signals
- Workflow patterns saved for future detection

### Events

| Event | Payload | Description |
|-------|---------|-------------|
| signal.detected | SignalDetectedEvent | New signal identified |
| signal.dismissed | SignalDismissedEvent | Signal marked as not actionable |
| case.created | CaseCreatedEvent | New case opened |
| case.updated | CaseUpdatedEvent | Case status/priority changed |
| case.resolved | CaseResolvedEvent | Case completed |
| pattern.discovered | PatternDiscoveredEvent | New workflow pattern found |

## 5. Dependencies

### Internal

| Module | Purpose |
|--------|---------|
| connected-data-spine | Entity events source |
| safe-execution-runtime | Action recommendations |
| security | Tenant isolation |

### External

| Package | Version | Purpose |
|---------|---------|---------|
| temporalio | ^1.4 | Event processing workflows |
| redis | ^5.0 | Event streaming |
| scikit-learn | ^1.4 | Pattern mining |
| anthropic | ^0.18 | AI-powered signal analysis |

### Services

| Service | Purpose |
|---------|---------|
| PostgreSQL | Signal and case storage |
| Redis | Event stream, real-time processing |
| Temporal | Durable signal processing |

## 6. API Contract

### Endpoints

| Method | Path | Request | Response | Description |
|--------|------|---------|----------|-------------|
| GET | /api/v1/signals | SignalQuery | SignalPage | Query detected signals |
| POST | /api/v1/signals/{id}/dismiss | DismissRequest | Signal | Dismiss a signal |
| GET | /api/v1/cases | CaseQuery | CasePage | Query cases |
| GET | /api/v1/cases/{id} | - | CaseDetail | Get case with signals |
| POST | /api/v1/cases/{id}/resolve | ResolveRequest | Case | Mark case resolved |
| POST | /api/v1/signal-rules | SignalRule | SignalRule | Create custom rule |
| GET | /api/v1/patterns | PatternQuery | list[Pattern] | Get discovered patterns |

### Error Codes

| Code | Description |
|------|-------------|
| SIGNAL_NOT_FOUND | Signal does not exist |
| CASE_NOT_FOUND | Case does not exist |
| INVALID_RULE | Signal rule configuration invalid |
| PATTERN_CONFLICT | Pattern conflicts with existing |

## 7. Test Cases

### Unit Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| UT-WFI-001 | Detect deal stalled signal | Deal unchanged 14 days | Signal created | Mock entity | - |
| UT-WFI-002 | Group related signals | 3 signals same account | Single case | - | - |
| UT-WFI-003 | Priority calculation | High-value + urgent | Priority = critical | - | - |
| UT-WFI-004 | Custom rule matching | Custom rule + event | Signal if match | Rule config | - |
| UT-WFI-005 | Pattern extraction | 10 similar executions | Pattern discovered | Execution traces | - |

### Integration Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| IT-WFI-001 | End-to-end signal flow | Entity change event | Signal + case created | Streaming setup | - |
| IT-WFI-002 | Alert delivery | Urgent signal | Alert sent | Alert channel | - |
| IT-WFI-003 | Pattern mining job | 1000 executions | Patterns discovered | Historical data | - |

- min_line_coverage: 85
- min_branch_coverage: 75

## 8. Edge Cases

### Boundary Conditions

- No entity changes in detection window
- Signal matches multiple rules
- Case reaches max signal limit
- Pattern mining with sparse data

### Concurrency

- Multiple signals for same entity simultaneously
- Case update during signal addition
- Pattern mining while new data arriving

### Failure Modes

- Entity event stream disconnected
- Signal rule evaluation timeout
- Case database write failure
- AI analysis service unavailable

## 9. Error Handling

### Error Types

| Type | Retryable | Handler |
|------|-----------|---------|
| EventStreamError | yes | Reconnect with backoff |
| RuleEvaluationError | no | Log and skip signal |
| CaseWriteError | yes | Retry with transaction |
| AIAnalysisError | yes | Fallback to rule-based |

- max_retries: 3
- backoff_strategy: exponential

## 10. Performance

- p50: 50
- p95: 200
- p99: 500
- target_rps: 1000
- memory_limit: 1024
- signal_detection_latency: 5000
- max_concurrent_rules: 100

## 11. Security

- requires_auth: true
- auth_method: JWT
- handles_pii: true
- encryption_at_rest: true
- encryption_in_transit: true

### Roles

| Role | Permissions |
|------|-------------|
| admin | Manage rules, view all cases |
| operator | Resolve cases, dismiss signals |
| analyst | Read signals and cases |

## 12. Implementation

### Algorithms

- **Signal Detection**: Rule-based pattern matching + ML anomaly detection
- **Case Grouping**: Entity-based clustering with temporal windows
- **Priority Scoring**: Weighted combination of urgency, impact, confidence
- **Pattern Mining**: Sequence mining on execution traces

### Patterns

- **Event Sourcing**: Signals as events for auditability
- **CQRS**: Separate read models for case queries
- **Saga**: Multi-step signal processing

### Constraints

- Signal detection must complete within 5 seconds
- Cases must have at least one signal
- Dismissed signals cannot be un-dismissed
- Pattern mining runs async (not real-time)

## 13. Acceptance

### Criteria

- [ ] Default signal rules detect common patterns (stalled deals, overdue tasks)
- [ ] Custom rules can be added via API
- [ ] Cases correctly group related signals
- [ ] Priority scoring reflects business impact
- [ ] Pattern mining identifies recurring workflows

### Definition of Done

- [ ] Signal detection engine implemented
- [ ] Case management API complete
- [ ] Pattern mining job functional
- [ ] Unit tests >85% coverage
- [ ] Integration tests passing
- [ ] Performance benchmarks met
