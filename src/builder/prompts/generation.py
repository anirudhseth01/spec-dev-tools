"""Prompts for spec generation in Spec Builder Mode.

These prompts are used by the BlockDesigner and SpecGenerator
to create block hierarchies and specification content.
"""

# Main prompt for spec generation
SPEC_GENERATION_PROMPT = """You are generating a specification markdown file for a software component.

Block information:
- Name: {name}
- Path: {path}
- Type: {block_type}
- Description: {description}
- Tech Stack: {tech_stack}
- Dependencies: {dependencies}
- API Endpoints: {api_endpoints}

Design decisions from planning session:
{decisions}

Generate a complete specification following this structure:

# Block Specification: {name}

## 0. Block Configuration
(Hierarchy, sub-blocks, scoped rules, same-as references)

## 1. Metadata
(spec_id, version, status, tech_stack, author, dates)

## 2. Overview
(Summary, goals, non-goals, background)

## 3. Inputs
(User inputs, system inputs, environment variables)

## 4. Outputs
(Return values, side effects, events)

## 5. Dependencies
(Internal, external, services)

## 6. API Contract
(Endpoints with method/path/request/response, error codes)

## 7. Test Cases
(Unit tests, integration tests, coverage thresholds)

## 8. Edge Cases
(Boundary conditions, concurrency, failure modes)

## 9. Error Handling
(Error types, retry strategy, backoff)

## 10. Performance
(Latency targets, throughput, memory limits)

## 11. Security
(Authentication, authorization, data protection)

## 12. Implementation
(Algorithms, patterns, constraints)

## 13. Acceptance Criteria
(Criteria checklist, done definition)

Guidelines:
- Use proper markdown formatting with tables
- Be specific and actionable in requirements
- Derive requirements from design decisions
- Include realistic test cases
- Consider security and performance implications
"""

# Prompt for designing the block hierarchy
HIERARCHY_DESIGN_PROMPT = """You are designing a hierarchical block structure for a software system.

System: {system_name}
Description: {description}

Design decisions:
{decisions}

Create a hierarchical block structure following these rules:
1. Exactly one ROOT block containing the entire system
2. ROOT contains COMPONENT blocks (major features/services)
3. COMPONENT blocks can contain MODULE blocks (sub-features)
4. MODULE blocks can contain LEAF blocks (implementation units)
5. Each block has dependencies on other blocks within the same level or below

Respond in JSON format:
{{
    "root_name": "system-name-slug",
    "blocks": [
        {{
            "path": "system-name",
            "name": "System Name",
            "block_type": "root",
            "description": "Root block description",
            "parent_path": null,
            "tech_stack": "Python, FastAPI",
            "dependencies": [],
            "api_endpoints": []
        }},
        {{
            "path": "system-name/component-name",
            "name": "Component Name",
            "block_type": "component",
            "description": "Component description",
            "parent_path": "system-name",
            "tech_stack": "Python, FastAPI",
            "dependencies": [],
            "api_endpoints": [
                {{"method": "GET", "path": "/api/endpoint", "description": "Description"}}
            ]
        }},
        {{
            "path": "system-name/component-name/module-name",
            "name": "Module Name",
            "block_type": "module",
            "description": "Module description",
            "parent_path": "system-name/component-name",
            "tech_stack": "Python",
            "dependencies": ["system-name/other-component"],
            "api_endpoints": []
        }},
        {{
            "path": "system-name/component-name/module-name/leaf-name",
            "name": "Leaf Name",
            "block_type": "leaf",
            "description": "Leaf implementation unit",
            "parent_path": "system-name/component-name/module-name",
            "tech_stack": "Python",
            "dependencies": [],
            "api_endpoints": []
        }}
    ],
    "cross_block_rules": [
        {{
            "rule": "All API calls must go through gateway",
            "applies_to": ["api-gateway"],
            "severity": "error"
        }}
    ]
}}

Design guidelines:
- Use slug-case for paths (lowercase, hyphens)
- Keep hierarchy depth to 3-4 levels max
- Group related functionality in components
- API endpoints go on blocks that expose them
- Dependencies should not create cycles
"""

# Prompt for extracting components from decisions
COMPONENT_EXTRACTION_PROMPT = """You are analyzing design decisions to identify system components.

Design decisions:
{decisions}

System description: {description}

Identify the main components that need to be built.
For each component, specify:
- name: slug-case identifier
- description: what it does
- category: api, service, data, integration, worker, library
- dependencies: other components it depends on
- api_endpoints: if it exposes HTTP endpoints

Respond in JSON format:
{{
    "components": [
        {{
            "name": "api-gateway",
            "description": "Main API entry point handling routing and auth",
            "category": "api",
            "dependencies": [],
            "api_endpoints": [
                {{"method": "GET", "path": "/health"}},
                {{"method": "GET", "path": "/api/v1/status"}}
            ]
        }},
        {{
            "name": "user-service",
            "description": "Handles user management and authentication",
            "category": "service",
            "dependencies": ["database"],
            "api_endpoints": []
        }},
        {{
            "name": "database",
            "description": "Data access layer",
            "category": "data",
            "dependencies": [],
            "api_endpoints": []
        }},
        {{
            "name": "notification-worker",
            "description": "Async notification processing",
            "category": "worker",
            "dependencies": ["user-service"],
            "api_endpoints": []
        }}
    ]
}}

Component categories:
- api: Exposes HTTP/REST/GraphQL endpoints
- service: Business logic layer
- data: Database access, repositories
- integration: Third-party integrations
- worker: Background job processors
- library: Shared utility code

Guidelines:
- Extract components based on architecture decisions
- Consider tech stack when naming (e.g., database type)
- Group related functionality
- Keep dependencies acyclic
- API components are usually at the top of the dependency chain
"""

# Template-specific prompts
API_SERVICE_TEMPLATE_PROMPT = """Generate an API service specification.

Focus areas:
- RESTful endpoint definitions
- Request/response schemas
- Authentication requirements
- Rate limiting
- Pagination for list endpoints
- Error responses

Include specific HTTP endpoints with:
- Method (GET, POST, PUT, DELETE)
- Path with parameters
- Request body schema
- Response body schema
- Status codes
"""

CLI_TOOL_TEMPLATE_PROMPT = """Generate a CLI tool specification.

Focus areas:
- Command structure (subcommands, flags)
- Input/output formats
- Configuration options
- Exit codes
- Shell completion support
- Help text

Include:
- Main commands and subcommands
- Required and optional flags
- Environment variable support
- Example usage
"""

WORKER_SERVICE_TEMPLATE_PROMPT = """Generate a worker service specification.

Focus areas:
- Queue/message processing
- Job types and payloads
- Retry logic
- Dead letter handling
- Concurrency limits
- Monitoring

Include:
- Message schemas
- Processing guarantees
- Error handling
- Scaling considerations
"""

DATA_PIPELINE_TEMPLATE_PROMPT = """Generate a data pipeline specification.

Focus areas:
- Data sources and sinks
- Transformation logic
- Scheduling
- Error handling
- Monitoring and alerting
- Data quality checks

Include:
- Input/output schemas
- Processing steps
- Failure modes
- Recovery procedures
"""

LIBRARY_TEMPLATE_PROMPT = """Generate a library specification.

Focus areas:
- Public API surface
- Core abstractions
- Extension points
- Error handling
- Performance considerations
- Versioning

Include:
- Main interfaces/classes
- Usage examples
- Configuration options
- Integration patterns
"""
