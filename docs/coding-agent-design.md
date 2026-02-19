# CodingAgent End-to-End Design

## Design Decisions Summary

| Question | Choice | Description |
|----------|--------|-------------|
| Scope per invocation | Skeleton-first | Generate interfaces → fill implementations |
| Existing code visibility | Full relevant files | Give agent complete context of related code |
| Handling ambiguity | Hybrid | Ask critical questions, assume minor ones |
| Language handling | Single agent + plugins | One agent with language-specific prompts/configs |

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CodingAgent                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │   Context    │───▶│   Skeleton   │───▶│Implementation│          │
│  │   Builder    │    │   Generator  │    │   Filler     │          │
│  └──────────────┘    └──────────────┘    └──────────────┘          │
│         │                   │                   │                   │
│         ▼                   ▼                   ▼                   │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │   Language   │    │   Ambiguity  │    │   Chunking   │          │
│  │   Plugin     │    │   Resolver   │    │   Strategy   │          │
│  └──────────────┘    └──────────────┘    └──────────────┘          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │   LLM Provider   │
                    │  (Claude API)    │
                    └──────────────────┘
```

---

## 2. Skeleton-First Generation Flow

### Phase 1: Interface Generation

```
┌─────────────────────────────────────────────────────────────────┐
│                    PHASE 1: SKELETON                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   INPUT: Spec (routed sections)                                  │
│          ├── api_contract                                        │
│          ├── inputs/outputs                                      │
│          └── dependencies                                        │
│                                                                  │
│   OUTPUT: Skeleton Files                                         │
│          ├── interfaces/protocols                                │
│          ├── abstract base classes                               │
│          ├── type definitions                                    │
│          ├── function signatures (body: pass/raise)              │
│          └── module structure (__init__.py files)                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Example Skeleton Output (Python):**

```python
# src/payment/gateway.py - SKELETON

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from decimal import Decimal

@dataclass
class PaymentRequest:
    """Input for payment processing."""
    amount: Decimal
    currency: str
    customer_id: str
    payment_method: str
    metadata: Optional[dict] = None

@dataclass
class PaymentResult:
    """Output from payment processing."""
    transaction_id: str
    status: str  # "success", "failed", "pending"
    error_message: Optional[str] = None

class PaymentGateway(ABC):
    """Abstract payment gateway interface."""

    @abstractmethod
    def process_payment(self, request: PaymentRequest) -> PaymentResult:
        """Process a payment request."""
        raise NotImplementedError

    @abstractmethod
    def refund(self, transaction_id: str, amount: Optional[Decimal] = None) -> PaymentResult:
        """Refund a payment."""
        raise NotImplementedError
```

### Phase 2: Implementation Filling

```
┌─────────────────────────────────────────────────────────────────┐
│                    PHASE 2: IMPLEMENTATION                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   INPUT: Skeleton + Full Spec + Related Code Context             │
│          ├── skeleton files from Phase 1                         │
│          ├── implementation section from spec                    │
│          ├── error_handling section                              │
│          └── relevant existing files (full content)              │
│                                                                  │
│   PROCESS: For each skeleton file:                               │
│          1. Identify unfilled methods                            │
│          2. Gather method-specific context                       │
│          3. Generate implementation                              │
│          4. Validate against interface contract                  │
│                                                                  │
│   OUTPUT: Complete Implementation Files                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation Example:**

```python
# src/payment/stripe_gateway.py - IMPLEMENTATION

from payment.gateway import PaymentGateway, PaymentRequest, PaymentResult
import stripe

