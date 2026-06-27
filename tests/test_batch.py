"""Tests for the batch pipeline orchestrator and JD file parser.

All pipeline calls are mocked — no API key is needed.

Coverage:
- ``jd_parser._extract_frontmatter``  — YAML extraction from markdown headers
- ``jd_parser._parse_filename``       — company/role derivation from filename
- ``jd_parser.parse_jd_file``         — end-to-end file parsing
- ``batch.discover_jd_files``         — directory scanning
- ``batch.run_batch`` (dry_run)       — no-op listing mode
- ``batch.run_batch`` (error isolation) — one failure doesn't abort the rest
- ``batch.run_batch`` (file movement) — files end up in the right subdirectory
- ``batch.run_batch`` (result counts) — aggregate totals are accurate
- ``vault.format_batch_summary``      — markdown output from BatchRunResult
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from job_agent.jd_parser import _extract_frontmatter, _parse_filename, parse_jd_file
from job_agent.models import (
    AnalysisResult,
    BatchJobResult,
    BatchRunResult,
    JDFileMetadata,
    PipelineState,
    RescorerResult,
    ScoringRubric,
    SectionScore,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _write_jd(tmp_path: Path, name: str, content: str) -> Path:
    """Write a JD file to tmp_path and return the path."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ── jd_parser: _extract_frontmatter ────────────────────────────────────────────

class TestExtractFrontmatter:
    """Unit tests for the YAML frontmatter extractor.

    The extractor must split the ``---...---`` block from the body and parse
    the simple key/value pairs it contains.  Files without a frontmatter block
    should pass through unchanged.
    """

    def test_no_frontmatter_returns_empty_dict_and_full_text(self):
        """Files with no ``---`` block should return an empty dict and the original text."""
        text = "# Job Description\n\nSome content."
        meta, body = _extract_frontmatter(text)
        assert meta == {}
        assert body == text

    def test_parses_string_fields(self):
        """String values should be returned as plain Python strings."""
        text = "---\ncompany: Acme\nrole: Data Scientist\n---\n\nBody text."
        meta, body = _extract_frontmatter(text)
        assert meta["company"] == "Acme"
        assert meta["role"] == "Data Scientist"
        assert body == "\nBody text."

    def test_parses_int_field(self):
        """Digit-only values should be returned as Python ints."""
        text = "---\nthreshold: 70\n---\n\nBody."
        meta, _ = _extract_frontmatter(text)
        assert meta["threshold"] == 70

    def test_parses_bool_false(self):
        """The string ``false`` should be converted to Python ``False``."""
        text = "---\nforce: false\n---\n\nBody."
        meta, _ = _extract_frontmatter(text)
        assert meta["force"] is False

    def test_parses_bool_true(self):
        """The string ``true`` should be converted to Python ``True``."""
        text = "---\nforce: true\n---\n\nBody."
        meta, _ = _extract_frontmatter(text)
        assert meta["force"] is True

    def test_strips_quotes_from_string(self):
        """Quoted string values should have their surrounding quotes removed."""
        text = '---\ncompany: "Acme Corp"\n---\n\nBody.'
        meta, _ = _extract_frontmatter(text)
        assert meta["company"] == "Acme Corp"

    def test_frontmatter_not_at_top_is_ignored(self):
        """A ``---`` block that does not start at line 1 should not be treated as frontmatter."""
        text = "Some intro.\n---\ncompany: Acme\n---\n\nBody."
        meta, body = _extract_frontmatter(text)
        assert meta == {}
        assert body == text


# ── jd_parser: _parse_filename ─────────────────────────────────────────────────

class TestParseFilename:
    """Unit tests for the filename-based company/role extractor.

    The convention is ``Company_Role_Words.md``: the first underscore-separated
    token is the company; all remaining tokens join with spaces to form the role.
    """

    def test_single_word_company_and_two_word_role(self):
        """Standard two-part name: first token = company, rest = role."""
        p = Path("job_descriptions/TODO/Deel_Data_Scientist.md")
        company, role = _parse_filename(p)
        assert company == "Deel"
        assert role == "Data Scientist"

    def test_three_tokens(self):
        """Three tokens: first is company, remaining two join as role."""
        p = Path("Acme_Senior_DS.md")
        company, role = _parse_filename(p)
        assert company == "Acme"
        assert role == "Senior DS"

    def test_no_underscore_uses_full_stem_for_both(self):
        """A filename with no underscores uses the full stem for both company and role."""
        p = Path("Acme.md")
        company, role = _parse_filename(p)
        assert company == "Acme"
        assert role == "Acme"

    def test_many_tokens(self):
        """Five-token filename: first token company, remaining four tokens joined as role."""
        p = Path("Big_Tech_Senior_Machine_Learning_Engineer.md")
        company, role = _parse_filename(p)
        assert company == "Big"
        assert role == "Tech Senior Machine Learning Engineer"


