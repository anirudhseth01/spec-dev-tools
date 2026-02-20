"""Research agent for validating technology choices and fetching documentation.

The ResearchAgent performs research on technology choices to help users
make informed decisions during the discussion phase. It also supports
analyzing GitHub repositories to find reusable patterns and code.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from src.builder.session import ResearchDepth
from src.llm.client import LLMClient


class ResearchStatus(Enum):
    """Status of a research request."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ResearchResult:
    """Result of technology research."""

    technology: str
    summary: str = ""
    documentation_snippets: list[str] = field(default_factory=list)
    known_issues: list[str] = field(default_factory=list)
    best_practices: list[str] = field(default_factory=list)
    related_technologies: list[str] = field(default_factory=list)
    recommendation: str = ""
    confidence: float = 0.0  # 0-1 confidence in recommendation
    status: ResearchStatus = ResearchStatus.COMPLETED

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "technology": self.technology,
            "summary": self.summary,
            "documentation_snippets": self.documentation_snippets,
            "known_issues": self.known_issues,
            "best_practices": self.best_practices,
            "related_technologies": self.related_technologies,
            "recommendation": self.recommendation,
            "confidence": self.confidence,
            "status": self.status.value,
        }


@dataclass
class ValidationResult:
    """Result of compatibility validation."""

    is_compatible: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "is_compatible": self.is_compatible,
            "warnings": self.warnings,
            "errors": self.errors,
            "suggestions": self.suggestions,
        }


@dataclass
class RepoFile:
    """A file from a GitHub repository."""

    path: str
    content: str = ""
    language: str = ""
    size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "path": self.path,
            "content": self.content,
            "language": self.language,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepoFile":
        """Create from dictionary."""
        return cls(
            path=data["path"],
            content=data.get("content", ""),
            language=data.get("language", ""),
            size_bytes=data.get("size_bytes", 0),
        )


@dataclass
class ReusableComponent:
    """A reusable component extracted from a repository."""

    name: str
    description: str
    source_file: str
    code_snippet: str = ""
    component_type: str = ""  # "pattern", "interface", "implementation", "utility"
    relevance_score: float = 0.0  # 0-1 relevance to the current project
    adaptation_notes: str = ""  # Notes on how to adapt for current project

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "source_file": self.source_file,
            "code_snippet": self.code_snippet,
            "component_type": self.component_type,
            "relevance_score": self.relevance_score,
            "adaptation_notes": self.adaptation_notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReusableComponent":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            description=data["description"],
            source_file=data["source_file"],
            code_snippet=data.get("code_snippet", ""),
            component_type=data.get("component_type", ""),
            relevance_score=data.get("relevance_score", 0.0),
            adaptation_notes=data.get("adaptation_notes", ""),
        )


@dataclass
class RepoAnalysis:
    """Analysis result of a GitHub repository."""

    repo_url: str
    repo_name: str = ""
    description: str = ""
    primary_language: str = ""
    structure_summary: str = ""
    architecture_patterns: list[str] = field(default_factory=list)
    key_files: list[RepoFile] = field(default_factory=list)
    reusable_components: list[ReusableComponent] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    status: ResearchStatus = ResearchStatus.COMPLETED
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "repo_url": self.repo_url,
            "repo_name": self.repo_name,
            "description": self.description,
            "primary_language": self.primary_language,
            "structure_summary": self.structure_summary,
            "architecture_patterns": self.architecture_patterns,
            "key_files": [f.to_dict() for f in self.key_files],
            "reusable_components": [c.to_dict() for c in self.reusable_components],
            "dependencies": self.dependencies,
            "recommendations": self.recommendations,
            "status": self.status.value,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepoAnalysis":
        """Create from dictionary."""
        return cls(
            repo_url=data["repo_url"],
            repo_name=data.get("repo_name", ""),
            description=data.get("description", ""),
            primary_language=data.get("primary_language", ""),
            structure_summary=data.get("structure_summary", ""),
            architecture_patterns=data.get("architecture_patterns", []),
            key_files=[RepoFile.from_dict(f) for f in data.get("key_files", [])],
            reusable_components=[
                ReusableComponent.from_dict(c)
                for c in data.get("reusable_components", [])
            ],
            dependencies=data.get("dependencies", []),
            recommendations=data.get("recommendations", []),
            status=ResearchStatus(data.get("status", "completed")),
            error_message=data.get("error_message", ""),
        )


