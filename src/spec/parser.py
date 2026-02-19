"""Parsers for specification and block markdown files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.spec.schemas import (
    AcceptanceCriteria,
    APIContract,
    Dependencies,
    EdgeCases,
    Endpoint,
    ErrorHandling,
    ImplementationNotes,
    InputParam,
    Inputs,
    Metadata,
    Outputs,
    Overview,
    PerformanceRequirements,
    SecurityRequirements,
    Spec,
    SpecStatus,
    TestCase,
    TestCases,
)
from src.spec.block import BlockMetadata, BlockSpec, BlockType, SubBlockInfo
from src.rules.schemas import MergeMode, Rule, RuleCategory, RuleLevel, RuleSeverity, SameAsReference


class SpecParser:
    """Parser for feature specification markdown files."""

    def __init__(self, specs_dir: str | Path = "specs") -> None:
        """Initialize parser with specs directory.

        Args:
            specs_dir: Directory containing specification files.
        """
        self.specs_dir = Path(specs_dir)

    def parse_file(self, file_path: Path | str) -> Spec:
        """Parse a specification file.

        Args:
            file_path: Path to the specification markdown file.

        Returns:
            Parsed Spec object.
        """
        file_path = Path(file_path)
        content = file_path.read_text()
        return self._parse_content(content, file_path)

    def parse_by_name(self, spec_name: str) -> Spec:
        """Parse a specification by name.

        Args:
            spec_name: Name of the specification (filename without extension).

        Returns:
            Parsed Spec object.

        Raises:
            FileNotFoundError: If specification file not found.
        """
        file_path = self.specs_dir / f"{spec_name}.md"
        if not file_path.exists():
            file_path = self.specs_dir / spec_name / "spec.md"
        if not file_path.exists():
            raise FileNotFoundError(f"Specification not found: {spec_name}")
        return self.parse_file(file_path)

    def list_specs(self) -> list[str]:
        """List all available specifications.

        Returns:
            List of specification names.
        """
        specs = []
        if not self.specs_dir.exists():
            return specs

        for path in self.specs_dir.glob("**/*.md"):
            if path.name == "spec.md":
                specs.append(path.parent.name)
            elif path.suffix == ".md" and path.stem not in ["README", "template"]:
                specs.append(path.stem)
        return sorted(set(specs))

    def _parse_content(self, content: str, file_path: Path) -> Spec:
        """Parse specification content.

        Args:
            content: Markdown content to parse.
            file_path: Path to file (for name extraction).

        Returns:
            Parsed Spec object.
        """
        name = self._extract_name(content, file_path)

        return Spec(
            name=name,
            metadata=self._parse_metadata(content),
            overview=self._parse_overview(content),
            inputs=self._parse_inputs(content),
            outputs=self._parse_outputs(content),
            dependencies=self._parse_dependencies(content),
            api_contract=self._parse_api_contract(content),
            test_cases=self._parse_test_cases(content),
            edge_cases=self._parse_edge_cases(content),
            error_handling=self._parse_error_handling(content),
            performance=self._parse_performance(content),
            security=self._parse_security(content),
            implementation=self._parse_implementation(content),
            acceptance=self._parse_acceptance(content),
        )

    def _extract_name(self, content: str, file_path: Path) -> str:
        """Extract specification name from content or filename."""
        # Try to find name in header (Feature Specification or Block Specification)
        match = re.search(
            r"^#\s*(?:Feature|Block)\s+Specification:\s*(.+)$", content, re.MULTILINE
        )
        if match:
            return match.group(1).strip()

        # Fall back to filename
        if file_path.name in ("spec.md", "block.md"):
            return file_path.parent.name
        return file_path.stem

    def _get_section(self, content: str, section_num: int, section_name: str) -> str:
        """Extract a numbered section from content.

        Args:
            content: Full markdown content.
            section_num: Section number (1-13).
            section_name: Section name for pattern matching.

        Returns:
            Section content or empty string.
        """
        pattern = rf"##\s*{section_num}\.\s*{section_name}.*?\n(.*?)(?=##\s*\d+\.|$)"
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def _parse_list_items(self, text: str) -> list[str]:
        """Parse bullet list items from text."""
        items = []
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                items.append(line[2:].strip())
        return items

    def _parse_checklist_items(self, text: str) -> list[str]:
        """Parse checklist items from text."""
        items = []
        for line in text.split("\n"):
            line = line.strip()
            match = re.match(r"^-\s*\[[ x]\]\s*(.+)$", line, re.IGNORECASE)
            if match:
                items.append(match.group(1).strip())
        return items

    def _parse_table(self, text: str) -> list[dict[str, str]]:
        """Parse markdown table into list of dicts."""
        lines = [l.strip() for l in text.split("\n") if l.strip() and "|" in l]
        if len(lines) < 2:
            return []

        # Parse header
        headers = [h.strip() for h in lines[0].split("|") if h.strip()]

        # Skip separator line, parse data rows
        rows = []
        for line in lines[2:]:
            values = [v.strip() for v in line.split("|") if v.strip()]
            if len(values) == len(headers):
                rows.append(dict(zip(headers, values)))
        return rows

    def _parse_metadata(self, content: str) -> Metadata:
        """Parse Section 1: Metadata."""
        section = self._get_section(content, 1, "Metadata")
        if not section:
            return Metadata()

        metadata = Metadata()

        # Parse key-value pairs
        for line in section.split("\n"):
            line = line.strip()
            # Remove leading bullet point if present
            if line.startswith("- ") or line.startswith("* "):
                line = line[2:]
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip().lower().replace(" ", "_").replace("-", "_")
                value = value.strip()

                if key == "spec_id" or key == "id":
                    metadata.spec_id = value
                elif key == "version":
                    metadata.version = value
                elif key == "status":
                    try:
                        metadata.status = SpecStatus(value.lower())
                    except ValueError:
                        metadata.status = SpecStatus.DRAFT
                elif key == "tech_stack":
                    metadata.tech_stack = value
                elif key == "author":
                    metadata.author = value
                elif key == "created":
                    metadata.created = value
                elif key == "updated":
                    metadata.updated = value

        return metadata

    def _parse_overview(self, content: str) -> Overview:
        """Parse Section 2: Overview."""
        section = self._get_section(content, 2, "Overview")
        if not section:
            return Overview()

        overview = Overview()

        # Find subsections
        summary_match = re.search(r"###\s*Summary\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if summary_match:
            overview.summary = summary_match.group(1).strip()

        goals_match = re.search(r"###\s*Goals\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if goals_match:
            overview.goals = self._parse_list_items(goals_match.group(1))

        non_goals_match = re.search(r"###\s*Non-Goals\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if non_goals_match:
            overview.non_goals = self._parse_list_items(non_goals_match.group(1))

        background_match = re.search(r"###\s*Background\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if background_match:
            overview.background = background_match.group(1).strip()

        return overview

    def _parse_inputs(self, content: str) -> Inputs:
        """Parse Section 3: Inputs."""
        section = self._get_section(content, 3, "Inputs")
        if not section:
            return Inputs()

        inputs = Inputs()

        def parse_input_table(subsection: str) -> list[InputParam]:
            params = []
            for row in self._parse_table(subsection):
                param = InputParam(
                    name=row.get("Name", row.get("name", "")),
                    type=row.get("Type", row.get("type", "")),
                    required=row.get("Required", row.get("required", "")).lower()
                    in ("yes", "true", "required"),
                    default=row.get("Default", row.get("default", "")),
                    description=row.get("Description", row.get("description", "")),
                )
                if param.name:
                    params.append(param)
            return params

        user_match = re.search(r"###\s*User\s*Inputs?\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if user_match:
            inputs.user_inputs = parse_input_table(user_match.group(1))

        system_match = re.search(r"###\s*System\s*Inputs?\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if system_match:
            inputs.system_inputs = parse_input_table(system_match.group(1))

        env_match = re.search(
            r"###\s*(?:Environment|Env)\s*(?:Variables?|Vars?)?\s*\n(.*?)(?=###|$)",
            section,
            re.DOTALL,
        )
        if env_match:
            inputs.env_vars = parse_input_table(env_match.group(1))

        return inputs

    def _parse_outputs(self, content: str) -> Outputs:
        """Parse Section 4: Outputs."""
        section = self._get_section(content, 4, "Outputs")
        if not section:
            return Outputs()

        outputs = Outputs()

        return_match = re.search(r"###\s*Return\s*Values?\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if return_match:
            outputs.return_values = self._parse_list_items(return_match.group(1))

        effects_match = re.search(r"###\s*Side\s*Effects?\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if effects_match:
            outputs.side_effects = self._parse_list_items(effects_match.group(1))

        events_match = re.search(r"###\s*Events?\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if events_match:
            outputs.events = self._parse_list_items(events_match.group(1))

        return outputs

    def _parse_dependencies(self, content: str) -> Dependencies:
        """Parse Section 5: Dependencies."""
        section = self._get_section(content, 5, "Dependencies")
        if not section:
            return Dependencies()

        deps = Dependencies()

        internal_match = re.search(r"###\s*Internal\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if internal_match:
            deps.internal = self._parse_list_items(internal_match.group(1))

        external_match = re.search(r"###\s*External\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if external_match:
            deps.external = self._parse_list_items(external_match.group(1))

        services_match = re.search(r"###\s*Services?\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if services_match:
            deps.services = self._parse_list_items(services_match.group(1))

        return deps

    def _parse_api_contract(self, content: str) -> APIContract:
        """Parse Section 6: API Contract."""
        section = self._get_section(content, 6, "API Contract")
        if not section:
            return APIContract()

        api = APIContract()

        endpoints_match = re.search(r"###\s*Endpoints?\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if endpoints_match:
            for row in self._parse_table(endpoints_match.group(1)):
                endpoint = Endpoint(
                    method=row.get("Method", row.get("method", "")),
                    path=row.get("Path", row.get("path", "")),
                    request_body=row.get("Request", row.get("request_body", "")),
                    response_body=row.get("Response", row.get("response_body", "")),
                    description=row.get("Description", row.get("description", "")),
                )
                if endpoint.path:
                    api.endpoints.append(endpoint)

        errors_match = re.search(r"###\s*Error\s*Codes?\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if errors_match:
            for row in self._parse_table(errors_match.group(1)):
                code = row.get("Code", row.get("code", ""))
                desc = row.get("Description", row.get("description", ""))
                if code:
                    api.error_codes[code] = desc

        return api

    def _parse_test_cases(self, content: str) -> TestCases:
        """Parse Section 7: Test Cases."""
        section = self._get_section(content, 7, "Test Cases")
        if not section:
            return TestCases()

        tests = TestCases()

        def parse_test_table(subsection: str) -> list[TestCase]:
            cases = []
            for row in self._parse_table(subsection):
                case = TestCase(
                    test_id=row.get("ID", row.get("test_id", "")),
                    description=row.get("Description", row.get("description", "")),
                    input=row.get("Input", row.get("input", "")),
                    expected_output=row.get("Expected", row.get("expected_output", "")),
                    setup=row.get("Setup", row.get("setup", "")),
                    teardown=row.get("Teardown", row.get("teardown", "")),
                )
                if case.test_id or case.description:
                    cases.append(case)
            return cases

        unit_match = re.search(r"###\s*Unit\s*Tests?\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if unit_match:
            tests.unit_tests = parse_test_table(unit_match.group(1))

        int_match = re.search(r"###\s*Integration\s*Tests?\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if int_match:
            tests.integration_tests = parse_test_table(int_match.group(1))

        # Parse coverage requirements
        coverage_match = re.search(r"min_line_coverage[:\s]*(\d+)", section, re.IGNORECASE)
        if coverage_match:
            tests.min_line_coverage = int(coverage_match.group(1))

        branch_match = re.search(r"min_branch_coverage[:\s]*(\d+)", section, re.IGNORECASE)
        if branch_match:
            tests.min_branch_coverage = int(branch_match.group(1))

        return tests

    def _parse_edge_cases(self, content: str) -> EdgeCases:
        """Parse Section 8: Edge Cases."""
        section = self._get_section(content, 8, "Edge Cases")
        if not section:
            return EdgeCases()

        edge = EdgeCases()

        boundary_match = re.search(
            r"###\s*Boundary\s*Conditions?\s*\n(.*?)(?=###|$)", section, re.DOTALL
        )
        if boundary_match:
            edge.boundary_conditions = self._parse_list_items(boundary_match.group(1))

        concurrency_match = re.search(r"###\s*Concurrency\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if concurrency_match:
            edge.concurrency = self._parse_list_items(concurrency_match.group(1))

        failure_match = re.search(r"###\s*Failure\s*Modes?\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if failure_match:
            edge.failure_modes = self._parse_list_items(failure_match.group(1))

        return edge

    def _parse_error_handling(self, content: str) -> ErrorHandling:
        """Parse Section 9: Error Handling."""
        section = self._get_section(content, 9, "Error Handling")
        if not section:
            return ErrorHandling()

        errors = ErrorHandling()

        types_match = re.search(r"###\s*Error\s*Types?\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if types_match:
            errors.error_types = self._parse_list_items(types_match.group(1))

        retries_match = re.search(r"max_retries[:\s]*(\d+)", section, re.IGNORECASE)
        if retries_match:
            errors.max_retries = int(retries_match.group(1))

        backoff_match = re.search(r"backoff_strategy[:\s]*(\w+)", section, re.IGNORECASE)
        if backoff_match:
            errors.backoff_strategy = backoff_match.group(1)

        return errors

    def _parse_performance(self, content: str) -> PerformanceRequirements:
        """Parse Section 10: Performance Requirements."""
        section = self._get_section(content, 10, "Performance")
        if not section:
            return PerformanceRequirements()

        perf = PerformanceRequirements()

        p50_match = re.search(r"p50[:\s]*(\d+)", section, re.IGNORECASE)
        if p50_match:
            perf.p50_ms = int(p50_match.group(1))

        p95_match = re.search(r"p95[:\s]*(\d+)", section, re.IGNORECASE)
        if p95_match:
            perf.p95_ms = int(p95_match.group(1))

        p99_match = re.search(r"p99[:\s]*(\d+)", section, re.IGNORECASE)
        if p99_match:
            perf.p99_ms = int(p99_match.group(1))

        rps_match = re.search(r"target_rps[:\s]*(\d+)", section, re.IGNORECASE)
        if rps_match:
            perf.target_rps = int(rps_match.group(1))

        mem_match = re.search(r"memory_limit[:\s]*(\d+)", section, re.IGNORECASE)
        if mem_match:
            perf.memory_limit_mb = int(mem_match.group(1))

        return perf

    def _parse_security(self, content: str) -> SecurityRequirements:
        """Parse Section 11: Security Requirements."""
        section = self._get_section(content, 11, "Security")
        if not section:
            return SecurityRequirements()

        security = SecurityRequirements()

        auth_match = re.search(r"requires_auth[:\s]*(yes|true|no|false)", section, re.IGNORECASE)
        if auth_match:
            security.requires_auth = auth_match.group(1).lower() in ("yes", "true")

        method_match = re.search(r"auth_method[:\s]*(\w+)", section, re.IGNORECASE)
        if method_match:
            security.auth_method = method_match.group(1)

        roles_match = re.search(r"###\s*Roles?\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if roles_match:
            security.roles = self._parse_list_items(roles_match.group(1))

        pii_match = re.search(r"handles_pii[:\s]*(yes|true|no|false)", section, re.IGNORECASE)
        if pii_match:
            security.handles_pii = pii_match.group(1).lower() in ("yes", "true")

        rest_match = re.search(
            r"encryption_at_rest[:\s]*(yes|true|no|false)", section, re.IGNORECASE
        )
        if rest_match:
            security.encryption_at_rest = rest_match.group(1).lower() in ("yes", "true")

        transit_match = re.search(
            r"encryption_in_transit[:\s]*(yes|true|no|false)", section, re.IGNORECASE
        )
        if transit_match:
            security.encryption_in_transit = transit_match.group(1).lower() in ("yes", "true")

        return security

    def _parse_implementation(self, content: str) -> ImplementationNotes:
        """Parse Section 12: Implementation Notes."""
        section = self._get_section(content, 12, "Implementation")
        if not section:
            return ImplementationNotes()

        impl = ImplementationNotes()

        algo_match = re.search(r"###\s*Algorithms?\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if algo_match:
            impl.algorithms = self._parse_list_items(algo_match.group(1))

        patterns_match = re.search(r"###\s*Patterns?\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if patterns_match:
            impl.patterns = self._parse_list_items(patterns_match.group(1))

        constraints_match = re.search(r"###\s*Constraints?\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if constraints_match:
            impl.constraints = self._parse_list_items(constraints_match.group(1))

        return impl

    def _parse_acceptance(self, content: str) -> AcceptanceCriteria:
        """Parse Section 13: Acceptance Criteria."""
        section = self._get_section(content, 13, "Acceptance")
        if not section:
            return AcceptanceCriteria()

        acceptance = AcceptanceCriteria()

        criteria_match = re.search(r"###\s*Criteria\s*\n(.*?)(?=###|$)", section, re.DOTALL)
        if criteria_match:
            acceptance.criteria = self._parse_checklist_items(criteria_match.group(1))
            if not acceptance.criteria:
                acceptance.criteria = self._parse_list_items(criteria_match.group(1))

        done_match = re.search(
            r"###\s*(?:Done\s*)?Definition(?:\s*of\s*Done)?\s*\n(.*?)(?=###|$)",
            section,
            re.DOTALL,
        )
        if done_match:
            acceptance.done_definition = self._parse_checklist_items(done_match.group(1))
            if not acceptance.done_definition:
                acceptance.done_definition = self._parse_list_items(done_match.group(1))

        return acceptance


class BlockParser:
    """Parser for block specification markdown files.

    Block specifications are organized in a hierarchical directory structure,
    with each block.md file representing a component in the system hierarchy.
    """

    def __init__(self, specs_dir: str | Path = "specs") -> None:
        """Initialize parser with specs directory.

        Args:
            specs_dir: Root directory containing block specifications.
        """
        self.specs_dir = Path(specs_dir)
        self._spec_parser = SpecParser(specs_dir)

    def discover_blocks(self) -> list[Path]:
        """Find all block.md files recursively.

        Returns:
            List of paths to block.md files, sorted by path.
        """
        if not self.specs_dir.exists():
            return []

        blocks = list(self.specs_dir.glob("**/block.md"))
        return sorted(blocks)

    def parse_block(self, block_path: Path) -> BlockSpec:
        """Parse a single block.md file.

        Args:
            block_path: Path to the block.md file.

        Returns:
            Parsed BlockSpec object.
        """
        content = block_path.read_text()

        # Parse block configuration (Section 0)
        block_metadata = self._parse_block_configuration(content)

        # Parse the spec content (Sections 1-13)
        spec = self._spec_parser._parse_content(content, block_path)

        # Calculate path relative to specs_dir
        block_dir = block_path.parent
        try:
            rel_path = block_dir.relative_to(self.specs_dir)
            path_str = str(rel_path)
        except ValueError:
            path_str = block_dir.name

        # Parse scoped rules and same-as references from Section 0
        scoped_rules = self._parse_scoped_rules_section(content)
        same_as_refs = self._parse_same_as_section(content)

        return BlockSpec(
            path=path_str,
            name=spec.name or block_dir.name,
            directory=block_dir,
            spec=spec,
            block_type=block_metadata.block_type,
            scoped_rules=scoped_rules,
            same_as_refs=same_as_refs,
        )

    def parse_hierarchy(self, root_path: Path | None = None) -> list[BlockSpec]:
        """Parse entire block hierarchy.

        Args:
            root_path: Optional root path to start from. Defaults to specs_dir.

        Returns:
            List of all BlockSpec objects with parent/child relationships resolved.
        """
        search_dir = root_path if root_path else self.specs_dir

        # Discover all blocks
        block_files = list(search_dir.glob("**/block.md"))
        if not block_files:
            return []

        # Parse all blocks
        blocks = [self.parse_block(path) for path in block_files]

        # Resolve parent/child relationships
        self._resolve_parent_child(blocks)

        return blocks

    def _parse_block_configuration(self, content: str) -> BlockMetadata:
        """Parse Section 0: Block Configuration.

        Args:
            content: Full markdown content.

        Returns:
            BlockMetadata with configuration data.
        """
        metadata = BlockMetadata()

        # Look for Section 0 - match until Section 1 or later
        section_match = re.search(
            r"##\s*0\.\s*Block\s*Configuration\s*\n(.*?)(?=##\s*[1-9])",
            content,
            re.DOTALL | re.IGNORECASE,
        )
        if not section_match:
            return metadata

        section = section_match.group(1)

        # Parse hierarchy subsection (0.1)
        hierarchy_data = self._parse_hierarchy_section(section)
        if hierarchy_data.get("block_type"):
            try:
                metadata.block_type = BlockType(hierarchy_data["block_type"].lower())
            except ValueError:
                pass
        metadata.parent_path = hierarchy_data.get("parent_path")

        # Parse sub-blocks subsection (0.2)
        metadata.sub_blocks = self._parse_sub_blocks_section(section)

        return metadata

    def _parse_hierarchy_section(self, section: str) -> dict[str, Any]:
        """Parse 0.1 Hierarchy table.

        Args:
            section: Section 0 content.

        Returns:
            Dictionary with block_type and parent_path.
        """
        result: dict[str, Any] = {}

        hierarchy_match = re.search(
            r"###\s*0\.1[:\s]+Hierarchy\s*\n(.*?)(?=###|$)", section, re.DOTALL | re.IGNORECASE
        )
        if not hierarchy_match:
            return result

        subsection = hierarchy_match.group(1)

        # Parse block type (handle "- block_type: value" format)
        type_match = re.search(r"[-*]?\s*block_type[:\s]+(\w+)", subsection, re.IGNORECASE)
        if type_match:
            result["block_type"] = type_match.group(1)

        # Parse parent path (handle "- parent: value" format)
        parent_match = re.search(r"[-*]?\s*parent[:\s]+([^\n]+)", subsection, re.IGNORECASE)
        if parent_match:
            parent_val = parent_match.group(1).strip()
            if parent_val and parent_val.lower() not in ("none", "null", "-", "n/a"):
                result["parent_path"] = parent_val

        return result

    def _parse_sub_blocks_section(self, section: str) -> list[SubBlockInfo]:
        """Parse 0.2 Sub-Blocks list.

        Args:
            section: Section 0 content.

        Returns:
            List of SubBlockInfo objects.
        """
        sub_blocks = []

        sub_match = re.search(
            r"###\s*0\.2[:\s]+Sub-?Blocks?\s*\n(.*?)(?=###|$)", section, re.DOTALL | re.IGNORECASE
        )
        if not sub_match:
            return sub_blocks

        subsection = sub_match.group(1)

        # Parse list items or table
        for line in subsection.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                item = line[2:].strip()
                # Check for "name - description" format
                if " - " in item:
                    name, _, desc = item.partition(" - ")
                    sub_blocks.append(SubBlockInfo(name=name.strip(), description=desc.strip()))
                else:
                    sub_blocks.append(SubBlockInfo(name=item))

        return sub_blocks

    def _parse_scoped_rules_section(self, content: str) -> list[Rule]:
        """Parse 0.3 Scoped Rules from Section 0.

        Args:
            content: Full markdown content.

        Returns:
            List of Rule objects.
        """
        rules = []

        # Look for Section 0 first
        section_match = re.search(
            r"##\s*0\.\s*Block\s*Configuration.*?\n(.*?)(?=##\s*\d+\.|$)",
            content,
            re.DOTALL | re.IGNORECASE,
        )
        if not section_match:
            return rules

        section = section_match.group(1)

        # Find scoped rules subsection
        rules_match = re.search(
            r"###\s*0\.3[:\s]+Scoped\s*Rules?\s*\n(.*?)(?=###|$)", section, re.DOTALL | re.IGNORECASE
        )
        if not rules_match:
            return rules

        subsection = rules_match.group(1)

        # Parse table format
        for row in self._parse_rule_table(subsection):
            rule = Rule(
                id=row.get("id", ""),
                name=row.get("name", ""),
                level=RuleLevel.SCOPED,
                category=self._parse_category(row.get("category", "")),
                severity=self._parse_severity(row.get("severity", "")),
                applies_to_sections=[s.strip() for s in row.get("sections", "").split(",") if s.strip()],
                validation_fn=row.get("validator", ""),
                description=row.get("description", ""),
            )
            if rule.id:
                rules.append(rule)

        return rules

    def _parse_same_as_section(self, content: str) -> list[SameAsReference]:
        """Parse 0.4 Same-As References from Section 0.

        Args:
            content: Full markdown content.

        Returns:
            List of SameAsReference objects.
        """
        refs = []

        # Look for Section 0 first
        section_match = re.search(
            r"##\s*0\.\s*Block\s*Configuration.*?\n(.*?)(?=##\s*\d+\.|$)",
            content,
            re.DOTALL | re.IGNORECASE,
        )
        if not section_match:
            return refs

        section = section_match.group(1)

        # Find same-as subsection
        same_as_match = re.search(
            r"###\s*0\.4[:\s]+Same-?As\s*(?:References?)?\s*\n(.*?)(?=###|$)",
            section,
            re.DOTALL | re.IGNORECASE,
        )
        if not same_as_match:
            return refs

        subsection = same_as_match.group(1)

        # Parse table format
        for row in self._parse_same_as_table(subsection):
            ref = SameAsReference(
                target_section=row.get("target_section", ""),
                source_block=row.get("source_block", ""),
                source_section=row.get("source_section"),
                merge_mode=self._parse_merge_mode(row.get("merge_mode", "replace")),
            )
            if ref.target_section and ref.source_block:
                refs.append(ref)

        return refs

    def _parse_rule_table(self, text: str) -> list[dict[str, str]]:
        """Parse a rules table from markdown."""
        lines = [l.strip() for l in text.split("\n") if l.strip() and "|" in l]
        if len(lines) < 2:
            return []

        # Parse header
        headers_raw = [h.strip().lower() for h in lines[0].split("|") if h.strip()]

        # Normalize headers
        header_map = {
            "id": "id",
            "rule_id": "id",
            "name": "name",
            "rule": "name",
            "category": "category",
            "severity": "severity",
            "level": "severity",
            "sections": "sections",
            "applies_to": "sections",
            "validator": "validator",
            "validation": "validator",
            "description": "description",
            "desc": "description",
        }
        headers = [header_map.get(h, h) for h in headers_raw]

        # Skip separator line, parse data rows
        rows = []
        for line in lines[2:]:
            values = [v.strip() for v in line.split("|") if v.strip()]
            if len(values) == len(headers):
                rows.append(dict(zip(headers, values)))
        return rows

    def _parse_same_as_table(self, text: str) -> list[dict[str, str]]:
        """Parse a same-as references table from markdown."""
        lines = [l.strip() for l in text.split("\n") if l.strip() and "|" in l]
        if len(lines) < 2:
            return []

        # Parse header
        headers_raw = [h.strip().lower() for h in lines[0].split("|") if h.strip()]

        # Normalize headers
        header_map = {
            "target": "target_section",
            "target_section": "target_section",
            "section": "target_section",
            "source": "source_block",
            "source_block": "source_block",
            "from": "source_block",
            "source_section": "source_section",
            "from_section": "source_section",
            "mode": "merge_mode",
            "merge": "merge_mode",
            "merge_mode": "merge_mode",
        }
        headers = [header_map.get(h, h) for h in headers_raw]

        # Skip separator line, parse data rows
        rows = []
        for line in lines[2:]:
            values = [v.strip() for v in line.split("|") if v.strip()]
            if len(values) == len(headers):
                rows.append(dict(zip(headers, values)))
        return rows

    def _parse_category(self, value: str) -> RuleCategory:
        """Parse rule category from string."""
        try:
            return RuleCategory(value.lower())
        except ValueError:
            return RuleCategory.CODE_QUALITY

    def _parse_severity(self, value: str) -> RuleSeverity:
        """Parse rule severity from string."""
        try:
            return RuleSeverity(value.lower())
        except ValueError:
            return RuleSeverity.WARNING

    def _parse_merge_mode(self, value: str) -> MergeMode:
        """Parse merge mode from string."""
        try:
            return MergeMode(value.lower())
        except ValueError:
            return MergeMode.REPLACE

    def _resolve_parent_child(self, blocks: list[BlockSpec]) -> None:
        """Resolve parent/child relationships between blocks.

        Args:
            blocks: List of BlockSpec objects to link together.
        """
        # Create lookup by path
        by_path = {block.path: block for block in blocks}

        for block in blocks:
            # Calculate depth based on path
            block.depth = block.path.count("/")

            # Find parent by path
            if "/" in block.path:
                parent_path = "/".join(block.path.split("/")[:-1])
                if parent_path in by_path:
                    block.parent = by_path[parent_path]
                    by_path[parent_path].children.append(block)