# ── jd_parser: parse_jd_file ───────────────────────────────────────────────────

class TestParseJdFile:
    """Integration tests for the top-level ``parse_jd_file`` function.

    Covers the full parsing flow: file reading, frontmatter extraction, and
    fallback to filename when frontmatter is absent.
    """

    def test_filename_fallback_no_frontmatter(self, tmp_path):
        """Without frontmatter, company and role should come from the filename."""
        jd = _write_jd(tmp_path, "Deel_Data_Scientist.md", "We are hiring a data scientist.")
        meta = parse_jd_file(jd)
        assert meta.company == "Deel"
        assert meta.role == "Data Scientist"
        assert meta.jd_text == "We are hiring a data scientist."
        assert meta.threshold is None
        assert meta.force is False

    def test_frontmatter_overrides_filename(self, tmp_path):
        """Frontmatter company/role should take precedence over the filename."""
        content = "---\ncompany: Actual Corp\nrole: ML Engineer\n---\n\nJD body."
        jd = _write_jd(tmp_path, "Wrong_Name.md", content)
        meta = parse_jd_file(jd)
        assert meta.company == "Actual Corp"
        assert meta.role == "ML Engineer"
        assert meta.jd_text == "JD body."

    def test_frontmatter_threshold_and_force(self, tmp_path):
        """Optional frontmatter fields ``threshold`` and ``force`` should be parsed."""
        content = "---\ncompany: Acme\nrole: DS\nthreshold: 55\nforce: true\n---\n\nBody."
        jd = _write_jd(tmp_path, "Acme_DS.md", content)
        meta = parse_jd_file(jd)
        assert meta.threshold == 55
        assert meta.force is True

    def test_returns_jdfilemetadata_instance(self, tmp_path):
        """parse_jd_file should always return a JDFileMetadata instance."""
        jd = _write_jd(tmp_path, "Acme_DS.md", "Body.")
        meta = parse_jd_file(jd)
        assert isinstance(meta, JDFileMetadata)

    def test_file_not_found_raises(self, tmp_path):
        """Requesting a nonexistent file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parse_jd_file(tmp_path / "nonexistent.md")


# ── batch: discover_jd_files ───────────────────────────────────────────────────

class TestDiscoverJdFiles:
    """Tests for the JD queue directory scanner.

    Only ``.md`` files should be returned, in alphabetical order.
    """

    def test_returns_only_md_files(self, tmp_path):
        """Non-``.md`` files in the directory should be ignored."""
        (tmp_path / "a.md").write_text("a")
        (tmp_path / "b.md").write_text("b")
        (tmp_path / "notes.txt").write_text("txt")

        from job_agent.batch import discover_jd_files
        files = discover_jd_files(tmp_path)
        assert len(files) == 2
        assert all(f.suffix == ".md" for f in files)

    def test_returns_sorted_alphabetically(self, tmp_path):
        """Files should be returned in alphabetical order by name."""
        (tmp_path / "z_role.md").write_text("z")
        (tmp_path / "a_role.md").write_text("a")
        (tmp_path / "m_role.md").write_text("m")

        from job_agent.batch import discover_jd_files
        files = discover_jd_files(tmp_path)
        names = [f.name for f in files]
        assert names == sorted(names)

    def test_empty_dir_returns_empty_list(self, tmp_path):
        """An empty directory should return an empty list, not raise."""
        from job_agent.batch import discover_jd_files
        assert discover_jd_files(tmp_path) == []


# ── batch: dry_run ─────────────────────────────────────────────────────────────

class TestBatchDryRun:
    """Tests for the ``--dry-run`` mode.

    Dry run should list files and return a result without processing anything
    or moving any files.
    """

    def test_dry_run_returns_result_with_total_but_no_processed(self, tmp_path):
        """Dry run should report the correct total but zero processed outcomes."""
        _write_jd(tmp_path, "Acme_DS.md", "Body.")
        _write_jd(tmp_path, "BigCo_Engineer.md", "Body.")

        from job_agent.batch import run_batch
        result = run_batch(todo_dir=tmp_path, dry_run=True)

        assert isinstance(result, BatchRunResult)
        assert result.total == 2
        assert result.applied == 0
        assert result.results == []

    def test_dry_run_does_not_move_files(self, tmp_path):
        """Files in the TODO directory should remain in place after a dry run."""
        jd = _write_jd(tmp_path, "Acme_DS.md", "Body.")

        from job_agent.batch import run_batch
        run_batch(todo_dir=tmp_path, dry_run=True)

        assert jd.exists(), "File should not be moved during dry run"


# ── batch: error isolation ─────────────────────────────────────────────────────

class TestBatchErrorIsolation:
    """Tests that per-job errors do not abort the rest of the batch.

    A single pipeline failure should be recorded as ``status="error"`` and
    the next job should still run.
    """

    def test_one_pipeline_error_does_not_stop_batch(self, tmp_path):
        """When the first job errors, the second should still be processed."""
        _write_jd(tmp_path, "Fail_Job.md", "Body.")
        _write_jd(tmp_path, "Pass_Job.md", "Body.")

        passing_state = _make_applied_state("Pass", "Job")
        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if kwargs["company"] == "Fail":
                raise RuntimeError("Simulated API failure")
            return passing_state

        with patch("job_agent.batch.run_pipeline", side_effect=side_effect):
            with patch("job_agent.batch.config") as mock_cfg:
                _configure_mock_config(mock_cfg, tmp_path)
                from job_agent.batch import run_batch
                result = run_batch(todo_dir=tmp_path, delay_seconds=0)

        assert call_count == 2, "Both jobs should have been attempted"
        assert result.errors == 1
        assert result.applied == 1

    def test_error_creates_sidecar_file(self, tmp_path):
        """A pipeline error should produce a ``.error.txt`` sidecar in the failed dir."""
        _write_jd(tmp_path, "Fail_Job.md", "Body.")

        def side_effect(**kwargs):
            raise RuntimeError("Something went wrong")

        with patch("job_agent.batch.run_pipeline", side_effect=side_effect):
            with patch("job_agent.batch.config") as mock_cfg:
                _configure_mock_config(mock_cfg, tmp_path)
                from job_agent.batch import run_batch
                run_batch(todo_dir=tmp_path, delay_seconds=0)

        failed_dir = tmp_path.parent / "failed"
        error_files = list(failed_dir.glob("*.error.txt"))
        assert len(error_files) == 1
        assert "Something went wrong" in error_files[0].read_text()


# ── batch: file movement ───────────────────────────────────────────────────────

class TestBatchFileMovement:
    """Tests that processed JD files are moved to the correct outcome directory.

    Each possible outcome (applied / skipped / gated_out) has its own sibling
    directory.  The original file should no longer exist in the TODO directory.
    """

    def test_applied_job_moved_to_applied_dir(self, tmp_path):
        """A job that passes both gates should be moved to ``applied/``."""
        _write_jd(tmp_path, "Acme_DS.md", "Body.")
        state = _make_applied_state("Acme", "DS")

        with patch("job_agent.batch.run_pipeline", return_value=state):
            with patch("job_agent.batch.config") as mock_cfg:
                _configure_mock_config(mock_cfg, tmp_path)
                from job_agent.batch import run_batch
                run_batch(todo_dir=tmp_path, delay_seconds=0)

        assert (tmp_path.parent / "applied" / "Acme_DS.md").exists()
        assert not (tmp_path / "Acme_DS.md").exists()

    def test_skipped_job_moved_to_skipped_dir(self, tmp_path):
        """A job stopped at Gate 1 should be moved to ``skipped/``."""
        _write_jd(tmp_path, "Acme_DS.md", "Body.")
        state = _make_skipped_state("Acme", "DS")

        with patch("job_agent.batch.run_pipeline", return_value=state):
            with patch("job_agent.batch.config") as mock_cfg:
                _configure_mock_config(mock_cfg, tmp_path)
                from job_agent.batch import run_batch
                run_batch(todo_dir=tmp_path, delay_seconds=0)

        assert (tmp_path.parent / "skipped" / "Acme_DS.md").exists()

    def test_gated_out_job_moved_to_gated_out_dir(self, tmp_path):
        """A job that fails Gate 2 (low rescore) should be moved to ``gated_out/``."""
        _write_jd(tmp_path, "Acme_DS.md", "Body.")
        state = _make_gated_out_state("Acme", "DS")

        with patch("job_agent.batch.run_pipeline", return_value=state):
            with patch("job_agent.batch.config") as mock_cfg:
                _configure_mock_config(mock_cfg, tmp_path)
                from job_agent.batch import run_batch
                run_batch(todo_dir=tmp_path, delay_seconds=0)

        assert (tmp_path.parent / "gated_out" / "Acme_DS.md").exists()


# ── batch: result counts ───────────────────────────────────────────────────────

class TestBatchResultCounts:
    """Tests that BatchRunResult aggregate counts are accurate.

    Runs a three-job batch with one of each outcome type and verifies that
    the counters in the returned BatchRunResult match exactly.
    """

    def test_aggregate_counts_are_correct(self, tmp_path):
        """applied / gated_out / skipped counts should each equal 1 for a three-job batch."""
        _write_jd(tmp_path, "A_Applied.md", "Body.")
        _write_jd(tmp_path, "B_Gated.md", "Body.")
        _write_jd(tmp_path, "C_Skipped.md", "Body.")

        states = {
            "A": _make_applied_state("A", "Applied"),
            "B": _make_gated_out_state("B", "Gated"),
            "C": _make_skipped_state("C", "Skipped"),
        }

        def side_effect(**kwargs):
            return states[kwargs["company"]]

        with patch("job_agent.batch.run_pipeline", side_effect=side_effect):
            with patch("job_agent.batch.config") as mock_cfg:
                _configure_mock_config(mock_cfg, tmp_path)
                from job_agent.batch import run_batch
                result = run_batch(todo_dir=tmp_path, delay_seconds=0)

        assert result.total == 3
        assert result.applied == 1
        assert result.gated_out == 1
        assert result.skipped == 1
        assert result.errors == 0


# ── vault: format_batch_summary ───────────────────────────────────────────────

class TestFormatBatchSummary:
    """Tests for the batch markdown formatter in vault.py.

    Verifies that the output contains the expected headings, company names,
    score deltas, and error sections.
    """

    def test_contains_run_id(self):
        """The run ID should appear in the markdown heading."""
        from job_agent.vault import format_batch_summary
        result = _make_batch_result("abc12345")
        md = format_batch_summary(result)
        assert "abc12345" in md

    def test_contains_all_outcome_rows(self):
        """Each company name from the results should appear in the output table."""
        from job_agent.vault import format_batch_summary
        result = _make_batch_result("abc12345")
        md = format_batch_summary(result)
        assert "Acme" in md
        assert "BigCo" in md

    def test_error_section_present_when_errors_exist(self):
        """When results contain errors, an ``## Errors`` section should be rendered."""
        from job_agent.vault import format_batch_summary
        result = _make_batch_result_with_error("xyz99")
        md = format_batch_summary(result)
        assert "## Errors" in md
        assert "Something went wrong" in md

    def test_no_error_section_when_no_errors(self):
        """When there are no errors, the ``## Errors`` section should be absent."""
        from job_agent.vault import format_batch_summary
        result = _make_batch_result("clean01")
        md = format_batch_summary(result)
        assert "## Errors" not in md

    def test_delta_calculated_correctly(self):
        """The score delta should be rendered as a signed integer (e.g. ``+15``)."""
        from job_agent.vault import format_batch_summary
        result = _make_batch_result("delta01")
        md = format_batch_summary(result)
        # Applied job: initial=70, final=85 → delta=+15
        assert "+15" in md


