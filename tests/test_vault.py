"""Unit tests for ``job_agent.vault``.

Formatting functions are pure (in → str out) so they need no mocking.
File I/O functions use a ``tmp_path`` fixture to stay off the real filesystem.
"""

import pytest

from job_agent.vault import (
    create_vault_folder,
    format_analysis_report,
    format_diff_report,
    format_rescore_report,
    format_status,
    write_to_vault,
)


class TestCreateVaultFolder:
    """Tests for ``create_vault_folder``."""

    def test_creates_folder(self, tmp_path):
        """Folder is created on disk."""
        folder = create_vault_folder(tmp_path, "Acme Corp", "Data Scientist")
        assert folder.exists()
        assert folder.is_dir()

    def test_folder_name_contains_company_and_role(self, tmp_path):
        """Folder name includes sanitised company and role."""
        folder = create_vault_folder(tmp_path, "Acme Corp", "Data Scientist")
        assert "Acme_Corp" in folder.name
        assert "Data_Scientist" in folder.name

    def test_folder_name_contains_date(self, tmp_path):
        """Folder name includes a date stamp."""
        from datetime import datetime
        folder = create_vault_folder(tmp_path, "Acme", "DS")
        date_str = datetime.now().strftime("%Y-%m-%d")
        assert date_str in folder.name

    def test_special_characters_sanitised(self, tmp_path):
        """Special characters in company/role are replaced with underscores."""
        folder = create_vault_folder(tmp_path, "Acme & Co.", "Sr. Data Scientist!")
        assert "&" not in folder.name
        assert "." not in folder.name
        assert "!" not in folder.name

    def test_idempotent_on_existing_folder(self, tmp_path):
        """Calling twice does not raise an error."""
        create_vault_folder(tmp_path, "Acme", "DS")
        create_vault_folder(tmp_path, "Acme", "DS")  # should not raise


class TestWriteToVault:
    """Tests for ``write_to_vault``."""

    def test_file_is_created(self, tmp_path):
        """File appears on disk after writing."""
        path = write_to_vault(tmp_path, "test.md", "Hello")
        assert path.exists()

    def test_file_content_matches(self, tmp_path):
        """File content is exactly what was passed."""
        write_to_vault(tmp_path, "report.md", "# Title\n\nBody text.")
        content = (tmp_path / "report.md").read_text(encoding="utf-8")
        assert content == "# Title\n\nBody text."

    def test_returns_path_object(self, tmp_path):
        """Return value is a ``Path`` pointing at the written file."""
        from pathlib import Path
        result = write_to_vault(tmp_path, "out.md", "x")
        assert isinstance(result, Path)
        assert result == tmp_path / "out.md"

    def test_overwrites_existing_file(self, tmp_path):
        """Calling twice with the same filename overwrites the file."""
        write_to_vault(tmp_path, "f.md", "first")
        write_to_vault(tmp_path, "f.md", "second")
        assert (tmp_path / "f.md").read_text() == "second"


class TestFormatAnalysisReport:
    """Tests for ``format_analysis_report``."""

    def test_contains_aggregate_score(self, analysis_result):
        """Report includes the aggregate score."""
        md = format_analysis_report(analysis_result)
        assert "75/100" in md

    def test_proceed_shows_green_tick(self, analysis_result):
        """Proceed=True renders a ✅ symbol."""
        md = format_analysis_report(analysis_result)
        assert "✅" in md

    def test_do_not_apply_shows_cross(self, failing_analysis_result):
        """Proceed=False renders an ❌ symbol."""
        md = format_analysis_report(failing_analysis_result)
        assert "❌" in md

    def test_soft_missing_section_present(self, analysis_result):
        """Soft missing keywords appear under their own heading."""
        md = format_analysis_report(analysis_result)
        assert "Soft Missing" in md
        assert "machine learning" in md

    def test_hard_missing_section_present(self, analysis_result):
        """Hard missing keywords appear under their own heading."""
        md = format_analysis_report(analysis_result)
        assert "Hard Missing" in md
        assert "FDA 510k" in md

    def test_section_scores_listed(self, analysis_result):
        """All three section names appear in the report."""
        md = format_analysis_report(analysis_result)
        assert "Summary" in md
        assert "Experience" in md
        assert "Skills" in md


class TestFormatDiffReport:
    """Tests for ``format_diff_report``."""

    def test_contains_original_summary(self, diff_result):
        """Original summary text appears in the diff."""
        md = format_diff_report(diff_result)
        assert diff_result.original_summary in md

    def test_contains_new_summary(self, diff_result):
        """New summary text appears in the diff."""
        md = format_diff_report(diff_result)
        assert diff_result.new_summary in md

    def test_contains_changes(self, diff_result):
        """Each change entry appears in the output."""
        md = format_diff_report(diff_result)
        for change in diff_result.changes:
            assert change in md

    def test_variant_label_in_heading(self, diff_result):
        """Variant label appears in the report heading."""
        md = format_diff_report(diff_result)
        assert "Technical" in md


class TestFormatRescorerReport:
    """Tests for ``format_rescore_report``."""

    def test_gate_passed_shows_tick(self, passing_rescore_result):
        """Passing gate renders ✅."""
        md = format_rescore_report(passing_rescore_result)
        assert "✅" in md

    def test_gate_failed_shows_cross(self, failing_rescore_result):
        """Failing gate renders ❌."""
        md = format_rescore_report(failing_rescore_result)
        assert "❌" in md

    def test_new_score_in_report(self, passing_rescore_result):
        """New aggregate score is present in the output."""
        md = format_rescore_report(passing_rescore_result)
        assert "85/100" in md

    def test_aggregate_delta_shown(self, passing_rescore_result):
        """Positive delta is shown with a + prefix."""
        md = format_rescore_report(passing_rescore_result)
        assert "+10" in md

    def test_regressions_section_shown_when_present(self, failing_rescore_result):
        """Regressions section appears when there are regressions."""
        md = format_rescore_report(failing_rescore_result)
        assert "Regressions" in md

    def test_no_regression_section_when_clean(self, passing_rescore_result):
        """No regressions section when list is empty."""
        md = format_rescore_report(passing_rescore_result)
        assert "Regressions" not in md


class TestFormatStatus:
    """Tests for ``format_status``."""

    def test_contains_company_and_role(self, pipeline_state):
        """Company and role appear in the status file."""
        md = format_status(pipeline_state)
        assert "Acme Corp" in md
        assert "Senior Data Scientist" in md

    def test_na_scores_when_no_analysis(self, pipeline_state):
        """Shows N/A when no analysis has been run."""
        md = format_status(pipeline_state)
        assert "N/A" in md

    def test_scores_shown_when_analysis_present(
        self, pipeline_state, analysis_result, passing_rescore_result
    ):
        """Initial and final scores appear when agents have run."""
        pipeline_state.analysis = analysis_result
        pipeline_state.rescore_result = passing_rescore_result
        md = format_status(pipeline_state)
        assert "75" in md
        assert "85" in md