# Prompts for research
SYSTEM_PROMPT_RESEARCH = """You are a technology research assistant helping a developer
choose the right technologies for their project.

Given a technology choice and the project context, provide:
1. A brief summary of the technology
2. Relevant documentation points
3. Known issues or gotchas
4. Best practices for this use case
5. Related technologies to consider
6. Your recommendation

Respond in JSON format:
{{
    "summary": "Brief overview of the technology",
    "documentation_snippets": ["Key point 1", "Key point 2"],
    "known_issues": ["Issue 1", "Issue 2"],
    "best_practices": ["Practice 1", "Practice 2"],
    "related_technologies": ["Related tech 1"],
    "recommendation": "Your recommendation for this use case",
    "confidence": 0.8
}}
"""

SYSTEM_PROMPT_COMPATIBILITY = """You are validating technology compatibility.

Given a list of technology choices, determine if they work well together.
Consider version compatibility, ecosystem fit, and architectural patterns.

Respond in JSON format:
{{
    "is_compatible": true,
    "warnings": ["Potential issue 1"],
    "errors": ["Critical incompatibility 1"],
    "suggestions": ["Consider doing X instead"]
}}
"""

SYSTEM_PROMPT_REPO_ANALYSIS = """You are analyzing a GitHub repository to find reusable patterns and code.

Given the repository structure and file contents, identify:
1. Architecture patterns used
2. Reusable components (interfaces, utilities, patterns)
3. Key implementation patterns
4. How these could be adapted for a new project

Focus on finding code that can be reused or adapted, not just copied.

Project context for relevance:
{context}

Respond in JSON format:
{{
    "structure_summary": "Brief overview of the repo structure",
    "architecture_patterns": ["Pattern 1", "Pattern 2"],
    "reusable_components": [
        {{
            "name": "ComponentName",
            "description": "What it does",
            "source_file": "path/to/file.py",
            "component_type": "pattern|interface|implementation|utility",
            "relevance_score": 0.8,
            "adaptation_notes": "How to adapt this for the current project"
        }}
    ],
    "dependencies": ["dependency1", "dependency2"],
    "recommendations": ["Recommendation 1", "Recommendation 2"]
}}
"""

SYSTEM_PROMPT_EXTRACT_CODE = """You are extracting relevant code snippets from a file.

Given the file content and the component description, extract the most relevant
code snippet that demonstrates the pattern or implementation.

Keep the snippet concise but complete enough to understand the pattern.
Include necessary imports and class/function definitions.

Return only the code snippet, no explanation.
"""