# ── Shared fixture builders ────────────────────────────────────────────────────

def _make_applied_state(company: str, role: str) -> PipelineState:
    """Build a PipelineState where both gates passed (gate_passed=True)."""
    rubric = ScoringRubric(
        keywords_identified=["Python"],
        section_weights={"summary": 0.5, "experience": 0.5},
    )
    analysis = AnalysisResult(
        aggregate_score=70,
        section_scores=[SectionScore(section="summary", score=70, rationale="ok")],
        hard_missing=[], soft_missing=[], recency_gaps=[],
        transferable_strengths=[],
        proceed_with_application=True,
        proceed_rationale="Good enough.",
        rubric=rubric,
    )
    rescore = RescorerResult(
        variant_label="leadership",
        new_aggregate_score=85,
        new_section_scores=[SectionScore(section="summary", score=85, rationale="improved")],
        score_deltas={"summary": 15},
        aggregate_delta=15,
        soft_gaps_resolved=[],
        soft_gaps_remaining=[],
        regressions=[],
        gate_passed=True,
    )
    return PipelineState(
        run_id="test01",
        company=company,
        role=role,
        job_description="JD",
        cv_text="CV",
        skills_table="Skills",
        analysis=analysis,
        rescore_result=rescore,
        selected_variant="leadership",
        vault_path="/tmp/vault/test",
    )