class StripeGateway(PaymentGateway):
    """Stripe implementation of PaymentGateway."""

    def __init__(self, api_key: str):
        stripe.api_key = api_key

    def process_payment(self, request: PaymentRequest) -> PaymentResult:
        """Process payment via Stripe."""
        try:
            intent = stripe.PaymentIntent.create(
                amount=int(request.amount * 100),  # Stripe uses cents
                currency=request.currency,
                customer=request.customer_id,
                payment_method=request.payment_method,
                confirm=True,
                metadata=request.metadata or {},
            )
            return PaymentResult(
                transaction_id=intent.id,
                status="success" if intent.status == "succeeded" else "pending",
            )
        except stripe.error.CardError as e:
            return PaymentResult(
                transaction_id="",
                status="failed",
                error_message=str(e),
            )

    def refund(self, transaction_id: str, amount: Optional[Decimal] = None) -> PaymentResult:
        """Refund via Stripe."""
        try:
            refund_params = {"payment_intent": transaction_id}
            if amount:
                refund_params["amount"] = int(amount * 100)

            refund = stripe.Refund.create(**refund_params)
            return PaymentResult(
                transaction_id=refund.id,
                status="success",
            )
        except stripe.error.StripeError as e:
            return PaymentResult(
                transaction_id="",
                status="failed",
                error_message=str(e),
            )
```

---

## 3. Context Building Strategy

### Full Relevant Files Approach

```python
class ContextBuilder:
    """Builds LLM context with full relevant file visibility."""

    def build_context(
        self,
        spec: RoutedSpec,
        project_root: Path,
        target_files: list[Path],
    ) -> CodeContext:
        """
        Gather full context for code generation.

        Strategy:
        1. Identify files that target files will import/depend on
        2. Identify files that import/depend on target files
        3. Load full content of related files (not snippets)
        4. Include project conventions (existing patterns)
        """
        context = CodeContext()

        # 1. Direct dependencies (imports)
        for target in target_files:
            deps = self._analyze_imports(target, project_root)
            for dep in deps:
                context.add_file(dep, self._read_full_file(dep))

        # 2. Reverse dependencies (who imports us)
        # Important for understanding interface contracts
        reverse_deps = self._find_importers(target_files, project_root)
        for rev_dep in reverse_deps:
            context.add_file(rev_dep, self._read_full_file(rev_dep))

        # 3. Sibling files (same directory, likely related)
        for target in target_files:
            siblings = self._get_siblings(target)
            for sibling in siblings[:5]:  # Limit to avoid explosion
                context.add_file(sibling, self._read_full_file(sibling))

        # 4. Type definitions / shared models
        type_files = self._find_type_files(project_root)
        for tf in type_files:
            context.add_file(tf, self._read_full_file(tf))

        return context
```

### Context Window Management

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONTEXT BUDGET (100k tokens)                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Reserved Allocations:                                          │
│   ├── System prompt + instructions    ~2,000 tokens   (2%)      │
│   ├── Spec sections (routed)          ~4,000 tokens   (4%)      │
│   ├── Rules (packed)                  ~4,000 tokens   (4%)      │
│   ├── Response buffer                ~20,000 tokens  (20%)      │
│   │                                                              │
│   Flexible Budget:                                               │
│   └── Related code context          ~70,000 tokens  (70%)       │
│       ├── Direct dependencies         ~30,000                   │
│       ├── Reverse dependencies        ~20,000                   │
│       └── Sibling/type files          ~20,000                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Ambiguity Resolution: Hybrid Approach

### Critical vs Minor Classification

```python
class AmbiguityResolver:
    """Handles ambiguous requirements with hybrid approach."""

    # Critical ambiguities - ALWAYS ASK
    CRITICAL_PATTERNS = [
        "security",           # Auth, encryption, access control
        "data_persistence",   # Database schema decisions
        "external_api",       # Third-party integrations
        "breaking_change",    # Changes to existing contracts
        "payment",            # Financial transactions
        "compliance",         # Legal/regulatory requirements
    ]

    # Minor ambiguities - ASSUME with clear documentation
    MINOR_PATTERNS = [
        "variable_naming",    # Use project conventions
        "error_message_text", # Use sensible defaults
        "log_levels",         # Follow logging standards
        "docstring_style",    # Match existing style
        "import_ordering",    # Use formatter defaults
    ]

    def resolve(self, ambiguity: Ambiguity) -> Resolution:
        """
        Resolve an ambiguity by asking or assuming.
        """
        if self._is_critical(ambiguity):
            return Resolution(
                action="ask",
                question=self._format_question(ambiguity),
                options=ambiguity.possible_choices,
            )
        else:
            assumption = self._make_assumption(ambiguity)
            return Resolution(
                action="assume",
                chosen=assumption,
                documentation=f"# ASSUMPTION: {ambiguity.description}\n"
                             f"# Chose: {assumption}\n"
                             f"# Reason: {self._explain_assumption(ambiguity)}",
            )

    def _is_critical(self, ambiguity: Ambiguity) -> bool:
        """Check if ambiguity requires user input."""
        return any(
            pattern in ambiguity.category.lower()
            for pattern in self.CRITICAL_PATTERNS
        )
