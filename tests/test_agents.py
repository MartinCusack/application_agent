"""Unit tests for ``job_agent.agents``.

All LLM calls are mocked so these tests run without an API key.
The mock returns the minimal valid JSON for each agent's output schema.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from job_agent.agents import (
    AnalystAgent,
    CoverLetterAgent,
    DiffAgent,
    RescorerAgent,
    WriterAgent,
)
from job_agent.models import (
    AnalysisResult,
    CoverLetterResult,
    DiffResult,
    RescorerResult,
    WriterResult,
)


def _mock_llm_response(payload: dict) -> MagicMock:
    """Build a mock LLM response object whose ``.content`` is JSON.

    Args:
        payload: Dict that will be serialised to JSON and returned as the
            mock content string.

    Returns:
        ``MagicMock`` with ``.content`` set to the serialised JSON string.
    """
    mock = MagicMock()
    mock.content = json.dumps(payload)
    return mock


# ── Shared LLM patch helper ───────────────────────────────────────────────────

def _patch_llm(agent_instance: object, payload: dict) -> MagicMock:
    """Patch the ``.llm.invoke`` method on an agent with a fixed payload.

    Args:
        agent_instance: Any ``BaseAgent`` subclass instance.
        payload: Response payload the mock should return.

    Returns:
        The configured ``MagicMock``.
    """
    mock = _mock_llm_response(payload)
    agent_instance.llm = MagicMock()
    agent_instance.llm.invoke.return_value = mock
    return mock


# ── AnalystAgent ──────────────────────────────────────────────────────────────

class TestAnalystAgent:
    """Tests for ``AnalystAgent.run``."""

    @pytest.fixture
    def analyst_payload(self) -> dict:
        """Minimal valid payload for ``AnalysisResult``."""
        return {
            "aggregate_score": 75,
            "section_scores": [
                {"section": "summary", "score": 70, "rationale": "OK"},
                {"section": "experience", "score": 80, "rationale": "Good"},
                {"section": "skills", "score": 65, "rationale": "Missing some"},
            ],
            "hard_missing": [
                {
                    "keyword": "FDA 510k",
                    "gap_type": "hard",
                    "rationale": "No regulatory experience",
                    "addressable_with_existing_skills": False,
                    "upskill_timeframe": "12 months",
                }
            ],
            "soft_missing": [
                {
                    "keyword": "machine learning",
                    "gap_type": "soft",
                    "rationale": "Uses 'predictive modelling' instead",
                }
            ],
            "proceed_with_application": True,
            "proceed_rationale": "Score above threshold.",
            "rubric": {
                "keywords_identified": ["Python", "FDA"],
                "section_weights": {"summary": 0.3, "experience": 0.5, "skills": 0.2},
            },
        }

    def test_returns_analysis_result_type(
        self, analyst_payload, sample_cv_text, sample_skills_table, sample_job_description
    ):
        """``run`` returns an ``AnalysisResult`` instance."""
        agent = AnalystAgent()
        _patch_llm(agent, analyst_payload)
        result = agent.run(sample_cv_text, sample_skills_table, sample_job_description)
        assert isinstance(result, AnalysisResult)

    def test_aggregate_score_parsed(
        self, analyst_payload, sample_cv_text, sample_skills_table, sample_job_description
    ):
        """Aggregate score from the payload is correctly parsed."""
        agent = AnalystAgent()
        _patch_llm(agent, analyst_payload)
        result = agent.run(sample_cv_text, sample_skills_table, sample_job_description)
        assert result.aggregate_score == 75

    def test_hard_soft_split_parsed(
        self, analyst_payload, sample_cv_text, sample_skills_table, sample_job_description
    ):
        """Hard and soft missing keywords are parsed into separate lists."""
        agent = AnalystAgent()
        _patch_llm(agent, analyst_payload)
        result = agent.run(sample_cv_text, sample_skills_table, sample_job_description)
        assert len(result.hard_missing) == 1
        assert len(result.soft_missing) == 1
        assert result.hard_missing[0].gap_type == "hard"
        assert result.soft_missing[0].gap_type == "soft"

    def test_rubric_keywords_included(
        self, analyst_payload, sample_cv_text, sample_skills_table, sample_job_description
    ):
        """Rubric keywords are captured in the result."""
        agent = AnalystAgent()
        _patch_llm(agent, analyst_payload)
        result = agent.run(sample_cv_text, sample_skills_table, sample_job_description)
        assert "Python" in result.rubric.keywords_identified

    @patch("job_agent.agents.time.sleep")
    def test_invalid_json_raises_value_error(
        self, _mock_sleep, sample_cv_text, sample_skills_table, sample_job_description
    ):
        """A non-JSON response raises ``ValueError`` after all retries."""
        agent = AnalystAgent()
        agent.llm = MagicMock()
        agent.llm.invoke.return_value = MagicMock(content="not json at all")
        with pytest.raises(ValueError, match="invalid JSON"):
            agent.run(sample_cv_text, sample_skills_table, sample_job_description)

    def test_json_in_markdown_fence_parsed(
        self, analyst_payload, sample_cv_text, sample_skills_table, sample_job_description
    ):
        """JSON wrapped in ```json ... ``` markdown fences is still parsed."""
        agent = AnalystAgent()
        fenced = f"```json\n{json.dumps(analyst_payload)}\n```"
        agent.llm = MagicMock()
        agent.llm.invoke.return_value = MagicMock(content=fenced)
        result = agent.run(sample_cv_text, sample_skills_table, sample_job_description)
        assert isinstance(result, AnalysisResult)


# ── CoverLetterAgent ──────────────────────────────────────────────────────────

class TestCoverLetterAgent:
    """Tests for ``CoverLetterAgent.run``."""

    @pytest.fixture
    def cover_letter_payload(self) -> dict:
        """Minimal valid payload for ``CoverLetterResult``."""
        return {
            "jd_signals": [
                "AI-powered diagnostics platform",
                "ISO 13485 compliance",
                "Series B growth stage",
            ],
            "cover_letter": "Dear Hiring Team, this is a tailored cover letter.",
            "tailoring_notes": [
                "Filled [COMPANY_MISSION] with 'AI-powered diagnostics platform' from JD para 1",
            ],
        }

    def test_returns_cover_letter_result_type(
        self, cover_letter_payload, sample_job_description, analysis_result
    ):
        """``run`` returns a ``CoverLetterResult`` instance."""
        agent = CoverLetterAgent()
        _patch_llm(agent, cover_letter_payload)
        result = agent.run(
            cover_letter_template="Dear Hiring Team, [COMPANY_MISSION].",
            cover_letter_rubric="No first-person pronouns.",
            job_description=sample_job_description,
            company="Acme",
            role="Data Scientist",
            analysis=analysis_result,
        )
        assert isinstance(result, CoverLetterResult)

    def test_jd_signals_populated(
        self, cover_letter_payload, sample_job_description, analysis_result
    ):
        """``jd_signals`` is non-empty and contains the expected extraction."""
        agent = CoverLetterAgent()
        _patch_llm(agent, cover_letter_payload)
        result = agent.run(
            cover_letter_template="Dear Hiring Team, [COMPANY_MISSION].",
            cover_letter_rubric="No first-person pronouns.",
            job_description=sample_job_description,
            company="Acme",
            role="Data Scientist",
            analysis=analysis_result,
        )
        assert len(result.jd_signals) > 0
        assert "AI-powered diagnostics platform" in result.jd_signals

    @patch("job_agent.agents.time.sleep")
    def test_missing_jd_signals_triggers_retry(
        self, _mock_sleep, cover_letter_payload, sample_job_description, analysis_result
    ):
        """A response missing ``jd_signals`` triggers the retry logic."""
        from pydantic import ValidationError

        agent = CoverLetterAgent()
        agent.llm = MagicMock()
        no_signals = {k: v for k, v in cover_letter_payload.items() if k != "jd_signals"}
        bad = MagicMock(content=json.dumps(no_signals))
        good = MagicMock(content=json.dumps(cover_letter_payload))
        agent.llm.invoke.side_effect = [bad, good]

        result = agent.run(
            cover_letter_template="Dear Hiring Team, [COMPANY_MISSION].",
            cover_letter_rubric="No first-person pronouns.",
            job_description=sample_job_description,
            company="Acme",
            role="Data Scientist",
            analysis=analysis_result,
        )

        assert isinstance(result, CoverLetterResult)
        assert agent.llm.invoke.call_count == 2


# ── WriterAgent ───────────────────────────────────────────────────────────────

class TestWriterAgent:
    """Tests for ``WriterAgent.run``."""

    @pytest.fixture
    def writer_payload(self) -> dict:
        return {
            "variant": {
                "label": "leadership",
                "summary_section": "Led team to deliver Y.",
                "changes_made": ["Added leadership framing"],
                "skills_rows_cited": ["Python | Expert"],
            }
        }

    def test_returns_writer_result_type(
        self, writer_payload, sample_cv_text, sample_skills_table, analysis_result
    ):
        """``run`` returns a ``WriterResult`` instance."""
        agent = WriterAgent()
        _patch_llm(agent, writer_payload)
        result = agent.run(sample_cv_text, sample_skills_table, analysis_result)
        assert isinstance(result, WriterResult)

    def test_variant_label_correct(
        self, writer_payload, sample_cv_text, sample_skills_table, analysis_result
    ):
        """Variant is labelled 'leadership'."""
        agent = WriterAgent()
        _patch_llm(agent, writer_payload)
        result = agent.run(sample_cv_text, sample_skills_table, analysis_result)
        assert result.variant.label == "leadership"


# ── DiffAgent ─────────────────────────────────────────────────────────────────

class TestDiffAgent:
    """Tests for ``DiffAgent.run``."""

    @pytest.fixture
    def diff_payload(self) -> dict:
        return {
            "variant_label": "technical",
            "original_summary": "Old summary.",
            "new_summary": "New summary.",
            "changes": ["Replaced 'predictive modelling' with 'machine learning'"],
        }

    def test_returns_diff_result_type(self, diff_payload):
        """``run`` returns a ``DiffResult`` instance."""
        agent = DiffAgent()
        _patch_llm(agent, diff_payload)
        result = agent.run("Old summary.", "New summary.", "technical")
        assert isinstance(result, DiffResult)

    def test_changes_list_populated(self, diff_payload):
        """Changes list from payload is correctly parsed."""
        agent = DiffAgent()
        _patch_llm(agent, diff_payload)
        result = agent.run("Old summary.", "New summary.", "technical")
        assert len(result.changes) == 1


# ── RescorerAgent ─────────────────────────────────────────────────────────────

class TestRescorerAgent:
    """Tests for ``RescorerAgent.run``."""

    @pytest.fixture
    def rescore_payload(self) -> dict:
        return {
            "variant_label": "technical",
            "new_aggregate_score": 85,
            "new_section_scores": [
                {"section": "summary", "score": 82, "rationale": "Improved"},
                {"section": "experience", "score": 88, "rationale": "Unchanged"},
                {"section": "skills", "score": 80, "rationale": "Better"},
            ],
            "score_deltas": {"summary": 12, "experience": 8, "skills": 15},
            "aggregate_delta": 10,
            "soft_gaps_resolved": ["machine learning"],
            "soft_gaps_remaining": [],
            "regressions": [],
            "gate_passed": True,
        }

    def test_returns_rescorer_result_type(
        self, rescore_payload, sample_cv_text, sample_job_description, analysis_result
    ):
        """``run`` returns a ``RescorerResult`` instance."""
        agent = RescorerAgent()
        _patch_llm(agent, rescore_payload)
        result = agent.run(sample_cv_text, sample_job_description, analysis_result, "technical")
        assert isinstance(result, RescorerResult)

    def test_gate_passed_true(
        self, rescore_payload, sample_cv_text, sample_job_description, analysis_result
    ):
        """``gate_passed`` reflects the value in the payload."""
        agent = RescorerAgent()
        _patch_llm(agent, rescore_payload)
        result = agent.run(sample_cv_text, sample_job_description, analysis_result, "technical")
        assert result.gate_passed is True

    def test_soft_gaps_resolved_populated(
        self, rescore_payload, sample_cv_text, sample_job_description, analysis_result
    ):
        """Resolved soft gaps are present in the result."""
        agent = RescorerAgent()
        _patch_llm(agent, rescore_payload)
        result = agent.run(sample_cv_text, sample_job_description, analysis_result, "technical")
        assert "machine learning" in result.soft_gaps_resolved


# ── Retry behaviour (BaseAgent._call) ─────────────────────────────────────────

class TestBaseAgentRetry:
    """Tests for the exponential-backoff retry logic in ``BaseAgent._call``."""

    @pytest.fixture
    def analyst_payload(self) -> dict:
        """Minimal valid payload for ``AnalysisResult`` (reused from TestAnalystAgent)."""
        return {
            "aggregate_score": 75,
            "section_scores": [
                {"section": "summary", "score": 70, "rationale": "OK"},
                {"section": "experience", "score": 80, "rationale": "Good"},
                {"section": "skills", "score": 65, "rationale": "Missing some"},
            ],
            "hard_missing": [],
            "soft_missing": [],
            "proceed_with_application": True,
            "proceed_rationale": "Above threshold.",
            "rubric": {
                "keywords_identified": ["Python"],
                "section_weights": {"summary": 0.3, "experience": 0.5, "skills": 0.2},
            },
        }

    @patch("job_agent.agents.time.sleep")
    def test_retries_on_bad_json_then_succeeds(
        self,
        mock_sleep,
        analyst_payload,
        sample_cv_text,
        sample_skills_table,
        sample_job_description,
    ):
        """Two bad-JSON responses followed by a good one eventually succeeds."""
        agent = AnalystAgent()
        agent.llm = MagicMock()
        bad = MagicMock(content="not json")
        good = MagicMock(content=json.dumps(analyst_payload))
        agent.llm.invoke.side_effect = [bad, bad, good]

        result = agent.run(sample_cv_text, sample_skills_table, sample_job_description)

        assert isinstance(result, AnalysisResult)
        assert agent.llm.invoke.call_count == 3

    @patch("job_agent.agents.time.sleep")
    def test_exponential_backoff_delays(
        self,
        mock_sleep,
        sample_cv_text,
        sample_skills_table,
        sample_job_description,
    ):
        """Sleep is called with 1 s then 2 s between the three attempts."""
        agent = AnalystAgent()
        agent.llm = MagicMock()
        agent.llm.invoke.return_value = MagicMock(content="not json")

        with pytest.raises(ValueError):
            agent.run(sample_cv_text, sample_skills_table, sample_job_description)

        assert mock_sleep.call_count == 2
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == [1.0, 2.0]

    @patch("job_agent.agents.time.sleep")
    def test_correction_prompt_appended_on_retry(
        self,
        mock_sleep,
        analyst_payload,
        sample_cv_text,
        sample_skills_table,
        sample_job_description,
    ):
        """After a bad-JSON response the second invoke receives the bad reply
        as an AIMessage and a correction HumanMessage."""
        from langchain_core.messages import AIMessage, HumanMessage

        agent = AnalystAgent()
        agent.llm = MagicMock()
        bad = MagicMock(content="not json")
        good = MagicMock(content=json.dumps(analyst_payload))
        agent.llm.invoke.side_effect = [bad, good]

        agent.run(sample_cv_text, sample_skills_table, sample_job_description)

        second_call_messages = agent.llm.invoke.call_args_list[1].args[0]
        # Last two messages are the correction pair
        assert isinstance(second_call_messages[-2], AIMessage)
        assert second_call_messages[-2].content == "not json"
        assert isinstance(second_call_messages[-1], HumanMessage)
        assert "not valid JSON" in second_call_messages[-1].content

    @patch("job_agent.agents.time.sleep")
    def test_retries_on_schema_validation_error(
        self,
        mock_sleep,
        analyst_payload,
        sample_cv_text,
        sample_skills_table,
        sample_job_description,
    ):
        """Valid JSON that fails Pydantic validation also triggers a retry."""
        from pydantic import ValidationError

        agent = AnalystAgent()
        agent.llm = MagicMock()
        bad_schema = MagicMock(content=json.dumps({"wrong_field": 1}))
        good = MagicMock(content=json.dumps(analyst_payload))
        agent.llm.invoke.side_effect = [bad_schema, good]

        result = agent.run(sample_cv_text, sample_skills_table, sample_job_description)

        assert isinstance(result, AnalysisResult)
        assert agent.llm.invoke.call_count == 2

    @patch("job_agent.agents.time.sleep")
    def test_schema_correction_includes_schema(
        self,
        mock_sleep,
        analyst_payload,
        sample_cv_text,
        sample_skills_table,
        sample_job_description,
    ):
        """Correction prompt for a schema error embeds the JSON schema."""
        from langchain_core.messages import HumanMessage

        agent = AnalystAgent()
        agent.llm = MagicMock()
        bad_schema = MagicMock(content=json.dumps({"wrong_field": 1}))
        good = MagicMock(content=json.dumps(analyst_payload))
        agent.llm.invoke.side_effect = [bad_schema, good]

        agent.run(sample_cv_text, sample_skills_table, sample_job_description)

        second_call_messages = agent.llm.invoke.call_args_list[1].args[0]
        correction_text = second_call_messages[-1].content
        assert "required schema" in correction_text
        assert "aggregate_score" in correction_text  # schema field name present
