"""Documentation generator agent."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ..base import BaseAgent


class DocFormat(Enum):
    """Output documentation format."""
    MARKDOWN = "markdown"
    OPENAPI = "openapi"
    MERMAID = "mermaid"


@dataclass
class GeneratedDoc:
    """A generated documentation file."""

    filename: str
    format: DocFormat
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocsGenerationResult:
    """Result of documentation generation."""

    spec_name: str
    docs: list[GeneratedDoc] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Check if generation was successful."""
        return len(self.errors) == 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "spec_name": self.spec_name,
            "success": self.success,
            "docs_generated": len(self.docs),
            "errors": self.errors,
            "files": [
                {"filename": d.filename, "format": d.format.value}
                for d in self.docs
            ],
        }


class DocsGeneratorAgent(BaseAgent):
    """Agent that generates documentation from specs."""

    def __init__(self, llm_client=None, output_dir: Path | None = None):
        """Initialize docs generator.

        Args:
            llm_client: Optional LLM client for enhanced generation.
            output_dir: Directory to write generated docs.
        """
        super().__init__()
        self.llm_client = llm_client
        self.output_dir = output_dir or Path("docs")

    @property
    def name(self) -> str:
        """Agent name."""
        return "docs_generator"

    @property
    def requires(self) -> list[str]:
        """Required inputs."""
        return ["spec"]

    @property
    def provides(self) -> list[str]:
        """Provided outputs."""
        return ["docs"]

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute documentation generation.

        Args:
            state: Pipeline state with spec.

        Returns:
            Updated state with generated docs.
        """
        spec = state.get("spec")
        if not spec:
            state["errors"] = state.get("errors", []) + ["No spec provided"]
            return state

        # Get spec content
        spec_content = state.get("spec_content", "")
        if not spec_content and hasattr(spec, "raw_content"):
            spec_content = spec.raw_content

        result = self.generate_docs(spec_content, getattr(spec, "name", "spec"))
        state["docs_result"] = result
        state["generated_docs"] = result.docs

        return state

    def generate_docs(self, spec_content: str, spec_name: str) -> DocsGenerationResult:
        """Generate documentation from spec content.

        Args:
            spec_content: Markdown spec content.
            spec_name: Name of the spec.

        Returns:
            DocsGenerationResult with generated docs.
        """
        result = DocsGenerationResult(spec_name=spec_name)

        try:
            # Generate README
            readme = self._generate_readme(spec_content, spec_name)
            result.docs.append(readme)

            # Generate API docs if endpoints exist
            if "### Endpoints" in spec_content or "## 6. API Contract" in spec_content:
                api_doc = self._generate_api_docs(spec_content, spec_name)
                result.docs.append(api_doc)

                # Generate OpenAPI spec
                openapi = self._generate_openapi(spec_content, spec_name)
                result.docs.append(openapi)

            # Generate architecture diagram
            arch_diagram = self._generate_architecture_diagram(spec_content, spec_name)
            result.docs.append(arch_diagram)

            # Generate sequence diagrams if events/flows exist
            if "### Events" in spec_content or "## 4. Outputs" in spec_content:
                seq_diagram = self._generate_sequence_diagram(spec_content, spec_name)
                result.docs.append(seq_diagram)

        except Exception as e:
            result.errors.append(str(e))

        return result

    def _generate_readme(self, spec_content: str, spec_name: str) -> GeneratedDoc:
        """Generate README from spec."""
        lines = [
            f"# {spec_name.replace('-', ' ').title()}",
            "",
        ]

        # Extract overview
        overview_match = re.search(
            r"## 2\. Overview\n(.*?)(?=\n## \d+\.|\Z)",
            spec_content,
            re.DOTALL
        )
        if overview_match:
            overview = overview_match.group(1).strip()

            # Extract summary
            summary_match = re.search(r"### Summary\n(.*?)(?=\n###|\Z)", overview, re.DOTALL)
            if summary_match:
                lines.extend([summary_match.group(1).strip(), ""])

            # Extract goals
            goals_match = re.search(r"### Goals\n(.*?)(?=\n###|\Z)", overview, re.DOTALL)
            if goals_match:
                lines.extend(["## Goals", "", goals_match.group(1).strip(), ""])

        # Add installation section
        lines.extend([
            "## Installation",
            "",
            "```bash",
            f"pip install {spec_name}",
            "```",
            "",
        ])

        # Extract dependencies
        deps_match = re.search(
            r"### External\n(.*?)(?=\n###|\n## |\Z)",
            spec_content,
            re.DOTALL
        )
        if deps_match:
            lines.extend([
                "## Dependencies",
                "",
                deps_match.group(1).strip(),
                "",
            ])

        # Add usage section
        lines.extend([
            "## Usage",
            "",
            "```python",
            f"from {spec_name.replace('-', '_')} import Client",
            "",
            "client = Client()",
            "# See API documentation for details",
            "```",
            "",
        ])

        # Add API reference link
        lines.extend([
            "## API Reference",
            "",
            f"See [API Documentation](api.md) for detailed API reference.",
            "",
        ])

        # Add contributing section
        lines.extend([
            "## Contributing",
            "",
            "Contributions are welcome! Please read our contributing guidelines.",
            "",
            "## License",
            "",
            "MIT",
        ])

        return GeneratedDoc(
            filename="README.md",
            format=DocFormat.MARKDOWN,
            content="\n".join(lines),
            metadata={"spec_name": spec_name},
        )

    def _generate_api_docs(self, spec_content: str, spec_name: str) -> GeneratedDoc:
        """Generate API documentation."""
        lines = [
            f"# {spec_name.replace('-', ' ').title()} API Reference",
            "",
        ]

        # Extract endpoints
        endpoints_match = re.search(
            r"### Endpoints\n(.*?)(?=\n###|\n## |\Z)",
            spec_content,
            re.DOTALL
        )
        if endpoints_match:
            lines.extend([
                "## Endpoints",
                "",
                endpoints_match.group(1).strip(),
                "",
            ])

        # Extract error codes
        errors_match = re.search(
            r"### Error Codes\n(.*?)(?=\n###|\n## |\Z)",
            spec_content,
            re.DOTALL
        )
        if errors_match:
            lines.extend([
                "## Error Codes",
                "",
                errors_match.group(1).strip(),
                "",
            ])

        # Extract inputs
        inputs_match = re.search(
            r"## 3\. Inputs\n(.*?)(?=\n## \d+\.|\Z)",
            spec_content,
            re.DOTALL
        )
        if inputs_match:
            lines.extend([
                "## Request Parameters",
                "",
                inputs_match.group(1).strip(),
                "",
            ])

        # Extract outputs
        outputs_match = re.search(
            r"## 4\. Outputs\n(.*?)(?=\n## \d+\.|\Z)",
            spec_content,
            re.DOTALL
        )
        if outputs_match:
            lines.extend([
                "## Response Format",
                "",
                outputs_match.group(1).strip(),
                "",
            ])

        return GeneratedDoc(
            filename="api.md",
            format=DocFormat.MARKDOWN,
            content="\n".join(lines),
            metadata={"spec_name": spec_name},
        )

    def _generate_openapi(self, spec_content: str, spec_name: str) -> GeneratedDoc:
        """Generate OpenAPI specification."""
        import json

        openapi = {
            "openapi": "3.0.3",
            "info": {
                "title": spec_name.replace("-", " ").title(),
                "version": "1.0.0",
            },
            "paths": {},
        }

        # Parse endpoints
        endpoint_pattern = re.compile(
            r"\|\s*(GET|POST|PUT|DELETE|PATCH)\s*\|\s*([^\s|]+)\s*\|\s*([^|]*)\s*\|\s*([^|]*)\s*\|\s*([^|]*)\s*\|"
        )

        for match in endpoint_pattern.finditer(spec_content):
            method = match.group(1).lower()
            path = match.group(2).strip()
            request_type = match.group(3).strip()
            response_type = match.group(4).strip()
            description = match.group(5).strip()

            if path not in openapi["paths"]:
                openapi["paths"][path] = {}

            openapi["paths"][path][method] = {
                "summary": description,
                "responses": {
                    "200": {
                        "description": "Success",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"}
                            }
                        }
                    }
                }
            }

            if request_type and request_type != "-":
                openapi["paths"][path][method]["requestBody"] = {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{request_type}"}
                        }
                    }
                }

        return GeneratedDoc(
            filename="openapi.json",
            format=DocFormat.OPENAPI,
            content=json.dumps(openapi, indent=2),
            metadata={"spec_name": spec_name},
        )

    def _generate_architecture_diagram(self, spec_content: str, spec_name: str) -> GeneratedDoc:
        """Generate Mermaid architecture diagram."""
        lines = [
            f"# {spec_name.replace('-', ' ').title()} Architecture",
            "",
            "```mermaid",
            "graph TB",
        ]

        # Add main component
        safe_name = spec_name.replace("-", "_")
        lines.append(f"    {safe_name}[{spec_name}]")

        # Add dependencies
        deps_pattern = re.compile(r"\|\s*(\w+)\s*\|\s*([^|]+)\s*\|")
        in_deps_section = False

        for line in spec_content.split("\n"):
            if "### External" in line or "### Services" in line:
                in_deps_section = True
                continue
            elif line.startswith("###") or line.startswith("## "):
                in_deps_section = False
                continue

            if in_deps_section:
                match = deps_pattern.search(line)
                if match:
                    dep_name = match.group(1)
                    dep_safe = dep_name.replace("-", "_").lower()
                    lines.append(f"    {safe_name} --> {dep_safe}[{dep_name}]")

        lines.extend([
            "```",
            "",
        ])

        return GeneratedDoc(
            filename="architecture.md",
            format=DocFormat.MERMAID,
            content="\n".join(lines),
            metadata={"spec_name": spec_name},
        )

    def _generate_sequence_diagram(self, spec_content: str, spec_name: str) -> GeneratedDoc:
        """Generate Mermaid sequence diagram."""
        lines = [
            f"# {spec_name.replace('-', ' ').title()} Sequence Diagram",
            "",
            "```mermaid",
            "sequenceDiagram",
            "    participant Client",
            f"    participant {spec_name.replace('-', '_')} as {spec_name}",
        ]

        # Add events as sequence steps
        events_pattern = re.compile(r"\|\s*(\w+\.\w+)\s*\|")

        for match in events_pattern.finditer(spec_content):
            event_name = match.group(1)
            parts = event_name.split(".")
            if len(parts) == 2:
                lines.append(f"    {spec_name.replace('-', '_')}-->>Client: {event_name}")

        lines.extend([
            "```",
            "",
        ])

        return GeneratedDoc(
            filename="sequence.md",
            format=DocFormat.MERMAID,
            content="\n".join(lines),
            metadata={"spec_name": spec_name},
        )

    def write_docs(self, result: DocsGenerationResult, output_dir: Path | None = None) -> list[Path]:
        """Write generated docs to files.

        Args:
            result: Generation result.
            output_dir: Output directory.

        Returns:
            List of written file paths.
        """
        output_dir = output_dir or self.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        written = []
        for doc in result.docs:
            file_path = output_dir / doc.filename
            file_path.write_text(doc.content)
            written.append(file_path)

        return written