```

### Question Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    AMBIGUITY DETECTED                            │
│                                                                  │
│   Spec says: "Store user preferences"                            │
│   Ambiguity: Storage mechanism not specified                     │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Classification: CRITICAL (data_persistence)                    │
│                                                                  │
│   ┌───────────────────────────────────────────────────────────┐ │
│   │  QUESTION TO USER:                                         │ │
│   │                                                            │ │
│   │  The spec mentions storing user preferences but doesn't   │ │
│   │  specify the storage mechanism. Which should I use?       │ │
│   │                                                            │ │
│   │  A) PostgreSQL (existing DB in project)                   │ │
│   │  B) Redis (for fast access, TTL support)                  │ │
│   │  C) SQLite (simple, file-based)                           │ │
│   │  D) In-memory only (no persistence)                       │ │
│   │                                                            │ │
│   └───────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Assumption Documentation

When assuming (minor ambiguities), document clearly:

```python
# src/utils/logger.py

# ASSUMPTION: Log format not specified in spec
# Chose: JSON structured logging
# Reason: Project already uses structlog in 3 other modules
# To change: Override LOG_FORMAT in config.py

import structlog

logger = structlog.get_logger()
```

---

## 5. Language Plugin System

### Plugin Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      CodingAgent                                 │
│                          │                                       │
│                          ▼                                       │
│               ┌─────────────────────┐                           │
│               │   LanguagePlugin    │                           │
│               │   Registry          │                           │
│               └──────────┬──────────┘                           │
│                          │                                       │
│    ┌─────────────────────┼─────────────────────┐                │
│    ▼                     ▼                     ▼                │
│ ┌──────────┐      ┌──────────┐      ┌──────────┐               │
│ │ Python   │      │ TypeScript│     │   Go     │               │
│ │ Plugin   │      │  Plugin   │     │  Plugin  │               │
│ └──────────┘      └──────────┘      └──────────┘               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Plugin Interface

```python
# src/agents/coding/plugins/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class LanguageConventions:
    """Language-specific conventions."""
    file_extension: str
    import_style: str           # "explicit", "wildcard", "namespace"
    type_annotation: str        # "inline", "separate", "optional"
    error_handling: str         # "exceptions", "result_types", "error_codes"
    naming_convention: str      # "snake_case", "camelCase", "PascalCase"
    docstring_format: str       # "google", "numpy", "jsdoc", "godoc"
    test_framework: str         # "pytest", "jest", "go test"

class LanguagePlugin(ABC):
    """Base class for language-specific code generation."""

    @property
    @abstractmethod
    def language_name(self) -> str:
        """Return language identifier."""
        pass

    @property
    @abstractmethod
    def conventions(self) -> LanguageConventions:
        """Return language conventions."""
        pass

    @abstractmethod
    def generate_skeleton_prompt(self, spec: RoutedSpec) -> str:
        """Generate language-specific skeleton prompt."""
        pass

    @abstractmethod
    def generate_implementation_prompt(
        self,
        skeleton: str,
        spec: RoutedSpec,
        context: CodeContext,
    ) -> str:
        """Generate language-specific implementation prompt."""
        pass

    @abstractmethod
    def parse_generated_code(self, llm_response: str) -> list[GeneratedFile]:
        """Parse LLM response into file objects."""
        pass

    @abstractmethod
    def validate_syntax(self, code: str) -> list[SyntaxError]:
        """Validate generated code syntax."""
        pass
