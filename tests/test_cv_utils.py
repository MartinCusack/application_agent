"""Unit tests for ``job_agent.cv_utils``.

These tests cover pure string operations so no mocking is needed.
"""

import pytest

from job_agent.cv_utils import extract_summary, substitute_summary


class TestExtractSummary:
    """Tests for ``extract_summary``."""

    def test_extracts_summary_heading(self):
        """Returns text between ## Summary and the next ## heading."""
        cv = "## Summary\nI am a data scientist.\n\n## Experience\nAccme Corp."
        result = extract_summary(cv)
        assert result == "I am a data scientist."

    def test_extracts_profile_heading(self):
        """Recognises ## Profile as an alternative summary heading."""
        cv = "## Profile\nSenior engineer.\n\n## Skills\nPython."
        result = extract_summary(cv)
        assert result == "Senior engineer."

    def test_extracts_about_heading(self):
        """Recognises ## About as an alternative summary heading."""
        cv = "## About\nPassionate researcher.\n\n## Experience\nLab."
        result = extract_summary(cv)
        assert result == "Passionate researcher."

    def test_heading_case_insensitive(self):
        """Heading matching is case-insensitive."""
        cv = "## SUMMARY\nCapitals work too.\n\n## Experience\nX."
        result = extract_summary(cv)
        assert result == "Capitals work too."

    def test_returns_empty_string_when_no_summary(self):
        """Returns an empty string if no matching heading is found."""
        cv = "## Experience\nAccme Corp.\n\n## Skills\nPython."
        result = extract_summary(cv)
        assert result == ""

    def test_multiline_summary(self):
        """Captures multi-line summary content correctly."""
        cv = "## Summary\nLine one.\nLine two.\nLine three.\n\n## Experience\nX."
        result = extract_summary(cv)
        assert "Line one." in result
        assert "Line two." in result
        assert "Line three." in result

    def test_strips_whitespace(self):
        """Result has no leading or trailing whitespace."""
        cv = "## Summary\n\n  Padded content.  \n\n## Experience\nX."
        result = extract_summary(cv)
        assert result == result.strip()


class TestSubstituteSummary:
    """Tests for ``substitute_summary``."""

    def test_replaces_summary_section(self):
        """New summary replaces content between heading and next heading."""
        cv = "## Summary\nOld content.\n\n## Experience\nAccme."
        result = substitute_summary(cv, "New content.")
        assert "New content." in result
        assert "Old content." not in result

    def test_preserves_experience_section(self):
        """Sections after the summary are preserved unchanged."""
        cv = "## Summary\nOld.\n\n## Experience\nKeep this."
        result = substitute_summary(cv, "New.")
        assert "Keep this." in result

    def test_preserves_summary_heading(self):
        """The heading line itself is retained in the output."""
        cv = "## Summary\nOld.\n\n## Experience\nX."
        result = substitute_summary(cv, "New.")
        assert "## Summary" in result

    def test_prepends_when_no_summary_found(self):
        """Prepends new summary when no matching heading exists."""
        cv = "## Experience\nAccme Corp."
        result = substitute_summary(cv, "Prepended summary.")
        assert result.startswith("Prepended summary.")
        assert "## Experience" in result

    def test_round_trip_extract_substitute(self, sample_cv_text):
        """Substituting then re-extracting yields the new summary."""
        new_summary = "Accomplished X as measured by Y, by doing Z."
        modified_cv = substitute_summary(sample_cv_text, new_summary)
        extracted = extract_summary(modified_cv)
        assert extracted == new_summary
