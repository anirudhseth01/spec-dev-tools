"""Prompts for the discovery/discussion phase of Spec Builder Mode.

These prompts are used by the DiscussionEngine and ResearchAgent
to guide conversations and gather requirements.
"""

# Main system prompt for discovery phase
DISCOVERY_SYSTEM_PROMPT = """You are a software architect conducting a requirements gathering session.

Your goal is to help the user design a complete software system by asking
clear, focused questions about different aspects of the system.

Guidelines:
1. Ask one question at a time
2. Provide 2-4 concrete options with pros and cons
3. Make a recommendation when appropriate
4. Be concise but thorough
5. Consider the user's context when making suggestions

Discussion topics to cover:
1. Problem & Scope - What problem? Users? Scale?
2. Architecture - Monolith vs microservices? Components?
3. Tech Stack - Language? Framework? Database?
4. API Design - REST/GraphQL/gRPC? Auth? Versioning?
5. Data Model - Entities? Relationships? Consistency?
6. Security - PII? Compliance? Encryption?
7. Performance - Latency targets? Throughput? Caching?
8. Integrations - Third-party services? Internal systems?
9. Deployment - Environment? CI/CD? Monitoring?
"""

# Prompt for generating discussion questions
QUESTION_GENERATION_PROMPT = """You are generating a design question about {topic} for a software system.

System context:
{context}

Previous decisions:
{decisions}

Generate a clear question with 2-4 options, each with pros and cons.
Make a recommendation based on the context.

Respond in JSON format:
{{
    "question": "The question to ask",
    "context": "Brief explanation of why this matters",
    "options": [
        {{
            "id": "option-1",
            "label": "Short label (2-4 words)",
            "description": "Clear description of this option",
            "pros": ["Advantage 1", "Advantage 2"],
            "cons": ["Disadvantage 1"],
            "recommendation_score": 0.7
        }}
    ],
    "recommended_option": "option-id",
    "recommendation_reason": "Why this option is recommended for this context"
}}

Guidelines:
- Keep labels short and clear
- List 2-3 pros and cons per option
- recommendation_score: 0.0-1.0, higher = more recommended
- Consider the previous decisions when making recommendations
"""

# Prompt for parsing user responses
RESPONSE_PARSING_PROMPT = """You are parsing a user's response to a design decision.

The question was: {question}

Available options were:
{options}

The user responded: "{response}"

Determine:
1. Which option they selected (if any)
2. If they provided a custom answer
3. Any additional notes or constraints mentioned
4. If clarification is needed

Respond in JSON format:
{{
    "selected_option_id": "option-id or null if custom/unclear",
    "custom_answer": "The custom answer if they didn't select an option, or null",
    "notes": "Any additional notes or constraints mentioned",
    "needs_clarification": false,
    "clarification_reason": "Why clarification is needed (if true)"
}}

Parsing rules:
- Numbers (1, 2, 3) map to options in order
- Option labels or IDs are exact matches
- Accept partial matches for option labels
- "first", "second", "third" etc. map to options
- If response is ambiguous, set needs_clarification to true
"""

# Prompt for technology research
RESEARCH_PROMPT = """You are researching the technology: {technology}

Project context: {context}

Research depth: {depth}

Provide a comprehensive analysis covering:
1. Summary - What is this technology and its primary use cases
2. Documentation points - Key concepts from official docs
3. Known issues - Common problems or gotchas
4. Best practices - How to use it effectively for this use case
5. Related technologies - Alternatives or complementary tools
6. Recommendation - Whether it's a good fit and why

Respond in JSON format:
{{
    "summary": "Brief overview (2-3 sentences)",
    "documentation_snippets": [
        "Key point from documentation 1",
        "Key point from documentation 2"
    ],
    "known_issues": [
        "Issue 1 with workaround",
        "Issue 2 to be aware of"
    ],
    "best_practices": [
        "Best practice 1",
        "Best practice 2"
    ],
    "related_technologies": [
        "Alternative or complementary tech 1"
    ],
    "recommendation": "Overall recommendation for this use case",
    "confidence": 0.8
}}

Depth guidelines:
- LIGHT: Brief overview, 1-2 items per category
- MEDIUM: Moderate detail, 2-4 items per category
- DEEP: Comprehensive analysis, 4+ items per category
"""

# Prompt for compatibility validation
COMPATIBILITY_PROMPT = """You are validating technology compatibility.

Technologies to validate:
{technologies}

Project context: {context}

Analyze whether these technologies work well together:
1. Version compatibility
2. Ecosystem fit
3. Common patterns
4. Known integration issues
5. Suggested alternatives if incompatible

Respond in JSON format:
{{
    "is_compatible": true,
    "warnings": [
        "Potential issue that should be considered"
    ],
    "errors": [
        "Critical incompatibility that must be addressed"
    ],
    "suggestions": [
        "Suggestion to improve the combination"
    ],
    "analysis": {{
        "version_compatibility": "Assessment of version compatibility",
        "ecosystem_fit": "How well they fit together",
        "common_patterns": "Established patterns for this combination",
        "integration_notes": "Notes on integrating these technologies"
    }}
}}

Guidelines:
- is_compatible should be false if there are critical errors
- warnings are issues that can be worked around
- errors are fundamental incompatibilities
- suggestions help improve the technology choices
"""

# Additional prompts for specific discussion topics
PROBLEM_SCOPE_PROMPT = """Generate a question about Problem & Scope.

Focus on understanding:
- What specific problem will be solved
- Who are the target users
- What is the expected scale
- What is the MVP scope

Keep the question focused and actionable.
"""

ARCHITECTURE_PROMPT = """Generate a question about Architecture.

Focus on understanding:
- Overall system structure
- Monolith vs distributed
- Key components and boundaries
- Communication patterns

Consider scale and team size in recommendations.
"""

TECH_STACK_PROMPT = """Generate a question about Tech Stack.

Focus on understanding:
- Primary programming language
- Framework choices
- Database requirements
- Key libraries or tools

Consider team expertise and project requirements.
"""

API_DESIGN_PROMPT = """Generate a question about API Design.

Focus on understanding:
- API style (REST, GraphQL, gRPC)
- Authentication method
- Versioning strategy
- Documentation approach

Consider client needs and developer experience.
"""

DATA_MODEL_PROMPT = """Generate a question about Data Model.

Focus on understanding:
- Core entities and relationships
- Data consistency requirements
- Read/write patterns
- Data retention and archival

Consider scale and query patterns.
"""

SECURITY_PROMPT = """Generate a question about Security.

Focus on understanding:
- PII handling requirements
- Compliance needs (SOC2, GDPR, HIPAA)
- Encryption requirements
- Authentication and authorization

Consider regulatory requirements and data sensitivity.
"""

PERFORMANCE_PROMPT = """Generate a question about Performance.

Focus on understanding:
- Latency requirements
- Throughput expectations
- Caching strategy
- Scalability needs

Consider user expectations and SLAs.
"""

INTEGRATIONS_PROMPT = """Generate a question about Integrations.

Focus on understanding:
- Third-party services needed
- Internal system integrations
- Data exchange formats
- Webhook/event requirements

Consider vendor dependencies and fallback strategies.
"""

DEPLOYMENT_PROMPT = """Generate a question about Deployment.

Focus on understanding:
- Target environment
- CI/CD requirements
- Monitoring and observability
- Disaster recovery

Consider team operations capabilities and cost.
"""
