"""Tests for ``job_agent.loaders``.

File operations use ``tmp_path`` to stay off the real filesystem.
Excel loading is tested with an in-memory ``openpyxl`` workbook.
"""

import pytest
import pandas as pd

from job_agent.loaders import load_cv, load_skills_table


class TestLoadCV:
    """Tests for ``load_cv``."""

    def test_reads_file_content(self, tmp_path):
        """Returns the exact UTF-8 content of the file."""
        cv_file = tmp_path / "cv.md"
        cv_file.write_text("## Summary\nData scientist.", encoding="utf-8")
        result = load_cv(cv_file)
        assert result == "## Summary\nData scientist."

    def test_raises_file_not_found(self, tmp_path):
        """Raises ``FileNotFoundError`` for a missing file."""
        with pytest.raises(FileNotFoundError, match="CV not found"):
            load_cv(tmp_path / "missing.md")

    def test_returns_string(self, tmp_path):
        """Return type is ``str``."""
        cv_file = tmp_path / "cv.md"
        cv_file.write_text("content", encoding="utf-8")
        assert isinstance(load_cv(cv_file), str)


class TestLoadSkillsTable:
    """Tests for ``load_skills_table``."""

    @pytest.fixture
    def skills_xlsx(self, tmp_path) -> "Path":
        """Write a minimal skills Excel file and return its path."""
        df = pd.DataFrame(
            {
                "Skill": ["Python", "SQL"],
                "Category": ["Programming", "Programming"],
                "Proficiency": ["Expert", "Advanced"],
                "Projects": ["Pipeline", "Reports"],
                "Roles": ["DS", "DA"],
                "Years": [5, 3],
            }
        )
        path = tmp_path / "skills.xlsx"
        df.to_excel(path, index=False)
        return path

    def test_returns_markdown_table(self, skills_xlsx):
        """Return value is a markdown pipe-table string."""
        result = load_skills_table(skills_xlsx)
        assert "|" in result
        assert "Python" in result
        assert "SQL" in result

    def test_contains_header_row(self, skills_xlsx):
        """Markdown table includes a header row."""
        result = load_skills_table(skills_xlsx)
        assert "Skill" in result
        assert "Category" in result

    def test_raises_file_not_found(self, tmp_path):
        """Raises ``FileNotFoundError`` for a missing file."""
        with pytest.raises(FileNotFoundError, match="Skills table not found"):
            load_skills_table(tmp_path / "missing.xlsx")

    def test_returns_string(self, skills_xlsx):
        """Return type is ``str``."""
        assert isinstance(load_skills_table(skills_xlsx), str)
