"""MCP server that lets agents validate and repair LaTeX bibliographies.

``mcp`` is an optional extra (Python 3.10+). The import stays inside
:func:`build_server` so the core package still imports on a minimal install.
"""

from __future__ import annotations

from typing import Any

from .agent import AgentResult, run_references

_INSTRUCTIONS = (
    "Use polish_references when the user wants bibliography problems fixed. "
    "Use validate_references to inspect citations and fields. "
    "Use curate_references to clean files without the surrounding validation passes. "
    "Pass project_dir as the LaTeX project root. "
    "Curate and polish rewrite .bib files and matching .tex citation keys, "
    "and they create .backup copies unless create_backups is false. "
    "validate_references may still apply text-level fixes required to parse a file. "
    "Set skip_metadata_update when the run must stay offline."
)


def build_server() -> Any:
    """Return a configured MCP server. Requires ``pip install 'bibfixer[mcp]'``."""
    try:
        from mcp.server.mcpserver import MCPServer
        from mcp.types import ToolAnnotations
    except ImportError as exc:
        raise ImportError(
            "The bibfixer MCP server needs the mcp extra: pip install 'bibfixer[mcp]'"
        ) from exc

    server = MCPServer("bibfixer", instructions=_INSTRUCTIONS)

    @server.tool(
        annotations=ToolAnnotations(
            title="Validate references",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    def validate_references(
        project_dir: str | None = None,
        bib_paths: list[str] | None = None,
    ) -> AgentResult:
        """Inspect bibliography files and TeX citations.

        May apply text-level fixes required to parse a .bib file. Does not
        remove entries, rewrite citation keys, or contact Crossref.
        """
        return run_references(
            "validate",
            project_dir=project_dir,
            bib_paths=bib_paths,
            skip_metadata_update=True,
        )

    @server.tool(
        annotations=ToolAnnotations(
            title="Curate references",
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=False,
            open_world_hint=True,
        )
    )
    def curate_references(
        project_dir: str | None = None,
        bib_paths: list[str] | None = None,
        create_backups: bool = True,
        preserve_keys: bool = False,
        skip_metadata_update: bool = False,
    ) -> AgentResult:
        """Clean bibliography files in place.

        Removes unused and duplicate entries, normalizes fields, and rewrites
        citation keys when main.tex is present. Creates .backup copies first.
        """
        return run_references(
            "curate",
            project_dir=project_dir,
            bib_paths=bib_paths,
            create_backups=create_backups,
            preserve_keys=preserve_keys,
            skip_metadata_update=skip_metadata_update,
        )

    @server.tool(
        annotations=ToolAnnotations(
            title="Polish references",
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=False,
            open_world_hint=True,
        )
    )
    def polish_references(
        project_dir: str | None = None,
        bib_paths: list[str] | None = None,
        create_backups: bool = True,
        preserve_keys: bool = False,
        skip_metadata_update: bool = False,
    ) -> AgentResult:
        """Validate, repair, then validate again.

        Prefer this when the user asks to fix references. Rewrites .bib files
        and matching .tex citations, and creates .backup copies first.
        """
        return run_references(
            "polish",
            project_dir=project_dir,
            bib_paths=bib_paths,
            create_backups=create_backups,
            preserve_keys=preserve_keys,
            skip_metadata_update=skip_metadata_update,
        )

    return server


def main() -> None:
    """Serve bibfixer tools over stdio."""
    build_server().run()


if __name__ == "__main__":
    main()
