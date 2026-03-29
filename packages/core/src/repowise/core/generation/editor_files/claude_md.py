"""ClaudeMdGenerator — generates and maintains .claude/CLAUDE.md for a repository."""

from __future__ import annotations

from pathlib import Path

from .base import BaseEditorFileGenerator
from .data import EditorFileData


class ClaudeMdGenerator(BaseEditorFileGenerator):
    """Generates and maintains .claude/CLAUDE.md.

    Writes to <repo_path>/.claude/CLAUDE.md so Claude Code auto-discovers it.
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

    def write(self, repo_path: Path, data: EditorFileData) -> Path:
        """Write to <repo_path>/.claude/CLAUDE.md, creating the directory if needed."""
        dot_claude = repo_path / ".claude"
        dot_claude.mkdir(parents=True, exist_ok=True)
        return super().write(dot_claude, data)

    def render_full(self, repo_path: Path, data: EditorFileData) -> str:
        """Preview what .claude/CLAUDE.md would contain without writing."""
        dot_claude = repo_path / ".claude"
        return super().render_full(dot_claude, data)
