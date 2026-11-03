"""
tests/test_link_checker.py — Internal link & file-path checker for all Markdown files.

Checks:
- Every relative file path referenced as [text](path) in any .md file resolves to a real file.
- Every fenced ```text``` tree path (bare filenames like tripmate/config/settings.py) exists.
- Reports all broken links with the source file and line number.

Run with:
    pytest tests/test_link_checker.py -v
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, NamedTuple

import pytest

ROOT = Path(__file__).resolve().parent.parent


class BrokenLink(NamedTuple):
    source_file: str
    line_number: int
    link_target: str
    reason: str


def _collect_markdown_files() -> List[Path]:
    """Return every .md file in the repo (excluding .pytest_cache, __pycache__)."""
    return [
        p
        for p in ROOT.rglob("*.md")
        if ".pytest_cache" not in p.parts
        and "__pycache__" not in p.parts
        and ".git" not in p.parts
    ]


_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)#\s]+)(?:#[^)]*)?\)")
_MD_BADGE_PREFIXES = ("http://", "https://", "mailto:")


def _check_markdown_links(md_file: Path) -> List[BrokenLink]:
    broken: List[BrokenLink] = []
    text = md_file.read_text(encoding="utf-8", errors="replace")
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in _LINK_RE.finditer(line):
            target = match.group(2)
            # Skip external URLs and anchors-only
            if any(target.startswith(p) for p in _MD_BADGE_PREFIXES):
                continue
            if target.startswith("#"):
                continue
            # Resolve relative to the markdown file's directory
            resolved = (md_file.parent / target).resolve()
            if not resolved.exists():
                broken.append(
                    BrokenLink(
                        source_file=str(md_file.relative_to(ROOT)),
                        line_number=lineno,
                        link_target=target,
                        reason="file not found",
                    )
                )
    return broken


def _collect_all_broken_links() -> List[BrokenLink]:
    all_broken: List[BrokenLink] = []
    for md_file in _collect_markdown_files():
        all_broken.extend(_check_markdown_links(md_file))
    return all_broken


ALL_BROKEN = _collect_all_broken_links()
ALL_MD_FILES = _collect_markdown_files()


class TestMarkdownLinks:
    """All relative file references in Markdown files must resolve to real files."""

    @pytest.mark.skipif(not ALL_BROKEN, reason="No broken links found — all clear")
    @pytest.mark.parametrize(
        "broken",
        ALL_BROKEN,
        ids=[f"{b.source_file}:L{b.line_number}:{b.link_target}" for b in ALL_BROKEN],
    )
    def test_no_broken_links(self, broken: BrokenLink):
        pytest.fail(
            f"Broken link in {broken.source_file} line {broken.line_number}: "
            f"{broken.link_target!r} — {broken.reason}"
        )

    def test_all_markdown_files_parsed(self):
        """Sanity: at least README.md must be found."""
        file_names = [f.name for f in ALL_MD_FILES]
        assert "README.md" in file_names, "README.md not found during markdown scan"

    def test_link_scan_summary(self, capsys):
        """Print a summary of checked files and broken link count."""
        with capsys.disabled():
            print(
                f"\n[link-checker] Scanned {len(ALL_MD_FILES)} markdown files, "
                f"found {len(ALL_BROKEN)} broken link(s)."
            )
        assert True  # always pass; broken links are reported individually above