```

### Python Plugin Example

```python
# src/agents/coding/plugins/python_plugin.py

class PythonPlugin(LanguagePlugin):
    """Python-specific code generation plugin."""

    @property
    def language_name(self) -> str:
        return "python"

    @property
    def conventions(self) -> LanguageConventions:
        return LanguageConventions(
            file_extension=".py",
            import_style="explicit",
            type_annotation="inline",
            error_handling="exceptions",
            naming_convention="snake_case",
            docstring_format="google",
            test_framework="pytest",
        )

    def generate_skeleton_prompt(self, spec: RoutedSpec) -> str:
        return f"""
You are generating Python code skeletons. Create ONLY:
- Abstract base classes (ABC) with @abstractmethod decorators
- Dataclasses for data structures with full type hints
- Protocol classes for duck typing interfaces
- Function signatures with `raise NotImplementedError`

DO NOT generate implementations yet.

## Conventions
- Use `from __future__ import annotations` for forward refs
- Use `@dataclass` for data containers
- Use `Optional[X]` not `X | None` for compatibility
- Include docstrings in Google format

## Spec
{spec.to_prompt_context()}

Generate the skeleton files:
"""

    def generate_implementation_prompt(
        self,
        skeleton: str,
        spec: RoutedSpec,
        context: CodeContext,
    ) -> str:
        return f"""
You are implementing Python code based on the provided skeleton.

## Skeleton to Implement
```python
{skeleton}
```

## Spec Requirements
{spec.to_prompt_context()}

## Existing Code Context
{context.to_prompt()}

## Implementation Guidelines
- Replace `raise NotImplementedError` with actual implementations
- Follow existing patterns from the context files
- Handle errors using try/except with specific exception types
- Add logging using the project's logger (see context)
- Maintain the exact function signatures from the skeleton

Generate the complete implementation:
"""

    def validate_syntax(self, code: str) -> list[SyntaxError]:
        """Validate Python syntax using ast.parse."""
        import ast
        errors = []
        try:
            ast.parse(code)
        except SyntaxError as e:
            errors.append(e)
        return errors
```

### TypeScript Plugin Example

```python
# src/agents/coding/plugins/typescript_plugin.py

class TypeScriptPlugin(LanguagePlugin):
    """TypeScript-specific code generation plugin."""

    @property
    def language_name(self) -> str:
        return "typescript"

    @property
    def conventions(self) -> LanguageConventions:
        return LanguageConventions(
            file_extension=".ts",
            import_style="explicit",
            type_annotation="inline",
            error_handling="exceptions",  # or "result_types" for fp-ts style
            naming_convention="camelCase",
            docstring_format="jsdoc",
            test_framework="jest",
        )

    def generate_skeleton_prompt(self, spec: RoutedSpec) -> str:
        return f"""
You are generating TypeScript code skeletons. Create ONLY:
- Interfaces for all data structures
- Abstract classes with abstract methods
- Type aliases for complex types
- Function signatures that throw 'Not implemented'

DO NOT generate implementations yet.

## Conventions
- Use `interface` for data shapes, `type` for unions/aliases
- Use `readonly` for immutable properties
- Export all public types
- Use JSDoc comments for documentation

## Spec
{spec.to_prompt_context()}

Generate the skeleton files:
"""
```

### Plugin Registry

```python
# src/agents/coding/plugins/registry.py

