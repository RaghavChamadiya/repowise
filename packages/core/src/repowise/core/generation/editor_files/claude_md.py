"""ClaudeMdGenerator — generates and maintains CLAUDE.md for a repository."""

from __future__ import annotations

from .base import BaseEditorFileGenerator


class ClaudeMdGenerator(BaseEditorFileGenerator):
    """Generates and maintains the CLAUDE.md file.

    The file has two sections:
      - User section (above the REPOWISE markers): never touched by Repowise.
      - Repowise section (between markers): auto-generated from indexed data.
    """

    filename = "CLAUDE.md"
    marker_tag = "REPOWISE"
    template_name = "claude_md.j2"
    user_placeholder = (
        "# CLAUDE.md\n\n"
        "<!-- Add your custom instructions below. "
        "Repowise will never modify anything outside the REPOWISE markers. -->\n"
        "<!-- Examples: coding style rules, test commands, "
        "workflow preferences, constraints -->\n"
    )