def _make_skipped_state(company: str, role: str) -> PipelineState:
    """Build a PipelineState where Gate 1 stopped the run (no rescore_result)."""
    rubric = ScoringRubric(
        keywords_identified=["Python"],
        section_weights={"summary": 1.0},
    )
    analysis = AnalysisResult(
        aggregate_score=30,
        section_scores=[SectionScore(section="summary", score=30, rationale="poor")],
        hard_missing=[], soft_missing=[], recency_gaps=[],
        transferable_strengths=[],
        proceed_with_application=False,
        proceed_rationale="Too many gaps.",
        rubric=rubric,
    )
    return PipelineState(
        run_id="test02",
        company=company,
        role=role,
        job_description="JD",
        cv_text="CV",
        skills_table="Skills",
        analysis=analysis,
        rescore_result=None,
        vault_path="/tmp/vault/test2",
    )


def _make_gated_out_state(company: str, role: str) -> PipelineState:
    """Build a PipelineState where Gate 2 failed (rescore gate_passed=False)."""
    state = _make_applied_state(company, role)
    state.rescore_result.new_aggregate_score = 50
    state.rescore_result.gate_passed = False
    return state


def _configure_mock_config(mock_cfg: MagicMock, tmp_path: Path) -> None:
    """Configure a mock config so batch.py uses tmp_path-relative paths with no delay."""
    mock_cfg.OBSIDIAN_VAULT_PATH = MagicMock()
    mock_cfg.OBSIDIAN_VAULT_PATH.expanduser.return_value = tmp_path / "vault"
    mock_cfg.MATCH_SCORE_THRESHOLD = 65
    mock_cfg.BATCH_DELAY_SECONDS = 0.0