class PluginRegistry:
    """Registry for language plugins."""

    def __init__(self):
        self._plugins: dict[str, LanguagePlugin] = {}
        self._register_defaults()

    def _register_defaults(self):
        """Register built-in plugins."""
        self.register(PythonPlugin())
        self.register(TypeScriptPlugin())
        self.register(GoPlugin())

    def register(self, plugin: LanguagePlugin) -> None:
        """Register a language plugin."""
        self._plugins[plugin.language_name] = plugin

    def get(self, language: str) -> LanguagePlugin:
        """Get plugin for a language."""
        if language not in self._plugins:
            raise ValueError(f"No plugin for language: {language}")
        return self._plugins[language]

    def detect_language(self, project_root: Path) -> str:
        """Auto-detect project language from files."""
        indicators = {
            "python": ["pyproject.toml", "setup.py", "requirements.txt"],
            "typescript": ["tsconfig.json", "package.json"],
            "go": ["go.mod", "go.sum"],
        }

        for lang, files in indicators.items():
            if any((project_root / f).exists() for f in files):
                return lang

        return "python"  # Default fallback
```

---

## 6. Complete CodingAgent Implementation

```python
# src/agents/coding/agent.py

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.agents.base import BaseAgent, AgentContext, AgentResult, AgentStatus
from src.agents.coding.plugins import PluginRegistry, LanguagePlugin
from src.agents.coding.context_builder import ContextBuilder
from src.agents.coding.ambiguity import AmbiguityResolver, Resolution
from src.llm.client import LLMClient


@dataclass
class GenerationState:
    """Tracks state across generation phases."""
    skeleton_files: dict[str, str] = field(default_factory=dict)
    implementation_files: dict[str, str] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    questions_asked: list[dict] = field(default_factory=list)


