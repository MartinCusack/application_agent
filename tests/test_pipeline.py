"""Tests for ``job_agent.pipeline``.

The pipeline is tested with all agent calls mocked so no real API calls
are made.  Tests verify control flow (early exits, vault writes) rather
than LLM output quality.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from job_agent.models import PipelineState
from job_agent.pipeline import run_pipeline


def _make_mock_agent(return_value):
    """Return a mock agent class whose ``.run()`` returns ``return_value``."""
    mock_instance = MagicMock()
    mock_instance.run.return_value = return_value
    mock_class = MagicMock(return_value=mock_instance)
    return mock_class


@pytest.fixture
def pipeline_patches(
    tmp_path,
    analysis_result,
    failing_analysis_result,
    writer_result,
    diff_result,
    passing_rescore_result,
    failing_rescore_result,
    sample_cv_text,
    sample_skills_table,
):
    """Bundle of commonly needed test objects for pipeline tests."""
    return {
        "tmp_path": tmp_path,
        "analysis": analysis_result,
        "failing_analysis": failing_analysis_result,
        "writer": writer_result,
        "diff": diff_result,
        "passing_rescore": passing_rescore_result,
        "failing_rescore": failing_rescore_result,
        "cv_text": sample_cv_text,
        "skills_table": sample_skills_table,
    }


class TestRunPipelineFullRun:
    """Tests for the happy-path full pipeline run."""

    def test_returns_pipeline_state(self, pipeline_patches):
        """``run_pipeline`` returns a ``PipelineState`` object."""
        p = pipeline_patches
        with (
            patch("job_agent.pipeline.load_cv", return_value=p["cv_text"]),
            patch("job_agent.pipeline.load_skills_table", return_value=p["skills_table"]),
            patch("job_agent.pipeline.create_vault_folder", return_value=p["tmp_path"]),
            patch("job_agent.pipeline.write_to_vault"),
            patch("job_agent.pipeline.AnalystAgent", _make_mock_agent(p["analysis"])),
            patch("job_agent.pipeline.WriterAgent", _make_mock_agent(p["writer"])),
            patch("job_agent.pipeline.DiffAgent", _make_mock_agent(p["diff"])),
            patch("job_agent.pipeline.RescorerAgent", _make_mock_agent(p["passing_rescore"])),
        ):
            state = run_pipeline("Acme", "DS", "A great job.")
        assert isinstance(state, PipelineState)

    def test_all_agent_outputs_populated(self, pipeline_patches):
        """All agent result fields are set on a successful full run."""
        p = pipeline_patches
        with (
            patch("job_agent.pipeline.load_cv", return_value=p["cv_text"]),
            patch("job_agent.pipeline.load_skills_table", return_value=p["skills_table"]),
            patch("job_agent.pipeline.create_vault_folder", return_value=p["tmp_path"]),
            patch("job_agent.pipeline.write_to_vault"),
            patch("job_agent.pipeline.AnalystAgent", _make_mock_agent(p["analysis"])),
            patch("job_agent.pipeline.WriterAgent", _make_mock_agent(p["writer"])),
            patch("job_agent.pipeline.DiffAgent", _make_mock_agent(p["diff"])),
            patch("job_agent.pipeline.RescorerAgent", _make_mock_agent(p["passing_rescore"])),
        ):
            state = run_pipeline("Acme", "DS", "A great job.")
        assert state.analysis is not None
        assert state.writer_result is not None
        assert state.diff_result is not None
        assert state.rescore_result is not None

    def test_vault_path_set(self, pipeline_patches):
        """``vault_path`` is populated with the folder path string."""
        p = pipeline_patches
        with (
            patch("job_agent.pipeline.load_cv", return_value=p["cv_text"]),
            patch("job_agent.pipeline.load_skills_table", return_value=p["skills_table"]),
            patch("job_agent.pipeline.create_vault_folder", return_value=p["tmp_path"]),
            patch("job_agent.pipeline.write_to_vault"),
            patch("job_agent.pipeline.AnalystAgent", _make_mock_agent(p["analysis"])),
            patch("job_agent.pipeline.WriterAgent", _make_mock_agent(p["writer"])),
            patch("job_agent.pipeline.DiffAgent", _make_mock_agent(p["diff"])),
            patch("job_agent.pipeline.RescorerAgent", _make_mock_agent(p["passing_rescore"])),
        ):
            state = run_pipeline("Acme", "DS", "A great job.")
        assert state.vault_path is not None


class TestRunPipelineEarlyExit:
    """Tests for early-exit behaviour."""

    def test_stops_after_analyst_when_not_proceeding(self, pipeline_patches):
        """Pipeline returns early if analyst recommends not applying."""
        p = pipeline_patches
        mock_writer = MagicMock()

        with (
            patch("job_agent.pipeline.load_cv", return_value=p["cv_text"]),
            patch("job_agent.pipeline.load_skills_table", return_value=p["skills_table"]),
            patch("job_agent.pipeline.create_vault_folder", return_value=p["tmp_path"]),
            patch("job_agent.pipeline.write_to_vault"),
            patch("job_agent.pipeline.AnalystAgent", _make_mock_agent(p["failing_analysis"])),
            patch("job_agent.pipeline.WriterAgent", mock_writer),
        ):
            state = run_pipeline("Acme", "DS", "A great job.")

        assert state.writer_result is None
        mock_writer.assert_not_called()

    def test_stops_after_rescorer_when_gate_fails(self, pipeline_patches):
        """Pipeline returns early if rescorer gate fails."""
        p = pipeline_patches

        with (
            patch("job_agent.pipeline.load_cv", return_value=p["cv_text"]),
            patch("job_agent.pipeline.load_skills_table", return_value=p["skills_table"]),
            patch("job_agent.pipeline.create_vault_folder", return_value=p["tmp_path"]),
            patch("job_agent.pipeline.write_to_vault"),
            patch("job_agent.pipeline.AnalystAgent", _make_mock_agent(p["analysis"])),
            patch("job_agent.pipeline.WriterAgent", _make_mock_agent(p["writer"])),
            patch("job_agent.pipeline.DiffAgent", _make_mock_agent(p["diff"])),
            patch("job_agent.pipeline.RescorerAgent", _make_mock_agent(p["failing_rescore"])),
        ):
            state = run_pipeline("Acme", "DS", "A great job.")

        assert state.rescore_result is not None
        assert state.rescore_result.gate_passed is False

    def test_custom_threshold_passed_to_rescorer(self, pipeline_patches):
        """A threshold passed to ``run_pipeline`` reaches ``RescorerAgent.run``."""
        p = pipeline_patches
        mock_rescorer_instance = MagicMock()
        mock_rescorer_instance.run.return_value = p["passing_rescore"]
        mock_rescorer_class = MagicMock(return_value=mock_rescorer_instance)

        with (
            patch("job_agent.pipeline.load_cv", return_value=p["cv_text"]),
            patch("job_agent.pipeline.load_skills_table", return_value=p["skills_table"]),
            patch("job_agent.pipeline.create_vault_folder", return_value=p["tmp_path"]),
            patch("job_agent.pipeline.write_to_vault"),
            patch("job_agent.pipeline.AnalystAgent", _make_mock_agent(p["analysis"])),
            patch("job_agent.pipeline.WriterAgent", _make_mock_agent(p["writer"])),
            patch("job_agent.pipeline.DiffAgent", _make_mock_agent(p["diff"])),
            patch("job_agent.pipeline.RescorerAgent", mock_rescorer_class),
        ):
            run_pipeline("Acme", "DS", "A great job.", threshold=80)

        _, kwargs = mock_rescorer_instance.run.call_args
        assert kwargs["threshold"] == 80


class TestRunPipelineVariantSelection:
    """Tests for CV variant selection logic."""

    def test_leadership_variant_selected(self, pipeline_patches):
        """Writer produces a leadership variant which is stored on state."""
        p = pipeline_patches
        with (
            patch("job_agent.pipeline.load_cv", return_value=p["cv_text"]),
            patch("job_agent.pipeline.load_skills_table", return_value=p["skills_table"]),
            patch("job_agent.pipeline.create_vault_folder", return_value=p["tmp_path"]),
            patch("job_agent.pipeline.write_to_vault"),
            patch("job_agent.pipeline.AnalystAgent", _make_mock_agent(p["analysis"])),
            patch("job_agent.pipeline.WriterAgent", _make_mock_agent(p["writer"])),
            patch("job_agent.pipeline.DiffAgent", _make_mock_agent(p["diff"])),
            patch("job_agent.pipeline.RescorerAgent", _make_mock_agent(p["passing_rescore"])),
        ):
            state = run_pipeline("Acme", "DS", "A great job.")
        assert state.selected_variant == "leadership"