def _make_batch_result(run_id: str) -> BatchRunResult:
    """Minimal BatchRunResult with one applied and one gated_out job."""
    from datetime import datetime
    return BatchRunResult(
        run_id=run_id,
        started_at=datetime(2025, 1, 15, 10, 0),
        completed_at=datetime(2025, 1, 15, 10, 5),
        total=2,
        applied=1,
        gated_out=1,
        skipped=0,
        errors=0,
        results=[
            BatchJobResult(
                company="Acme",
                role="Data Scientist",
                jd_file="Acme_Data_Scientist.md",
                status="applied",
                initial_score=70,
                final_score=85,
            ),
            BatchJobResult(
                company="BigCo",
                role="Engineer",
                jd_file="BigCo_Engineer.md",
                status="gated_out",
                initial_score=65,
                final_score=55,
            ),
        ],
    )


def _make_batch_result_with_error(run_id: str) -> BatchRunResult:
    """BatchRunResult with a single error job."""
    from datetime import datetime
    return BatchRunResult(
        run_id=run_id,
        started_at=datetime(2025, 1, 15, 10, 0),
        completed_at=datetime(2025, 1, 15, 10, 5),
        total=1,
        applied=0,
        gated_out=0,
        skipped=0,
        errors=1,
        results=[
            BatchJobResult(
                company="FailCo",
                role="Engineer",
                jd_file="FailCo_Engineer.md",
                status="error",
                error_message="Something went wrong",
            ),
        ],
    )