class CodingAgent(BaseAgent):
    """
    Generates code from specifications using skeleton-first approach.

    Flow:
    1. Build context (full relevant files)
    2. Generate skeletons (interfaces, types, signatures)
    3. Resolve ambiguities (ask critical, assume minor)
    4. Fill implementations
    5. Validate and return
    """

    name = "coding_agent"

    def __init__(
        self,
        llm_client: LLMClient,
        plugin_registry: PluginRegistry | None = None,
    ):
        self.llm = llm_client
        self.plugins = plugin_registry or PluginRegistry()
        self.context_builder = ContextBuilder()
        self.ambiguity_resolver = AmbiguityResolver()
        self.state = GenerationState()

    def execute(self, context: AgentContext) -> AgentResult:
        """Execute code generation."""
        try:
            # Detect or get language
            language = self._get_language(context)
            plugin = self.plugins.get(language)

            # Get routed spec sections
            routed_spec = context.parent_context.get("routed_spec")

            # Phase 1: Generate skeletons
            skeletons = self._generate_skeletons(plugin, routed_spec, context)
            self.state.skeleton_files = skeletons

            # Phase 2: Check for ambiguities
            ambiguities = self._detect_ambiguities(routed_spec, skeletons)
            for ambiguity in ambiguities:
                resolution = self.ambiguity_resolver.resolve(ambiguity)
                if resolution.action == "ask":
                    # Critical: need to ask user
                    # In real implementation, this would pause and wait
                    self.state.questions_asked.append({
                        "question": resolution.question,
                        "options": resolution.options,
                    })
                else:
                    # Minor: document assumption
                    self.state.assumptions.append(resolution.documentation)

            # Phase 3: Build full context
            target_files = [Path(f) for f in skeletons.keys()]
            code_context = self.context_builder.build_context(
                spec=routed_spec,
                project_root=context.project_root,
                target_files=target_files,
            )

            # Phase 4: Generate implementations
            implementations = self._fill_implementations(
                plugin=plugin,
                skeletons=skeletons,
                routed_spec=routed_spec,
                code_context=code_context,
            )
            self.state.implementation_files = implementations

            # Phase 5: Validate syntax
            errors = []
            for filepath, code in implementations.items():
                syntax_errors = plugin.validate_syntax(code)
                errors.extend(syntax_errors)

            if errors:
                return AgentResult(
                    status=AgentStatus.FAILED,
                    message=f"Syntax validation failed: {len(errors)} errors",
                    errors=[str(e) for e in errors],
                    data={"implementations": implementations},
                )

            # Write files
            files_created = []
            for filepath, code in implementations.items():
                full_path = context.project_root / filepath
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(code)
                files_created.append(str(filepath))

            return AgentResult(
                status=AgentStatus.SUCCESS,
                message=f"Generated {len(files_created)} files",
                data={
                    "code": implementations,
                    "files_created": files_created,
                    "assumptions": self.state.assumptions,
                },
            )

        except Exception as e:
            return AgentResult(
                status=AgentStatus.FAILED,
                message=str(e),
                errors=[str(e)],
            )

    def _get_language(self, context: AgentContext) -> str:
        """Determine target language."""
        # From spec metadata
        if context.spec.metadata and context.spec.metadata.tech_stack:
            for tech in context.spec.metadata.tech_stack:
                if tech.lower() in ["python", "typescript", "go"]:
                    return tech.lower()

        # Auto-detect from project
        return self.plugins.detect_language(context.project_root)

    def _generate_skeletons(
        self,
        plugin: LanguagePlugin,
        routed_spec: RoutedSpec,
        context: AgentContext,
    ) -> dict[str, str]:
        """Generate code skeletons using LLM."""
        prompt = plugin.generate_skeleton_prompt(routed_spec)

        response = self.llm.generate(
            system_prompt=self._get_system_prompt("skeleton"),
            user_prompt=prompt,
        )

        return plugin.parse_generated_code(response)

    def _fill_implementations(
        self,
        plugin: LanguagePlugin,
        skeletons: dict[str, str],
        routed_spec: RoutedSpec,
        code_context: CodeContext,
    ) -> dict[str, str]:
        """Fill skeleton implementations using LLM."""
        implementations = {}

        for filepath, skeleton in skeletons.items():
            prompt = plugin.generate_implementation_prompt(
                skeleton=skeleton,
                spec=routed_spec,
                context=code_context,
            )

            response = self.llm.generate(
                system_prompt=self._get_system_prompt("implementation"),
                user_prompt=prompt,
            )

            # Parse and validate
            generated = plugin.parse_generated_code(response)
            implementations.update(generated)

        return implementations

    def _get_system_prompt(self, phase: str) -> str:
        """Get system prompt for generation phase."""
        base = """You are an expert software engineer generating production-quality code.

Rules:
- Follow the spec exactly
- Use existing patterns from the codebase
- Include proper error handling
- Add appropriate logging
- Write clear, maintainable code
- Include type hints/annotations
"""

        if phase == "skeleton":
            return base + """
Current Phase: SKELETON GENERATION
- Generate ONLY interfaces, types, and signatures
- NO implementations yet
- Include all required data structures
"""

        elif phase == "implementation":
            return base + """
Current Phase: IMPLEMENTATION
- Fill in all method bodies
- Follow the exact signatures from the skeleton
- Implement all required functionality
- Handle all edge cases mentioned in the spec
"""

        return base