class GitHubAnalyzer:
    """Analyzes GitHub repositories to find reusable patterns and code.

    Uses the `gh` CLI to fetch repository information and content,
    then uses LLM to analyze patterns and identify reusable components.
    """

    # File extensions to analyze by language
    LANGUAGE_EXTENSIONS = {
        "python": [".py"],
        "typescript": [".ts", ".tsx"],
        "javascript": [".js", ".jsx"],
        "go": [".go"],
        "rust": [".rs"],
        "java": [".java"],
        "ruby": [".rb"],
    }

    # Files to always fetch for context
    IMPORTANT_FILES = [
        "README.md",
        "README.rst",
        "setup.py",
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "requirements.txt",
    ]

    # Directories to skip
    SKIP_DIRS = [
        "node_modules",
        "venv",
        ".venv",
        "__pycache__",
        ".git",
        "dist",
        "build",
        ".tox",
        ".pytest_cache",
    ]

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        depth: ResearchDepth = ResearchDepth.MEDIUM,
    ):
        """Initialize the analyzer.

        Args:
            llm_client: LLM client for analysis.
            depth: Depth of analysis to perform.
        """
        self.llm_client = llm_client
        self.depth = depth
        self._cache: dict[str, RepoAnalysis] = {}

    async def analyze_repo(
        self, repo_url: str, context: str = ""
    ) -> RepoAnalysis:
        """Analyze a GitHub repository.

        Args:
            repo_url: GitHub repository URL (e.g., https://github.com/owner/repo)
            context: Project context for relevance scoring.

        Returns:
            RepoAnalysis with findings.
        """
        # Check cache
        cache_key = f"{repo_url}:{context[:50]}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Parse repo URL
        repo_info = self._parse_repo_url(repo_url)
        if not repo_info:
            return RepoAnalysis(
                repo_url=repo_url,
                status=ResearchStatus.FAILED,
                error_message=f"Invalid GitHub URL: {repo_url}",
            )

        owner, repo_name = repo_info

        try:
            # Fetch repo metadata
            metadata = await self._fetch_repo_metadata(owner, repo_name)

            # Fetch file tree
            file_tree = await self._fetch_file_tree(owner, repo_name)

            # Identify key files to fetch
            key_file_paths = self._identify_key_files(
                file_tree, metadata.get("language", "")
            )

            # Fetch file contents
            key_files = await self._fetch_file_contents(owner, repo_name, key_file_paths)

            # Analyze with LLM
            analysis = await self._analyze_with_llm(
                repo_url, repo_name, metadata, key_files, context
            )

            # Extract code snippets for reusable components
            if self.depth != ResearchDepth.LIGHT:
                analysis = await self._extract_code_snippets(
                    owner, repo_name, analysis
                )

            # Cache result
            self._cache[cache_key] = analysis
            return analysis

        except Exception as e:
            return RepoAnalysis(
                repo_url=repo_url,
                repo_name=repo_name,
                status=ResearchStatus.FAILED,
                error_message=str(e),
            )

    def _parse_repo_url(self, url: str) -> tuple[str, str] | None:
        """Parse GitHub URL to extract owner and repo name.

        Args:
            url: GitHub URL.

        Returns:
            Tuple of (owner, repo) or None if invalid.
        """
        # Handle various GitHub URL formats
        patterns = [
            r"github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$",
            r"github\.com/([^/]+)/([^/]+?)(?:/.*)?$",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1), match.group(2)

        return None

    async def _fetch_repo_metadata(
        self, owner: str, repo: str
    ) -> dict[str, Any]:
        """Fetch repository metadata using gh CLI.

        Args:
            owner: Repository owner.
            repo: Repository name.

        Returns:
            Repository metadata dict.
        """
        try:
            result = subprocess.run(
                [
                    "gh", "api",
                    f"repos/{owner}/{repo}",
                    "--jq", "{name, description, language, default_branch, topics}",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return {"name": repo, "language": ""}

            return json.loads(result.stdout)

        except Exception:
            return {"name": repo, "language": ""}

    async def _fetch_file_tree(
        self, owner: str, repo: str, path: str = ""
    ) -> list[dict[str, Any]]:
        """Fetch repository file tree using gh CLI.

        Args:
            owner: Repository owner.
            repo: Repository name.
            path: Optional path prefix.

        Returns:
            List of file/directory entries.
        """
        try:
            result = subprocess.run(
                [
                    "gh", "api",
                    f"repos/{owner}/{repo}/git/trees/HEAD?recursive=1",
                    "--jq", ".tree",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                return []

            tree = json.loads(result.stdout)

            # Filter out skipped directories
            filtered = []
            for item in tree:
                skip = False
                for skip_dir in self.SKIP_DIRS:
                    if skip_dir in item.get("path", ""):
                        skip = True
                        break
                if not skip:
                    filtered.append(item)

            return filtered

        except Exception:
            return []

    def _identify_key_files(
        self, file_tree: list[dict], primary_language: str
    ) -> list[str]:
        """Identify key files to fetch based on language and importance.

        Args:
            file_tree: Repository file tree.
            primary_language: Primary language of the repo.

        Returns:
            List of file paths to fetch.
        """
        key_files = []
        extensions = []

        # Get extensions for primary language
        lang_lower = primary_language.lower()
        if lang_lower in self.LANGUAGE_EXTENSIONS:
            extensions = self.LANGUAGE_EXTENSIONS[lang_lower]

        # Limit based on depth
        max_files = {
            ResearchDepth.LIGHT: 5,
            ResearchDepth.MEDIUM: 15,
            ResearchDepth.DEEP: 30,
        }.get(self.depth, 15)

        # First, add important files
        for item in file_tree:
            if item.get("type") == "blob":
                path = item.get("path", "")
                if any(path.endswith(f) for f in self.IMPORTANT_FILES):
                    key_files.append(path)

        # Then add source files by priority
        source_files = []
        for item in file_tree:
            if item.get("type") == "blob":
                path = item.get("path", "")
                # Skip test files for now
                if "test" in path.lower() or "spec" in path.lower():
                    continue
                if extensions and any(path.endswith(ext) for ext in extensions):
                    # Prioritize files in src/, lib/, or root
                    priority = 0
                    if path.startswith("src/") or path.startswith("lib/"):
                        priority = 1
                    elif "/" not in path:
                        priority = 2
                    source_files.append((priority, path, item.get("size", 0)))

        # Sort by priority, then by path
        source_files.sort(key=lambda x: (-x[0], x[1]))

        # Add source files up to limit
        for _, path, size in source_files:
            if len(key_files) >= max_files:
                break
            # Skip very large files (> 50KB)
            if size > 50000:
                continue
            key_files.append(path)

        return key_files

    async def _fetch_file_contents(
        self, owner: str, repo: str, paths: list[str]
    ) -> list[RepoFile]:
        """Fetch contents of specific files.

        Args:
            owner: Repository owner.
            repo: Repository name.
            paths: List of file paths.

        Returns:
            List of RepoFile objects.
        """
        files = []

        for path in paths:
            try:
                result = subprocess.run(
                    [
                        "gh", "api",
                        f"repos/{owner}/{repo}/contents/{path}",
                        "--jq", ".content",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    import base64

                    content = base64.b64decode(result.stdout.strip()).decode(
                        "utf-8", errors="replace"
                    )

                    # Detect language from extension
                    language = ""
                    for lang, exts in self.LANGUAGE_EXTENSIONS.items():
                        if any(path.endswith(ext) for ext in exts):
                            language = lang
                            break

                    files.append(
                        RepoFile(
                            path=path,
                            content=content,
                            language=language,
                            size_bytes=len(content),
                        )
                    )

            except Exception:
                continue

        return files

    async def _analyze_with_llm(
        self,
        repo_url: str,
        repo_name: str,
        metadata: dict[str, Any],
        files: list[RepoFile],
        context: str,
    ) -> RepoAnalysis:
        """Analyze repository using LLM.

        Args:
            repo_url: Repository URL.
            repo_name: Repository name.
            metadata: Repository metadata.
            files: Key files with content.
            context: Project context.

        Returns:
            RepoAnalysis with findings.
        """
        if not self.llm_client:
            # Return basic analysis without LLM
            return RepoAnalysis(
                repo_url=repo_url,
                repo_name=repo_name,
                description=metadata.get("description", ""),
                primary_language=metadata.get("language", ""),
                key_files=files,
                status=ResearchStatus.COMPLETED,
            )

        # Build prompt with file contents
        file_summaries = []
        for f in files[:10]:  # Limit files in prompt
            content_preview = f.content[:2000] if len(f.content) > 2000 else f.content
            file_summaries.append(f"### {f.path}\n```{f.language}\n{content_preview}\n```")

        files_text = "\n\n".join(file_summaries)

        user_prompt = f"""
Repository: {repo_name}
Description: {metadata.get('description', 'N/A')}
Primary Language: {metadata.get('language', 'Unknown')}
Topics: {', '.join(metadata.get('topics', []))}

File Contents:
{files_text}
"""

        try:
            system_prompt = SYSTEM_PROMPT_REPO_ANALYSIS.format(context=context)

            response = self.llm_client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=2048,
                temperature=0.3,
            )

            data = json.loads(response.content)

            return RepoAnalysis(
                repo_url=repo_url,
                repo_name=repo_name,
                description=metadata.get("description", ""),
                primary_language=metadata.get("language", ""),
                structure_summary=data.get("structure_summary", ""),
                architecture_patterns=data.get("architecture_patterns", []),
                key_files=files,
                reusable_components=[
                    ReusableComponent(
                        name=c.get("name", ""),
                        description=c.get("description", ""),
                        source_file=c.get("source_file", ""),
                        component_type=c.get("component_type", ""),
                        relevance_score=c.get("relevance_score", 0.0),
                        adaptation_notes=c.get("adaptation_notes", ""),
                    )
                    for c in data.get("reusable_components", [])
                ],
                dependencies=data.get("dependencies", []),
                recommendations=data.get("recommendations", []),
                status=ResearchStatus.COMPLETED,
            )

        except Exception as e:
            return RepoAnalysis(
                repo_url=repo_url,
                repo_name=repo_name,
                description=metadata.get("description", ""),
                primary_language=metadata.get("language", ""),
                key_files=files,
                status=ResearchStatus.FAILED,
                error_message=f"LLM analysis failed: {str(e)}",
            )

    async def _extract_code_snippets(
        self, owner: str, repo: str, analysis: RepoAnalysis
    ) -> RepoAnalysis:
        """Extract code snippets for reusable components.

        Args:
            owner: Repository owner.
            repo: Repository name.
            analysis: Current analysis.

        Returns:
            Updated analysis with code snippets.
        """
        if not self.llm_client:
            return analysis

        for component in analysis.reusable_components:
            # Find the file content
            file_content = None
            for f in analysis.key_files:
                if f.path == component.source_file:
                    file_content = f.content
                    break

            if not file_content:
                # Try to fetch the file
                files = await self._fetch_file_contents(
                    owner, repo, [component.source_file]
                )
                if files:
                    file_content = files[0].content

            if file_content:
                try:
                    response = self.llm_client.generate(
                        system_prompt=SYSTEM_PROMPT_EXTRACT_CODE,
                        user_prompt=f"""
Component: {component.name}
Description: {component.description}

File content:
```
{file_content[:5000]}
```

Extract the relevant code snippet.
""",
                        max_tokens=1024,
                        temperature=0.1,
                    )

                    component.code_snippet = response.content.strip()

                except Exception:
                    pass

        return analysis

    def clear_cache(self) -> None:
        """Clear the analysis cache."""
        self._cache.clear()


class ResearchAgent:
    """Agent for researching technology choices and analyzing repositories.

    Performs research based on the configured depth:
    - LIGHT: Quick validation only
    - MEDIUM: Fetch key documentation
    - DEEP: Comprehensive research including repo analysis
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        depth: ResearchDepth = ResearchDepth.MEDIUM,
    ):
        """Initialize the research agent.

        Args:
            llm_client: LLM client for generating research.
            depth: Depth of research to perform.
        """
        self.llm_client = llm_client
        self.depth = depth
        self._cache: dict[str, ResearchResult] = {}
        self._github_analyzer = GitHubAnalyzer(llm_client, depth)

    async def research_technology(
        self, tech: str, context: str = ""
    ) -> ResearchResult:
        """Research a technology choice.

        Args:
            tech: Technology name to research.
            context: Project context for relevant research.

        Returns:
            ResearchResult with findings.
        """
        # Check cache
        cache_key = f"{tech}:{context[:50]}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not self.llm_client:
            # Return basic result without LLM
            result = ResearchResult(
                technology=tech,
                summary=f"Research for {tech} (LLM not available)",
                status=ResearchStatus.COMPLETED,
            )
            return result

        try:
            user_prompt = self._build_research_prompt(tech, context)

            response = self.llm_client.generate(
                system_prompt=SYSTEM_PROMPT_RESEARCH,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=self._get_max_tokens(),
            )

            data = json.loads(response.content)

            result = ResearchResult(
                technology=tech,
                summary=data.get("summary", ""),
                documentation_snippets=data.get("documentation_snippets", []),
                known_issues=data.get("known_issues", []),
                best_practices=data.get("best_practices", []),
                related_technologies=data.get("related_technologies", []),
                recommendation=data.get("recommendation", ""),
                confidence=data.get("confidence", 0.5),
                status=ResearchStatus.COMPLETED,
            )

            # Cache result
            self._cache[cache_key] = result
            return result

        except Exception as e:
            return ResearchResult(
                technology=tech,
                summary=f"Research failed: {str(e)}",
                status=ResearchStatus.FAILED,
            )

    async def analyze_github_repo(
        self, repo_url: str, context: str = ""
    ) -> RepoAnalysis:
        """Analyze a GitHub repository for reusable patterns and code.

        Args:
            repo_url: GitHub repository URL.
            context: Project context for relevance scoring.

        Returns:
            RepoAnalysis with findings.
        """
        return await self._github_analyzer.analyze_repo(repo_url, context)

    async def validate_compatibility(
        self, choices: list[str], context: str = ""
    ) -> ValidationResult:
        """Validate that technology choices work together.

        Args:
            choices: List of technology names.
            context: Project context.

        Returns:
            ValidationResult with compatibility assessment.
        """
        if not self.llm_client:
            # Without LLM, assume compatible
            return ValidationResult(
                is_compatible=True,
                warnings=["Compatibility not validated (LLM not available)"],
            )

        try:
            user_prompt = f"""
Validate compatibility of these technology choices:
{', '.join(choices)}

Project context: {context}
"""

            response = self.llm_client.generate(
                system_prompt=SYSTEM_PROMPT_COMPATIBILITY,
                user_prompt=user_prompt,
                temperature=0.2,
            )

            data = json.loads(response.content)

            return ValidationResult(
                is_compatible=data.get("is_compatible", True),
                warnings=data.get("warnings", []),
                errors=data.get("errors", []),
                suggestions=data.get("suggestions", []),
            )

        except Exception as e:
            return ValidationResult(
                is_compatible=True,
                warnings=[f"Compatibility check failed: {str(e)}"],
            )

    async def fetch_documentation(
        self, tech: str, topics: list[str]
    ) -> list[str]:
        """Fetch relevant documentation snippets.

        Args:
            tech: Technology name.
            topics: Specific topics to research.

        Returns:
            List of documentation snippets.
        """
        if self.depth == ResearchDepth.LIGHT:
            return []

        if not self.llm_client:
            return []

        try:
            user_prompt = f"""
Find documentation snippets for {tech} about:
{', '.join(topics)}

Return as JSON array of strings.
"""

            response = self.llm_client.generate(
                system_prompt="You are a documentation assistant. Return relevant documentation snippets as a JSON array of strings.",
                user_prompt=user_prompt,
                temperature=0.1,
            )

            return json.loads(response.content)

        except Exception:
            return []

    def _build_research_prompt(self, tech: str, context: str) -> str:
        """Build the research prompt based on depth."""
        base = f"Research the technology: {tech}"

        if context:
            base += f"\n\nProject context: {context}"

        depth_instructions = {
            ResearchDepth.LIGHT: "\n\nProvide a brief overview only.",
            ResearchDepth.MEDIUM: "\n\nProvide moderate detail with key documentation points.",
            ResearchDepth.DEEP: "\n\nProvide comprehensive analysis including edge cases and advanced patterns.",
        }

        return base + depth_instructions.get(self.depth, "")

    def _get_max_tokens(self) -> int:
        """Get max tokens based on research depth."""
        return {
            ResearchDepth.LIGHT: 512,
            ResearchDepth.MEDIUM: 1024,
            ResearchDepth.DEEP: 2048,
        }.get(self.depth, 1024)

    def clear_cache(self) -> None:
        """Clear the research cache."""
        self._cache.clear()
        self._github_analyzer.clear_cache()
