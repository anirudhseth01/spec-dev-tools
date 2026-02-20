"""Dependency graph visualization."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class OutputFormat(Enum):
    """Output format for visualizations."""
    MERMAID = "mermaid"
    DOT = "dot"
    ASCII = "ascii"
    JSON = "json"


@dataclass
class GraphNode:
    """A node in the dependency graph."""

    name: str
    block_type: str = "component"
    status: str = "draft"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    """An edge in the dependency graph."""

    source: str
    target: str
    edge_type: str = "depends_on"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DependencyGraph:
    """A dependency graph of blocks."""

    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)

    def add_node(self, node: GraphNode) -> None:
        """Add a node to the graph."""
        self.nodes[node.name] = node

    def add_edge(self, edge: GraphEdge) -> None:
        """Add an edge to the graph."""
        self.edges.append(edge)

    def get_roots(self) -> list[str]:
        """Get nodes with no incoming edges."""
        targets = {e.target for e in self.edges}
        return [n for n in self.nodes if n not in targets]

    def get_leaves(self) -> list[str]:
        """Get nodes with no outgoing edges."""
        sources = {e.source for e in self.edges}
        return [n for n in self.nodes if n not in sources]

    def get_dependencies(self, node: str) -> list[str]:
        """Get direct dependencies of a node."""
        return [e.target for e in self.edges if e.source == node]

    def get_dependents(self, node: str) -> list[str]:
        """Get nodes that depend on this node."""
        return [e.source for e in self.edges if e.target == node]

    def topological_sort(self) -> list[str]:
        """Sort nodes in topological order."""
        in_degree = {n: 0 for n in self.nodes}
        for edge in self.edges:
            if edge.target in in_degree:
                in_degree[edge.target] += 1

        queue = [n for n, d in in_degree.items() if d == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            for edge in self.edges:
                if edge.source == node and edge.target in in_degree:
                    in_degree[edge.target] -= 1
                    if in_degree[edge.target] == 0:
                        queue.append(edge.target)

        return result


class GraphBuilder:
    """Build dependency graphs from specs."""

    def __init__(self, specs_dir: Path):
        """Initialize graph builder.

        Args:
            specs_dir: Directory containing specs.
        """
        self.specs_dir = specs_dir

    def build_graph(self) -> DependencyGraph:
        """Build dependency graph from all specs.

        Returns:
            DependencyGraph with all blocks and dependencies.
        """
        graph = DependencyGraph()

        # Find all block specs
        for block_file in self.specs_dir.rglob("block.md"):
            rel_path = block_file.parent.relative_to(self.specs_dir)
            block_name = str(rel_path)

            content = block_file.read_text()

            # Create node
            node = GraphNode(
                name=block_name,
                block_type=self._extract_block_type(content),
                status=self._extract_status(content),
            )
            graph.add_node(node)

            # Extract dependencies
            deps = self._extract_dependencies(content)
            for dep in deps:
                graph.add_edge(GraphEdge(
                    source=block_name,
                    target=dep,
                    edge_type="depends_on",
                ))

            # Extract parent relationship
            parent = self._extract_parent(content)
            if parent and parent != "none":
                graph.add_edge(GraphEdge(
                    source=block_name,
                    target=parent,
                    edge_type="child_of",
                ))

        return graph

    def _extract_block_type(self, content: str) -> str:
        """Extract block type from content."""
        match = re.search(r"block_type:\s*(\w+)", content)
        return match.group(1) if match else "component"

    def _extract_status(self, content: str) -> str:
        """Extract status from content."""
        match = re.search(r"status:\s*(\w+)", content)
        return match.group(1) if match else "draft"

    def _extract_parent(self, content: str) -> str | None:
        """Extract parent from content."""
        match = re.search(r"parent:\s*(\S+)", content)
        return match.group(1) if match else None

    def _extract_dependencies(self, content: str) -> list[str]:
        """Extract internal dependencies from content."""
        deps = []

        # Find internal dependencies section
        internal_match = re.search(
            r"### Internal\n(.*?)(?=\n###|\n## |\Z)",
            content,
            re.DOTALL
        )

        if internal_match:
            section = internal_match.group(1)
            # Find module names in table
            module_pattern = re.compile(r"\|\s*(\S+)\s*\|")
            for match in module_pattern.finditer(section):
                module_name = match.group(1)
                if module_name not in ["Module", "Purpose", "-", ""]:
                    deps.append(module_name)

        return deps


class GraphVisualizer:
    """Visualize dependency graphs in various formats."""

    def __init__(self):
        """Initialize visualizer."""
        pass

    def render(self, graph: DependencyGraph, format: OutputFormat) -> str:
        """Render graph in specified format.

        Args:
            graph: The dependency graph.
            format: Output format.

        Returns:
            Rendered string.
        """
        if format == OutputFormat.MERMAID:
            return self._render_mermaid(graph)
        elif format == OutputFormat.DOT:
            return self._render_dot(graph)
        elif format == OutputFormat.ASCII:
            return self._render_ascii(graph)
        elif format == OutputFormat.JSON:
            return self._render_json(graph)
        else:
            raise ValueError(f"Unknown format: {format}")

    def _render_mermaid(self, graph: DependencyGraph) -> str:
        """Render as Mermaid diagram."""
        lines = ["graph TD"]

        # Add nodes with styling
        for name, node in graph.nodes.items():
            safe_name = name.replace("/", "_").replace("-", "_")

            # Style based on type
            if node.block_type == "root":
                lines.append(f"    {safe_name}[[\"{name}\"]]")
            elif node.block_type == "component":
                lines.append(f"    {safe_name}[\"{name}\"]")
            elif node.block_type == "module":
                lines.append(f"    {safe_name}(\"{name}\")")
            else:
                lines.append(f"    {safe_name}>{name}]")

        # Add edges
        for edge in graph.edges:
            source = edge.source.replace("/", "_").replace("-", "_")
            target = edge.target.replace("/", "_").replace("-", "_")

            if edge.edge_type == "child_of":
                lines.append(f"    {source} -.-> {target}")
            else:
                lines.append(f"    {source} --> {target}")

        # Add styling
        lines.extend([
            "",
            "    classDef root fill:#e1f5fe,stroke:#01579b",
            "    classDef component fill:#f3e5f5,stroke:#7b1fa2",
            "    classDef module fill:#e8f5e9,stroke:#2e7d32",
        ])

        # Apply classes
        for name, node in graph.nodes.items():
            safe_name = name.replace("/", "_").replace("-", "_")
            lines.append(f"    class {safe_name} {node.block_type}")

        return "\n".join(lines)

    def _render_dot(self, graph: DependencyGraph) -> str:
        """Render as DOT/Graphviz."""
        lines = [
            "digraph G {",
            "    rankdir=TB;",
            "    node [shape=box];",
            "",
        ]

        # Add nodes
        for name, node in graph.nodes.items():
            safe_name = name.replace("/", "_").replace("-", "_")
            color = {
                "root": "lightblue",
                "component": "lavender",
                "module": "lightgreen",
            }.get(node.block_type, "white")

            lines.append(f'    {safe_name} [label="{name}" fillcolor="{color}" style="filled"];')

        lines.append("")

        # Add edges
        for edge in graph.edges:
            source = edge.source.replace("/", "_").replace("-", "_")
            target = edge.target.replace("/", "_").replace("-", "_")
            style = "dashed" if edge.edge_type == "child_of" else "solid"
            lines.append(f'    {source} -> {target} [style="{style}"];')

        lines.append("}")

        return "\n".join(lines)

    def _render_ascii(self, graph: DependencyGraph) -> str:
        """Render as ASCII tree."""
        lines = []

        def render_node(name: str, prefix: str = "", is_last: bool = True):
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{name}")

            children = graph.get_dependents(name)
            child_prefix = prefix + ("    " if is_last else "│   ")

            for i, child in enumerate(children):
                render_node(child, child_prefix, i == len(children) - 1)

        # Start from roots
        roots = graph.get_roots()
        for i, root in enumerate(roots):
            if i > 0:
                lines.append("")
            lines.append(root)
            children = graph.get_dependents(root)
            for j, child in enumerate(children):
                render_node(child, "", j == len(children) - 1)

        return "\n".join(lines)

    def _render_json(self, graph: DependencyGraph) -> str:
        """Render as JSON."""
        import json

        data = {
            "nodes": [
                {
                    "id": name,
                    "type": node.block_type,
                    "status": node.status,
                }
                for name, node in graph.nodes.items()
            ],
            "edges": [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "type": edge.edge_type,
                }
                for edge in graph.edges
            ],
        }

        return json.dumps(data, indent=2)


def generate_graph_file(
    specs_dir: Path,
    output_file: Path,
    format: OutputFormat = OutputFormat.MERMAID
) -> None:
    """Generate graph visualization file.

    Args:
        specs_dir: Directory containing specs.
        output_file: Output file path.
        format: Output format.
    """
    builder = GraphBuilder(specs_dir)
    graph = builder.build_graph()

    visualizer = GraphVisualizer()
    content = visualizer.render(graph, format)

    # Wrap in markdown if mermaid
    if format == OutputFormat.MERMAID:
        content = f"# Dependency Graph\n\n```mermaid\n{content}\n```\n"

    output_file.write_text(content)