```

---

## 7. LLM Chunking Strategy

For large specs or codebases that exceed context limits:

```python
class ChunkingStrategy:
    """Manages context chunking for large codebases."""

    MAX_CONTEXT_TOKENS = 100_000
    RESERVED_RESPONSE = 20_000
    RESERVED_SYSTEM = 5_000
    AVAILABLE_CONTEXT = MAX_CONTEXT_TOKENS - RESERVED_RESPONSE - RESERVED_SYSTEM

    def chunk_for_skeleton(
        self,
        spec: RoutedSpec,
        files: list[CodeFile],
    ) -> list[GenerationChunk]:
        """
        Chunk for skeleton generation.

        Strategy: Skeleton gen needs less context, prioritize spec.
        """
        chunks = []

        # Skeleton doesn't need much existing code
        # Just the spec and type definitions
        spec_tokens = self._count_tokens(spec.to_prompt_context())
        type_files = [f for f in files if self._is_type_file(f)]
        type_tokens = sum(self._count_tokens(f.content) for f in type_files)

        if spec_tokens + type_tokens <= self.AVAILABLE_CONTEXT:
            # Fits in one chunk
            chunks.append(GenerationChunk(
                spec=spec,
                files=type_files,
            ))
        else:
            # Split spec by sections (rare)
            for section_group in self._split_spec_sections(spec):
                chunks.append(GenerationChunk(
                    spec=section_group,
                    files=type_files[:5],  # Limit files
                ))

        return chunks

    def chunk_for_implementation(
        self,
        skeleton: str,
        spec: RoutedSpec,
        context_files: list[CodeFile],
    ) -> list[GenerationChunk]:
        """
        Chunk for implementation generation.

        Strategy: Implementation needs full context.
        If too large, chunk by method/function.
        """
        skeleton_tokens = self._count_tokens(skeleton)
        spec_tokens = self._count_tokens(spec.to_prompt_context())
        context_tokens = sum(self._count_tokens(f.content) for f in context_files)

        total = skeleton_tokens + spec_tokens + context_tokens

        if total <= self.AVAILABLE_CONTEXT:
            return [GenerationChunk(
                skeleton=skeleton,
                spec=spec,
                files=context_files,
            )]

        # Need to chunk - prioritize by relevance
        chunks = []

        # Group methods from skeleton
        methods = self._extract_methods(skeleton)

        for method_batch in self._batch_methods(methods, batch_size=3):
            # Get relevant files for these methods
            relevant_files = self._find_relevant_files(
                methods=method_batch,
                files=context_files,
                max_tokens=self.AVAILABLE_CONTEXT - skeleton_tokens - spec_tokens,
            )

            chunks.append(GenerationChunk(
                skeleton=skeleton,  # Full skeleton for interface reference
                spec=spec,
                files=relevant_files,
                target_methods=method_batch,
            ))

        return chunks
```

---

## 8. Integration with FlowOrchestrator

```python
# Usage in flow_orchestrator.py

def create_coding_flow(
    spec: Spec,
    project_root: Path,
    llm_client: LLMClient,
) -> FlowOrchestrator:
    """Create a flow with CodingAgent as first step."""

    orchestrator = FlowOrchestrator(spec, project_root, FlowStrategy.DAG)

    # Register CodingAgent
    coding_agent = CodingAgent(llm_client)
    orchestrator.register_agent(
        agent=coding_agent,
        depends_on=[],
        provides=["code", "files_created", "skeleton"],
        priority=100,  # Run first
    )

    # Other agents depend on code
    test_agent = TestGeneratorAgent(llm_client)
    orchestrator.register_agent(
        agent=test_agent,
        depends_on=["coding_agent"],
        provides=["tests", "test_files"],
        priority=90,
    )

    # Add monitoring hook
    orchestrator.add_hook("post_agent", lambda name, result:
        print(f"[{name}] {result.status.value}: {result.message}")
    )

    return orchestrator
```

---

## 9. Summary

The CodingAgent design provides:

1. **Skeleton-First**: Clean separation between interface design and implementation
2. **Full Context**: Agents see complete relevant files, not snippets
3. **Smart Ambiguity Handling**: Critical questions asked, minor assumptions documented
4. **Language Agnostic**: Single agent with pluggable language support
5. **Chunking Support**: Handles large codebases by intelligent batching
6. **Flow Integration**: Works seamlessly with FlowOrchestrator DAG execution

This "tracer bullet" design can now be applied to other agents (SecurityScanAgent, TestGeneratorAgent, etc.) with appropriate modifications.
